"""Tests TDD para el endpoint ``GET /distribution`` con param ``event_id``.

Feature 016 — Race Analysis Championship Charts Fix.

Contrato target (post-fix):
    GET /api/athletes/{athlete_id}/race-analysis/distribution
        ?event_id=<id>&season=<year>

Estado pre-fix (DEBEN FALLAR):
    - El endpoint acepta ``valida_num`` (int), NO ``event_id``.
    - Para campeonatos: la query busca por ``e.sequence_number = :valida_num``.
      Como el campeonato tiene ``sequence_number=1`` pero el frontend
      enviaba ``valida_num=99``, no hay match → el fallback retorna
      ``DistributionResponse(category_id=0, category_code="")``,
      violando el schema (``category_id ge=1``, ``category_code min_length=1``)
      → ResponseValidationError → HTTP 500.
    - T007: si no hay datos comparables (n<5 / DNF) también puede devolver 500
      si pasa por el mismo branch vacío.
    - T008: un event_id no reconocido puede causar 500 en lugar de 404.

Por qué estos tests DEBEN FALLAR ahora:
    Todos los tests envían ``event_id=<n>`` como query param. El router actual
    ignora ``event_id`` (no está declarado) y exige ``valida_num`` como
    requerido → FastAPI devuelve 422 (param requerido ausente), no 200/404.
    Eso hace que T006 y T007 fallen (esperan 200, reciben 422) y T008 falle
    (espera 404, recibe 422 o 500 según implementación).

Datos: solo ficticios (nunca reales). Atleta "Juan Ficticio Pérez", DOB 2014-07-10.
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
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_club,
    create_distribution_scenario,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_user,
    link_user_to_club,
)
from app.models.race_result import ResultStatus


# ---------------------------------------------------------------------------
# Engine SQLite in-memory
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
# Seed: escenario completo de distribución (copa + campeonato)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def distribution_seeded(session_factory) -> async_sessionmaker[AsyncSession]:
    """Seed base: club + coach + escenario copa/campeonato con atleta ficticio.

    IDs asignados:
    - club_id=1, coach user_id=10
    - athlete_id=201  ("Juan Ficticio Pérez", DOB 2014-07-10)
    - cup_series_id=50, championship_series_id=51
    - category_id=200 (INF_B_FICT)
    - cup_event_id_1=501, cup_event_id_2=502
    - championship_event_id=503
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_fict")
        await create_user(s, user_id=10, role=UserRole.coach, email="coach_fict@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)

        # Usuario para el atleta ficticio (can_login=False como es atleta menor)
        await create_user(
            s,
            user_id=1201,
            role=UserRole.athlete,
            email="juanficticio@test.com",
            first_name="Juan Ficticio",
            last_name="Pérez",
            can_login=False,
        )

        await create_distribution_scenario(
            s,
            athlete_id=201,
            coach_user_id=10,
            season=2026,
            cup_series_id=50,
            championship_series_id=51,
            category_id=200,
            cup_event_id_1=501,
            cup_event_id_2=502,
            championship_event_id=503,
        )
        await s.commit()
    return session_factory


# ---------------------------------------------------------------------------
# Helper: construir usuario coach para overrides
# ---------------------------------------------------------------------------


def _coach_user(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="Coach",
        email="coach_fict@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(
                club_id=club_id,
                role_in_club=ClubRole.coach,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Fixture de cliente con auth override
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(distribution_seeded):
    """AsyncClient con auth=coach y DB SQLite seeded."""

    def _override_db():
        async def _inner():
            async with distribution_seeded() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        return _inner

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_current_user] = lambda: _coach_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T006 — Campeonato devuelve 200 con category_id válido
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distribution_championship_event_returns_200_with_valid_category(
    coach_client,
):
    """T006: GET distribution con event_id del campeonato → 200, category_id ≥1.

    Pre-fix: el endpoint usa ``valida_num`` (requerido). Al enviar ``event_id``
    FastAPI devuelve 422 (param requerido ausente). En consecuencia este test
    FALLA en el código actual — ese fallo es el esperado.

    Contrato target post-fix:
    - Acepta ``event_id`` como query param.
    - Para el campeonato (series.kind='championship', sequence_number=1,
      event_id=503) el atleta ficticio sí compitió → debe retornar 200
      con ``category_id >= 1`` y ``category_code`` no vacío.
    - NUNCA 500.
    """
    resp = await coach_client.get(
        "/api/athletes/201/race-analysis/distribution",
        params={"event_id": 503, "season": 2026},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["category_id"] >= 1, (
        f"category_id debe ser ≥1 (nunca 0). Recibí: {body.get('category_id')}"
    )
    assert body["category_code"], (
        f"category_code no debe estar vacío. Recibí: {body.get('category_code')!r}"
    )


# ---------------------------------------------------------------------------
# T007 — Evento sin datos comparables → 200, nunca 500, nunca category_id=0
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def distribution_dnf_seeded(session_factory) -> async_sessionmaker[AsyncSession]:
    """Seed extendido: igual que distribution_seeded + evento DNF (event_id=601).

    Evento 601: el atleta ficticio (id=201) compite con DNF, y hay solo 2
    corredores terminados (n<5) → sin curva normal computable.
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_fict_dnf")
        await create_user(s, user_id=10, role=UserRole.coach, email="coach_fict_dnf@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await create_user(
            s,
            user_id=1201,
            role=UserRole.athlete,
            email="juanficticiodnf@test.com",
            first_name="Juan Ficticio",
            last_name="Pérez",
            can_login=False,
        )
        await create_distribution_scenario(
            s,
            athlete_id=201,
            coach_user_id=10,
            season=2026,
            cup_series_id=50,
            championship_series_id=51,
            category_id=200,
            cup_event_id_1=501,
            cup_event_id_2=502,
            championship_event_id=503,
        )
        # Evento extra con DNF del atleta y <5 finishers
        await create_race_event(
            s,
            event_id=601,
            series_id=50,
            sequence_number=3,
            name="Evento DNF Ficticio",
            event_date=date(2026, 4, 19),
            created_by_user_id=10,
        )
        # 2 finishers
        await create_race_competitor(
            s, competitor_id=6001, normalized_name="winner fict ev601",
            display_name="Corredor Ficticio F 601",
        )
        await create_race_result(
            s, event_id=601, category_id=200, competitor_id=6001, position=1,
            race_time_ms=1_800_000, bib_number=1, status=ResultStatus.FINISHED,
        )
        await create_race_competitor(
            s, competitor_id=6002, normalized_name="runner2 fict ev601",
            display_name="Corredor Ficticio G 601",
        )
        await create_race_result(
            s, event_id=601, category_id=200, competitor_id=6002, position=2,
            race_time_ms=1_810_000, bib_number=2, status=ResultStatus.FINISHED,
        )
        # Atleta ficticio: DNF — position=None (constraint: position IS NULL OR >= 1)
        # reutiliza su competitor global (id=201*10=2010)
        await create_race_result(
            s, event_id=601, category_id=200, competitor_id=2010,
            athlete_id=201, position=None, race_time_ms=None, bib_number=99,
            status=ResultStatus.DNF,
        )
        await s.commit()
    return session_factory


@pytest.mark.asyncio
async def test_distribution_no_comparable_data_returns_200_never_500(
    distribution_dnf_seeded,
):
    """T007: GET distribution con event donde el atleta compitió pero con DNF
    → 200, ``category_id ≥ 1``, ``curve == []``, ``confidence == 'low'``.
    NUNCA 500. NUNCA ``category_id == 0``.

    Escenario: evento 601 con el atleta ficticio (DNF) y solo 2 finishers.
    La curva no es computable (n<5 FINISHED) → confidence=low, curve=[].
    Pero el endpoint debe retornar 200 con category_id válido.

    Pre-fix: puede fallar por 422 (si el endpoint no acepta event_id) o por
    500 (si el fallback retorna category_id=0 violando el schema).
    """

    def _override_db():
        async def _inner():
            async with distribution_dnf_seeded() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise
        return _inner

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_current_user] = lambda: _coach_user()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/athletes/201/race-analysis/distribution",
                params={"event_id": 601, "season": 2026},
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Esperaba 200 (nunca 500). Recibí {resp.status_code}. Body: {resp.text[:300]}"
    )
    body = resp.json()
    # Nunca category_id=0 (violaría el schema)
    assert body["category_id"] >= 1, (
        f"category_id debe ser ≥1. Recibí: {body.get('category_id')}"
    )
    # DNF → sin tiempo propio
    assert body.get("athlete_time_ms") is None, (
        "athlete_time_ms debe ser None para un DNF"
    )
    # n<5 FINISHED → sin curva normal
    assert body.get("curve") == [], (
        f"curve debe ser [] con n<5 finishers. Recibí: {body.get('curve')}"
    )
    assert body.get("confidence") == "low", (
        f"confidence debe ser 'low' con n<5. Recibí: {body.get('confidence')!r}"
    )


# ---------------------------------------------------------------------------
# T008 — Evento en el que el atleta NO participó → 404, sin PII
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distribution_nonparticipated_event_returns_404_no_pii(
    coach_client,
):
    """T008: GET distribution con event_id en el que el atleta no participó
    (o id inexistente como 999999) → 404. El cuerpo NO debe contener
    ``athlete_id`` ni ``competitor_id`` (privacidad).

    Pre-fix: el endpoint no reconoce el param ``event_id`` → FastAPI 422.
    Si el endpoint sí reconociera event_id pero no lo encontrara podría
    retornar 500 en lugar de 404. El test verifica el contrato target (404).
    """
    resp = await coach_client.get(
        "/api/athletes/201/race-analysis/distribution",
        params={"event_id": 999999, "season": 2026},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 404, (
        f"Esperaba 404 para event_id inexistente. Recibí {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
    # Privacidad: el cuerpo de error nunca debe exponer IDs personales
    body_text = resp.text
    assert "athlete_id" not in body_text, (
        "La respuesta 404 no debe contener 'athlete_id' (privacidad)"
    )
    assert "competitor_id" not in body_text, (
        "La respuesta 404 no debe contener 'competitor_id' (privacidad)"
    )
