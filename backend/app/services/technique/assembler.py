"""Session assembler for the Technique & Gymkhana Library (feature 018, T027).

Provides two public coroutines:

* :func:`assemble_technique_session` — creates a normal ``TrainingSession``
  via the existing training service, writes ``TechniqueSessionExercise`` rows
  in the same transaction, and computes the age-band mix flag.

  Feature 019 Phase B (O-6): when ``payload.combined_layout`` is present, a
  hidden synthetic ``TechniqueExercise`` (``is_hidden=True``, ``is_gymkhana=True``)
  is created (or updated, when ``payload.combined_exercise_id`` is set) to persist
  the free-form combined circuit as ``layout_json``.  The re-edit path (with
  ``combined_exercise_id``) skips session creation and updates the existing session
  link rows instead — no duplicate session is created (FR-015).

* :func:`get_session_exercises` — returns the ordered exercise list for a
  previously assembled session with full eager-loading of skills and age bands.

Design rules (Constitution I):
- This module never calls ``db.commit()`` directly during validation helpers;
  the commit(s) are issued once at the end of :func:`assemble_technique_session`
  after both the session and the link rows are flushed.
- All DB operations use ``AsyncSession`` (rule 1, rule 5).
- No raw SQL concatenation (rule 4).
- ``create_session`` from ``app.services.training.sessions`` is called exactly
  once (create path only) and owns the session row + attendances + calendar event.
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.technique_exercise import (
    AgeBand,
    ExerciseDifficulty,
    SessionSegment,
    TechniqueExercise,
    TechniqueExerciseAgeBand,
    TechniqueSessionExercise,
)
from app.models.training_session import SessionKind, TrainingSession
from app.schemas.technique import AssembleSessionRequest
from app.schemas.training_session import TrainingSessionCreate

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)

# Sentinel position used for the synthetic combined-circuit exercise link row.
# Must be outside normal position range (0-based within each segment) so the
# synthetic row sorts last and the frontend can easily identify it (O-6).
_SYNTHETIC_EXERCISE_POSITION = 9999


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _create_synthetic_exercise(
    db: AsyncSession,
    *,
    technical_focus: str,
    layout_json: dict | None,
    created_by_user_id: int,
    club_id: int | None,
) -> TechniqueExercise:
    """Create a hidden synthetic TechniqueExercise for the combined circuit (O-6).

    The synthetic exercise is marked ``is_hidden=True`` (kept out of the public
    catalog) and ``is_gymkhana=True`` (it holds a gymkhana circuit layout).
    Its ``slug`` is a random UUID-hex so it never conflicts with seeded slugs.

    All required NOT NULL columns are populated with safe fixed defaults; the
    meaningful payload is ``layout_json`` (the GymkhanaLayoutPhaseB dict).

    Args:
        db: Active async session.  ``db.flush()`` is called to populate ``.id``;
            the caller owns the final ``db.commit()``.
        technical_focus: Used to build a human-readable exercise name.
        layout_json: Serialized ``GymkhanaLayoutPhaseB`` dict (may be None).
        created_by_user_id: Authenticated coach/admin user id.
        club_id: Club the enclosing session belongs to.

    Returns:
        Flushed (but not committed) ``TechniqueExercise`` with ``.id`` populated.
    """
    synthetic = TechniqueExercise(
        slug=f"synthetic-gymkhana-{uuid.uuid4().hex}",
        name=f"Circuito combinado — {technical_focus[:80]}",
        summary="Circuito de gymkhana combinado generado por el compositor.",
        how_to="Sigue el circuito combinado según las instrucciones del entrenador.",
        difficulty=ExerciseDifficulty.MEDIA,
        is_game=False,
        is_gymkhana=True,
        is_seeded=False,
        is_hidden=True,
        layout_json=layout_json,
        layout_ascii=None,
        layout_alt=None,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
    )
    # Explicitly mark the M2M/relationship collections as loaded (empty).
    # Without this, accessing them after the caller's later db.commit()
    # (expire_on_commit=False keeps the *row* fresh, but these collections
    # were never touched so SQLAlchemy still treats them as unloaded) would
    # trigger an implicit lazy load — which raises sqlalchemy.exc.MissingGreenlet
    # under AsyncSession outside of an explicit await context. Setting them
    # here avoids that lazy load entirely (no IO required, response stays sync).
    synthetic.skills = []
    synthetic.age_bands = []
    synthetic.materials = []
    db.add(synthetic)
    await db.flush()  # populate .id without committing
    return synthetic


async def _resolve_synthetic_session(
    db: AsyncSession,
    combined_exercise_id: int,
) -> tuple[TechniqueExercise, int]:
    """Validate the synthetic exercise and return it along with its session id.

    Used on the re-edit path (``combined_exercise_id`` set in the request).
    Verifies that the exercise exists, is synthetic (is_hidden + is_gymkhana),
    and is linked to exactly one training session.

    Args:
        db: Active async session.
        combined_exercise_id: PK of the synthetic ``TechniqueExercise``.

    Returns:
        Two-tuple ``(synthetic_exercise, training_session_id)``.

    Raises:
        HTTPException 422: synthetic exercise not found, not hidden, not gymkhana,
            or not linked to any session.
    """
    # Eager-load skills/age_bands so _serialize_session_item (router layer)
    # can read them synchronously without an implicit lazy load — which would
    # raise MissingGreenlet under AsyncSession on a re-edit (fresh request,
    # fresh session, so the create-path's in-memory empty-collection trick
    # does not carry over).
    ex_result = await db.execute(
        select(TechniqueExercise)
        .where(TechniqueExercise.id == combined_exercise_id)
        .options(
            selectinload(TechniqueExercise.skills),
            selectinload(TechniqueExercise.age_bands),
        )
    )
    synthetic = ex_result.scalar_one_or_none()
    if synthetic is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Ejercicio sintético {combined_exercise_id} no encontrado. "
                "Verifica combined_exercise_id."
            ),
        )
    if not synthetic.is_hidden or not synthetic.is_gymkhana:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El ejercicio {combined_exercise_id} no es un circuito combinado "
                "sintético válido para re-edición (O-6)."
            ),
        )

    # Find the session linked to this synthetic exercise.
    link_result = await db.execute(
        select(TechniqueSessionExercise.training_session_id)
        .where(TechniqueSessionExercise.exercise_id == combined_exercise_id)
        .limit(1)
    )
    session_id = link_result.scalar_one_or_none()
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El ejercicio sintético {combined_exercise_id} no está "
                "vinculado a ninguna sesión. No se puede re-editar."
            ),
        )
    return synthetic, session_id


async def _load_exercises_by_ids(
    db: AsyncSession, exercise_ids: list[int]
) -> dict[int, TechniqueExercise]:
    """Load and return exercises keyed by id, with age_bands eagerly loaded.

    Args:
        db: Active async session. Caller owns commit/rollback.
        exercise_ids: Distinct exercise primary keys to look up.

    Returns:
        Mapping of ``exercise_id → TechniqueExercise`` for every id that
        exists in the database.  Missing ids are absent from the dict —
        callers must detect the gap and raise 422.

    Side-effects:
        Issues 2 SELECT statements (one primary + one ``selectinload``
        IN-query for ``age_bands``).  No writes.
    """
    result = await db.execute(
        select(TechniqueExercise)
        .where(TechniqueExercise.id.in_(exercise_ids))
        .options(
            selectinload(TechniqueExercise.age_bands),
            selectinload(TechniqueExercise.skills),
        )
    )
    return {ex.id: ex for ex in result.scalars().all()}


def _compute_mixes_age_bands(
    exercises: dict[int, TechniqueExercise],
    item_exercise_ids: list[int],
) -> bool:
    """Return True when the selected exercises span more than one age band.

    Args:
        exercises: Mapping of id → loaded ``TechniqueExercise`` (with
            ``age_bands`` already eager-loaded).
        item_exercise_ids: Ordered list of exercise ids from the request
            items (may contain duplicates; deduplicated internally).

    Returns:
        ``True`` when the union of ``AgeBand`` values across all chosen
        exercises has cardinality > 1 (FR-014); ``False`` otherwise.

    Side-effects:
        None — pure computation, no I/O.
    """
    bands: set[AgeBand] = set()
    for eid in dict.fromkeys(item_exercise_ids):  # preserves unique order
        ex = exercises.get(eid)
        if ex is not None:
            for ab in ex.age_bands:
                bands.add(ab.age_band)
    return len(bands) > 1


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def assemble_technique_session(
    db: AsyncSession,
    *,
    payload: AssembleSessionRequest,
    current_user: "User",
    club_id: int,
) -> tuple[TrainingSession, bool, list[TechniqueSessionExercise], int | None]:
    """Create (or re-edit) a normal training session and attach technique exercise rows.

    Two paths depending on ``payload.combined_exercise_id``:

    **CREATE path** (``combined_exercise_id`` is None):
        Step 1 — Validate component items and resolve exercises (422 on missing).
        Step 2 — When ``combined_layout`` is present, create a hidden synthetic
            ``TechniqueExercise`` (``is_hidden=True``, ``is_gymkhana=True``) via
            ``_create_synthetic_exercise``; its ``layout_json`` holds the
            serialized ``GymkhanaLayoutPhaseB`` dict (feature 019, O-6).
        Step 3 — Create ``TrainingSession`` via ``training_svc.create_session``
            (owns commit + reload; creates calendar event + attendances).
        Step 4 — Insert ``TechniqueSessionExercise`` link rows for each component
            exercise, plus one additional link row for the synthetic exercise (if
            created); ``db.commit()`` persists all link rows.
        Step 5 — Compute ``mixes_age_bands`` (FR-014).

    **RE-EDIT path** (``combined_exercise_id`` is set):
        Step 1 — Validate component items and resolve exercises (422 on missing).
        Step 2 — Validate the synthetic exercise via ``_resolve_synthetic_session``;
            obtain the existing ``training_session_id`` from its link row.
        Step 3 — When ``combined_layout`` is provided, update ``layout_json`` on
            the synthetic exercise in place (no new row, FR-015).
        Step 4 — Delete all existing ``TechniqueSessionExercise`` rows for the
            session; re-insert component exercises + synthetic exercise link row.
            The ``TrainingSession`` row itself is NOT recreated — no duplicate (FR-015).
        Step 5 — Commit and reload; compute ``mixes_age_bands``.

    Args:
        db: Active async session.
        payload: Validated ``AssembleSessionRequest`` (Pydantic v2).
        current_user: Authenticated coach/admin ``User``.
        club_id: Club the session belongs to (router-verified).

    Returns:
        Four-tuple ``(training_session, mixes_age_bands, items, combined_exercise_id)``
        where:

        * ``training_session`` — the ``TrainingSession`` ORM object (created or
          reloaded from DB on re-edit).
        * ``mixes_age_bands`` — bool flag for the age-mix UI notice (FR-014).
        * ``items`` — list of all ``TechniqueSessionExercise`` rows including the
          synthetic exercise link (if present).
        * ``combined_exercise_id`` — PK of the synthetic exercise, or ``None``
          when no combined layout was requested.

    Raises:
        HTTPException 422: empty items, unknown exercise_id, invalid synthetic
            exercise on re-edit, or constraint violations from ``create_session``.
        ValueError: propagated from ``create_session`` for coach-club membership
            violations (should be caught by the router layer).

    Side-effects:
        Issues multiple SELECT / INSERT / DELETE statements.  Commits 1–2 times.
    """
    # --- Step 1: validate component item list and resolve exercises -----------
    if not payload.items:
        # Redundant with Pydantic min_length=1 but explicit for defensive safety.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La sesión debe contener al menos un ejercicio.",
        )

    item_exercise_ids: list[int] = [item.exercise_id for item in payload.items]
    exercises = await _load_exercises_by_ids(db, item_exercise_ids)

    missing = sorted(set(item_exercise_ids) - exercises.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ejercicios no encontrados: {missing}",
        )

    # Determine which execution path applies.
    is_re_edit = payload.combined_exercise_id is not None

    # =========================================================================
    # RE-EDIT PATH
    # =========================================================================
    if is_re_edit:
        # --- Step 2 (re-edit): validate synthetic exercise and get session id -
        synthetic, existing_session_id = await _resolve_synthetic_session(
            db, payload.combined_exercise_id  # type: ignore[arg-type]
        )

        # --- Step 3 (re-edit): update layout_json when a new layout is given -
        if payload.combined_layout is not None:
            synthetic.layout_json = payload.combined_layout.model_dump()

        # --- Step 4 (re-edit): replace TechniqueSessionExercise link rows ----
        # Delete all existing links for this session (including the old synthetic link).
        await db.execute(
            sa_delete(TechniqueSessionExercise).where(
                TechniqueSessionExercise.training_session_id == existing_session_id
            )
        )
        await db.flush()

        # Re-insert component exercise links.
        link_rows: list[TechniqueSessionExercise] = []
        for item in payload.items:
            row = TechniqueSessionExercise(
                training_session_id=existing_session_id,
                exercise_id=item.exercise_id,
                segment=item.segment,
                position=item.position,
            )
            db.add(row)
            link_rows.append(row)

        # Re-insert the synthetic exercise link (sentinel position sorts last).
        synthetic_link = TechniqueSessionExercise(
            training_session_id=existing_session_id,
            exercise_id=synthetic.id,
            segment=SessionSegment.PRINCIPAL,
            position=_SYNTHETIC_EXERCISE_POSITION,
        )
        # Populate the relationship in-memory (avoids a lazy load later, which
        # would raise MissingGreenlet under AsyncSession).
        synthetic_link.exercise = synthetic
        db.add(synthetic_link)
        link_rows.append(synthetic_link)

        await db.commit()

        # Reload ORM attributes (id, etc.) on link rows.
        for row in link_rows:
            await db.refresh(row)
        # db.refresh() above expires (and lazily-reloads-on-access) the
        # ``.exercise`` relationship we set in-memory; re-populate the
        # synthetic link's relationship to avoid a later MissingGreenlet
        # lazy load in the router's synchronous response serialization.
        synthetic_link.exercise = synthetic

        # Reload the training session so that ORM attributes are fresh.
        session_result = await db.execute(
            select(TrainingSession).where(TrainingSession.id == existing_session_id)
        )
        training_session = session_result.scalar_one()

        mixes = _compute_mixes_age_bands(exercises, item_exercise_ids)

        logger.debug(
            "Sesión de técnica re-editada | session_id=%s synthetic_id=%s "
            "exercises=%d mixes_age_bands=%s",
            existing_session_id,
            synthetic.id,
            len(link_rows),
            mixes,
        )

        return training_session, mixes, link_rows, synthetic.id

    # =========================================================================
    # CREATE PATH
    # =========================================================================

    # --- Step 2 (create): create synthetic exercise when combined_layout set --
    combined_layout_dict: dict | None = None
    synthetic_id: int | None = None

    if payload.combined_layout is not None:
        combined_layout_dict = payload.combined_layout.model_dump()
        synthetic = await _create_synthetic_exercise(
            db,
            technical_focus=payload.technical_focus,
            layout_json=combined_layout_dict,
            created_by_user_id=current_user.id,
            club_id=club_id,
        )
        synthetic_id = synthetic.id

    # --- Step 3 (create): create the normal TrainingSession ------------------
    # Import here to avoid circular references at module load time.
    from app.services.training.sessions import create_session as training_create_session

    session_payload = TrainingSessionCreate(
        scheduled_date=payload.scheduled_date,
        scheduled_start_time=payload.scheduled_start_time,
        duration_min=payload.duration_min,
        location=payload.location,
        technical_focus=payload.technical_focus,
        objectives=payload.objectives,
        convocados_athlete_ids=payload.convocados_athlete_ids,
        session_kind=SessionKind.ENTRENAMIENTO,
        # Fields not exposed by AssembleSessionRequest; use schema defaults.
        description=None,
        route_text=None,
        strava_url=None,
        coach_notes=None,
        send_notification=False,
    )

    # create_session flushes attendances, creates the parallel CalendarEvent,
    # and calls db.commit() + reloads before returning.
    training_session = await training_create_session(
        db=db,
        payload=session_payload,
        coach=current_user,
        club_id=club_id,
        notification_service=None,
        dispatcher=None,
    )

    # --- Step 4 (create): insert TechniqueSessionExercise rows ---------------
    link_rows: list[TechniqueSessionExercise] = []
    for item in payload.items:
        row = TechniqueSessionExercise(
            training_session_id=training_session.id,
            exercise_id=item.exercise_id,
            segment=item.segment,
            position=item.position,
        )
        db.add(row)
        link_rows.append(row)

    # When a synthetic exercise was created, link it to the session.
    # It uses a sentinel position so it sorts last and is identifiable by the frontend.
    if synthetic_id is not None:
        synthetic_link = TechniqueSessionExercise(
            training_session_id=training_session.id,
            exercise_id=synthetic_id,
            segment=SessionSegment.PRINCIPAL,
            position=_SYNTHETIC_EXERCISE_POSITION,
        )
        # Populate the relationship in-memory (avoids a lazy load later, which
        # would raise MissingGreenlet under AsyncSession — see
        # _create_synthetic_exercise's comment on the same pattern).
        synthetic_link.exercise = synthetic
        db.add(synthetic_link)
        link_rows.append(synthetic_link)

    await db.commit()

    # Reload the link rows with `.exercise` (including the synthetic exercise)
    # plus its `.skills`/`.age_bands` eagerly loaded, ordered by
    # (segment, position). This replaces an in-place `db.refresh()` loop that
    # expired `.exercise` on the *component* links (only the synthetic link was
    # re-populated), causing a MissingGreenlet lazy load during the router's
    # synchronous response serialization — surfaced by the e2e run against
    # aiomysql (aiosqlite served the cached relationship without IO, so the
    # unit tests did not catch it).
    link_rows = await get_session_exercises(db, training_session.id)

    # --- Step 5 (create): compute mixes_age_bands ----------------------------
    mixes = _compute_mixes_age_bands(exercises, item_exercise_ids)

    logger.debug(
        "Sesión de técnica ensamblada | session_id=%s synthetic_id=%s "
        "exercises=%d mixes_age_bands=%s",
        training_session.id,
        synthetic_id,
        len(link_rows),
        mixes,
    )

    return training_session, mixes, link_rows, synthetic_id


async def get_session_exercises(
    db: AsyncSession,
    training_session_id: int,
) -> list[TechniqueSessionExercise]:
    """Return the ordered technique exercise list for an assembled session.

    Rows are sorted by ``(segment, position)`` — matching the UI display
    order (calentamiento → principal → vuelta_calma, then by position within
    each segment).  The related ``exercise.skills`` and ``exercise.age_bands``
    are eagerly loaded to avoid N+1 queries when the router serialises each
    item into ``TechniqueSessionItem`` (FR-013, FR-020).

    The query intentionally includes exercises whose ``is_hidden=true`` so
    that previously assembled sessions remain intact after a coach hides an
    exercise from the catalog (FR-020).

    Args:
        db: Active async session.  Caller owns commit/rollback.
        training_session_id: Primary key of the ``TrainingSession``.

    Returns:
        List of ``TechniqueSessionExercise`` rows with ``.exercise``,
        ``.exercise.skills``, and ``.exercise.age_bands`` loaded.
        Returns an empty list when the session exists but has no linked
        exercises (e.g. a regular non-technique session).

    Side-effects:
        Issues SELECT statements (primary + up to 3 ``selectinload``
        IN-queries).  No writes.
    """
    result = await db.execute(
        select(TechniqueSessionExercise)
        .where(
            TechniqueSessionExercise.training_session_id == training_session_id
        )
        .options(
            selectinload(TechniqueSessionExercise.exercise).selectinload(
                TechniqueExercise.skills
            ),
            selectinload(TechniqueSessionExercise.exercise).selectinload(
                TechniqueExercise.age_bands
            ),
        )
        .order_by(
            TechniqueSessionExercise.segment,
            TechniqueSessionExercise.position,
        )
    )
    return list(result.scalars().all())
