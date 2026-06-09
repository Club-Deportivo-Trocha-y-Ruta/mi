"""Pydantic v2 read schemas for the race results and season standings endpoints.

These schemas are intentionally read-only (no mutation paths here).  All
``display_name`` / ``club_text`` fields come from ``race_competitors`` which
was populated during PDF ingestion — they are **not** athlete PII (no DOB,
medical data, or minor's full legal name appears on results pages).

Privacidad Ley 1581:
- ``athlete_id`` is only included to let the frontend apply club-highlight
  logic; it is a numeric FK, not a name or identifying string.
- Parent-scoped responses are filtered in the service layer before the schema
  is ever constructed, so no cross-athlete rows reach this layer.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Per-event finishing order
# ---------------------------------------------------------------------------


class ResultRow(BaseModel):
    """One competitor's result in a single event / category."""

    position: Optional[int] = Field(
        None,
        description="Finishing position (1-based). None for DNF/DNS/DSQ.",
    )
    competitor_id: int
    display_name: str = Field(
        ...,
        description="Competitor name as it appeared in the official PDF.",
    )
    club_text: Optional[str] = Field(
        None,
        description="Club as printed in the PDF (raw, not normalized).",
    )
    athlete_id: Optional[int] = Field(
        None,
        description="FK to athletes.id when this competitor is a confirmed club athlete.",
    )
    is_our_club: bool = Field(
        ...,
        description="True when athlete_id is not None (confirmed Trocha y Ruta athlete).",
    )
    status: str = Field(..., description="Result status: finished/dnf/dns/dsq/minus_laps.")
    race_time_ms: Optional[int] = Field(
        None, description="Race time in milliseconds (only for 'finished' status)."
    )
    laps_behind: Optional[int] = Field(
        None, description="Laps behind the winner (only for 'minus_laps' status)."
    )
    points_awarded: int = Field(..., description="Points credited to the competitor.")
    bib_number: Optional[int] = Field(None, description="Race bib number.")

    model_config = {"from_attributes": True}


class CategoryResults(BaseModel):
    """All result rows for one category within an event."""

    category_id: int
    code: str = Field(..., description="Category code, e.g. 'INF_M'.")
    label: str = Field(..., description="Human-readable category label.")
    rows: list[ResultRow]


class EventResultsRead(BaseModel):
    """Full per-event finishing order grouped by category.

    Categories are ordered by ``RaceCategory.sort_order``; within each
    category rows are ordered by (position ASC NULLS LAST, competitor_id ASC).

    Event metadata fields allow the frontend to render a page header without
    a separate coach-only detail call (no minor PII included).
    """

    race_event_id: int
    event_name: str = Field(..., description="Official name of the race event.")
    event_date: date = Field(..., description="Date the race was held.")
    location: Optional[str] = Field(None, description="Municipality / venue of the race.")
    status: str = Field(..., description="RaceEventStatus value (scheduled/completed/cancelled).")
    categories: list[CategoryResults]


# ---------------------------------------------------------------------------
# Season standings
# ---------------------------------------------------------------------------


class StandingRow(BaseModel):
    """One competitor's cumulative standing for a series / season / category."""

    rank: int = Field(..., description="Rank within this category (1-based, by points DESC).")
    competitor_id: int
    display_name: str = Field(
        ...,
        description="Competitor name as it appeared in the official PDF.",
    )
    club_text: Optional[str] = None
    athlete_id: Optional[int] = Field(
        None,
        description="FK to athletes.id when confirmed as a club athlete.",
    )
    is_our_club: bool = Field(
        ...,
        description="True when athlete_id is not None.",
    )
    total_points: int = Field(..., description="Sum of points_awarded across all events.")
    races_run: int = Field(..., description="Number of events where this competitor finished.")
    podiums: int = Field(..., description="Number of top-3 finishes.")
    best_position: Optional[int] = Field(
        None, description="Best finishing position across the season."
    )


class CategoryStandings(BaseModel):
    """Ranked standings for one category within a series / season."""

    category_id: int
    code: str
    label: str
    rows: list[StandingRow]


class EventStandingsRead(BaseModel):
    """Season general standings scoped to the series of the given race event.

    Categories are ordered by ``RaceCategory.sort_order``; within each
    category rows are ordered by rank ASC (ties broken by podiums DESC,
    then best_position ASC).

    Event metadata fields allow the frontend to render a page header without
    a separate coach-only detail call (no minor PII included).
    """

    race_event_id: int
    event_name: str = Field(..., description="Official name of the anchor race event.")
    event_date: date = Field(..., description="Date the anchor race was held.")
    location: Optional[str] = Field(None, description="Municipality / venue of the anchor race.")
    status: str = Field(..., description="RaceEventStatus value of the anchor event.")
    series_id: int
    season_year: int
    categories: list[CategoryStandings]
