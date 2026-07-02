"""Read-only catalog queries for the Strength Training Library (feature 021).

All functions are async and accept an ``AsyncSession``; they never commit or
flush — callers own the transaction boundary (Constitution I).

Eager-loading strategy (mirrors technique feature 018, Constitution IV):
  The single relationship leg — ``age_bands`` — is loaded with
  ``selectinload`` to avoid N+1.

Filter semantics (contracts/strength-api.md ``GET /exercises``):
  All query params are optional and AND-combined. ``age_band`` matches when
  the requested band is among the exercise's linked age bands (subselect
  against ``strength_exercise_age_bands``). ``q`` performs a free-text
  case-insensitive LIKE over ``name`` and ``summary``.
"""
from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.strength import (
    EquipmentKind,
    MovementCategory,
    StrengthExercise,
    StrengthExerciseAgeBand,
)
from app.models.technique_exercise import AgeBand

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _exercise_select(*, include_hidden: bool):  # type: ignore[return]
    """Build the base SELECT for ``StrengthExercise`` with the age_bands eager load.

    Args:
        include_hidden: when ``False``, restricts to rows where
            ``is_hidden = false`` (default catalog view).

    Returns:
        A SQLAlchemy ``Select`` ready to be extended with ``.where()`` clauses.
        No DB I/O is performed here.

    Side-effects:
        None — pure query builder.
    """
    stmt = select(StrengthExercise).options(
        selectinload(StrengthExercise.age_bands),
    )
    if not include_hidden:
        stmt = stmt.where(StrengthExercise.is_hidden.is_(False))
    return stmt


# ---------------------------------------------------------------------------
# Public catalog functions
# ---------------------------------------------------------------------------


async def list_exercises(
    db: AsyncSession,
    *,
    equipment: EquipmentKind | None = None,
    age_band: AgeBand | None = None,
    movement_category: MovementCategory | None = None,
    q: str | None = None,
    include_hidden: bool = False,
) -> list[StrengthExercise]:
    """Return catalog exercises matching all supplied filters (AND semantics).

    All filters are optional and combinable (contracts/strength-api.md
    ``GET /api/strength/exercises``). An empty result is returned as an empty
    list — never raises a "not found" error.

    Args:
        db: Active async session. Caller owns commit/rollback.
        equipment: ``EquipmentKind`` enum value. Equality filter.
        age_band: ``AgeBand`` enum value. Only exercises that target this
            band (via ``strength_exercise_age_bands``) are returned.
        movement_category: ``MovementCategory`` enum value. Equality filter.
        q: Free-text search term. When provided, matches exercises whose
            ``name`` or ``summary`` contains the term (case-insensitive).
        include_hidden: When ``True``, also returns exercises with
            ``is_hidden = true`` (curation view). Default ``False``.

    Returns:
        List of ``StrengthExercise`` ORM objects with ``.age_bands`` already
        loaded (no N+1). Order follows DB default (mirrors
        ``services/technique/catalog.py:list_exercises``).

    Side-effects:
        Issues up to 2 SELECT statements per call: one primary query + one
        ``selectinload`` IN-query for the age_bands collection. No writes.
    """
    stmt = _exercise_select(include_hidden=include_hidden)

    # --- equipment equality filter -------------------------------------------
    if equipment is not None:
        stmt = stmt.where(StrengthExercise.equipment == equipment)

    # --- age_band filter -------------------------------------------------------
    if age_band is not None:
        stmt = stmt.where(
            StrengthExercise.id.in_(
                select(StrengthExerciseAgeBand.exercise_id).where(
                    StrengthExerciseAgeBand.age_band == age_band
                )
            )
        )

    # --- movement_category equality filter --------------------------------
    if movement_category is not None:
        stmt = stmt.where(StrengthExercise.movement_category == movement_category)

    # --- free-text filter ---------------------------------------------------
    if q:
        like_term = f"%{q}%"
        stmt = stmt.where(
            or_(
                StrengthExercise.name.ilike(like_term),
                StrengthExercise.summary.ilike(like_term),
            )
        )

    result = await db.execute(stmt)
    # .unique() collapses any duplicate identity rows that SQLAlchemy may
    # produce when combined with the selectinload join.
    return list(result.scalars().unique().all())


async def get_exercise(
    db: AsyncSession,
    exercise_id: int,
    *,
    include_hidden: bool = False,
) -> StrengthExercise | None:
    """Return a single exercise by primary key, or ``None`` if not found.

    Args:
        db: Active async session. Caller owns commit/rollback.
        exercise_id: Primary key of the ``StrengthExercise`` row.
        include_hidden: When ``False`` (default), a hidden exercise is
            treated as not found (``None``). Pass ``True`` for curation/
            admin flows that must be able to see hidden rows.

    Returns:
        ``StrengthExercise`` with ``.age_bands`` eagerly loaded, or ``None``
        when the id is unknown (or hidden and ``include_hidden=False``).

    Side-effects:
        Issues up to 2 SELECT statements (one primary + one selectinload
        IN-query). No writes.
    """
    stmt = select(StrengthExercise).where(StrengthExercise.id == exercise_id).options(
        selectinload(StrengthExercise.age_bands),
    )
    if not include_hidden:
        stmt = stmt.where(StrengthExercise.is_hidden.is_(False))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
