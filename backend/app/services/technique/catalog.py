"""Read-only catalog queries for the Technique & Gymkhana Library (feature 018).

All functions are async and accept an ``AsyncSession``; they never commit or
flush — callers own the transaction boundary (Constitution I).

Materials subset rule (research D2 / data-model rule 2):
  An exercise matches an ``available`` material set when **every** material
  linked to that exercise is present in the set.  Exercises whose only linked
  material is the ``is_none`` / "sin_material" sentinel always match.

  Implementation: a correlated ``NOT EXISTS`` sub-query checks that no
  required material for the exercise lies outside the available slugs.
  This runs entirely in the DB; no post-filter in Python.

Eager-loading strategy (research D2, Constitution IV):
  All three relationship legs — ``skills``, ``materials``, ``age_bands`` — are
  loaded with ``selectinload`` to avoid N+1 and the column-multiplication that
  ``joinedload`` would cause across two simultaneous M2M legs.
"""
from __future__ import annotations

import logging

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.technique_exercise import (
    AgeBand,
    ExerciseDifficulty,
    TechniqueExercise,
    TechniqueExerciseAgeBand,
    technique_exercise_materials,
    technique_exercise_skills,
)
from app.models.technique_material import TechniqueMaterial
from app.models.technique_skill import TechniqueSkill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _exercise_select(*, include_hidden: bool):  # type: ignore[return]
    """Build the base SELECT for ``TechniqueExercise`` with all three eager loads.

    Args:
        include_hidden: when ``False``, restricts to rows where
            ``is_hidden = false`` (default catalog view).

    Returns:
        A SQLAlchemy ``Select`` ready to be extended with ``.where()`` clauses.
        No DB I/O is performed here.

    Side-effects:
        None — pure query builder.
    """
    stmt = select(TechniqueExercise).options(
        selectinload(TechniqueExercise.skills),
        selectinload(TechniqueExercise.materials),
        selectinload(TechniqueExercise.age_bands),
    )
    if not include_hidden:
        stmt = stmt.where(TechniqueExercise.is_hidden.is_(False))
    return stmt


# ---------------------------------------------------------------------------
# Public catalog functions
# ---------------------------------------------------------------------------


async def list_exercises(
    db: AsyncSession,
    *,
    skill: str | None = None,
    age_band: AgeBand | None = None,
    difficulty: ExerciseDifficulty | None = None,
    materials: list[str] | None = None,
    include_hidden: bool = False,
    is_game: bool | None = None,
) -> list[TechniqueExercise]:
    """Return catalog exercises matching all supplied filters (AND semantics).

    All filters are optional and combinable (FR-002, contracts/rest-api.md
    ``GET /api/technique/exercises``).  An empty result is returned as an empty
    list — never raises a "not found" error (FR-004).

    Args:
        db: Active async session.  Caller owns commit/rollback.
        skill: Slug of a ``TechniqueSkill`` (e.g. ``"frenado"``).  When
            provided, only exercises linked to that skill are returned.
        age_band: ``AgeBand`` enum value.  Only exercises that target this
            band (via ``technique_exercise_age_bands``) are returned.
        difficulty: ``ExerciseDifficulty`` enum value.  Equality filter.
        materials: List of material slugs **available** to the coach today.
            Applies the materials subset rule (research D2): only exercises
            whose **entire** required-material set is within this list are
            returned.  Exercises linked only to the ``is_none`` sentinel
            (no equipment needed) always match.  Pass ``None`` to skip.
        include_hidden: When ``True``, also returns exercises with
            ``is_hidden = true`` (curation view, US5).  Default ``False``.
        is_game: ``True`` returns only engagement (🎉) exercises;
            ``False`` returns only non-game exercises; ``None`` skips the
            filter.

    Returns:
        List of ``TechniqueExercise`` ORM objects with ``.skills``,
        ``.materials``, and ``.age_bands`` already loaded (no N+1).
        Order follows DB default (unspecified but stable within a transaction).

    Side-effects:
        Issues up to 4 SELECT statements per call: one primary query + three
        ``selectinload`` IN-queries for the relationship collections.
        No writes.
    """
    stmt = _exercise_select(include_hidden=include_hidden)

    # --- skill slug filter ---------------------------------------------------
    # Sub-select: resolve slug → id, then filter through the M2M join table.
    if skill is not None:
        skill_id_sub = (
            select(TechniqueSkill.id)
            .where(TechniqueSkill.slug == skill)
            .scalar_subquery()
        )
        stmt = stmt.where(
            TechniqueExercise.id.in_(
                select(technique_exercise_skills.c.exercise_id).where(
                    technique_exercise_skills.c.skill_id == skill_id_sub
                )
            )
        )

    # --- age_band filter -----------------------------------------------------
    if age_band is not None:
        stmt = stmt.where(
            TechniqueExercise.id.in_(
                select(TechniqueExerciseAgeBand.exercise_id).where(
                    TechniqueExerciseAgeBand.age_band == age_band
                )
            )
        )

    # --- difficulty equality filter ------------------------------------------
    if difficulty is not None:
        stmt = stmt.where(TechniqueExercise.difficulty == difficulty)

    # --- is_game equality filter ---------------------------------------------
    if is_game is not None:
        stmt = stmt.where(TechniqueExercise.is_game.is_(is_game))

    # --- materials subset filter (research D2, data-model invariant 2) -------
    # Exclude exercises that have at least one required material (is_none=false)
    # NOT present in the available set.  "sin_material" exercises produce zero
    # rows in the NOT EXISTS sub-query and always pass through.
    if materials is not None:
        available_ids_sub = (
            select(TechniqueMaterial.id)
            .where(TechniqueMaterial.slug.in_(materials))
            .scalar_subquery()
        )
        # Correlated sub-query: does this exercise have any required material
        # that is NOT in the available set?
        has_unavailable_material = (
            select(technique_exercise_materials.c.exercise_id)
            .join(
                TechniqueMaterial,
                TechniqueMaterial.id == technique_exercise_materials.c.material_id,
            )
            .where(
                technique_exercise_materials.c.exercise_id == TechniqueExercise.id,
                TechniqueMaterial.is_none.is_(False),
                TechniqueMaterial.id.not_in(available_ids_sub),
            )
        )
        stmt = stmt.where(~exists(has_unavailable_material))

    result = await db.execute(stmt)
    # .unique() collapses any duplicate identity rows that SQLAlchemy may
    # produce when multiple selectinload joins are combined.
    return list(result.scalars().unique().all())


