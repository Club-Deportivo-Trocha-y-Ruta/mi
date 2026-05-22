"""Tests sentinela de privacidad para ``/api/athletes/{id}/race-analysis/*`` (BE-3).

Para cada endpoint, parseamos el JSON crudo de la respuesta y verificamos
recursivamente que NO contiene keys prohibidas:

- ``athlete_id`` (el cliente ya lo conoce por la URL).
- ``competitor_id`` (PK interna de ``race_competitors``).
- ``display_name`` (nombre real del atleta — los pseudónimos lo
  reemplazan).
- ``generated_by_user_id`` / ``requested_by_user_id`` (PK del coach que
  generó el insight/run).
- ``agent_run_id`` / PK BigInt interna de agent_runs.

El helper ``assert_no_keys_recursively`` baja por listas y dicts hasta
cualquier nivel — si algún campo está donde no debe, el test falla con
trace claro.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_user_to_club,
)


_AGENT_RUNS_FULL_DDL = """
CREATE TABLE agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id VARCHAR(64) NOT NULL UNIQUE,
    graph_name VARCHAR(64) NOT NULL,
    prompt_version VARCHAR(32) NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    input_json TEXT NOT NULL,
    final_output_json TEXT NULL,
    error_message TEXT NULL,
    langfuse_trace_id VARCHAR(128) NULL,
    requested_by_user_id INTEGER NOT NULL,
    checkpoint_thread_id VARCHAR(64) NOT NULL,
    explain_mode INTEGER NOT NULL DEFAULT 0,
    cost_usd NUMERIC NULL,
    athlete_id INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
)
"""


# ---------------------------------------------------------------------------
# Helper privacy validator
# ---------------------------------------------------------------------------


# Estas keys NO deben aparecer NUNCA en ningún payload público.
FORBIDDEN_KEYS_GLOBAL = {
    "athlete_id",
    "competitor_id",
    "display_name",
    "generated_by_user_id",
    "requested_by_user_id",
    "agent_run_id",
}


def assert_no_keys_recursively(
    payload: Any,
    forbidden: set[str],
    path: str = "$",
) -> None:
    """Recorre listas/dicts y falla si alguna key prohibida aparece a
    cualquier nivel del payload.

    Si encuentra una key prohibida, lanza AssertionError con el path
    completo (formato JSONPath) para facilitar el debug.
    """
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in forbidden:
                raise AssertionError(
                    f"Key prohibida '{k}' encontrada en {path}.{k} — payload={payload!r}"
                )
            assert_no_keys_recursively(v, forbidden, path=f"{path}.{k}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_keys_recursively(item, forbidden, path=f"{path}[{i}]")
    # Tipos primitivos (str, int, float, bool, None) — no recurse.


# ---------------------------------------------------------------------------
# Engine + seeded factory + client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "parent_athlete",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
            "athlete_ai_insights",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.exec_driver_sql(_AGENT_RUNS_FULL_DDL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(session_factory):
    """Seed: 1 club + 1 coach + 1 athlete con datos race + 1 insight + 1 run."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach)
        await link_user_to_club(
            s, user_id=10, club_id=1, role_in_club=ClubRole.coach
        )
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        await create_race_event(
            s,
            event_id=1,
            series_id=1,
            sequence_number=1,
            name="V1",
            event_date=date(2026, 1, 31),
        )
        # 5 corredores para que distribution devuelva puntos.
        await create_race_competitor(
            s, competitor_id=1001, normalized_name="winner", display_name="Winner Real"
        )
        await create_race_result(
            s,
            event_id=1,
            category_id=100,
            competitor_id=1001,
            position=1,
            race_time_ms=1_800_000,
            bib_number=1,
        )
        await create_race_competitor(
            s,
            competitor_id=1002,
            normalized_name="athlete",
            display_name="Athlete Real Name",
            athlete_id=144,
        )
        await create_race_result(
            s,
            event_id=1,
            category_id=100,
            competitor_id=1002,
            athlete_id=144,
            position=3,
            race_time_ms=1_810_000,
            bib_number=3,
        )
        for i, cid in enumerate([1003, 1004, 1005]):
            await create_race_competitor(
                s,
                competitor_id=cid,
                normalized_name=f"r{i}",
                display_name=f"Runner Real {i}",
            )
            await create_race_result(
                s,
                event_id=1,
                category_id=100,
                competitor_id=cid,
                position=4 + i,
                race_time_ms=1_815_000 + i * 1_000,
                bib_number=4 + i,
            )

        # Insight aprobado activo + run.
        await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
        )
        # 1 fila en agent_runs (raw SQL para que las columnas no mapeadas existan).
        from sqlalchemy import text

        await s.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, requested_by_user_id,
                    checkpoint_thread_id, explain_mode, athlete_id
                ) VALUES (
                    'run-x1', 'race-analyst', 'race_analyst_v1', :sa,
                    'completed', '{"season": 2026, "valida_nums": [1]}',
                    10, 'tid-x1', 0, 144
                )
                """
            ),
            {"sa": datetime.now(timezone.utc)},
        )
        await s.commit()
    return session_factory


def _coach() -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        first_name="Coach",
        last_name="Test",
        email="coach@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=1, role_in_club=ClubRole.coach)
        ],
    )


@pytest_asyncio.fixture
async def coach_client(seeded_factory):
    async def _override_db():
        async with seeded_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _coach
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insights_response_never_exposes_athlete_id_or_competitor_id(
    coach_client,
):
    resp = await coach_client.get(
        "/api/athletes/144/race-analysis/insights",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert_no_keys_recursively(body, FORBIDDEN_KEYS_GLOBAL)


@pytest.mark.asyncio
async def test_runs_response_never_exposes_requested_by_user_id_or_internal_pk(
    coach_client,
):
    resp = await coach_client.get(
        "/api/athletes/144/race-analysis/runs",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert_no_keys_recursively(body, FORBIDDEN_KEYS_GLOBAL)
    # ``id`` (PK interna del run) NO debe aparecer como key — el alias público
    # es ``run_id`` (UUID hex). Verificamos puntualmente.
    for item in body.get("items", []):
        assert "id" not in item
        assert "run_id" in item


@pytest.mark.asyncio
async def test_distribution_response_never_exposes_display_name_or_competitor_id(
    coach_client,
):
    resp = await coach_client.get(
        "/api/athletes/144/race-analysis/distribution",
        params={"season": 2026, "valida_num": 1},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert_no_keys_recursively(body, FORBIDDEN_KEYS_GLOBAL)
    # Y además: el string "Athlete Real Name" del seed NO debe aparecer en
    # ningún lado del JSON serializado.
    raw_text = resp.text
    assert "Athlete Real Name" not in raw_text
    assert "Runner Real" not in raw_text
    assert "Winner Real" not in raw_text


@pytest.mark.asyncio
async def test_evolution_response_only_exposes_aggregated_fields(coach_client):
    resp = await coach_client.get(
        "/api/athletes/144/race-analysis/evolution",
        params={"season": 2026, "metric": "podium_gap_ms"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert_no_keys_recursively(body, FORBIDDEN_KEYS_GLOBAL)
    # Cada punto de la serie debe tener exactamente estos campos: el contrato
    # cerrado de EvolutionPoint (extra="forbid") garantiza esto, pero acá
    # validamos también que no se haya leak-eado nada.
    expected_keys = {"valida_num", "event_id", "event_date", "value", "unit"}
    for point in body.get("series", []):
        assert set(point.keys()) <= expected_keys
