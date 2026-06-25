"""Session assembler for the Technique & Gymkhana Library (feature 018, T027).

Provides two public coroutines:

* :func:`assemble_technique_session` — creates a normal ``TrainingSession``
  via the existing training service, writes ``TechniqueSessionExercise`` rows
  in the same transaction, and computes the age-band mix flag.

* :func:`get_session_exercises` — returns the ordered exercise list for a
  previously assembled session with full eager-loading of skills and age bands.

Design rules (Constitution I):
- This module never calls ``db.commit()`` directly during validation helpers;
  the single commit is issued at the end of :func:`assemble_technique_session`
  after both the session and the link rows are flushed.
- All DB operations use ``AsyncSession`` (rule 1, rule 5).
- No raw SQL concatenation (rule 4).
- ``create_session`` from ``app.services.training.sessions`` is called exactly
  once and owns the session row + attendances + calendar event creation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.technique_exercise import (
    AgeBand,
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
) -> tuple[TrainingSession, bool, list[TechniqueSessionExercise]]:
    """Create a normal training session and attach technique exercise rows.

    Step 1 — Validate items:
        ``payload.items`` must be non-empty (enforced by the Pydantic schema)
        and every referenced ``exercise_id`` must exist in the database.
        Raises ``HTTPException 422`` on violation.

    Step 2 — Create TrainingSession via ``training_svc.create_session``:
        Maps ``AssembleSessionRequest`` fields into a ``TrainingSessionCreate``
        schema and delegates to the existing creation path so that the new
        session appears in the standard calendar/list and supports attendance
        and the rubric (FR-011, FR-012).  ``create_session`` is called with
        ``notification_service=None`` and ``dispatcher=None`` (no parent
        email is triggered from the technique path).

        ``create_session`` internally calls ``db.commit()`` and reloads the
        session.  After it returns, the session id is stable.

    Step 3 — Insert ``TechniqueSessionExercise`` rows:
        One row per item in ``payload.items`` (segment, position preserved).
        A second ``db.commit()`` persists the link rows.

    Step 4 — Compute ``mixes_age_bands``:
        Collects the union of ``AgeBand`` values across all exercises;
        returns ``True`` when the union has > 1 distinct band (FR-014).

    Args:
        db: Active async session.  The function calls ``db.commit()`` twice
            (once inside ``create_session``, once after inserting link rows).
        payload: Validated request body (``AssembleSessionRequest``).
        current_user: Authenticated coach/admin ``User`` object.
        club_id: Club the session belongs to (verified by the router before
            this call via ``user_club_role``).

    Returns:
        Three-tuple ``(training_session, mixes_age_bands, items)`` where:

        * ``training_session`` — the newly created and reloaded
          ``TrainingSession`` ORM object.
        * ``mixes_age_bands`` — bool flag for the age-mix UI notice.
        * ``items`` — list of ``TechniqueSessionExercise`` rows in insertion
          order (same order as ``payload.items``).

    Raises:
        HTTPException 422: when ``payload.items`` is empty (redundant guard
            beyond Pydantic) or when any ``exercise_id`` does not exist.
        HTTPException 422: propagated from ``create_session`` for constraint
            violations on the session row.
        ValueError: propagated from ``create_session`` when the coach is not
            a member of the target club (should be caught by router).

    Side-effects:
        Issues multiple SELECT and INSERT statements; commits the transaction
        twice.  Logs a debug line with the new session id.
    """
    # --- Step 1: validate item list and resolve exercises --------------------
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

    # --- Step 2: create the normal TrainingSession ---------------------------
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

    # --- Step 3: insert TechniqueSessionExercise rows ------------------------
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

    await db.commit()

    # Reload link rows so that ORM attributes (id, etc.) are populated.
    for row in link_rows:
        await db.refresh(row)

    # --- Step 4: compute mixes_age_bands -------------------------------------
    mixes = _compute_mixes_age_bands(exercises, item_exercise_ids)

    logger.debug(
        "Sesión de técnica ensamblada | session_id=%s exercises=%d mixes_age_bands=%s",
        training_session.id,
        len(link_rows),
        mixes,
    )

    return training_session, mixes, link_rows


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
