"""Progress-notes service for the Strength Training Library (feature 021, T034).

Mirrors ``app/services/technique/progress.py`` (feature 018) closely: all
functions are async, accept an ``AsyncSession``, and never commit or flush
past what is strictly needed to obtain DB-assigned defaults — callers own
the transaction boundary (Constitution I).

Privacy invariant (FR-020, data-model.md §3):
    Every public function in this module is scoped to a SINGLE athlete_id
    supplied by the caller.  No function ever returns, ranks, or aggregates
    progress data across more than one athlete.  This invariant must be
    preserved in all future edits — do NOT add parameters that accept
    multiple athlete_ids or return cross-athlete comparisons.

Append-only design (data-model.md §3 "Progress: append-only; no
transitions, latest-wins read"):
    Progress is recorded as immutable events.  There is no UPDATE or DELETE
    path.  The "current" state exposed to callers is always derived from
    the most-recent event per (athlete_id, exercise_id), computed in Python
    from the ordered history after a single DB fetch — same technique as
    the 018 service, avoiding any window-function compatibility concern
    with the MySQL 8.4 target.

Club-scope note:
    Unlike the router, this module does NOT perform club-membership checks.
    That guard (``_require_athlete_club_scope``, mirrored from
    ``app/routers/technique.py:417``) is a router-level concern applied
    BEFORE these functions are called, exactly as in feature 018. Keeping
    it out of the service keeps these functions reusable and testable in
    isolation.
"""
from __future__ import annotations

import logging
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete
from app.models.strength import StrengthExercise, StrengthProgressNote, StrengthProgressStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------


