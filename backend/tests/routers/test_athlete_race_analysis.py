"""Tests de integración del router ``/api/athletes/{id}/race-analysis/*`` (BE-3).

Cobertura:

- ``GET /insights`` — coach mismo club, coach cross-club (403), parent
  hijo propio, parent hijo ajeno (403).
- ``GET /insights/{id}`` — supersedes chain incluida; parent 404 cuando
  no es activa.
- ``GET /runs`` — coach 200; parent 403.
- ``POST /runs`` — coach inyecta athlete_id desde el path; parent 403;
  schema validation (season < 2020 → 422).
- ``GET /distribution`` — sentinel privacidad: pseudónimos, no
  display_name ni competitor_id.
- ``GET /evolution`` — series ordenada por valida_num.

Estrategia: SQLite async in-memory real con override de
``get_db``/``get_current_user``. Stub del runner (no LangGraph real).
"""
from __future__ import annotations

import json
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

from app.config import settings
from app.dependencies import get_current_user, get_db, verify_athlete_access
from app.main import app
from app.models import Base
from app.models.athlete import Athlete
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
    link_parent_to_athlete,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Engine + DB / app overrides
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
    # NO incluimos agent_runs aquí: el modelo ORM tiene un subset de columnas
    # (input_json, final_output_json, etc. NO están mapeadas) y el router
    # accede vía SQL crudo. Creamos la tabla completa con DDL custom.
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
            "anthropometric_records",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        # Crear agent_runs con DDL custom que matchea el schema productivo.
        await conn.exec_driver_sql(_AGENT_RUNS_FULL_DDL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(
    session_factory,
) -> async_sessionmaker[AsyncSession]:
    """Seed: club1 + coach (en club1) + coach2 (en club2) + parent + 2 athletes."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_club(s, club_id=2, code="club2")
        # Coach 10 está en club 1.
        await create_user(s, user_id=10, role=UserRole.coach, email="coach1@test.com")
        await link_user_to_club(
            s, user_id=10, club_id=1, role_in_club=ClubRole.coach
        )
        # Coach 11 está en club 2 (no en club 1).
        await create_user(s, user_id=11, role=UserRole.coach, email="coach2@test.com")
        await link_user_to_club(
            s, user_id=11, club_id=2, role_in_club=ClubRole.coach
        )
        # Parent
        await create_user(s, user_id=20, role=UserRole.parent, email="parent@test.com")
        # Athletes (cada uno con su user separado)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_user(s, user_id=145, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_athlete(
            s,
            athlete_id=145,
            club_id=1,
            user_id=145,
            first_name="Otro",
            last_name="Atleta",
        )
        # Parent 20 es padre de athlete 144 (NO de 145).
        await link_parent_to_athlete(s, parent_user_id=20, athlete_id=144)
        # Datos de race para evolution / distribution
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        # 1 evento con 5 corredores (suficiente para distribution n=5).
        await create_race_event(
            s,
            event_id=1,
            series_id=1,
            sequence_number=1,
            name="V1",
            event_date=date(2026, 1, 31),
        )
        # Ganador
        await create_race_competitor(
            s,
            competitor_id=1001,
            normalized_name="winner",
            display_name="Winner Test",
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
        # Atleta 144 P3
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
        # 3 runners más
        for i, cid in enumerate([1003, 1004, 1005]):
            await create_race_competitor(
                s,
                competitor_id=cid,
                normalized_name=f"runner{i}",
                display_name=f"Runner Real{i}",
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

        # Insights: 1 activo aprobado, 1 deprecada, 1 archivada para athlete 144.
        now = datetime.now(timezone.utc)
        active_insight = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
        )
        deprecated_insight = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=2,
            coach_approved=True,
            is_active=None,
            deprecated_at=now,
        )

        await s.commit()
    return session_factory


def _make_user(user_id: int, role: UserRole, club_id: int | None = 1) -> SimpleNamespace:
    """Helper local — independiente de la sesión DB para los overrides."""
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
async def client_factory(seeded_factory):
    """Devuelve una función para construir un cliente con auth override.

    Uso::

        async with client_factory(user=coach_user) as ac:
            await ac.get(...)
    """

    def _build(user: SimpleNamespace):
        async def _override_db():
            async with seeded_factory() as s:
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
# GET /insights — RBAC + filtros
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_insights_as_coach_same_club_returns_200_filtered_active(
    client_factory,
):
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # Solo el insight activo (latest_only=True por default).
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["is_active"] is True


@pytest.mark.asyncio
async def test_get_insights_as_coach_cross_club_returns_403(client_factory):
    """Coach 11 está en club 2; athlete 144 está en club 1 → 403."""
    coach_cross = _make_user(11, UserRole.coach, club_id=2)
    async with client_factory(user=coach_cross) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_insights_as_parent_own_child_returns_200_forced_active_only(
    client_factory,
):
    """Parent 20 es padre de 144; aunque pase include_deprecated=true el router
    lo fuerza a False."""
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            params={"include_deprecated": "true", "latest_only": "false"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # Parent NO debe ver deprecadas aunque haya pedido include_deprecated=true.
    for item in body["items"]:
        assert item["deprecated_at"] is None


@pytest.mark.asyncio
async def test_get_insights_as_parent_other_child_returns_403(client_factory):
    """Parent 20 NO es padre de 145 → 403."""
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/145/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /insights/{id} — detail + supersedes chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_insight_detail_includes_supersedes_chain(
    seeded_factory, client_factory
):
    """Detalle expone la cadena ``supersedes`` con insights anteriores."""
    # Setup: encadenar deprecated → active.
    async with seeded_factory() as s:
        from sqlalchemy import select
        from app.models.athlete_ai_insight import AthleteAiInsight

        rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.athlete_id == 144)
        )
        all_insights = list(rows.scalars().all())
        active = next(i for i in all_insights if i.is_active == 1)
        deprecated = next(i for i in all_insights if i.deprecated_at is not None)
        # Encadenar: deprecated.superseded_by_insight_id = active.id
        deprecated.superseded_by_insight_id = active.id
        await s.commit()
        active_id = active.id

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{active_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # supersedes incluye al menos al deprecated previo.
    assert len(body["supersedes"]) >= 1


@pytest.mark.asyncio
async def test_get_insight_detail_parent_404_when_not_active(
    seeded_factory, client_factory
):
    """Padre intentando ver insight deprecado/archivado → 404 (no oracle 403)."""
    async with seeded_factory() as s:
        from sqlalchemy import select
        from app.models.athlete_ai_insight import AthleteAiInsight

        rows = await s.execute(
            select(AthleteAiInsight)
            .where(AthleteAiInsight.athlete_id == 144)
            .where(AthleteAiInsight.deprecated_at.is_not(None))
        )
        deprecated = rows.scalar_one()
        deprecated_id = deprecated.id

    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{deprecated_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /runs — RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_runs_as_coach_returns_200(client_factory):
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/runs",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_get_runs_as_parent_returns_403(client_factory):
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/runs",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /runs — inyecta athlete_id + RBAC + validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_runs_as_coach_inyects_athlete_id(
    client_factory, monkeypatch
):
    """El body NO trae athlete_id; el router lo inyecta del path.

    Mockeamos submit_run y check_budget para no disparar el grafo real.
    Verificamos que la fila agent_runs creada tiene ``athlete_id=144``.
    """
    # Mockear submit_run para que no haga IO real.
    from app.services.race.ai import runner as runner_mod
    from app.routers import athlete_race_analysis as router_mod
    from app.services.race.ai import budget_guard as guard_mod

    submit_calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        submit_calls.append((run_id, initial_state, on_complete))
        # Nada más.

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    # AI_ENABLED true para el test.
    monkeypatch.setattr(settings, "ai_enabled", True)

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {
        "season": 2026,
        "valida_nums": [1, 2],
        "explain_mode": False,
    }
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    assert len(submit_calls) == 1
    rid, initial_state, _on_complete = submit_calls[0]
    # El estado inicial contiene athlete_id inyectado del path.
    assert initial_state["athlete_id"] == 144
    assert initial_state["season"] == 2026


@pytest.mark.asyncio
async def test_post_runs_injects_ltad_and_maturation(client_factory, monkeypatch):
    """Feature 011 US2: initial_state carries real ltad_group + maturation_status.

    On unfixed code these keys were never injected → analyst defaulted to
    Pre-PHV/Bambino for everyone. Athlete 144 was born 2014 → bambino; no
    anthropometric record table here → maturation_status is None (no default).
    """
    from app.routers import athlete_race_analysis as router_mod

    submit_calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        submit_calls.append((run_id, initial_state, on_complete))

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    monkeypatch.setattr(settings, "ai_enabled", True)

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [1, 2], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    _, initial_state, _ = submit_calls[0]
    assert initial_state["ltad_group"] == "bambino"
    assert "maturation_status" in initial_state
    assert initial_state["maturation_status"] is None
    # Privacy (feature 011): forbidden_names injected so weather_notes scrubbing
    # is not a no-op in the graph path.
    assert "forbidden_names" in initial_state
    assert isinstance(initial_state["forbidden_names"], list)


@pytest.mark.asyncio
async def test_post_runs_as_parent_returns_403(client_factory):
    parent = _make_user(20, UserRole.parent, club_id=None)
    body = {"season": 2026, "valida_nums": [1], "explain_mode": False}
    async with client_factory(user=parent) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_runs_with_season_lt_2020_returns_422(client_factory):
    """Schema valida season ≥ 2020."""
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json={"season": 1990, "valida_nums": None, "explain_mode": False},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /distribution — pseudonimización
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_distribution_coach_receives_display_name(client_factory):
    """Coach recibe display_name poblado; competitor_id nunca viaja al cliente."""
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/distribution",
            params={"season": 2026, "event_id": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    # 5 corredores seedeados.
    assert body["sample_size"] == 5
    # competitor_id nunca viaja.
    assert "competitor_id" not in resp.text
    # Cada point tiene pseudonym y display_name poblado para coach.
    for pt in body["points"]:
        assert pt["pseudonym"].startswith("C")
        assert pt["display_name"] is not None
        assert len(pt["display_name"]) > 0


@pytest.mark.asyncio
async def test_get_distribution_parent_receives_display_name_none(client_factory):
    """Parent recibe display_name=None (pseudónimo únicamente)."""
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/distribution",
            params={"season": 2026, "event_id": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_size"] == 5
    for pt in body["points"]:
        assert pt["pseudonym"].startswith("C")
        assert pt["display_name"] is None


# ---------------------------------------------------------------------------
# GET /evolution — orden por valida_num
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_evolution_returns_series_ordered_by_valida(client_factory):
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/evolution",
            params={"season": 2026, "metric": "podium_gap_ms"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    valida_nums = [p["valida_num"] for p in body["series"]]
    assert valida_nums == sorted(valida_nums)
