"""Skill-progress service for the Technique & Gymkhana Library (feature 018, T036).

All functions are async and accept an ``AsyncSession``; they never commit or
flush — callers own the transaction boundary (Constitution I).

Privacy invariant (FR-017, SC-005):
    Every public function in this module is scoped to a SINGLE athlete_id
    supplied by the caller.  No function ever returns, ranks, or aggregates
    data across more than one athlete.  This invariant must be preserved in
    all future edits — do NOT add parameters that accept multiple athlete_ids
    or return cross-athlete comparisons.

Append-only design (FR-015):
    Progress is recorded as immutable events.  There is no UPDATE or DELETE
    path.  The "current" state is always derived from the most-recent event
    per (athlete_id, skill_id), computed in Python from the ordered history
    after a single DB fetch.
"""
from __future__ import annotations

import logging
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete
from app.models.technique_exercise import AthleteSkillProgress, SkillProgressStatus
from app.models.technique_skill import TechniqueSkill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------


class AthleteProgressResult(TypedDict):
    """Return type for ``get_athlete_progress``.

    ``current``: the single most-recent ``AthleteSkillProgress`` event per
        skill_id for this athlete (latest status per skill).
    ``history``: every ``AthleteSkillProgress`` event for this athlete,
        ordered by ``recorded_at`` ascending (oldest first).

    Both lists contain only records for the requested athlete — never any
    other athlete (FR-017, SC-005).
    """

    current: list[AthleteSkillProgress]
    history: list[AthleteSkillProgress]


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def add_progress_event(
    db: AsyncSession,
    athlete_id: int,
    *,
    skill_id: int,
    status: SkillProgressStatus,
    coach_note: str | None,
    season: int,
    recorded_by_user_id: int,
) -> AthleteSkillProgress:
    """Append a new skill-progress event for a single athlete (FR-015).

    This is the only write path for skill progress.  Events are never
    updated or deleted; the current mastery state is always the latest event
    per (athlete_id, skill_id).

    Privacy invariant (FR-017, SC-005): this function writes data for
    exactly one athlete identified by ``athlete_id``.  No cross-athlete
    write ever occurs here.

    Args:
        db: Active async session.  Caller owns commit/rollback.
        athlete_id: PK of the ``athletes`` table row being tracked.
        skill_id: PK of the ``technique_skills`` row.
        status: New mastery level — one of ``introducido``, ``en_progreso``,
            ``dominado``.
        coach_note: Optional mastery-climate note (≤ 300 chars).  Must not
            contain minor PII — enforced by the schema layer.
        season: Four-digit year used to scope the event to a training season
            (FR-016).
        recorded_by_user_id: PK of the ``users`` row (coach or admin) who
            is recording this observation.

    Returns:
        The newly created ``AthleteSkillProgress`` ORM object, with the
        ``skill`` relationship eagerly loaded so the router can serialise
        the ``SkillProgressEvent`` response schema without a second query.

    Raises:
        ValueError: when the ``athlete_id`` does not resolve to a known
            athlete row.  The router must convert this to ``HTTP 404``
            (graceful 7–9 handling per FR-018).
    """
    # Verify the athlete exists — raises ValueError for the router to 404.
    athlete_exists_result = await db.execute(
        select(Athlete.id).where(Athlete.id == athlete_id)
    )
    if athlete_exists_result.scalar_one_or_none() is None:
        raise ValueError(f"Athlete {athlete_id} not found")

    event = AthleteSkillProgress(
        athlete_id=athlete_id,
        skill_id=skill_id,
        status=status,
        coach_note=coach_note,
        season=season,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.add(event)
    # Flush so the DB assigns ``event.id`` and ``event.recorded_at`` before
    # we eagerly load the skill relationship below.
    await db.flush()

    # Reload with the skill relationship populated so callers can serialise
    # the response without an extra round-trip.
    result = await db.execute(
        select(AthleteSkillProgress)
        .where(AthleteSkillProgress.id == event.id)
        .options(selectinload(AthleteSkillProgress.skill))
    )
    loaded: AthleteSkillProgress = result.scalar_one()

    logger.debug(
        "Progress event added: athlete_id=%s skill_id=%s status=%s season=%s",
        athlete_id,
        skill_id,
        status,
        season,
        # NOTE: coach_note deliberately excluded from log (minors privacy).
    )
    return loaded


async def get_athlete_progress(
    db: AsyncSession,
    athlete_id: int,
) -> AthleteProgressResult:
    """Return the full progress history and current state for ONE athlete (US4).

    Privacy invariant (FR-017, SC-005): the WHERE clause unconditionally
    filters on ``athlete_id``.  The returned dict contains ONLY records for
    this athlete.  No ranking, no aggregation, no cross-athlete data is
    ever present in the result.  This invariant must never be weakened.

    ``current`` is computed in Python from ``history`` by iterating the
    chronologically ordered list and keeping the last-seen event per
    skill_id.  A single DB round-trip therefore serves both halves of the
    response, avoiding any window-function compatibility concern with the
    MySQL 8.4 target.

    Graceful empty response (FR-018):
        When the athlete exists but has never had a progress event recorded,
        both ``current`` and ``history`` are empty lists — this is NOT a
        404.  The router raises 404 only when the athlete_id itself is
        unknown (see ``add_progress_event``).  The progress endpoint returns
        an empty result for a valid athlete with no events yet.

    Args:
        db: Active async session.  Caller owns commit/rollback.
        athlete_id: PK of the ``athletes`` table row to retrieve.

    Returns:
        ``AthleteProgressResult`` typed dict with:
          - ``history``: every ``AthleteSkillProgress`` event for this
            athlete, ordered by ``recorded_at`` ascending, with ``.skill``
            eagerly loaded.
          - ``current``: the latest event per ``skill_id`` derived from
            ``history`` (preserves the same ORM objects — no extra query).

    Raises:
        ValueError: when ``athlete_id`` does not resolve to a known athlete
            row.  The router must convert this to ``HTTP 404`` (FR-018).
    """
    # Verify the athlete exists — raises ValueError for the router to 404.
    athlete_exists_result = await db.execute(
        select(Athlete.id).where(Athlete.id == athlete_id)
    )
    if athlete_exists_result.scalar_one_or_none() is None:
        raise ValueError(f"Athlete {athlete_id} not found")

    # Single query: all events for this athlete, oldest-first, with skill loaded.
    # The WHERE athlete_id = :athlete_id is the privacy boundary (SC-005).
    result = await db.execute(
        select(AthleteSkillProgress)
        .where(AthleteSkillProgress.athlete_id == athlete_id)
        .options(selectinload(AthleteSkillProgress.skill))
        .order_by(AthleteSkillProgress.recorded_at.asc())
    )
    history: list[AthleteSkillProgress] = list(result.scalars().all())

    # Derive current state: last-seen event per skill_id.
    # Iterating in ascending recorded_at order means later iterations
    # overwrite earlier ones — the final dict value is always the latest event.
    latest_per_skill: dict[int, AthleteSkillProgress] = {}
    for event in history:
        latest_per_skill[event.skill_id] = event

    current: list[AthleteSkillProgress] = list(latest_per_skill.values())

    return AthleteProgressResult(current=current, history=history)
