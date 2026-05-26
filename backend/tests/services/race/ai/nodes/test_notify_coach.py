"""Tests del nodo notify_coach.

Contrato actual (post Family Relations track, 2026-05-25)
=========================================================
``notified`` ahora refleja si el dispatcher procesó al menos 1 insight,
no si "el nodo corrió". Casos:

- Sin ``persisted_insight_ids`` en el state ⇒ ``notified=False``,
  ``insights_dispatched=0``.
- ``insight_approved=False`` ⇒ ``notified=False`` (no se dispatchea).
- ``NOTIFICATION_SEND_EMAILS=false`` ⇒ el nodo sigue ejecutando in-app
  (logs) pero los emails se cortocircuitan en ``NotificationService``.

La lógica de "qué insight genera email" vive en
:mod:`app.services.notification.race_insight_dispatcher` — este nodo es
solo el cableador.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.notify_coach import notify_coach


@pytest.mark.asyncio
async def test_notify_log_only_when_disabled(monkeypatch):
    """Con flag OFF y state vacío, el nodo loggea pero no dispatcha."""
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")
    update = await notify_coach({"coach_id": 1, "athlete_id": 2, "run_id": "r"})
    assert update["notified"] is False
    assert update["insights_dispatched"] == 0


@pytest.mark.asyncio
async def test_notify_skips_when_no_persisted_ids(monkeypatch):
    """Sin insights persistidos en el state, no hay nada que dispatchear."""
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "true")
    update = await notify_coach({"coach_id": 1, "athlete_id": 2, "run_id": "r"})
    assert update["notified"] is False
    assert update["insights_dispatched"] == 0


@pytest.mark.asyncio
async def test_notify_skips_when_not_approved(monkeypatch):
    """Aún con persisted_ids, si insight_approved=False (rejected/draft), no dispatcha."""
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "true")
    update = await notify_coach(
        {
            "coach_id": 1,
            "athlete_id": 2,
            "run_id": "r",
            "persisted_insight_ids": [101, 102],
            "insight_approved": False,
        }
    )
    assert update["notified"] is False
    assert update["insights_dispatched"] == 0


@pytest.mark.asyncio
async def test_notify_dispatches_when_approved(monkeypatch):
    """Con approved=True + persisted_ids, llama al dispatcher por cada insight.

    Mockeamos ``_dispatch_for_persisted_insights`` para no requerir DB real.
    """
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "true")

    async def _fake_dispatch(state):
        return len(state.get("persisted_insight_ids") or [])

    from app.services.race.ai.nodes import notify_coach as module

    monkeypatch.setattr(module, "_dispatch_for_persisted_insights", _fake_dispatch)

    update = await notify_coach(
        {
            "coach_id": 1,
            "athlete_id": 2,
            "run_id": "r",
            "persisted_insight_ids": [101, 102, 103],
            "insight_approved": True,
        }
    )
    assert update["notified"] is True
    assert update["insights_dispatched"] == 3
