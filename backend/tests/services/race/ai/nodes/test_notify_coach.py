"""Tests del nodo notify_coach."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.notify_coach import notify_coach


@pytest.mark.asyncio
async def test_notify_log_only_when_disabled(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")
    update = await notify_coach({"coach_id": 1, "athlete_id": 2, "run_id": "r"})
    assert update["notified"] is False


@pytest.mark.asyncio
async def test_notify_marks_when_enabled(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "true")
    update = await notify_coach({"coach_id": 1, "athlete_id": 2, "run_id": "r"})
    assert update["notified"] is True
