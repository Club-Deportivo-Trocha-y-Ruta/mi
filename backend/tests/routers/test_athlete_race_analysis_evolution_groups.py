"""Tests TDD para ``GET /evolution`` con grupos de comparación (feature 039).

Contrato objetivo (``specs/039-season-comparison-groups/contracts/evolution-api.md``):

    GET /api/athletes/{athlete_id}/race-analysis/evolution
        ?season=<year>&metric=<m>&series_id=<int, opcional>

    - Respuesta 200 SIEMPRE incluye ``groups`` (lista de
      ``ComparisonGroupOption``), incluso sin ``series_id``.
    - ``series_id`` (≥1) filtra ``series`` a esa sola serie y fija
      ``selected_group``. RBAC no cambia: admin/coach/parent-propio → 200;
      parent ajeno → 403, con o sin ``series_id`` (el filtro no debe abrir
      una vía de acceso paralela).
    - ``series_id=0`` → 422 (``Query(..., ge=1)``).

Estado actual (TDD-rojo): el router NO declara el parámetro ``series_id`` —
FastAPI simplemente lo ignora (no lo valida, no lo usa), y
``EvolutionResponse``/``EvolutionPoint`` no tienen ``groups``/``series_id``.
Los asserts que verifican esos campos DEBEN FALLAR ahora.

Escenario: reutiliza ``tests.fixtures.race_groups.seed_base_season`` (feature
039) — atleta ficticio "Camila Ficticia Salazar" (id=850) con una copa de 5
válidas + Cto. Departamental + Cto. Nacional, más un padre propio y un padre
ajeno (vinculado a un segundo atleta ficticio) agregados aquí para las
pruebas de RBAC. Todos los nombres son ficticios (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from datetime import date
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
from app.models.athlete import Athlete, Sex
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_groups import CLUB_ID, COACH_USER_ID, seed_base_season
from tests.fixtures.race_history_fixtures import create_user, link_parent_to_athlete

# ---------------------------------------------------------------------------
# Engine SQLite in-memory (mismo DDL que test_athlete_race_analysis_races.py)
# ---------------------------------------------------------------------------

_AGENT_RUNS_DDL = """
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

