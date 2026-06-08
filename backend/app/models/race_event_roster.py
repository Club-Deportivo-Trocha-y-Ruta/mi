"""SQLAlchemy model for `race_event_roster` (manual call-up list for a competition).

Tracks which club athletes are entered in a competition independent of imported
results — usable before any PDF is available.  The reconciliation between roster
entries and actual results is computed on demand in the service layer (never stored).

Migration: ``e5f6a7b8c9d0`` chained to ``b4c5d6e7f8a9``.
Feature: 007-competitions-consolidation, Wave C (US3 — FR-022/FR-023).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.race_event import RaceEvent
    from app.models.user import User


class RaceEventRosterStatus(str, enum.Enum):
    """Lifecycle state of a roster entry.

    - ``called_up``  — default; athlete has been added to the call-up list.
    - ``confirmed``  — coach has confirmed the athlete will start.
    - ``withdrawn``  — athlete was removed from the entry after being called up.
    """

    called_up = "called_up"
    confirmed = "confirmed"
    withdrawn = "withdrawn"


class RaceEventRoster(Base):
    """One club athlete's call-up entry for a race event.

    Uniqueness ``(race_event_id, athlete_id)`` prevents double-entry.
    The FK on ``race_event_id`` is CASCADE so that deleting a competition
    cleans up its roster automatically.  The FK on ``athlete_id`` is RESTRICT
    to avoid silently orphaning a call-up when an athlete is removed.

    ``note`` is for logistical use only (e.g., "travel confirmed") — never
    medical or training data — and must not contain the athlete's full name
    (Ley 1581).
    """

    __tablename__ = "race_event_roster"
    __table_args__ = (
        UniqueConstraint(
            "race_event_id",
            "athlete_id",
            name="uq_race_event_roster_event_athlete",
        ),
        Index("ix_race_event_roster_race_event_id", "race_event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_event_id: Mapped[int] = mapped_column(
        ForeignKey("race_events.id", ondelete="CASCADE"), nullable=False
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[RaceEventRosterStatus] = mapped_column(
        Enum(
            RaceEventRosterStatus,
            name="raceeventrosterstatus",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RaceEventRosterStatus.called_up,
    )
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    race_event: Mapped["RaceEvent"] = relationship(
        "RaceEvent",
        foreign_keys="[RaceEventRoster.race_event_id]",
        back_populates="roster_entries",
    )
    athlete: Mapped["Athlete"] = relationship(
        "Athlete",
        foreign_keys="[RaceEventRoster.athlete_id]",
    )
    created_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceEventRoster.created_by_user_id]",
    )
