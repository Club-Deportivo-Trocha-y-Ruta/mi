"""Tests de regresión v1 — la incorporación de v2 NO debe romper v1.

Contratos a defender:

- Insights con ``prompt_version=race_analyst_v1`` persistidos siguen
  siendo legibles por el listado ``GET /api/athletes/{id}/race-analysis/insights``.
- El schema de response v1 no cambia (no se agregan campos requeridos
  que rompan clientes existentes; los campos opcionales que aparezcan
  para v2 deben ser opcionales o tener default).
- ``valida_num`` puede ser 0 (sentinel agregado) — no debe filtrarse.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

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
from app.schemas.athlete_race_analysis import AthleteInsightOut

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
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
async def seeded_v1_factory(session_factory):
    """Seed: 1 athlete + 3 insights v1 + 1 insight v2 (mixto)."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach, email="c@t.com")
        await link_user_to_club(
            s, user_id=10, club_id=1, role_in_club=ClubRole.coach
        )
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)

        # 3 v1 insights aprobados activos.
        for valida in (1, 2, 3):
            await create_insight(
                s,
                athlete_id=144,
                season=2026,
                valida_num=valida,
                prompt_version="race_analyst_v1",
                coach_approved=True,
                is_active=1,
            )
        # 1 v2 insight aprobado activo (coexiste).
        await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=4,
            prompt_version="race_analyst_v2",
            coach_approved=True,
            is_active=1,
            summary_text="## Qué pasó\nVálida 4 análisis v2.",
        )

        await s.commit()
    return session_factory


def _make_user(user_id: int, role: UserRole) -> SimpleNamespace:
    cm = SimpleNamespace(
        club_id=1,
        role_in_club=ClubRole.coach if role == UserRole.coach else ClubRole.parent,
    )
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"u{user_id}@test.com",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[cm],
    )


@pytest_asyncio.fixture
async def client_factory(seeded_v1_factory):
    def _build(user: SimpleNamespace):
        async def _override_db():
            async with seeded_v1_factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _build
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Listado mixto v1 + v2
# ---------------------------------------------------------------------------


async def test_list_insights_includes_both_v1_and_v2(client_factory):
    """El listado debe retornar v1 y v2 indistintamente."""
    coach = _make_user(10, UserRole.coach)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            params={"latest_only": "false", "limit": 100},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    versions = {item["prompt_version"] for item in body["items"]}
    assert "race_analyst_v1" in versions
    assert "race_analyst_v2" in versions


async def test_v1_insight_schema_unchanged(client_factory):
    """El response de un insight v1 sigue cumpliendo el schema completo."""
    coach = _make_user(10, UserRole.coach)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            params={"latest_only": "false", "limit": 100},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    v1_items = [
        item for item in body["items"] if item["prompt_version"] == "race_analyst_v1"
    ]
    assert len(v1_items) >= 1
    # Validar contra el schema Pydantic — falla si se agregaron campos required.
    for raw in v1_items:
        parsed = AthleteInsightOut.model_validate(raw)
        assert parsed.prompt_version == "race_analyst_v1"
        assert parsed.is_active is True


# ---------------------------------------------------------------------------
# Detalle v1 sigue funcionando
# ---------------------------------------------------------------------------


async def test_v1_insight_detail_endpoint_still_serves(
    seeded_v1_factory, client_factory
):
    """GET /insights/{id} sigue retornando v1 con la misma forma."""
    from sqlalchemy import select
    from app.models.athlete_ai_insight import AthleteAiInsight

    async with seeded_v1_factory() as s:
        rows = await s.execute(
            select(AthleteAiInsight).where(
                AthleteAiInsight.athlete_id == 144,
                AthleteAiInsight.prompt_version == "race_analyst_v1",
            )
        )
        v1_row = list(rows.scalars().all())[0]
        v1_id = v1_row.id

    coach = _make_user(10, UserRole.coach)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{v1_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prompt_version"] == "race_analyst_v1"
    # Estructura legacy: estos campos siempre presentes.
    assert "summary_text" in body
    assert "recommendations" in body
    assert "metrics_snapshot" in body


# ---------------------------------------------------------------------------
# Filtros sobre prompt_version (si se agregan) son opcionales
# ---------------------------------------------------------------------------


async def test_list_insights_no_prompt_version_filter_returns_mixed(client_factory):
    """Sin filtro explícito de prompt_version, el listado mezcla v1 y v2."""
    coach = _make_user(10, UserRole.coach)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            params={"latest_only": "false", "limit": 100},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # Default no filtra por prompt_version → ambos.
    assert body["total"] >= 4