_TABLES = (
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


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.exec_driver_sql(_AGENT_RUNS_DDL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Seed: escenario base (race_groups) + padre propio + padre ajeno
# ---------------------------------------------------------------------------

_PARENT_OWN_ID = 1950
_PARENT_OWN_EMAIL = "padre_propio_g039@test.com"
_OTHER_ATHLETE_ID = 851
_OTHER_ATHLETE_USER_ID = 1851
_PARENT_OTHER_ID = 1951
_PARENT_OTHER_EMAIL = "padre_ajeno_g039@test.com"


@pytest_asyncio.fixture
async def evolution_groups_seeded(session_factory):
    """Escenario (a) de ``race_groups`` + padre propio + padre ajeno.

    Devuelve ``(session_factory, scenario)`` — ``scenario`` es el
    ``RaceGroupsScenario`` con los IDs ya committeados; las peticiones HTTP
    posteriores abren sesiones nuevas desde ``session_factory`` (el objeto
    ``scenario.session`` no se reutiliza tras este fixture).
    """
    async with session_factory() as s:
        scenario = await seed_base_season(s)

        # Padre propio — vinculado al atleta del escenario (id=850).
        await create_user(
            s, user_id=_PARENT_OWN_ID, role=UserRole.parent, email=_PARENT_OWN_EMAIL,
        )
        await link_parent_to_athlete(
            s, parent_user_id=_PARENT_OWN_ID, athlete_id=scenario.athlete_id,
        )

        # Atleta ficticio 2 (sin relación con el padre propio) + padre ajeno.
        await create_user(
            s,
            user_id=_OTHER_ATHLETE_USER_ID,
            role=UserRole.athlete,
            can_login=False,
            email="otro_atleta_g039@test.com",
        )
        other_athlete = Athlete(
            id=_OTHER_ATHLETE_ID,
            user_id=_OTHER_ATHLETE_USER_ID,
            first_name="Otro Ficticio",
            last_name="Ramírez",
            birth_date=date(2013, 5, 20),
            sex=Sex.M,
            club_id=CLUB_ID,
            created_by=COACH_USER_ID,
        )
        s.add(other_athlete)
        await s.flush()

        await create_user(
            s, user_id=_PARENT_OTHER_ID, role=UserRole.parent, email=_PARENT_OTHER_EMAIL,
        )
        await link_parent_to_athlete(
            s, parent_user_id=_PARENT_OTHER_ID, athlete_id=_OTHER_ATHLETE_ID,
        )

        await s.commit()

    return session_factory, scenario


# ---------------------------------------------------------------------------
# Helpers: usuarios para overrides de auth
# ---------------------------------------------------------------------------


def _coach_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=COACH_USER_ID,
        first_name="Entrenador",
        last_name="Ficticio",
        email="coach_g039@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[SimpleNamespace(club_id=CLUB_ID, role_in_club=ClubRole.coach)],
    )


def _parent_own_user() -> SimpleNamespace:
    """Padre vinculado al atleta del escenario (id=850)."""
    return SimpleNamespace(
        id=_PARENT_OWN_ID,
        first_name="Padre",
        last_name="Ficticio",
        email=_PARENT_OWN_EMAIL,
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _parent_other_user() -> SimpleNamespace:
    """Padre vinculado al atleta ajeno (id=851), NO al del escenario."""
    return SimpleNamespace(
        id=_PARENT_OTHER_ID,
        first_name="Padre",
        last_name="Ajeno",
        email=_PARENT_OTHER_EMAIL,
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _make_client(session_factory_fixture, user_fn):
    """Construye un ``AsyncClient`` con override de DB + auth."""

    def _override_db():
        async def _inner():
            async with session_factory_fixture() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        return _inner

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_current_user] = user_fn
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_evolution_coach_returns_200_with_groups_key(evolution_groups_seeded):
    """Coach del club del atleta → 200 y el body incluye la key ``groups``.

    Pre-implementación: ``EvolutionResponse`` no tiene ``groups`` — el
    assert de la key debe fallar (TDD-red).
    """
    session_factory, scenario = evolution_groups_seeded
    async with _make_client(session_factory, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{scenario.athlete_id}/race-analysis/evolution",
            params={"season": scenario.season, "metric": "ranking"},
            headers={"Authorization": "Bearer fake"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    body = resp.json()
    assert "groups" in body, (
        "La respuesta debe incluir 'groups' (feature 039, aún no implementado). "
        f"Keys recibidas: {sorted(body.keys())}"
    )
    assert isinstance(body["groups"], list) and len(body["groups"]) == 3, (
        f"groups debe tener 3 series (copa + Cto. Dep. + Cto. Nal.). "
        f"Recibí: {body.get('groups')}"
    )


@pytest.mark.asyncio
async def test_evolution_series_id_filter_returns_only_that_group(
    evolution_groups_seeded,
):
    """``series_id=<copa>`` → 200 y todo punto de ``series`` pertenece a ella.

    Pre-implementación: el router ignora ``series_id`` (parámetro no
    declarado) → ``series`` sigue trayendo las 7 filas de la temporada
    completa, sin campo ``series_id`` en cada punto. El assert de longitud
    y el de pertenencia deben fallar.
    """
    session_factory, scenario = evolution_groups_seeded
    async with _make_client(session_factory, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{scenario.athlete_id}/race-analysis/evolution",
            params={
                "season": scenario.season,
                "metric": "ranking",
                "series_id": scenario.cup_series_id,
            },
            headers={"Authorization": "Bearer fake"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    body = resp.json()
    series = body.get("series", [])
    assert len(series) == 5, (
        f"Con series_id={scenario.cup_series_id} esperaba solo las 5 válidas "
        f"de la copa. Recibí {len(series)} puntos: {series}"
    )
    assert all(p.get("series_id") == scenario.cup_series_id for p in series), (
        f"Todos los puntos deben tener series_id={scenario.cup_series_id}. "
        f"Recibí: {[p.get('series_id') for p in series]}"
    )


@pytest.mark.asyncio
async def test_evolution_parent_of_athlete_returns_200_without_competitor_names(
    evolution_groups_seeded,
):
    """Padre del propio atleta → 200 y el body no contiene nombres reales de
    competidores (Ley 1581) — ni siquiera con los campos nuevos de grupo.
    """
    session_factory, scenario = evolution_groups_seeded
    async with _make_client(session_factory, _parent_own_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{scenario.athlete_id}/race-analysis/evolution",
            params={"season": scenario.season, "metric": "ranking"},
            headers={"Authorization": "Bearer fake"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Padre del propio atleta debe recibir 200. "
        f"Recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    raw = resp.text
    forbidden_substrings = (
        "Rival Ficticio",  # display_name de los rivales sembrados
        "Camila Ficticia",  # nombre del propio atleta (no debe viajar tampoco)
        "Salazar",
    )
    for needle in forbidden_substrings:
        assert needle not in raw, (
            f"La respuesta a un parent no debe contener {needle!r} "
            "(nombre real de un competidor o del atleta)."
        )


@pytest.mark.asyncio
async def test_evolution_parent_of_another_athlete_with_series_id_gets_same_denial(
    evolution_groups_seeded,
):
    """El padre ajeno recibe el MISMO status con y sin ``series_id`` — el
    filtro no debe abrir una vía de acceso paralela al RBAC existente.
    """
    session_factory, scenario = evolution_groups_seeded

    async with _make_client(session_factory, _parent_other_user) as ac:
        resp_without = await ac.get(
            f"/api/athletes/{scenario.athlete_id}/race-analysis/evolution",
            params={"season": scenario.season, "metric": "ranking"},
            headers={"Authorization": "Bearer fake"},
        )
    app.dependency_overrides.clear()

    async with _make_client(session_factory, _parent_other_user) as ac:
        resp_with = await ac.get(
            f"/api/athletes/{scenario.athlete_id}/race-analysis/evolution",
            params={
                "season": scenario.season,
                "metric": "ranking",
                "series_id": scenario.cup_series_id,
            },
            headers={"Authorization": "Bearer fake"},
        )
    app.dependency_overrides.clear()

    assert resp_without.status_code == 403, (
        f"Padre ajeno sin series_id debe recibir 403 (denegación de hoy). "
        f"Recibí {resp_without.status_code}. Body: {resp_without.text[:300]}"
    )
    assert resp_with.status_code == resp_without.status_code, (
        f"El filtro series_id no debe cambiar la denegación: sin filtro "
        f"{resp_without.status_code}, con filtro {resp_with.status_code}."
    )


@pytest.mark.asyncio
async def test_evolution_series_id_zero_returns_422(evolution_groups_seeded):
    """``series_id=0`` viola ``ge=1`` → 422.

    Pre-implementación: el parámetro no existe en el router, FastAPI lo
    ignora silenciosamente → 200 (no 422). El assert debe fallar.
    """
    session_factory, scenario = evolution_groups_seeded
    async with _make_client(session_factory, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{scenario.athlete_id}/race-analysis/evolution",
            params={"season": scenario.season, "metric": "ranking", "series_id": 0},
            headers={"Authorization": "Bearer fake"},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422, (
        f"series_id=0 debe fallar validación (ge=1). Recibí {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
