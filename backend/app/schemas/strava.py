"""Pydantic v2 schemas for the Strava activity sync module (feature 025).

Covers connection management, OAuth authorize-URL issuance, activity read
views (coach review list + athlete/session scoped), coach linking, session
suggestions, reconcile summaries, and the inbound webhook event payload.

Privacidad Ley 1581 / minors:
- ``ActivityOut`` NEVER includes coordinates, polylines, maps, or free-text
  location fields — only numeric/duration/HR summary metrics survive ingest
  (see ``services/strava/ingest.py`` stripping and ``models/strava_activity``
  which has no such columns at all).
- ``ReconcileResultOut`` is numeric-only (counts), never activity or athlete
  identifiers — it is returned to a machine caller (GitHub Actions), not a
  logged-in user.
- ``StravaWebhookEvent`` mirrors Strava's payload verbatim; it is consumed
  server-side only and never echoed back to a client.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConnectionStatusLiteral = Literal["active", "disconnected", "broken", "none"]
UpstreamStateLiteral = Literal["present", "removed_upstream"]


# ---------------------------------------------------------------------------
# A. Connection management
# ---------------------------------------------------------------------------


class ConnectionStatusOut(BaseModel):
    """Response for GET /api/athletes/{athlete_id}/strava/connection."""

    model_config = ConfigDict(from_attributes=True)

    status: ConnectionStatusLiteral
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    authorized_by: str | None = Field(
        default=None, description="Display name of the user who ran the connect flow."
    )
    last_sync_at: datetime | None = None


class AuthorizeUrlOut(BaseModel):
    """Response for POST /api/athletes/{athlete_id}/strava/connect."""

    authorize_url: str = Field(
        ..., description="Strava OAuth authorize URL with signed short-lived state."
    )


# ---------------------------------------------------------------------------
# C. Activities & linking
# ---------------------------------------------------------------------------


class ActivityLinkOut(BaseModel):
    """Nested link info embedded in ActivityOut when the activity is linked."""

    model_config = ConfigDict(from_attributes=True)

    training_session_id: int
    session_label: str = Field(
        ..., description="Human-readable label of the linked training session."
    )
    linked_by: str = Field(..., description="Display name of the linking coach/admin.")
    linked_at: datetime


class ActivityOut(BaseModel):
    """Read view of a Strava activity.

    NEVER includes coordinates, polylines, maps, or location text — only the
    fields listed below are ever populated (enforced by the privacy test
    asserting no such attribute exists on this schema or the response body).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    athlete_name: str
    name: str
    sport_type: str
    start_date_local: datetime
    elapsed_time_s: int
    moving_time_s: int | None = None
    distance_m: float | None = None
    total_elevation_gain_m: float | None = None
    average_heartrate: float | None = None
    max_heartrate: float | None = None
    is_trainer: bool
    upstream_state: UpstreamStateLiteral
    summary_complete: bool
    link: ActivityLinkOut | None = None


class ActivityListOut(BaseModel):
    """Paginated envelope for GET /api/activities and the athlete-scoped variant."""

    items: list[ActivityOut]
    total: int
    page: int
    page_size: int


class LinkUpdateIn(BaseModel):
    """Request body for PATCH /api/activities/{id}/link.

    ``training_session_id`` as an int links/re-links; ``None`` unlinks.
    """

    training_session_id: int | None = None


class SessionSuggestionOut(BaseModel):
    """One candidate training session for linking an activity (FR-008)."""

    model_config = ConfigDict(from_attributes=True)

    training_session_id: int
    scheduled_date: datetime
    session_kind: str | None = None
    location: str | None = None
    technical_focus: str | None = None
    same_day: bool
    athlete_in_attendance: bool


class SessionSuggestionListOut(BaseModel):
    """Response for GET /api/activities/{id}/session-suggestions."""

    suggestions: list[SessionSuggestionOut]


class SessionActivitiesOut(BaseModel):
    """Response for GET /api/training-sessions/{session_id}/activities."""

    items: list[ActivityOut]


# ---------------------------------------------------------------------------
# B. Machine endpoints
# ---------------------------------------------------------------------------


class ReconcileResultOut(BaseModel):
    """Response for POST /api/integrations/strava/reconcile.

    Numeric-only — no athlete/activity identifiers or PII (returned to a
    machine caller, not a logged-in user).
    """

    connections_processed: int
    activities_upserted: int
    connections_broken: int


class StravaWebhookEvent(BaseModel):
    """Inbound Strava webhook event payload (POST /api/integrations/strava/webhook).

    Field names mirror Strava's payload verbatim (snake_case, not aliased).
    """

    object_type: Literal["activity", "athlete"]
    aspect_type: Literal["create", "update", "delete"]
    object_id: int
    owner_id: int
    subscription_id: int
    event_time: int
    updates: dict[str, Any] = Field(default_factory=dict)
