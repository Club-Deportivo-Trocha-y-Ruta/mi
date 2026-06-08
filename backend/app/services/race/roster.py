"""Service layer for the race-event roster (call-up) feature.

Feature: 007-competitions-consolidation, Wave C (US3 FR-022/FR-023).

All database operations are async (``AsyncSession``).  Parameterised queries
only — no string concatenation for SQL.

Privacy (Ley 1581):
- Logs emit ids only; athlete names and notes are never logged.
- The ``athlete_name`` field assembled here is the registered club name (first +
  last from ``athletes``), not free-form user input.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete
from app.models.race_event import RaceEvent
from app.models.race_event_roster import RaceEventRoster
from app.models.race_result import RaceResult
from app.schemas.race_roster import (
    RosterEntryCreate,
    RosterEntryRead,
    RosterEntryUpdate,
    RosterRead,
    RosterReconciliation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _entry_to_read(entry: RaceEventRoster) -> RosterEntryRead:
    """Convert an ORM ``RaceEventRoster`` row to the read schema.

    Requires ``entry.athlete`` to be loaded (use ``selectinload``).
    """
    athlete = entry.athlete
    athlete_name = f"{athlete.first_name} {athlete.last_name}"
    return RosterEntryRead(
        id=entry.id,
        athlete_id=entry.athlete_id,
        athlete_name=athlete_name,
        status=entry.status,
        note=entry.note,
    )


async def _load_event_or_404(db: AsyncSession, race_event_id: int) -> RaceEvent:
    """Return the ``RaceEvent`` or raise HTTP 404."""
    result = await db.execute(
        select(RaceEvent).where(RaceEvent.id == race_event_id)
    )
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )
    return event


async def _load_entry_or_404(
    db: AsyncSession,
    race_event_id: int,
    entry_id: int,
) -> RaceEventRoster:
    """Return the roster entry (with athlete eager-loaded) or raise HTTP 404.

    Validates that the entry belongs to the given event.
    """
    result = await db.execute(
        select(RaceEventRoster)
        .options(selectinload(RaceEventRoster.athlete))
        .where(
            RaceEventRoster.id == entry_id,
            RaceEventRoster.race_event_id == race_event_id,
        )
    )
    entry: Optional[RaceEventRoster] = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Entrada de nómina con id={entry_id} no existe "
                f"para el evento id={race_event_id}."
            ),
        )
    return entry


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


async def _compute_reconciliation(
    db: AsyncSession,
    race_event_id: int,
    roster_athlete_ids: set[int],
) -> RosterReconciliation:
    """Compute the roster/results discrepancy for a competition.

    Called-up athletes with no result vs. athletes with a result not in the
    roster.  Both directions use a single query each — no N+1.

    Args:
        db: Async DB session.
        race_event_id: The competition to reconcile.
        roster_athlete_ids: Set of athlete IDs already loaded from the roster.

    Returns:
        ``RosterReconciliation`` with two sorted lists of athlete IDs.
    """
    # Distinct athlete_ids with non-deleted results for this event.
    result_stmt = (
        select(RaceResult.athlete_id)
        .where(
            RaceResult.event_id == race_event_id,
            RaceResult.athlete_id.is_not(None),
            RaceResult.deleted_at.is_(None),
        )
        .distinct()
    )
    rows = await db.execute(result_stmt)
    result_athlete_ids: set[int] = {r for (r,) in rows.all()}

    called_up_no_result = sorted(roster_athlete_ids - result_athlete_ids)
    result_not_called_up = sorted(result_athlete_ids - roster_athlete_ids)

    return RosterReconciliation(
        called_up_no_result=called_up_no_result,
        result_not_called_up=result_not_called_up,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get_roster(
    db: AsyncSession,
    race_event_id: int,
    allowed_athlete_ids: Optional[set[int]] = None,
) -> RosterRead:
    """Return the full roster for a competition, with reconciliation.

    Args:
        db: Async DB session.
        race_event_id: The competition whose roster to retrieve.
        allowed_athlete_ids: If ``None`` (coach/admin), all entries are
            returned.  If a ``set`` (parent scope), only entries whose
            ``athlete_id`` is in the set are included.  An empty set means the
            caller has no linked children and gets an empty list.

    Raises:
        HTTPException 404: If the race event does not exist.
    """
    await _load_event_or_404(db, race_event_id)

    stmt = (
        select(RaceEventRoster)
        .options(selectinload(RaceEventRoster.athlete))
        .where(RaceEventRoster.race_event_id == race_event_id)
        .order_by(RaceEventRoster.id)
    )

    if allowed_athlete_ids is not None:
        # Parent scope: restrict to own children.
        if not allowed_athlete_ids:
            entries_orm: list[RaceEventRoster] = []
        else:
            stmt = stmt.where(
                RaceEventRoster.athlete_id.in_(allowed_athlete_ids)
            )
            rows = await db.execute(stmt)
            entries_orm = list(rows.scalars().all())
    else:
        rows = await db.execute(stmt)
        entries_orm = list(rows.scalars().all())

    entries = [_entry_to_read(e) for e in entries_orm]

    # Privacy (Ley 1581): the free-text `note` is a coach planning field that
    # could mention another athlete. Parents (scoped reads) never receive it.
    if allowed_athlete_ids is not None:
        entries = [e.model_copy(update={"note": None}) for e in entries]

    # Reconciliation is only meaningful for the full (coach/admin) view.
    if allowed_athlete_ids is None:
        roster_ids = {e.athlete_id for e in entries_orm}
        reconciliation = await _compute_reconciliation(db, race_event_id, roster_ids)
    else:
        # Parents see an empty reconciliation to avoid leaking other athletes.
        reconciliation = RosterReconciliation()

    logger.info(
        "roster_get race_event_id=%s entries=%s",
        race_event_id,
        len(entries),
    )
    return RosterRead(
        race_event_id=race_event_id,
        entries=entries,
        reconciliation=reconciliation,
    )


async def add_roster_entry(
    db: AsyncSession,
    race_event_id: int,
    payload: RosterEntryCreate,
    created_by_user_id: int,
) -> RosterEntryRead:
    """Add a club athlete to the competition's call-up roster.

    Args:
        db: Async DB session.
        race_event_id: The competition to add the entry to.
        payload: ``RosterEntryCreate`` with athlete_id, status, note.
        created_by_user_id: ID of the coach/admin making the request.

    Raises:
        HTTPException 404: If the race event or athlete does not exist.
        HTTPException 409: If the athlete is already in the roster for this event.
        HTTPException 422: If the athlete does not belong to any club
            (i.e., the ``athletes`` table has no row for the given id).
    """
    await _load_event_or_404(db, race_event_id)

    # Validate that the athlete exists (club membership is implied by being
    # in the ``athletes`` table which carries a club_id).
    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == payload.athlete_id)
    )
    athlete: Optional[Athlete] = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Atleta con id={payload.athlete_id} no existe o no pertenece a ningún club.",
        )

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    entry = RaceEventRoster(
        race_event_id=race_event_id,
        athlete_id=payload.athlete_id,
        status=payload.status,
        note=payload.note,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(entry)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Atleta id={payload.athlete_id} ya está en la nómina "
                f"del evento id={race_event_id}."
            ),
        )

    # Reload with athlete relationship for name assembly.
    await db.refresh(entry, ["athlete"])

    logger.info(
        "roster_add race_event_id=%s entry_id=%s created_by=%s",
        race_event_id,
        entry.id,
        created_by_user_id,
    )
    return _entry_to_read(entry)


async def update_roster_entry(
    db: AsyncSession,
    race_event_id: int,
    entry_id: int,
    payload: RosterEntryUpdate,
) -> RosterEntryRead:
    """Partially update a roster entry's status and/or note.

    Args:
        db: Async DB session.
        race_event_id: The competition the entry belongs to.
        entry_id: The roster entry to update.
        payload: Fields to update (only set fields are applied).

    Raises:
        HTTPException 404: If the entry or event does not exist.
    """
    entry = await _load_entry_or_404(db, race_event_id, entry_id)

    updated_fields = payload.model_dump(exclude_unset=True)
    for field, value in updated_fields.items():
        setattr(entry, field, value)

    await db.flush()

    logger.info(
        "roster_update race_event_id=%s entry_id=%s fields=%s",
        race_event_id,
        entry_id,
        sorted(updated_fields.keys()),
    )
    return _entry_to_read(entry)


async def delete_roster_entry(
    db: AsyncSession,
    race_event_id: int,
    entry_id: int,
) -> None:
    """Remove an athlete from the competition's call-up roster.

    Args:
        db: Async DB session.
        race_event_id: The competition the entry belongs to.
        entry_id: The roster entry to delete.

    Raises:
        HTTPException 404: If the entry or event does not exist.
    """
    entry = await _load_entry_or_404(db, race_event_id, entry_id)
    await db.delete(entry)
    await db.flush()

    logger.info(
        "roster_delete race_event_id=%s entry_id=%s",
        race_event_id,
        entry_id,
    )