async def get_exercise(
    db: AsyncSession,
    exercise_id: int,
) -> TechniqueExercise | None:
    """Return a single exercise by primary key, or ``None`` if not found.

    Hidden exercises are included (the detail endpoint always serves them so
    the curation UI can edit or unhide them — FR-019).

    Args:
        db: Active async session.  Caller owns commit/rollback.
        exercise_id: Primary key of the ``TechniqueExercise`` row.

    Returns:
        ``TechniqueExercise`` with ``.skills``, ``.materials``, and
        ``.age_bands`` eagerly loaded, or ``None`` when the id is unknown.

    Side-effects:
        Issues up to 4 SELECT statements (one primary + three
        ``selectinload`` IN-queries).  No writes.
    """
    result = await db.execute(
        select(TechniqueExercise)
        .where(TechniqueExercise.id == exercise_id)
        .options(
            selectinload(TechniqueExercise.skills),
            selectinload(TechniqueExercise.materials),
            selectinload(TechniqueExercise.age_bands),
        )
    )
    return result.scalar_one_or_none()


async def list_skills(db: AsyncSession) -> list[TechniqueSkill]:
    """Return all technique skills ordered by ``sort_order``.

    Used to populate the skill filter control on the catalog UI.

    Args:
        db: Active async session.  Caller owns commit/rollback.

    Returns:
        List of all ``TechniqueSkill`` rows, ascending by ``sort_order``.
        Empty list when the table has not been seeded yet.

    Side-effects:
        Issues one SELECT.  No writes.
    """
    result = await db.execute(
        select(TechniqueSkill).order_by(TechniqueSkill.sort_order)
    )
    return list(result.scalars().all())


async def list_materials(db: AsyncSession) -> list[TechniqueMaterial]:
    """Return all technique materials ordered alphabetically by ``slug``.

    Used to populate the material availability selector on the catalog UI.
    The ``is_none`` sentinel row is included so the client can distinguish
    "no-equipment exercises" in its display logic.

    Args:
        db: Active async session.  Caller owns commit/rollback.

    Returns:
        List of all ``TechniqueMaterial`` rows, ascending by ``slug``.
        Empty list when the table has not been seeded yet.

    Side-effects:
        Issues one SELECT.  No writes.
    """
    result = await db.execute(
        select(TechniqueMaterial).order_by(TechniqueMaterial.slug)
    )
    return list(result.scalars().all())
