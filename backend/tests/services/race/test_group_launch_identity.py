"""Unit tests: identidad de válida en ``group_launch`` (hotfix 2026-09-16).

Cubre directamente (sin pasar por HTTP):
- :func:`resolve_events_for_season_valida` — ambigüedad de
  ``(season, valida_num)`` entre copas.
- :func:`find_active_run` con ``event_id`` — no adoptar el run activo de
  OTRA copa que comparte ``sequence_number``.

Datos 100% ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services.race.group_launch import (
    find_active_run,
    resolve_events_for_season_valida,
)
from tests.fixtures.race_history_fixtures import create_race_event, create_race_series

pytestmark = pytest.mark.asyncio

_AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id TEXT NOT NULL UNIQUE,
    graph_name      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',
    input_json      TEXT,
    checkpoint_thread_id TEXT NOT NULL,
    explain_mode    INTEGER NOT NULL DEFAULT 0
)
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in ("race_series", "race_events")]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.execute(text(_AGENT_RUNS_DDL))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_two_cups_same_valida(session_factory) -> dict:
    """Copa A (series=1, event=100) y Copa B (series=2, event=200), ambas Válida 4."""
    async with session_factory() as s:
        await create_race_series(s, series_id=1, season_year=2026, name="Copa A Test")
        await create_race_series(s, series_id=2, season_year=2026, name="Copa B Test")
        await create_race_event(
            s, event_id=100, series_id=1, sequence_number=4, name="Copa A V4"
        )
        await create_race_event(
            s, event_id=200, series_id=2, sequence_number=4, name="Copa B V4"
        )
        await s.commit()
    return {"event_a": 100, "event_b": 200}


async def _seed_run(
    session_factory,
    *,
    external_run_id: str,
    athlete_id: int,
    valida_nums: list[int],
    event_id: int | None,
    season: int = 2026,
) -> None:
    payload: dict = {
        "athlete_id": athlete_id,
        "season": season,
        "valida_nums": valida_nums,
        "explain_mode": False,
    }
    if event_id is not None:
        payload["event_id"] = event_id
    async with session_factory() as s:
        await s.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, checkpoint_thread_id
                ) VALUES (:rid, 'race-analyst', 'race_analyst_v3', :sa, 'running', :inp, :rid)
                """
            ),
            {
                "rid": external_run_id,
                "sa": _utc_now(),
                "inp": json.dumps(payload),
            },
        )
        await s.commit()


class TestResolveEventsForSeasonValida:
    async def test_unambiguous_single_cup(self, session_factory):
        await _seed_two_cups_same_valida(session_factory)
        async with session_factory() as s:
            ids = await resolve_events_for_season_valida(s, 2026, 4)
        # Dos copas comparten Válida 4 en la misma temporada → ambiguo.
        assert sorted(ids) == [100, 200]

    async def test_no_match_returns_empty(self, session_factory):
        await _seed_two_cups_same_valida(session_factory)
        async with session_factory() as s:
            ids = await resolve_events_for_season_valida(s, 2026, 99)
        assert ids == []


class TestFindActiveRunEventIdentity:
    async def test_run_with_matching_event_id_is_found(self, session_factory):
        await _seed_two_cups_same_valida(session_factory)
        await _seed_run(
            session_factory,
            external_run_id="run-b",
            athlete_id=7,
            valida_nums=[4],
            event_id=200,
        )
        async with session_factory() as s:
            found = await find_active_run(s, 7, 2026, 4, event_id=200)
        assert found == "run-b"

    async def test_run_with_different_event_id_is_not_adopted(self, session_factory):
        """Copa A V4 activo no debe "bloquear" un lanzamiento de Copa B V4."""
        await _seed_two_cups_same_valida(session_factory)
        await _seed_run(
            session_factory,
            external_run_id="run-a",
            athlete_id=7,
            valida_nums=[4],
            event_id=100,
        )
        async with session_factory() as s:
            found = await find_active_run(s, 7, 2026, 4, event_id=200)
        assert found is None

    async def test_legacy_run_without_event_id_ambiguous_not_adopted(
        self, session_factory
    ):
        """Run legado (pre-hotfix, sin event_id) + válida ambigua → nunca match."""
        await _seed_two_cups_same_valida(session_factory)
        await _seed_run(
            session_factory,
            external_run_id="run-legacy",
            athlete_id=7,
            valida_nums=[4],
            event_id=None,
        )
        async with session_factory() as s:
            found = await find_active_run(s, 7, 2026, 4, event_id=200)
        assert found is None

    async def test_legacy_run_without_event_id_unambiguous_is_adopted(
        self, session_factory
    ):
        """Run legado sin event_id, pero (season, valida_num) único → sí adopta."""
        await _seed_two_cups_same_valida(session_factory)
        await _seed_run(
            session_factory,
            external_run_id="run-legacy-solo",
            athlete_id=8,
            valida_nums=[99],  # sin ambigüedad: ningún otro evento usa el 99.
            event_id=None,
        )
        async with session_factory() as s:
            # No hay ningún evento sequence_number=99 sembrado → 0 candidatos,
            # así que sigue sin adoptar (0 != 1). Sembramos uno para el caso
            # verdaderamente unívoco.
            await create_race_event(
                s, event_id=300, series_id=1, sequence_number=99, name="Cto Dep"
            )
            await s.commit()
            found = await find_active_run(s, 8, 2026, 99, event_id=300)
        assert found == "run-legacy-solo"

    async def test_without_event_id_kwarg_keeps_legacy_behavior(self, session_factory):
        """Callers que no pasan event_id (ej. athlete_race_analysis.py) no cambian."""
        await _seed_two_cups_same_valida(session_factory)
        await _seed_run(
            session_factory,
            external_run_id="run-a-legacy-caller",
            athlete_id=9,
            valida_nums=[4],
            event_id=100,
        )
        async with session_factory() as s:
            found = await find_active_run(s, 9, 2026, 4)
        assert found == "run-a-legacy-caller"
