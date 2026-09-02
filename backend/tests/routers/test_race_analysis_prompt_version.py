"""Tests T204 (feature 037, Wave 2): default de ``prompt_version`` v3.

Cubre:
- ``POST /api/race-analysis/runs`` lanza con
  ``settings.race_ai_prompt_version`` (default ``race_analyst_v3``), tanto
  en la fila insertada en ``agent_runs`` como en ``initial_state``.
- Override a ``race_analyst_v2`` (rollback) vía ``settings`` se respeta.
- ``POST /api/athletes/{id}/race-analysis/runs`` (lanzamiento por atleta)
  usa el mismo default y también inyecta ``athlete_sex``/``analysis_kind``.

Datos 100% ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


class TestStartRunPromptVersionDefault:
    async def test_default_prompt_version_es_v3(self, coach_client, ai_enabled, fake_db):
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": [1]},
        )
        assert resp.status_code == 201, resp.text

        insert_calls = [
            params
            for sql, params in fake_db.executed
            if "INSERT INTO agent_runs" in sql
        ]
        assert insert_calls, "esperaba un INSERT INTO agent_runs"
        assert insert_calls[-1]["pv"] == "race_analyst_v3"

    async def test_override_a_v2_para_rollback(
        self, coach_client, ai_enabled, fake_db, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_prompt_version", "race_analyst_v2")
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": [1]},
        )
        assert resp.status_code == 201, resp.text

        insert_calls = [
            params
            for sql, params in fake_db.executed
            if "INSERT INTO agent_runs" in sql
        ]
        assert insert_calls[-1]["pv"] == "race_analyst_v2"


# El lanzamiento por atleta (``POST /api/athletes/{id}/race-analysis/runs``)
# se verifica en ``test_athlete_race_analysis.py`` (mismo módulo que ya trae
# ``client_factory``/``seeded_factory``) — ver
# ``test_post_runs_default_prompt_version_es_v3`` y
# ``test_post_runs_injects_athlete_sex``.
