"""Schemas para el resumen del panel de mando del entrenador (coach home)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WeeklyLoadBandOut(BaseModel):
    age_band: Literal["10-12", "13-15"]
    planned_minutes: int
    cap_minutes: int
    athlete_count: int


class CoachSummaryOut(BaseModel):
    generated_at: datetime
    consents_pending: int | None
    insights_stale: int | None
    weekly_load: list[WeeklyLoadBandOut] | None
