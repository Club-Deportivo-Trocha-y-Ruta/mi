"""``POST /api/race-analysis/runs`` bloquea con 451 sin consentimiento IA
vigente (feature 037, T203 — spec §out-of-scope "AI-consent gate on POST
/runs (tracked separately, as in 036)" ya cerrado por esta tarea).

Mismo contrato que ``routers/ai.py::_ensure_ai_consent``: sin autorización
parental vigente para compartir datos con terceros (``third_party_sharing``),
el endpoint responde 451 y el grafo NUNCA se lanza (ni se inserta la fila
``agent_runs`` en estado consumible).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_start_run_returns_451_without_ai_consent(
    coach_client, ai_enabled, fake_db, fake_graph, monkeypatch
):
    from app.routers import race_analysis as router_mod

    async def _fake_no_consent(athlete_id: int, db) -> bool:
        return False

    monkeypatch.setattr(
        router_mod, "athlete_has_ai_processing_consent", _fake_no_consent
    )

    resp = await coach_client.post(
        "/api/race-analysis/runs",
        json={"athlete_id": 1, "season": 2026, "valida_nums": [1]},
    )

    assert resp.status_code == 451, resp.text
    assert len(fake_graph.invocations) == 0


async def test_start_run_launches_with_ai_consent_granted(
    coach_client, ai_enabled, fake_db, fake_graph, monkeypatch
):
    """Consentimiento vigente (True, comportamiento por defecto sin padres
    vinculados en la fixture) → 201, comportamiento normal sin cambios."""
    from app.routers import race_analysis as router_mod

    async def _fake_consent(athlete_id: int, db) -> bool:
        return True

    monkeypatch.setattr(
        router_mod, "athlete_has_ai_processing_consent", _fake_consent
    )

    resp = await coach_client.post(
        "/api/race-analysis/runs",
        json={"athlete_id": 1, "season": 2026, "valida_nums": [1]},
    )

    assert resp.status_code == 201, resp.text