class LatestProgressRow(TypedDict):
    """One row of ``get_latest_progress`` — maps 1:1 onto ``ProgressOut``.

    ``exercise_name`` is denormalized here (joined from ``StrengthExercise``)
    so the router can serialize ``ProgressOut`` without a second query.
    """

    exercise_id: int
    exercise_name: str
    status: StrengthProgressStatus
    coach_note: str | None
    season: int
    recorded_at: object  # datetime; kept loose to avoid import-only-for-typing


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def add_progress_note(
    db: AsyncSession,
    athlete_id: int,
    *,
    exercise_id: int,
    status: StrengthProgressStatus,
    coach_note: str | None,
    season: int,
    recorded_by_user_id: int,
) -> StrengthProgressNote:
    """Append a new progress note for a single athlete (append-only).

    This is the only write path for strength progress. Notes are never
    updated or deleted; the current mastery state is always the latest note
    per (athlete_id, exercise_id).

    Privacy invariant (FR-020): this function writes data for exactly one
    athlete identified by ``athlete_id``. No cross-athlete write ever
    occurs here.

    Args:
        db: Active async session. Caller owns commit/rollback.
        athlete_id: PK of the ``athletes`` table row being tracked.
        exercise_id: PK of the ``strength_exercises`` row.
        status: New mastery level — one of ``introducido``, ``en_progreso``,
            ``dominado``.
        coach_note: Optional mastery-climate note (<= 500 chars). Must not
            contain minor PII — enforced by the schema layer.
        season: Four-digit year used to scope the note to a training season.
        recorded_by_user_id: PK of the ``users`` row (coach or admin) who
            is recording this observation.

    Returns:
        The newly created ``StrengthProgressNote`` ORM object, with the
        ``exercise`` relationship eagerly loaded so the router can
        serialize the ``ProgressOut`` response schema without a second
        query.

    Raises:
        ValueError: when ``athlete_id`` does not resolve to a known athlete
            row, or ``exercise_id`` does not resolve to a known exercise
            row. The router must convert this to ``HTTP 404`` (contracts:
            "404 unknown exercise").
    """
    athlete_exists_result = await db.execute(
        select(Athlete.id).where(Athlete.id == athlete_id)
    )
    if athlete_exists_result.scalar_one_or_none() is None:
        raise ValueError(f"Athlete {athlete_id} not found")

    exercise_exists_result = await db.execute(
        select(StrengthExercise.id).where(StrengthExercise.id == exercise_id)
    )
    if exercise_exists_result.scalar_one_or_none() is None:
        raise ValueError(f"Exercise {exercise_id} not found")

    note = StrengthProgressNote(
        athlete_id=athlete_id,
        exercise_id=exercise_id,
        status=status,
        coach_note=coach_note,
        season=season,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.add(note)
    # Flush so the DB assigns ``note.id`` and ``note.recorded_at`` before we
    # eagerly load the exercise relationship below.
    await db.flush()

    result = await db.execute(
        select(StrengthProgressNote)
        .where(StrengthProgressNote.id == note.id)
        .options(selectinload(StrengthProgressNote.exercise))
    )
    loaded: StrengthProgressNote = result.scalar_one()

    logger.debug(
        "Strength progress note added: athlete_id=%s exercise_id=%s status=%s "
        "season=%s",
        athlete_id,
        exercise_id,
        status,
        season,
        # NOTE: coach_note deliberately excluded from log (minors privacy).
    )
    return loaded


async def get_latest_progress(
    db: AsyncSession,
    athlete_id: int,
) -> list[LatestProgressRow]:
    """Return the latest progress note per exercise for ONE athlete (US4).

    Privacy invariant (FR-020): the WHERE clause unconditionally filters on
    ``athlete_id``. The returned list contains ONLY rows for this athlete.
    No ranking, no aggregation, no cross-athlete data is ever present in
    the result. This invariant must never be weakened.

    The "latest per exercise_id" state is computed in Python from the full
    per-athlete history, ordered by ``recorded_at`` ascending, keeping the
    last-seen row per exercise_id — same single-round-trip technique as
    ``services/technique/progress.py::get_athlete_progress``.

    Graceful empty response:
        When the athlete exists but has never had a progress note
        recorded, this returns an empty list — this is NOT an error. The
        router raises 404 only when ``athlete_id`` itself is unknown.

    Args:
        db: Active async session. Caller owns commit/rollback.
        athlete_id: PK of the ``athletes`` table row to retrieve.

    Returns:
        List of ``LatestProgressRow`` — one per distinct ``exercise_id``
        the athlete has a note for, each carrying the joined
        ``exercise_name`` for display (contracts/strength-api.md:
        "GET /athletes/{athlete_id}/progress" -> "latest row per
        exercise").

    Raises:
        ValueError: when ``athlete_id`` does not resolve to a known athlete
            row. The router must convert this to ``HTTP 404``.
    """
    athlete_exists_result = await db.execute(
        select(Athlete.id).where(Athlete.id == athlete_id)
    )
    if athlete_exists_result.scalar_one_or_none() is None:
        raise ValueError(f"Athlete {athlete_id} not found")

    # Single query: all notes for this athlete, oldest-first, with the
    # exercise relationship eagerly loaded for the display name.
    # The WHERE athlete_id = :athlete_id is the privacy boundary.
    result = await db.execute(
        select(StrengthProgressNote)
        .where(StrengthProgressNote.athlete_id == athlete_id)
        .options(selectinload(StrengthProgressNote.exercise))
        .order_by(StrengthProgressNote.recorded_at.asc())
    )
    history: list[StrengthProgressNote] = list(result.scalars().all())

    # Derive latest-per-exercise: iterating in ascending recorded_at order
    # means later iterations overwrite earlier ones — the final dict value
    # is always the latest note for that exercise_id.
    latest_per_exercise: dict[int, StrengthProgressNote] = {}
    for note in history:
        latest_per_exercise[note.exercise_id] = note

    return [
        LatestProgressRow(
            exercise_id=note.exercise_id,
            exercise_name=note.exercise.name,
            status=note.status,
            coach_note=note.coach_note,
            season=note.season,
            recorded_at=note.recorded_at,
        )
        for note in latest_per_exercise.values()
    ]
