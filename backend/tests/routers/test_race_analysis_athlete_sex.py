"""``POST /api/race-analysis/runs`` inyecta ``athlete_sex``/``analysis_kind``
en el ``initial_state`` del grafo (feature 037, T101 — spec §problem 7).
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.asyncio


class _FakeAthleteRow:
    """Row-like que imita ``select(Athlete)`` con ``sex`` como enum-like."""

    def __init__(self, athlete_id: int, sex_value: str | None, birth_date=None):
        from types import SimpleNamespace

        self.id = athlete_id
        self.birth_date = birth_date
        self.nickname = None
        self.sex = SimpleNamespace(value=sex_value) if sex_value else None

    def scalar_one_or_none(self):
        return self


class _EmptyAthleteResult:
    def scalar_one_or_none(self):
        return None


def _patch_athlete_select(fake_db, athlete_row):
    """Enseña a ``FakeSession.execute`` a responder ``select(Athlete)...``.

    ``FakeSession`` (tests/routers/conftest.py) dispatcha por substring del
    SQL — no tiene entrada para ``athletes`` porque el módulo no lo
    necesitaba antes de T101. Envolvemos ``execute`` para interceptar SOLO
    esa consulta y delegar el resto al comportamiento original.
    """
    original_execute = fake_db.execute

    async def _patched_execute(stmt, params=None):
        sql = getattr(stmt, "text", None) or str(stmt)
        if "FROM athletes" in sql:
            return athlete_row if athlete_row is not None else _EmptyAthleteResult()
        return await original_execute(stmt, params)

    fake_db.execute = _patched_execute


class TestStartRunAthleteSex:
    async def test_start_run_injects_athlete_sex_male(
        self, coach_client, ai_enabled, fake_db, fake_graph
    ):
        _patch_athlete_select(fake_db, _FakeAthleteRow(athlete_id=1, sex_value="M"))

        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": [1]},
        )
        assert resp.status_code == 201
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(fake_graph.invocations) == 1
        initial_state = fake_graph.invocations[0][0]
        assert initial_state["athlete_sex"] == "M"
        assert initial_state["analysis_kind"] == "valida"

    async def test_start_run_injects_athlete_sex_female(
        self, coach_client, ai_enabled, fake_db, fake_graph
    ):
        _patch_athlete_select(fake_db, _FakeAthleteRow(athlete_id=1, sex_value="F"))

        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": [1]},
        )
        assert resp.status_code == 201
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        initial_state = fake_graph.invocations[0][0]
        assert initial_state["athlete_sex"] == "F"

    async def test_start_run_athlete_sex_none_when_athlete_not_found(
        self, coach_client, ai_enabled, fake_db, fake_graph
    ):
        _patch_athlete_select(fake_db, None)

        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 999, "season": 2026, "valida_nums": [1]},
        )
        assert resp.status_code == 201
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        initial_state = fake_graph.invocations[0][0]
        assert initial_state["athlete_sex"] is None

    async def test_start_run_accepts_explicit_analysis_kind_season(
        self, coach_client, ai_enabled, fake_db, fake_graph
    ):
        _patch_athlete_select(fake_db, _FakeAthleteRow(athlete_id=1, sex_value="M"))

        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={
                "athlete_id": 1,
                "season": 2026,
                "valida_nums": [1],
                "analysis_kind": "season",
            },
        )
        assert resp.status_code == 201
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        initial_state = fake_graph.invocations[0][0]
        assert initial_state["analysis_kind"] == "season"

    async def test_start_run_rejects_invalid_analysis_kind(self, coach_client, ai_enabled):
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "analysis_kind": "bogus"},
        )
        assert resp.status_code == 422
