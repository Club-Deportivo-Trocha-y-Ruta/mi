"""Tests v3 — endpoint ``POST /api/athletes/{id}/race-analysis/season-summary``.

Contratos vigentes (feature 037, T203):

- El endpoint YA NO invoca el LLM de forma síncrona: lanza un run agéntico
  (``analysis_kind="season"``) sobre el mismo grafo LangGraph que
  ``POST /runs`` — el cliente hace polling de
  ``GET /api/race-analysis/runs/{run_id}/status``. Persistencia final queda
  a cargo de los nodos del grafo (``persist_insight``), no de este endpoint.
- 422 si el atleta tiene <3 válidas analizadas en la temporada (mismo guard
  que v2, evaluado ANTES de lanzar el run).
- 202 si ≥3 válidas analizadas, ``ai_enabled`` y consentimiento IA vigente.
- 451 si el atleta NO tiene consentimiento parental vigente para
  procesamiento con IA (Ley 1581 art. 9).
- Solo coach/admin pueden invocarlo (parent → 403).

Reusa la fixture SQLite in-memory de la versión anterior de este archivo
(seed de club/atleta/insights vía ``tests.fixtures.race_history_fixtures``).
"""

from __future__ import annotations

from datetime import date
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

from app.config import settings
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
    create_race_event,
    create_race_series,
    create_user,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Fixtures locales — DB + auth override
# ---------------------------------------------------------------------------


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


async def _seed_athlete_with_n_insights(
    session_factory: async_sessionmaker[AsyncSession],
    n_insights: int,
    *,
    athlete_id: int = 144,
    season: int = 2026,
) -> None:
    """Helper: siembra atleta + N insights aprobados activos para temporada."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach, email="c@t.com")
        await link_user_to_club(
            s, user_id=10, club_id=1, role_in_club=ClubRole.coach
        )
        await create_user(s, user_id=20, role=UserRole.parent, email="p@t.com")
        await create_user(
            s, user_id=athlete_id, role=UserRole.athlete, can_login=False
        )
        await create_athlete(s, athlete_id=athlete_id, club_id=1, user_id=athlete_id)
        await create_race_series(s, series_id=1, season_year=season)
        await create_race_category(s, category_id=100, code="INF_B")
        for valida in range(1, n_insights + 1):
            await create_race_event(
                s,
                event_id=valida,
                series_id=1,
                sequence_number=valida,
                name=f"V{valida}",
                event_date=date(season, 1, 31),
            )
            await create_insight(
                s,
                athlete_id=athlete_id,
                season=season,
                valida_num=valida,
                coach_approved=True,
                is_active=1,
            )
        await s.commit()


def _make_user(
    user_id: int, role: UserRole, club_id: int | None = 1
) -> SimpleNamespace:
    cm = (
        SimpleNamespace(
            club_id=club_id,
            role_in_club=(
                ClubRole.coach if role == UserRole.coach
                else ClubRole.admin if role == UserRole.admin
                else ClubRole.parent
            ),
        )
        if club_id is not None
        else None
    )
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"u{user_id}@test.com",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[cm] if cm else [],
    )


@pytest_asyncio.fixture
async def client_factory(session_factory):
    def _build(user: SimpleNamespace):
        async def _override_db():
            async with session_factory() as s:
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


URL = "/api/athletes/144/race-analysis/season-summary"


def _stub_graph_launch(monkeypatch) -> list[dict[str, Any]]:
    """Mockea ``submit_run``/``check_budget`` — no dispara el grafo real.

    Retorna la lista donde se acumulan los ``initial_state`` de cada
    lanzamiento, para que los tests inspeccionen qué se le pasó al grafo.
    """
    from app.routers import athlete_race_analysis as router_mod

    captured: list[dict[str, Any]] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        captured.append({"run_id": run_id, "initial_state": initial_state})

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    return captured


# ---------------------------------------------------------------------------
# 422 — menos de 3 válidas analizadas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_summary_returns_422_with_less_than_3_validas(
    session_factory, client_factory, monkeypatch
):
    """Solo 2 válidas analizadas → 422 (se evalúa ANTES de lanzar el run)."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    _stub_graph_launch(monkeypatch)
    await _seed_athlete_with_n_insights(session_factory, n_insights=2)

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 202 — con 3+ válidas, flag ON y consentimiento por defecto (sin padres
# vinculados == autorizado, ver app.services.privacy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_summary_success_with_3_validas_launches_run(
    session_factory, client_factory, monkeypatch
):
    """3 válidas + flag ON → 202, devuelve run_id y lanza el grafo con
    analysis_kind='season', valida_nums=None y el prompt_version v3."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    captured = _stub_graph_launch(monkeypatch)
    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "run_id" in body and body["run_id"]
    assert body["status"] == "running"

    assert len(captured) == 1
    initial_state = captured[0]["initial_state"]
    assert initial_state["athlete_id"] == 144
    assert initial_state["analysis_kind"] == "season"
    assert initial_state["valida_nums"] is None
    assert initial_state["prompt_version"] == "race_season_summary_v3"
    assert captured[0]["run_id"] == body["run_id"]


# ---------------------------------------------------------------------------
# 403 — RBAC: parent NO puede invocar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_summary_parent_forbidden(
    session_factory, client_factory, monkeypatch
):
    """Parent intentando lanzar resumen de temporada → 403."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    _stub_graph_launch(monkeypatch)
    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 202 — admin también puede
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_summary_admin_allowed(
    session_factory, client_factory, monkeypatch
):
    """Admin tiene acceso (coach/admin only)."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    _stub_graph_launch(monkeypatch)
    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    admin = _make_user(99, UserRole.admin, club_id=1)
    async with client_factory(user=admin) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# 451 — sin consentimiento parental vigente (Ley 1581 art. 9, feature 037)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_summary_returns_451_without_ai_consent(
    session_factory, client_factory, monkeypatch
):
    """Atleta sin consentimiento IA vigente → 451, el grafo nunca se lanza."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    captured = _stub_graph_launch(monkeypatch)
    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    from app.routers import athlete_race_analysis as router_mod

    async def _fake_no_consent(athlete_id: int, db) -> bool:
        return False

    monkeypatch.setattr(
        router_mod, "athlete_has_ai_processing_consent", _fake_no_consent
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 451, resp.text
    assert not captured, "El run no debe lanzarse sin consentimiento vigente"


@pytest.mark.asyncio
async def test_season_summary_launches_with_consent_granted(
    session_factory, client_factory, monkeypatch
):
    """Consentimiento vigente explícito (True) → 202, comportamiento normal."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    captured = _stub_graph_launch(monkeypatch)
    await _seed_athlete_with_n_insights(session_factory, n_insights=3)

    from app.routers import athlete_race_analysis as router_mod

    async def _fake_consent(athlete_id: int, db) -> bool:
        return True

    monkeypatch.setattr(
        router_mod, "athlete_has_ai_processing_consent", _fake_consent
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    assert resp.status_code == 202, resp.text
    assert len(captured) == 1
