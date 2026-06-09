"""Pydantic v2 schemas for the race-event roster (call-up) endpoints.

Feature: 007-competitions-consolidation, Wave C (US3 FR-022/FR-023).

Privacy (Ley 1581):
- ``athlete_name`` is included in read responses so the frontend can display
  entries without a separate lookup — it is the athlete's registered name,
  not free-text entered by a coach.
- Logs in the service and router MUST use ids only; names MUST NOT appear.
- Parent-scoped responses are filtered in the service layer before any schema
  is constructed.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.race_event_roster import RaceEventRosterStatus


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RosterEntryCreate(BaseModel):
    """Body for POST /{race_event_id}/roster — add an athlete to the call-up list."""

    athlete_id: int = Field(..., description="ID of the club athlete to call up.")
    status: RaceEventRosterStatus = Field(
        default=RaceEventRosterStatus.called_up,
        description="Initial status; defaults to 'called_up'.",
    )
    note: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Optional logistical note (no athlete names or medical data).",
    )

    model_config = {"extra": "forbid"}


class RosterEntryUpdate(BaseModel):
    """Body for PATCH /{race_event_id}/roster/{entry_id} — partial update."""

    status: Optional[RaceEventRosterStatus] = Field(
        default=None,
        description="New status for the entry.",
    )
    note: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Updated logistical note.",
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class RosterEntryRead(BaseModel):
    """Single call-up entry as returned by the API."""

    id: int
    athlete_id: int
    athlete_name: str = Field(
        ...,
        description="Athlete's full name for display (first + last).",
    )
    status: RaceEventRosterStatus
    note: Optional[str] = None

    model_config = {"from_attributes": True}


class RosterReconciliation(BaseModel):
    """Computed discrepancies between the call-up roster and imported results.

    Both lists contain athlete IDs only (no names) to limit PII exposure in
    the API contract.  The frontend resolves names from its local athlete cache.

    - ``called_up_no_result``: athletes in the roster who have no matching
      ``race_results.athlete_id`` for the event (called up but did not appear
      in the official results — DNS, late withdrawal, or data gap).
    - ``result_not_called_up``: distinct ``athlete_id`` values found in
      non-deleted results for the event that are not in the roster (club
      athletes who raced but were not on the call-up list).
    """

    called_up_no_result: list[int] = Field(
        default_factory=list,
        description="Athlete IDs in roster with no race result for this event.",
    )
    result_not_called_up: list[int] = Field(
        default_factory=list,
        description="Athlete IDs with a result but not in the roster.",
    )


class RosterRead(BaseModel):
    """Full roster response for a competition, including reconciliation."""

    race_event_id: int
    entries: list[RosterEntryRead]
    reconciliation: RosterReconciliation

    model_config = {"from_attributes": True}
