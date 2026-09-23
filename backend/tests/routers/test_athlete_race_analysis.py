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
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
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
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES


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
    decided_by_user_id INTEGER,
    decided_at DATETIME,
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
            "race_course_variants",
            "race_course_category_setups",
            "athlete_ai_insights",
            "anthropometric_records",
            "parental_consents",
            *AUDIT_TABLES,
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
        await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
        )
        await create_insight(
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


@pytest.fixture(autouse=True)
def _default_ai_consent_granted(monkeypatch):
    """Consentimiento IA vigente por defecto en toda esta suite (feature 037,
    T405): estos tests cubren RBAC/filtros/lanzamiento de runs, no el gate de
    consentimiento en sí — ese vive en ``test_athlete_race_analysis_consent.py``.
    Sin este default, el fixture del atleta 144 (con padre vinculado pero sin
    fila ``ParentalConsent``) rompería todos los ``POST /runs`` con 451.
    """
    from app.routers import athlete_race_analysis as router_mod

    async def _fake_consent(athlete_id: int, db) -> bool:
        return True

    monkeypatch.setattr(router_mod, "athlete_has_ai_processing_consent", _fake_consent)


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


@pytest.mark.asyncio
async def test_get_insights_as_admin_returns_200(client_factory):
    """T076: admin alcanza lo mismo que un coach del club, sin membresía."""
    admin = _make_user(999, UserRole.admin, club_id=None)
    async with client_factory(user=admin) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1


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


@pytest.mark.asyncio
async def test_get_insight_detail_as_admin_returns_200(
    seeded_factory, client_factory
):
    """T076: admin ve el detalle igual que un coach del club, incluida una
    versión deprecada (el filtro "solo activa" es exclusivo de parent)."""
    async with seeded_factory() as s:
        from sqlalchemy import select
        from app.models.athlete_ai_insight import AthleteAiInsight

        rows = await s.execute(
            select(AthleteAiInsight)
            .where(AthleteAiInsight.athlete_id == 144)
            .where(AthleteAiInsight.deprecated_at.is_not(None))
        )
        deprecated_id = rows.scalar_one().id

    admin = _make_user(999, UserRole.admin, club_id=None)
    async with client_factory(user=admin) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{deprecated_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert resp.json()["id"] == deprecated_id


@pytest.mark.asyncio
async def test_get_insight_detail_parent_never_sees_podium_gap(
    seeded_factory, client_factory
):
    """Decisión del dueño (2026-09-23): la familia nunca ve la brecha a la
    ganadora ni al podio, en ninguna parte. Regresión del bug donde
    ``field_reading.gap_to_p3_hhmmss`` viajaba intacto al padre — la
    omisión server-side (feature 037) solo cubría
    ``expected_position``/``delta_vs_expected``. El coach sigue viendo el
    campo completo.
    """
    structured = {
        "schema_version": "v3",
        "headline": "Resumen de prueba",
        "field_reading": {
            "percentile": 58.3,
            "expected_position": 5,
            "actual_position": 7,
            "delta_vs_expected": -2,
            "gap_to_p3_hhmmss": "0:03:12",
            "series_label": "Válida 3 · Copa Valle",
            "summary": "Lectura de prueba.",
        },
        "trend": "stable",
        "observations": [],
        "actions": [],
        "watch_signals": [],
        "coach_question": "¿Cómo vamos con la carga?",
        "data_gaps": [],
        "principles_cited": [],
    }
    async with seeded_factory() as s:
        insight = await create_insight(
            s,
            athlete_id=144,
            valida_num=3,
            coach_approved=True,
            is_active=1,
            structured_json=structured,
        )
        await s.commit()
        insight_id = insight.id

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{insight_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    coach_field_reading = resp.json()["structured"]["field_reading"]
    assert coach_field_reading["gap_to_p3_hhmmss"] == "0:03:12"

    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{insight_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    parent_field_reading = resp.json()["structured"]["field_reading"]
    assert "gap_to_p3_hhmmss" not in parent_field_reading
    assert "0:03:12" not in resp.text


@pytest.mark.asyncio
async def test_get_insight_detail_as_parent_other_child_returns_403(client_factory):
    """Wave 5 (feature 036, US7 acceptance scenario 3): la única de las 8
    rutas de este router que no tenía su propio denied-path test explícito.

    Parent 20 NO es padre de 145 (mismo fixture que
    ``test_get_insights_as_parent_other_child_returns_403``) — pide el
    detalle de un insight bajo el atleta 145. ``verify_athlete_access``
    corre como dependencia ANTES del cuerpo del handler y sólo mira
    ``athlete_id`` (path param), así que el 403 dispara sin importar si
    ``insight_id`` existe de verdad para el atleta 145 — no hace falta
    sembrar un insight real para probar el corte de ownership.
    """
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/145/race-analysis/insights/1",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# T030/T033 (feature 036) — event_id/event_date/series_kind + orden por
# fecha de carrera
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_insights_exposes_event_date_and_series_kind(
    seeded_factory, client_factory
):
    """T030: el payload de insights expone event_id + event_date +
    series_kind — identidad de carrera vía event_id, no la convención
    retirada ``valida_num === 99``. Un insight sin event_id (agregado de
    temporada) expone ambos campos nuevos como ``None``."""
    async with seeded_factory() as s:
        # event_id=1 fue sembrado por seeded_factory: series_id=1 (kind
        # default 'cup'), sequence_number=1, event_date=2026-01-31.
        anchored = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=3,
            event_id=1,
            coach_approved=True,
            is_active=1,
        )
        season_aggregate = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=0,
            use_case="season_summary_v2",
            event_id=None,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    items = {item["id"]: item for item in resp.json()["items"]}

    anchored_item = items[anchored.id]
    assert anchored_item["event_id"] == 1
    assert anchored_item["event_date"] == "2026-01-31"
    assert anchored_item["series_kind"] == "cup"

    aggregate_item = items[season_aggregate.id]
    assert aggregate_item["event_id"] is None
    assert aggregate_item["event_date"] is None
    assert aggregate_item["series_kind"] is None


@pytest.mark.asyncio
async def test_get_insight_detail_exposes_event_date_and_series_kind(
    seeded_factory, client_factory
):
    """T030: el detalle (``GET /insights/{id}``) también expone los campos
    nuevos, no solo el listado."""
    async with seeded_factory() as s:
        anchored = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=3,
            event_id=1,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{anchored.id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_id"] == 1
    assert body["event_date"] == "2026-01-31"
    assert body["series_kind"] == "cup"


@pytest.mark.asyncio
async def test_get_insights_exposes_series_level(seeded_factory, client_factory):
    """T038 (feature 039): el payload de insights expone ``series_level``
    resuelto vía ``event_id`` → ``race_series.level``. Un insight anclado a
    un campeonato nacional expone ``'national'``; el agregado de temporada
    (sin ``event_id``) expone ``None`` — igual que ``series_kind`` (T030)."""
    async with seeded_factory() as s:
        from app.models.race_series import RaceSeriesKind, RaceSeriesLevel

        await create_race_series(
            s,
            series_id=3,
            season_year=2026,
            name="Campeonato Nacional Fedeciclismo",
            kind=RaceSeriesKind.championship,
            level=RaceSeriesLevel.national,
        )
        await create_race_event(
            s,
            event_id=3,
            series_id=3,
            sequence_number=1,
            name="Campeonato Nacional",
            event_date=date(2026, 8, 15),
        )
        national_insight = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=None,
            event_id=3,
            coach_approved=True,
            is_active=1,
        )
        season_aggregate = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=0,
            use_case="season_summary_v2",
            event_id=None,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    items = {item["id"]: item for item in resp.json()["items"]}

    national_item = items[national_insight.id]
    assert national_item["series_kind"] == "championship"
    assert national_item["series_level"] == "national"

    aggregate_item = items[season_aggregate.id]
    assert aggregate_item["event_id"] is None
    assert aggregate_item["series_kind"] is None
    assert aggregate_item["series_level"] is None

    # El detalle expone lo mismo que el listado.
    async with client_factory(user=coach) as ac:
        detail_resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{national_insight.id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["series_level"] == "national"


@pytest.mark.asyncio
async def test_get_insights_exposes_series_id_name_short_name(
    seeded_factory, client_factory
):
    """Hotfix "identidad de válida" (2026-09-16, ver
    ~/.claude/plans/multicopa-identidad-valida.md): el payload de insights
    expone ``series_id``/``series_name``/``series_short_name`` resueltos vía
    ``event_id`` — el cliente arma el label (chip/largo) sin un calendario
    hardcodeado de una sola copa. ``short_name`` cae a ``None`` cuando la
    serie no lo tiene definido; el agregado de temporada (sin ``event_id``)
    expone los tres como ``None``."""
    async with seeded_factory() as s:
        from app.models.race_series import RaceSeries

        letsgo = RaceSeries(
            id=7,
            name="Copa Let's Go Interdepartamental XCO",
            short_name="Let's Go",
            season_year=2026,
            organizer="Liga",
            points_scheme_code="copa_valle_2026",
        )
        s.add(letsgo)
        await s.flush()
        await create_race_event(
            s,
            event_id=7,
            series_id=7,
            sequence_number=4,
            name="Cuarta Válida",
            event_date=date(2026, 9, 13),
        )
        with_short_name = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=4,
            event_id=7,
            coach_approved=True,
            is_active=1,
        )
        # event_id=1 fue sembrado por seeded_factory: series_id=1
        # ("Copa Valle de Ciclomontanismo"), sin short_name.
        without_short_name = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=3,
            event_id=1,
            coach_approved=True,
            is_active=1,
        )
        season_aggregate = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=0,
            use_case="season_summary_v2",
            event_id=None,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    items = {item["id"]: item for item in resp.json()["items"]}

    letsgo_item = items[with_short_name.id]
    assert letsgo_item["series_id"] == 7
    assert letsgo_item["series_name"] == "Copa Let's Go Interdepartamental XCO"
    assert letsgo_item["series_short_name"] == "Let's Go"

    valle_item = items[without_short_name.id]
    assert valle_item["series_id"] == 1
    assert valle_item["series_name"] == "Copa Valle de Ciclomontanismo"
    assert valle_item["series_short_name"] is None

    aggregate_item = items[season_aggregate.id]
    assert aggregate_item["series_id"] is None
    assert aggregate_item["series_name"] is None
    assert aggregate_item["series_short_name"] is None

    # El detalle expone lo mismo.
    async with client_factory(user=coach) as ac:
        detail_resp = await ac.get(
            f"/api/athletes/144/race-analysis/insights/{with_short_name.id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["series_short_name"] == "Let's Go"


@pytest.mark.asyncio
async def test_get_insights_parent_gets_series_fields_scoped_to_own_child(
    seeded_factory, client_factory
):
    """Los campos nuevos (series_id/name/short_name) no amplían el acceso de
    un parent: solo ve el insight de su propio hijo (athlete_id=144, NO
    145), igual que antes de este hotfix — se limita a agregar campos al
    MISMO insight ya visible, nunca a exponer datos de otro atleta."""
    async with seeded_factory() as s:
        from app.models.race_series import RaceSeries

        letsgo = RaceSeries(
            id=7, name="Copa Let's Go", short_name="Let's Go",
            season_year=2026, organizer="Liga",
            points_scheme_code="copa_valle_2026",
        )
        s.add(letsgo)
        await s.flush()
        await create_race_event(
            s, event_id=7, series_id=7, sequence_number=1,
            name="Válida I Let's Go", event_date=date(2026, 3, 1),
        )
        own_child_insight = await create_insight(
            s, athlete_id=144, season=2026, valida_num=1, event_id=7,
            coach_approved=True, is_active=1,
        )
        await s.commit()

    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        # Hijo propio (144): ve los campos nuevos con normalidad.
        own_resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
        # Atleta ajeno (145): sigue bloqueado con 403 — el nuevo campo no
        # abre una vía de acceso paralela.
        other_resp = await ac.get(
            "/api/athletes/145/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )

    assert own_resp.status_code == 200
    own_items = {item["id"]: item for item in own_resp.json()["items"]}
    assert own_items[own_child_insight.id]["series_short_name"] == "Let's Go"

    assert other_resp.status_code == 403


@pytest.mark.asyncio
async def test_get_insights_filters_by_event_id(seeded_factory, client_factory):
    """Hotfix "identidad de válida": el filtro opcional ``event_id`` permite
    pedir solo insights anclados a una válida concreta — evita que el
    cliente reciba el insight de OTRA copa con el mismo valida_num
    (ambigüedad copa vs. copa, el bug original de este hotfix)."""
    async with seeded_factory() as s:
        from app.models.race_series import RaceSeries

        other_series = RaceSeries(
            id=8, name="Otra Copa 2026", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        s.add(other_series)
        await s.flush()
        await create_race_event(
            s, event_id=8, series_id=8, sequence_number=1,
            name="Válida I Otra Copa", event_date=date(2026, 3, 1),
        )
        target = await create_insight(
            s, athlete_id=144, season=2026, valida_num=1, event_id=8,
            coach_approved=True, is_active=1,
        )
        # event_id=1 (seeded_factory, series_id=1): mismo valida_num=1,
        # copa distinta.
        other = await create_insight(
            s, athlete_id=144, season=2026, valida_num=1, event_id=1,
            coach_approved=True, is_active=1,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            params={"event_id": 8},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert target.id in ids
    assert other.id not in ids


@pytest.mark.asyncio
async def test_get_insights_exposes_priority_tier(seeded_factory, client_factory):
    """Hotfix "identidad de válida": el payload de insights expone
    ``priority`` resuelto vía ``race_event_tier.get_race_tier`` (NUNCA la
    columna cruda) para el evento anclado. Un campeonato con la columna en
    NULL igual expone ``'CD'``; sin ``priority`` ni campeonato expone
    ``None``; el agregado de temporada (sin event_id) también expone
    ``None``."""
    async with seeded_factory() as s:
        from app.models.race_event import RaceEvent, RaceEventPriority

        # event_id=1 (seeded_factory): sin priority asignada, no campeonato.
        no_priority_insight = await create_insight(
            s, athlete_id=144, season=2026, valida_num=1, event_id=1,
            coach_approved=True, is_active=1,
        )

        # Evento con priority='A' explícito en la columna.
        await create_race_event(
            s, event_id=9, series_id=1, sequence_number=2,
            name="V2", event_date=date(2026, 4, 1),
        )
        evt9 = (
            await s.execute(select(RaceEvent).where(RaceEvent.id == 9))
        ).scalar_one()
        evt9.priority = RaceEventPriority.A
        a_priority_insight = await create_insight(
            s, athlete_id=144, season=2026, valida_num=2, event_id=9,
            coach_approved=True, is_active=1,
        )

        # Evento de campeonato con la columna priority en NULL.
        await create_race_event(
            s, event_id=10, series_id=1, sequence_number=3,
            name="Cto. Departamental", event_date=date(2026, 5, 1),
        )
        evt10 = (
            await s.execute(select(RaceEvent).where(RaceEvent.id == 10))
        ).scalar_one()
        evt10.is_championship = True
        cd_insight = await create_insight(
            s, athlete_id=144, season=2026, valida_num=3, event_id=10,
            coach_approved=True, is_active=1,
        )

        season_aggregate = await create_insight(
            s, athlete_id=144, season=2026, valida_num=0,
            use_case="season_summary_v2", event_id=None,
            coach_approved=True, is_active=1,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    items = {item["id"]: item for item in resp.json()["items"]}

    assert items[no_priority_insight.id]["priority"] is None
    assert items[a_priority_insight.id]["priority"] == "A"
    assert items[cd_insight.id]["priority"] == "CD"
    assert items[season_aggregate.id]["priority"] is None


@pytest.mark.asyncio
async def test_get_insights_orders_by_race_date_not_generated_at(
    seeded_factory, client_factory
):
    """T033: el historial se ordena por FECHA DE CARRERA, no por el
    timestamp de generación. V4 (evento más reciente) se genera ANTES que
    V3 (evento menos reciente) — si el bug persistiera V3 precedería a V4
    en la respuesta."""
    from app.models.race_series import RaceSeriesKind

    async with seeded_factory() as s:
        await create_race_series(
            s, series_id=9, season_year=2026, name="Copa 9", kind=RaceSeriesKind.cup
        )
        ev3 = await create_race_event(
            s, event_id=30, series_id=9, sequence_number=3,
            name="V3", event_date=date(2026, 3, 15),
        )
        ev4 = await create_race_event(
            s, event_id=31, series_id=9, sequence_number=4,
            name="V4", event_date=date(2026, 4, 12),
        )
        base_gen = datetime(2026, 5, 1, tzinfo=timezone.utc)
        # Orden de GENERACIÓN invertido respecto al orden de carrera.
        v4 = await create_insight(
            s, athlete_id=144, season=2026, valida_num=4, event_id=ev4.id,
            coach_approved=True, is_active=1, generated_at=base_gen,
        )
        v3 = await create_insight(
            s, athlete_id=144, season=2026, valida_num=3, event_id=ev3.id,
            coach_approved=True, is_active=1,
            generated_at=base_gen + timedelta(minutes=5),
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/insights",
            params={"latest_only": "true"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    ids_in_order = [item["id"] for item in resp.json()["items"]]
    assert ids_in_order.index(v4.id) < ids_in_order.index(v3.id)


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


@pytest.mark.asyncio
async def test_get_runs_as_admin_returns_200(client_factory):
    """T076: admin alcanza el histórico de runs igual que un coach."""
    admin = _make_user(999, UserRole.admin, club_id=None)
    async with client_factory(user=admin) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/runs",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


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
    from app.routers import athlete_race_analysis as router_mod

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
async def test_post_runs_ambiguous_valida_returns_409(
    seeded_factory, client_factory, monkeypatch
):
    """Guard cup vs championship (feature 014): si valida_num=1 mapea a >1 evento
    en la temporada (copa válida 1 + campeonato seq=1), el lanzamiento por
    deportista es ambiguo → 409, sin disparar el grafo.
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

    # Segundo evento con sequence_number=1 (campeonato, su propia serie) donde
    # el atleta 144 también participó → colisión con la válida 1 de copa.
    async with seeded_factory() as s:
        from app.models.race_series import RaceSeriesKind

        await create_race_series(
            s,
            series_id=2,
            season_year=2026,
            name="Campeonato Departamental",
            kind=RaceSeriesKind.championship,
        )
        await create_race_event(
            s,
            event_id=2,
            series_id=2,
            sequence_number=1,
            name="Campeonato",
            event_date=date(2026, 6, 12),
        )
        await create_race_result(
            s,
            event_id=2,
            category_id=100,
            competitor_id=1002,
            athlete_id=144,
            position=2,
            race_time_ms=1_805_000,
            bib_number=3,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [1], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 409, resp.text
    assert len(submit_calls) == 0


@pytest.mark.asyncio
async def test_post_runs_with_event_id_disambiguates_and_launches(
    seeded_factory, client_factory, monkeypatch
):
    """Anclar por event_id resuelve la ambigüedad cup vs championship: el
    lanzamiento desde una competición concreta procede (201), deriva el
    valida_num del evento y propaga event_id al estado inicial.
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

    # Mismo escenario colisión que el test 409: evento 2 (campeonato seq=1).
    async with seeded_factory() as s:
        from app.models.race_series import RaceSeriesKind

        await create_race_series(
            s,
            series_id=2,
            season_year=2026,
            name="Campeonato Departamental",
            kind=RaceSeriesKind.championship,
        )
        await create_race_event(
            s,
            event_id=2,
            series_id=2,
            sequence_number=1,
            name="Campeonato",
            event_date=date(2026, 6, 12),
        )
        await create_race_result(
            s,
            event_id=2,
            category_id=100,
            competitor_id=1002,
            athlete_id=144,
            position=2,
            race_time_ms=1_805_000,
            bib_number=3,
        )
        await s.commit()

    coach = _make_user(10, UserRole.coach, club_id=1)
    # event_id=2 (campeonato) → debe anclar a ese evento, NO al de copa (id=1).
    body = {"season": 2026, "event_id": 2, "valida_nums": [1], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    assert len(submit_calls) == 1
    _rid, initial_state, _on = submit_calls[0]
    assert initial_state["event_id"] == 2
    assert initial_state["valida_nums"] == [1]


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
async def test_post_runs_default_prompt_version_es_v3(client_factory, monkeypatch):
    """Feature 037 (T204): el lanzamiento por atleta usa
    ``settings.race_ai_prompt_version`` (default ``race_analyst_v3``) en vez
    del ``PROMPT_VERSION_ANALYST_V2`` hardcodeado.
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
    assert initial_state["prompt_version"] == "race_analyst_v3"
    assert initial_state["analysis_kind"] == "valida"


@pytest.mark.asyncio
async def test_post_runs_override_a_v2_para_rollback(client_factory, monkeypatch):
    """Rollback sin deploy: ``RACE_AI_PROMPT_VERSION=race_analyst_v2``."""
    from app.routers import athlete_race_analysis as router_mod

    submit_calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        submit_calls.append((run_id, initial_state, on_complete))

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "race_ai_prompt_version", "race_analyst_v2")

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [1], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    _, initial_state, _ = submit_calls[0]
    assert initial_state["prompt_version"] == "race_analyst_v2"


@pytest.mark.asyncio
async def test_post_runs_injects_athlete_sex(client_factory, monkeypatch):
    """Feature 037 (T204): ``athlete_sex`` viaja al state igual que en
    ``race_analysis.py::start_run`` — necesario para ``athlete_ref`` v3.
    Atleta 144 (fixture) sin sexo registrado explícitamente en este test
    module → la clave debe existir de todas formas (puede ser ``None``).
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
    body = {"season": 2026, "valida_nums": [1], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    _, initial_state, _ = submit_calls[0]
    assert "athlete_sex" in initial_state


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
async def test_post_runs_as_admin_returns_201(client_factory, monkeypatch):
    """T076: admin puede lanzar un run igual que un coach (sin membresía)."""
    from app.routers import athlete_race_analysis as router_mod

    submit_calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        submit_calls.append((run_id, initial_state, on_complete))

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    monkeypatch.setattr(settings, "ai_enabled", True)

    admin = _make_user(999, UserRole.admin, club_id=None)
    body = {"season": 2026, "valida_nums": [1], "explain_mode": False}
    async with client_factory(user=admin) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    assert len(submit_calls) == 1


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
# T043 (feature 036) — guard: no duplicar un run activo para la misma
# válida
# ---------------------------------------------------------------------------


async def _seed_active_agent_run(
    seeded_factory,
    *,
    external_run_id: str,
    athlete_id: int = 144,
    season: int = 2026,
    valida_nums: list[int] | None,
    db_status: str = "running",
) -> None:
    """Inserta una fila ``agent_runs`` activa — mismo patrón de INSERT que
    ``start_athlete_run`` usa en producción (mismas columnas/valores)."""
    input_json = json.dumps(
        {
            "athlete_id": athlete_id,
            "season": season,
            "valida_nums": valida_nums,
            "explain_mode": False,
        }
    )
    async with seeded_factory() as s:
        await s.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, requested_by_user_id,
                    checkpoint_thread_id, explain_mode, athlete_id
                ) VALUES (
                    :rid, :gn, :pv, :sa, :st, :inp, :uid, :tid, 0, :aid
                )
                """
            ),
            {
                "rid": external_run_id,
                "gn": "race-analyst",
                "pv": "race_analyst_v2",
                "sa": datetime.now(timezone.utc),
                "st": db_status,
                "inp": input_json,
                "uid": 10,
                "tid": external_run_id,
                "aid": athlete_id,
            },
        )
        await s.commit()


@pytest.mark.asyncio
async def test_post_runs_rejects_when_active_run_exists_for_same_valida(
    seeded_factory, client_factory, monkeypatch
):
    """T043: si YA hay un run activo (running/awaiting_hitl) para el mismo
    atleta + válida, el lanzamiento debe rechazarse con 409 en vez de
    iniciar un segundo run duplicado. Reusa
    ``group_launch.find_active_run`` (mismo mecanismo que ya usa el
    lanzamiento grupal para ``already_running``) en vez de duplicar la
    lógica de matching sobre ``input_json``.
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

    await _seed_active_agent_run(
        seeded_factory,
        external_run_id="run-activo-abc123",
        athlete_id=144,
        season=2026,
        valida_nums=[3],
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [3], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 409, resp.text
    assert len(submit_calls) == 0
    assert "en curso" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_runs_allows_different_valida_when_another_is_active(
    seeded_factory, client_factory, monkeypatch
):
    """El guard es específico por válida: un run activo en la válida 3 NO
    debe bloquear un lanzamiento nuevo para la válida 2."""
    from app.routers import athlete_race_analysis as router_mod

    submit_calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        submit_calls.append((run_id, initial_state, on_complete))

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    monkeypatch.setattr(settings, "ai_enabled", True)

    await _seed_active_agent_run(
        seeded_factory,
        external_run_id="run-activo-otra-valida",
        athlete_id=144,
        season=2026,
        valida_nums=[3],
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [2], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    assert len(submit_calls) == 1


@pytest.mark.asyncio
async def test_post_runs_allows_when_previous_run_for_same_valida_completed(
    seeded_factory, client_factory, monkeypatch
):
    """Un run TERMINADO (completed) para la misma válida no cuenta como
    activo — el guard solo mira ``running``/``awaiting_hitl``."""
    from app.routers import athlete_race_analysis as router_mod

    submit_calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        submit_calls.append((run_id, initial_state, on_complete))

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    monkeypatch.setattr(settings, "ai_enabled", True)

    await _seed_active_agent_run(
        seeded_factory,
        external_run_id="run-viejo-completado",
        athlete_id=144,
        season=2026,
        valida_nums=[3],
        db_status="completed",
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [3], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201, resp.text
    assert len(submit_calls) == 1


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


@pytest.mark.asyncio
async def test_get_distribution_as_admin_returns_200(client_factory):
    """T076: admin alcanza la distribución igual que un coach del club."""
    admin = _make_user(999, UserRole.admin, club_id=None)
    async with client_factory(user=admin) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/distribution",
            params={"season": 2026, "event_id": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert resp.json()["sample_size"] == 5


@pytest.mark.asyncio
async def test_get_distribution_as_parent_other_child_returns_403(client_factory):
    """T077: Parent 20 NO es padre de 145 → 403.

    Antes de este test, ``verify_athlete_access`` nunca se ejercía sin
    mockear (``test_athlete_race_analysis_privacy.py`` sobreescribe la
    dependencia directamente), así que una regresión que dejara este
    endpoint sin la dependencia de ownership habría pasado inadvertida.
    """
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/145/race-analysis/distribution",
            params={"season": 2026, "event_id": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


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


@pytest.mark.asyncio
async def test_get_evolution_as_admin_returns_200(client_factory):
    """T076: admin alcanza la evolución igual que un coach del club."""
    admin = _make_user(999, UserRole.admin, club_id=None)
    async with client_factory(user=admin) as ac:
        resp = await ac.get(
            "/api/athletes/144/race-analysis/evolution",
            params={"season": 2026, "metric": "podium_gap_ms"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    assert len(resp.json()["series"]) >= 1


@pytest.mark.asyncio
async def test_get_evolution_as_parent_other_child_returns_403(client_factory):
    """T077: Parent 20 NO es padre de 145 → 403 (misma razón que distribution:
    el endpoint nunca se probó con la dependencia de ownership real)."""
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.get(
            "/api/athletes/145/race-analysis/evolution",
            params={"season": 2026, "metric": "podium_gap_ms"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403

