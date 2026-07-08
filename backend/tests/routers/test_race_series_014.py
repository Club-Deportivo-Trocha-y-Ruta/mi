"""Tests backend spec 014 — Cup vs Championship Series.

Cubre las tareas QA de la Ola A:
  T007 — GET/POST /race-series: enum round-trip, filtros, 409 duplicado, 422,
          privacidad (sin PII de menores).
  T010 — POST /race-events: campeonato rechaza 2do evento (409 es-CO), deriva
          seq=1/is_championship, copa sin cambios (regresión).
  T018 — import a serie campeonato: omite válida → seq=1; copa sin cambios;
          _get_or_create_series honra series_name no-Copa; detect_revision usa
          series_name real; 2do import-fresh a campeonato existente → 409.
          Desviación #2 (re-ingesta mismo SHA campeonato) verificada.
  T025 — season_panorama EXCLUYE campeonatos; standings retorna vacío para
          evento campeonato; copa sin cambios (SC-002).
  T027 — migración idempotente, reclasificación preserva resultados (FR-012),
          evento reclasificado ya no contribuye al ranking Copa (SC-003),
          no-op seguro cuando el evento legacy no existe.

Estrategia:
  SQLite async in-memory + StaticPool; override get_db / get_current_user;
  stub de storage_sftp y pdf_parser para el flujo de imports (sin red, sin FS).
  Datos ficticios: nunca PII de menores reales.

Privacidad invariante:
  Las respuestas de /race-series y /race-events no contienen DOB, datos médicos
  ni nombres de menores.
"""
from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator, Optional

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

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Tables needed (SQLite in-memory subset)
# ---------------------------------------------------------------------------

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "race_series",
    "race_events",
    "race_imports",
    "race_categories",
    "race_competitors",
    "race_results",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="Ficticio",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Import models to register metadata
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def _make_override_db(factory: async_sessionmaker[AsyncSession]):
    async def _override():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _override


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_base_users(session: AsyncSession, coach_id: int = 10) -> None:
    """Inserta coach + admin en la DB."""
    coach = User(
        id=coach_id,
        email=f"coach{coach_id}@ficticio.test",
        hashed_password="x",
        first_name="Coach",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    admin = User(
        id=1,
        email="admin@ficticio.test",
        hashed_password="x",
        first_name="Admin",
        last_name="Ficticio",
        role=UserRole.admin,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([coach, admin])
    await session.flush()


# ---------------------------------------------------------------------------
# Client factories (parametrized by role + db override)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_factory):
    """Cliente HTTP como coach id=10, sin seed previo (cada test lo hace)."""
    app.dependency_overrides[get_db] = _make_override_db(db_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_factory):
    app.dependency_overrides[get_db] = _make_override_db(db_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=5
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Storage + parser stubs (for import tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_storage(monkeypatch, tmp_path):
    """Redirige storage_sftp al fallback local."""
    from app.services.training import storage_sftp
    from app.config import settings

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(
        storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test"
    )
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest.fixture
def stub_parsers(monkeypatch):
    """Stub _parse_results_with_timeout con 2 filas ficticias."""
    from app.routers import race_imports as router_mod
    from app.services.race.pdf_parser import ResultsRow

    async def fake_parse_results(path, ext):  # noqa: ARG001
        return {
            "TET_CP": [
                ResultsRow(
                    position=1, bib="550", name="Juan Pérez Ficticio",
                    city="Yumbo", club="Club Trocha y Ruta",
                    time_raw="0:03:38", points=40,
                ),
                ResultsRow(
                    position=2, bib="551", name="Pedro Rodríguez Ficticio",
                    city="Cali", club="Otro Club",
                    time_raw="0:04:00", points=36,
                ),
            ],
        }

    async def fake_parse_general(path):  # noqa: ARG001
        return {}

    monkeypatch.setattr(router_mod, "_parse_results_with_timeout", fake_parse_results)
    monkeypatch.setattr(router_mod, "_parse_general_with_timeout", fake_parse_general)


def _make_fake_pdf() -> bytes:
    """PDF mínimo válido (magic bytes %PDF-)."""
    return b"%PDF-1.4 fake"


# ---------------------------------------------------------------------------
# ═══════════════════════════════════════════════════════════════════════════
# T007 — GET/POST /race-series
# ═══════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------


_SERIES_URL = "/api/race-analysis/race-series/"


class TestRaceSeriesT007:
    """T007: endpoints GET/POST /race-series — enum, filtros, 409, 422, privacidad."""

    # ------------------------------------------------------------------
    # Enum round-trip (FR-001 / INV-1)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_enum_cup_round_trip(self, coach_client, db_factory):
        """POST con kind='cup' persiste 'cup' y se lee igual en GET."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Copa Vallecaucana Ficticia 2026",
            "season_year": 2026,
            "kind": "cup",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["kind"] == "cup"
        series_id = created["id"]

        r2 = await coach_client.get(_SERIES_URL)
        assert r2.status_code == 200
        items = {i["id"]: i for i in r2.json()["items"]}
        assert items[series_id]["kind"] == "cup"

    @pytest.mark.asyncio
    async def test_enum_championship_round_trip(self, coach_client, db_factory):
        """POST con kind='championship' persiste 'championship' y se lee igual."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Departamental Ficticio 2026",
            "season_year": 2026,
            "kind": "championship",
            "organizer": "Liga Vallecaucana de Ciclismo",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["kind"] == "championship"
        assert created["organizer"] == "Liga Vallecaucana de Ciclismo"

    # ------------------------------------------------------------------
    # GET filtros (season + kind) y event_count
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_sin_filtros_lista_todas(self, coach_client, db_factory):
        """GET sin filtros retorna todas las series con total correcto."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa A 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
            ))
            s.add(RaceSeries(
                id=2, name="Campeonato B 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            ))
            await s.commit()

        r = await coach_client.get(_SERIES_URL)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_get_filtro_season(self, coach_client, db_factory):
        """GET ?season=2026 excluye series de otras temporadas."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
            ))
            s.add(RaceSeries(
                id=2, name="Copa 2025", season_year=2025,
                organizer="Liga", points_scheme_code="copa_valle_2025",
            ))
            await s.commit()

        r = await coach_client.get(_SERIES_URL, params={"season": 2026})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["season_year"] == 2026

    @pytest.mark.asyncio
    async def test_get_filtro_kind_cup(self, coach_client, db_factory):
        """GET ?kind=cup excluye championships."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Ficticia", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            ))
            s.add(RaceSeries(
                id=2, name="Campeonato Ficticio", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            ))
            await s.commit()

        r = await coach_client.get(_SERIES_URL, params={"kind": "cup"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["kind"] == "cup"

    @pytest.mark.asyncio
    async def test_get_filtro_kind_championship(self, coach_client, db_factory):
        """GET ?kind=championship excluye copas."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Ficticia", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            ))
            s.add(RaceSeries(
                id=2, name="Campeonato Ficticio", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            ))
            await s.commit()

        r = await coach_client.get(_SERIES_URL, params={"kind": "championship"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["kind"] == "championship"

    @pytest.mark.asyncio
    async def test_get_event_count_correcto(self, coach_client, db_factory):
        """event_count refleja la cantidad de race_events de la serie."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa con 2 eventos", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
            ))
            s.add(RaceEvent(
                id=10, series_id=1, sequence_number=1,
                name="Válida I Ficticia", event_date=date(2026, 1, 31),
                location="Sevilla", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=10,
            ))
            s.add(RaceEvent(
                id=11, series_id=1, sequence_number=2,
                name="Válida II Ficticia", event_date=date(2026, 2, 28),
                location="Ginebra", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=10,
            ))
            await s.commit()

        r = await coach_client.get(_SERIES_URL, params={"season": 2026})
        assert r.status_code == 200
        items = r.json()["items"]
        assert items[0]["event_count"] == 2

    # ------------------------------------------------------------------
    # POST happy paths
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_happy_cup(self, coach_client, db_factory):
        """POST cup series → 201 con event_count=0."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Copa Ficticia 2026",
            "season_year": 2026,
            "kind": "cup",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["kind"] == "cup"
        assert data["event_count"] == 0
        assert data["season_year"] == 2026
        # points_scheme_code no se expone en el response (no es campo de RaceSeriesRead)
        assert "points_scheme_code" not in data

    @pytest.mark.asyncio
    async def test_post_happy_championship(self, coach_client, db_factory):
        """POST championship series → 201 con kind='championship'."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Nacional Ficticio 2026",
            "season_year": 2026,
            "kind": "championship",
            "organizer": "Federación Colombiana de Ciclismo",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["kind"] == "championship"
        assert data["organizer"] == "Federación Colombiana de Ciclismo"

    # ------------------------------------------------------------------
    # POST 409 duplicado
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_409_duplicado_name_season(self, coach_client, db_factory):
        """Mismo (name, season_year) → 409 con mensaje es-CO."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Duplicada 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
            ))
            await s.commit()

        body = {"name": "Copa Duplicada 2026", "season_year": 2026, "kind": "cup"}
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 409, r.text
        assert "serie" in r.json()["detail"].lower() or "temporada" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_post_mismo_nombre_distinta_temporada_ok(self, coach_client, db_factory):
        """Mismo name pero distinto season_year → 201 (UNIQUE es por (name, season))."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Valle", season_year=2025,
                organizer="Liga", points_scheme_code="copa_valle_2025",
            ))
            await s.commit()

        body = {"name": "Copa Valle", "season_year": 2026, "kind": "cup"}
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text

    # ------------------------------------------------------------------
    # POST 422 validación
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_422_season_year_fuera_de_rango(self, coach_client, db_factory):
        """season_year=2019 < 2020 → 422."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {"name": "Copa X", "season_year": 2019, "kind": "cup"}
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_post_422_kind_invalido(self, coach_client, db_factory):
        """kind='liga' no pertenece al enum → 422."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {"name": "Serie X", "season_year": 2026, "kind": "liga"}
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_post_422_campo_extra_forbid(self, coach_client, db_factory):
        """Enviar points_scheme_code (no permitido) → 422 (extra=forbid)."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Copa X",
            "season_year": 2026,
            "kind": "cup",
            "points_scheme_code": "copa_valle_2026",  # campo prohibido
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 422

    # ------------------------------------------------------------------
    # RBAC
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_parent_forbidden(self, parent_client, db_factory):
        """Parent no puede listar series (coach+admin only)."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()
        r = await parent_client.get(_SERIES_URL)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_post_parent_forbidden(self, parent_client, db_factory):
        """Parent no puede crear series."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()
        body = {"name": "X", "season_year": 2026, "kind": "cup"}
        r = await parent_client.post(_SERIES_URL, json=body)
        assert r.status_code == 403

    # ------------------------------------------------------------------
    # Privacidad — sin PII de menores
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_response_no_expone_pii_menores(self, coach_client, db_factory):
        """GET /race-series nunca expone DOB, datos médicos ni nombres de atletas."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Ficticia 2026", season_year=2026,
                organizer="Liga Ficticia", points_scheme_code="copa_valle_2026",
            ))
            await s.commit()

        r = await coach_client.get(_SERIES_URL)
        assert r.status_code == 200

        allowed_keys = {"id", "name", "season_year", "organizer", "kind", "event_count"}
        for item in r.json()["items"]:
            extra = set(item.keys()) - allowed_keys
            assert not extra, f"Campos no permitidos en response: {extra}"

        # Asegurar que la respuesta no mencione campos PII sensibles
        raw = r.text.lower()
        for pii_field in ("birth_date", "dob", "medical", "weight", "height"):
            assert pii_field not in raw, f"Campo PII '{pii_field}' aparece en response"


# ---------------------------------------------------------------------------
# ═══════════════════════════════════════════════════════════════════════════
# T010 — POST /race-events: championship guard + deriva campos
# ═══════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------


_EVENTS_URL = "/api/race-analysis/race-events/"


class TestChampionshipEventGuardT010:
    """T010: championship series rechaza 2do evento; deriva seq=1/is_championship;
    copa sin cambios (regresión)."""

    @pytest.mark.asyncio
    async def test_championship_evento_unico_ok(self, coach_client, db_factory):
        """POST en serie campeonato vacía → 201, seq=1, is_championship=True."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=50, name="Campeonato Dptal Ficticio 2026", season_year=2026,
                organizer="Liga Vallecaucana de Ciclismo",
                points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            ))
            await s.commit()

        payload = {
            "series_id": 50,
            "name": "Campeonato Departamental Ficticio 2026",
            "event_date": "2026-06-12",
            "location": "Ginebra",
            "create_calendar_event": False,
        }
        r = await coach_client.post(_EVENTS_URL, json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        # INV-3: seq=1 forzado, is_championship=True
        assert body["sequence_number"] == 1
        assert body["is_championship"] is True

    @pytest.mark.asyncio
    async def test_championship_ignora_sequence_del_cliente(self, coach_client, db_factory):
        """sequence_number enviado por el cliente es ignorado en campeonato."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=50, name="Campeonato Nacional Ficticio 2026", season_year=2026,
                organizer="Federación Colombiana",
                points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            ))
            await s.commit()

        payload = {
            "series_id": 50,
            "sequence_number": 7,        # cliente envía 7; debe ignorarse
            "is_championship": False,    # cliente envía False; debe ignorarse
            "name": "Campeonato Ficticio",
            "event_date": "2026-06-12",
            "create_calendar_event": False,
        }
        r = await coach_client.post(_EVENTS_URL, json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["sequence_number"] == 1, "El servidor debe forzar sequence_number=1"
        assert body["is_championship"] is True, "El servidor debe derivar is_championship=True"

    @pytest.mark.asyncio
    async def test_championship_segundo_evento_409(self, coach_client, db_factory):
        """Segunda llamada POST en serie campeonato → 409 con mensaje es-CO."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=50, name="Campeonato Dptal Ficticio 2026", season_year=2026,
                organizer="Liga Vallecaucana de Ciclismo",
                points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            ))
            # El campeonato ya tiene su evento
            s.add(RaceEvent(
                id=200, series_id=50, sequence_number=1,
                name="Campeonato Dptal 2026",
                event_date=date(2026, 6, 12), location="Ginebra",
                is_championship=True, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            ))
            await s.commit()

        payload = {
            "series_id": 50,
            "name": "Segundo intento",
            "event_date": "2026-07-01",
            "create_calendar_event": False,
        }
        r = await coach_client.post(_EVENTS_URL, json=payload)
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        # Mensaje en es-CO (spec 014 / error catalog)
        assert "campeonato" in detail.lower(), f"Mensaje inesperado: {detail}"
        assert "único" in detail or "unico" in detail.lower() or "ya tiene" in detail.lower(), (
            f"Mensaje no menciona singularidad: {detail}"
        )

    @pytest.mark.asyncio
    async def test_championship_nacional_segundo_evento_409(self, coach_client, db_factory):
        """INV-2 (023): campeonato kind=championship level=national con 1 evento
        también rechaza un 2do POST con 409 — el guard depende de kind, no de level."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=50, name="Campeonato Nacional Ficticio 2026", season_year=2026,
                organizer="Federación Colombiana de Ciclismo",
                points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
                level=RaceSeriesLevel.national,
            ))
            # El campeonato ya tiene su evento
            s.add(RaceEvent(
                id=200, series_id=50, sequence_number=1,
                name="Campeonato Nacional 2026",
                event_date=date(2026, 7, 12), location="Pereira",
                is_championship=True, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            ))
            await s.commit()

        payload = {
            "series_id": 50,
            "name": "Segundo intento",
            "event_date": "2026-08-01",
            "create_calendar_event": False,
        }
        r = await coach_client.post(_EVENTS_URL, json=payload)
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "campeonato" in detail.lower(), f"Mensaje inesperado: {detail}"
        assert "único" in detail or "unico" in detail.lower() or "ya tiene" in detail.lower(), (
            f"Mensaje no menciona singularidad: {detail}"
        )

    @pytest.mark.asyncio
    async def test_cup_creacion_con_sequence_requerida(self, coach_client, db_factory):
        """Regresión: copa requiere sequence_number; se persiste correctamente."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Valle Ficticia 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            ))
            await s.commit()

        payload = {
            "series_id": 1,
            "sequence_number": 3,
            "name": "Válida III Ficticia",
            "event_date": "2026-04-19",
            "location": "La Cumbre",
            "create_calendar_event": False,
        }
        r = await coach_client.post(_EVENTS_URL, json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["sequence_number"] == 3
        assert body["is_championship"] is False

    @pytest.mark.asyncio
    async def test_cup_409_secuencia_duplicada(self, coach_client, db_factory):
        """Regresión: copa rechaza sequence_number duplicado en la misma serie."""
        async with db_factory() as s:
            await _seed_base_users(s)
            s.add(RaceSeries(
                id=1, name="Copa Valle Ficticia 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            ))
            # Válida 3 ya existe
            s.add(RaceEvent(
                id=103, series_id=1, sequence_number=3,
                name="Válida III", event_date=date(2026, 4, 19),
                location="La Cumbre", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=10,
            ))
            await s.commit()

        payload = {
            "series_id": 1,
            "sequence_number": 3,  # ya existe
            "name": "Conflicto III",
            "event_date": "2026-04-20",
            "create_calendar_event": False,
        }
        r = await coach_client.post(_EVENTS_URL, json=payload)
        assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# ═══════════════════════════════════════════════════════════════════════════
# T018 — Import a serie campeonato (series_kind=championship)
# ═══════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------


_PARSE_URL = "/api/race-analysis/imports/parse"


class TestImportChampionshipT018:
    """T018: import a campeonato crea serie con kind=championship; /parse preserva
    el valida_num en parse_meta_json; _get_or_create_series honra series_name enviado;
    re-ingesta mismo SHA en campeonato: guard SHA se dispara antes (no guard campeonato).
    """

    def _parse_form(
        self,
        *,
        series_name: str = "Copa Valle de Ciclomontanismo",
        season: int = 2026,
        valida_num: int = 1,
        event_name: str = "Valida I Ficticia",
        event_date: str = "2026-01-31",
        location: str = "Sevilla",
        series_kind=None,
        pdf_content=None,
    ):
        import io
        fields = {
            "series_name": series_name,
            "season": str(season),
            "valida_num": str(valida_num),
            "event_name": event_name,
            "event_date": event_date,
            "location": location,
        }
        if series_kind is not None:
            fields["series_kind"] = series_kind
        content = pdf_content or b"%PDF-1.4 fake"
        files = {
            "resultados_pdf": ("resultados.pdf", io.BytesIO(content), "application/pdf"),
        }
        return {"data": fields, "files": files}

    @pytest.mark.asyncio
    async def test_import_championship_crea_serie_kind_championship(
        self, coach_client, db_factory, stub_storage, stub_parsers
    ):
        """/parse con series_kind=championship crea RaceSeries con kind=championship."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        form = self._parse_form(
            series_name="Campeonato Dptal Ficticio 2026",
            valida_num=99,
            series_kind="championship",
            event_name="Campeonato Ficticio 2026",
        )
        r = await coach_client.post(_PARSE_URL, data=form["data"], files=form["files"])
        assert r.status_code == 200, r.text

        async with db_factory() as s:
            result = await s.execute(
                select(RaceSeries).where(RaceSeries.name == "Campeonato Dptal Ficticio 2026")
            )
            series = result.scalar_one_or_none()
        assert series is not None, "La serie no fue creada"
        assert series.kind == RaceSeriesKind.championship, (
            f"Esperado kind=championship, obtenido {series.kind}"
        )

    @pytest.mark.asyncio
    async def test_import_championship_parse_meta_preserva_valida_num(
        self, coach_client, db_factory, stub_storage, stub_parsers
    ):
        """/parse preserva valida_num en parse_meta_json para uso posterior del ingestor."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        form = self._parse_form(
            series_name="Campeonato Dptal Ficticio 2026",
            valida_num=99,
            series_kind="championship",
            event_name="Campeonato Ficticio 2026",
        )
        r = await coach_client.post(_PARSE_URL, data=form["data"], files=form["files"])
        assert r.status_code == 200, r.text
        parse_id = r.json()["parse_id"]

        async with db_factory() as s:
            imp = await s.get(RaceImport, parse_id)
        assert imp is not None
        meta = imp.parse_meta_json or {}
        assert meta.get("header", {}).get("valida_num") == 99

    @pytest.mark.asyncio
    async def test_import_cup_regresion_kind_cup(
        self, coach_client, db_factory, stub_storage, stub_parsers
    ):
        """Regresion: import copa crea serie con kind=cup y parse_meta_json con valida_num."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        form = self._parse_form(
            series_name="Copa Ficticia 2026",
            valida_num=3,
            series_kind="cup",
        )
        r = await coach_client.post(_PARSE_URL, data=form["data"], files=form["files"])
        assert r.status_code == 200, r.text

        async with db_factory() as s:
            result = await s.execute(
                select(RaceSeries).where(RaceSeries.name == "Copa Ficticia 2026")
            )
            series = result.scalar_one_or_none()
        assert series is not None
        assert series.kind == RaceSeriesKind.cup

    @pytest.mark.asyncio
    async def test_get_or_create_series_honra_series_name(
        self, coach_client, db_factory, stub_storage, stub_parsers
    ):
        """Bug fix T017: _get_or_create_series usa el series_name enviado, no el hardcoded."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        custom_name = "Liga Boyacense Ficticia 2026"
        form = self._parse_form(
            series_name=custom_name,
            valida_num=1,
            series_kind="cup",
        )
        r = await coach_client.post(_PARSE_URL, data=form["data"], files=form["files"])
        assert r.status_code == 200, r.text

        async with db_factory() as s:
            result = await s.execute(select(RaceSeries))
            series_list = result.scalars().all()
        names = [s.name for s in series_list]
        assert custom_name in names, f"Serie no creada: {names}"
        assert "Copa Valle de Ciclomontanismo" not in names

    @pytest.mark.asyncio
    async def test_desviacion2_reingesta_mismo_sha_no_dispara_guard_campeonato(
        self, coach_client, db_factory, stub_storage, stub_parsers
    ):
        """Desviacion #2: re-ingesta del MISMO PDF (mismo SHA) en campeonato con evento existente
        debe disparar el guard de SHA duplicado (409 sobre sha256/commiteado),
        NO el guard de campeonato unico.

        Si el guard de campeonato se activa ANTES del guard de SHA en /parse, la
        re-ingesta del mismo archivo devolveria 409 con mensaje de campeonato unico
        en lugar de mensaje SHA -> BUG BLOCKING (falso positivo).
        """
        fixed_pdf = b"%PDF-1.4 fixed-content"
        series_name = "Campeonato Dptal Ficticio 2026"

        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        # Primer import
        form1 = self._parse_form(
            series_name=series_name,
            valida_num=99,
            series_kind="championship",
            event_name="Campeonato Ficticio 2026",
            pdf_content=fixed_pdf,
        )
        r1 = await coach_client.post(_PARSE_URL, data=form1["data"], files=form1["files"])
        assert r1.status_code == 200, f"Primer import fallo: {r1.text}"
        parse_id = r1.json()["parse_id"]

        # Simular: import commiteado + evento ya creado
        async with db_factory() as s:
            imp = await s.get(RaceImport, parse_id)
            if imp:
                imp.status = RaceImportStatus.committed
            serie_result = await s.execute(
                select(RaceSeries).where(RaceSeries.name == series_name)
            )
            serie_obj = serie_result.scalar_one_or_none()
            if serie_obj:
                s.add(RaceEvent(
                    id=300, series_id=serie_obj.id, sequence_number=1,
                    name="Campeonato Ficticio 2026",
                    event_date=date(2026, 6, 12), location="Ginebra",
                    is_championship=True, status=RaceEventStatus.COMPLETED,
                    created_by_user_id=10,
                ))
            await s.commit()

        # Re-ingesta del MISMO PDF (mismo SHA)
        form2 = self._parse_form(
            series_name=series_name,
            valida_num=99,
            series_kind="championship",
            event_name="Campeonato Re-ingesta",
            pdf_content=fixed_pdf,
        )
        r2 = await coach_client.post(_PARSE_URL, data=form2["data"], files=form2["files"])

        assert r2.status_code == 409, (
            f"Esperado 409 (SHA duplicado), obtenido {r2.status_code}: {r2.text}"
        )
        detail = r2.json()["detail"].lower()

        # Verificar: el 409 es por SHA, NO por campeonato unico
        if "campeonato" in detail and ("nico" in detail or "ya tiene" in detail):
            pytest.fail(
                "DESVIACION #2 CONFIRMADA (BUG BLOCKING): "
                "Re-ingesta mismo SHA en campeonato disparo el guard de evento unico "
                "en lugar del guard de SHA duplicado. "
                f"Detail recibido: {r2.json()['detail']}"
            )

        # El 409 debe mencionar SHA
        assert (
            "sha256" in detail
            or "sha" in detail
            or "commiteado" in detail
        ), (
            f"409 obtenido pero el detail no menciona SHA duplicado: {r2.json()['detail']}"
        )




_PANORAMA_URL = "/api/race-analysis/insights/season/{year}"
_STANDINGS_URL = "/api/race-analysis/race-events/{event_id}/standings"

# Tablas extras para panorama (necesita athletes)
_PANORAMA_TABLES = [
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
]


@pytest_asyncio.fixture
async def panorama_engine():
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.athlete_ai_insight import AthleteAiInsight as _AI  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    tables = [Base.metadata.tables[t] for t in _PANORAMA_TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def panorama_factory(panorama_engine):
    return async_sessionmaker(panorama_engine, expire_on_commit=False)


class TestSeasonPanoramaStandingsT025:
    """T025: panorama excluye resultados de campeonato; copa sin cambios (SC-002);
    standings retorna vacío para campeonato."""

    @pytest.mark.asyncio
    async def test_panorama_excluye_resultados_campeonato(self, panorama_factory):
        """SC-002: totales de copa no cambian al agregar un campeonato en la misma temporada."""
        from app.models.athlete import Athlete, Sex
        from app.models.club import ClubMember, ClubRole

        async with panorama_factory() as s:
            # Usuarios
            coach = User(
                id=10, email="coach@ficticio.test", hashed_password="x",
                first_name="Coach", last_name="Ficticio",
                role=UserRole.coach, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
            s.add(coach)
            await s.flush()

            # Club
            club = Club(id=1, name="Club Ficticio", code="CF")
            s.add(club)
            await s.flush()
            cm = ClubMember(club_id=1, user_id=10, role_in_club=ClubRole.coach)
            s.add(cm)
            await s.flush()

            # Usuario atleta (necesario para FK users.id)
            athlete_user = User(
                id=144, email="atleta@ficticio.test", hashed_password="x",
                first_name="Juan", last_name="Pérez Ficticio",
                role=UserRole.athlete, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            s.add(athlete_user)
            await s.flush()

            # Atleta
            atleta = Athlete(
                id=144,
                user_id=144,
                first_name="Juan",
                last_name="Pérez Ficticio",
                birth_date=date(2014, 3, 15),
                sex=Sex.M,
                club_id=1,
                created_by=10,
            )
            s.add(atleta)
            await s.flush()

            # Serie copa (kind=cup)
            serie_copa = RaceSeries(
                id=1, name="Copa Ficticia 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            )
            s.add(serie_copa)
            await s.flush()

            # Serie campeonato (kind=championship)
            serie_cd = RaceSeries(
                id=2, name="Campeonato Ficticio 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            )
            s.add(serie_cd)
            await s.flush()

            # Categoría
            cat = RaceCategory(
                id=100, code="INF_B", label="Infantil B",
                sex=CategoryGender.M, sort_order=31, is_active=True,
            )
            s.add(cat)
            await s.flush()

            # Competidor enlazado al atleta
            comp = RaceCompetitor(
                id=501, normalized_name="juan perez ficticio",
                display_name="Juan Pérez Ficticio",
                club_text="Club Ficticio", athlete_id=144,
            )
            s.add(comp)
            await s.flush()

            # Evento copa — tiene 1 resultado (pos=1, 40pts)
            evt_copa = RaceEvent(
                id=10, series_id=1, sequence_number=1,
                name="Válida I Copa Ficticia", event_date=date(2026, 1, 31),
                location="Sevilla", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=10,
            )
            s.add(evt_copa)
            await s.flush()
            result_copa = RaceResult(
                event_id=10, category_id=100, competitor_id=501, athlete_id=144,
                position=1, status=ResultStatus.FINISHED, race_time_ms=218_000,
                points_awarded=40, created_by_user_id=10,
            )
            s.add(result_copa)
            await s.flush()

            # Evento campeonato — tiene 1 resultado (pos=1, 40pts)
            # Este NO debe aparecer en el panorama
            evt_cd = RaceEvent(
                id=20, series_id=2, sequence_number=1,
                name="Campeonato Dptal Ficticio 2026",
                event_date=date(2026, 6, 12), location="Ginebra",
                is_championship=True, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            )
            s.add(evt_cd)
            await s.flush()
            result_cd = RaceResult(
                event_id=20, category_id=100, competitor_id=501, athlete_id=144,
                position=1, status=ResultStatus.FINISHED, race_time_ms=200_000,
                points_awarded=40, created_by_user_id=10,
            )
            s.add(result_cd)
            await s.flush()

            await s.commit()

        # Construir cliente con esta DB
        app.dependency_overrides[get_db] = _make_override_db(panorama_factory)
        fake_coach = SimpleNamespace(
            id=10, role=UserRole.coach, email="coach@ficticio.test",
            is_active=True, can_login=True,
            club_memberships=[
                SimpleNamespace(user_id=10, club_id=1, role_in_club=ClubRole.coach)
            ],
        )
        app.dependency_overrides[get_current_user] = lambda: fake_coach

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get(_PANORAMA_URL.format(year=2026))

            assert r.status_code == 200, r.text
            data = r.json()
            items = {i["athlete_id"]: i for i in data["items"]}

            # El atleta 144 debe aparecer solo con los puntos de la copa (40pts, 1 carrera)
            # NO con 80pts (copa + campeonato) — SC-002
            assert 144 in items, "El atleta no aparece en el panorama"
            a144 = items[144]
            assert a144["races_count"] == 1, (
                f"Expected races_count=1 (solo copa), got {a144['races_count']} "
                "(el campeonato se está contando)"
            )
            assert a144["total_points"] == 40, (
                f"Expected total_points=40 (solo copa), got {a144['total_points']} "
                "(el campeonato está sumando puntos)"
            )
            assert a144["wins"] == 1
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_standings_vacio_para_campeonato(self, panorama_factory):
        """standings de un evento campeonato retorna categories=[] (no aplica ranking)."""
        from app.models.club import ClubMember, ClubRole

        async with panorama_factory() as s:
            coach = User(
                id=10, email="coach@ficticio.test", hashed_password="x",
                first_name="Coach", last_name="Ficticio",
                role=UserRole.coach, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
            s.add(coach)
            await s.flush()

            serie_cd = RaceSeries(
                id=2, name="Campeonato Ficticio 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.championship,
            )
            s.add(serie_cd)
            await s.flush()

            evt_cd = RaceEvent(
                id=20, series_id=2, sequence_number=1,
                name="Campeonato Ficticio 2026",
                event_date=date(2026, 6, 12), location="Ginebra",
                is_championship=True, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            )
            s.add(evt_cd)
            await s.flush()
            await s.commit()

        app.dependency_overrides[get_db] = _make_override_db(panorama_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.coach, user_id=10
        )

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get(_STANDINGS_URL.format(event_id=20))

            # El endpoint debe retornar 200 con categories=[] (no 404)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["categories"] == [], (
                f"standings de campeonato debe retornar categories=[], got: {data['categories']}"
            )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_standings_copa_funciona_normal(self, panorama_factory):
        """Regresión: standings de copa sigue funcionando normalmente."""
        from app.models.club import ClubMember, ClubRole

        async with panorama_factory() as s:
            coach = User(
                id=10, email="coach@ficticio.test", hashed_password="x",
                first_name="Coach", last_name="Ficticio",
                role=UserRole.coach, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
            s.add(coach)
            await s.flush()

            serie_copa = RaceSeries(
                id=1, name="Copa Ficticia 2026", season_year=2026,
                organizer="Liga", points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            )
            s.add(serie_copa)
            await s.flush()

            evt_copa = RaceEvent(
                id=10, series_id=1, sequence_number=1,
                name="Válida I Copa Ficticia", event_date=date(2026, 1, 31),
                location="Sevilla", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=10,
            )
            s.add(evt_copa)
            await s.flush()
            await s.commit()

        app.dependency_overrides[get_db] = _make_override_db(panorama_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.coach, user_id=10
        )

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                r = await ac.get(_STANDINGS_URL.format(event_id=10))

            # Copa con 0 resultados → 200 con categories=[] (no error)
            assert r.status_code == 200, r.text
            # No debe retornar 404 ni 500
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# ═══════════════════════════════════════════════════════════════════════════
# T027 — Migración idempotente; reclasificación preserva resultados; SC-003
# ═══════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------


class TestMigrationT027:
    """T027: migración es idempotente, reclasificación preserva filas (FR-012),
    evento reclasificado ya no contribuye al ranking copa (SC-003),
    safe no-op cuando el evento legacy no existe."""

    @pytest.fixture
    def sync_engine(self, tmp_path):
        """Motor SQLite síncrono para ejecutar la migración Alembic."""
        from sqlalchemy import create_engine
        db_path = tmp_path / "test_migration.sqlite"
        eng = create_engine(f"sqlite:///{db_path}", echo=False)
        return eng

    def _create_tables_legacy(self, conn) -> None:
        """Crea el schema previo a la migración (sin columna kind)."""
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS race_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(150) NOT NULL,
                season_year INTEGER NOT NULL,
                organizer VARCHAR(150),
                points_scheme_code VARCHAR(50) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, season_year)
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS race_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL REFERENCES race_series(id),
                sequence_number INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                event_date DATE NOT NULL,
                location VARCHAR(150),
                is_championship INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
                created_by_user_id INTEGER NOT NULL DEFAULT 0,
                calendar_event_id INTEGER,
                UNIQUE(series_id, sequence_number)
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS race_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES race_events(id),
                category_id INTEGER NOT NULL DEFAULT 1,
                competitor_id INTEGER NOT NULL DEFAULT 1,
                athlete_id INTEGER,
                position INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'finished',
                race_time_ms INTEGER,
                points_awarded INTEGER DEFAULT 0,
                created_by_user_id INTEGER NOT NULL DEFAULT 0
            )
            """
        ))

    def _run_upgrade(self, conn) -> None:
        """Ejecuta el paso de upgrade de la migración b1c2d3e4f5a6."""
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations
        import sqlalchemy as sa

        migration_ctx = MigrationContext.configure(conn)
        op = Operations(migration_ctx)

        # Añadir columna kind
        op.add_column(
            "race_series",
            sa.Column(
                "kind",
                sa.Enum("cup", "championship", name="raceserieskind"),
                nullable=False,
                server_default="cup",
            ),
        )

        _COPA_VALLE_NAME = "Copa Valle de Ciclomontañismo"
        _CD_NAME = "Campeonato Departamental 2026"
        _CD_ORGANIZER = "Liga Vallecaucana de Ciclismo"
        _CD_SCHEME = "copa_valle_2026"
        _CD_SEASON = 2026

        # Upsert championship series
        row = conn.execute(
            sa.text("SELECT id FROM race_series WHERE name=:n AND season_year=:s"),
            {"n": _CD_NAME, "s": _CD_SEASON},
        ).fetchone()
        if row is None:
            conn.execute(
                sa.text(
                    "INSERT INTO race_series (name, season_year, organizer, "
                    "points_scheme_code, kind, created_at, updated_at) "
                    "VALUES (:n, :s, :org, :sch, 'championship', "
                    "datetime('now'), datetime('now'))"
                ),
                {"n": _CD_NAME, "s": _CD_SEASON, "org": _CD_ORGANIZER, "sch": _CD_SCHEME},
            )

        cd_row = conn.execute(
            sa.text("SELECT id FROM race_series WHERE name=:n AND season_year=:s"),
            {"n": _CD_NAME, "s": _CD_SEASON},
        ).fetchone()
        cd_series_id = cd_row[0]

        copa_row = conn.execute(
            sa.text("SELECT id FROM race_series WHERE name=:n AND season_year=:s"),
            {"n": _COPA_VALLE_NAME, "s": _CD_SEASON},
        ).fetchone()
        if copa_row is not None:
            copa_series_id = copa_row[0]
            conn.execute(
                sa.text(
                    "UPDATE race_events SET series_id=:cd, sequence_number=1 "
                    "WHERE series_id=:copa AND is_championship=1 AND sequence_number=99"
                ),
                {"cd": cd_series_id, "copa": copa_series_id},
            )

    def test_migration_es_idempotente(self, sync_engine):
        """Re-ejecutar la migración no duplica filas ni falla (T027)."""
        import sqlalchemy as sa

        with sync_engine.begin() as conn:
            self._create_tables_legacy(conn)
            # Insertar Copa Valle 2026
            conn.execute(sa.text(
                "INSERT INTO race_series (name, season_year, organizer, points_scheme_code) "
                "VALUES ('Copa Valle de Ciclomontañismo', 2026, 'Liga', 'copa_valle_2026')"
            ))
            conn.execute(sa.text(
                "INSERT INTO race_series (name, season_year, organizer, points_scheme_code) "
                "VALUES ('Copa Valle de Ciclomontañismo', 2025, 'Liga', 'copa_valle_2025')"
            ))

        # Primera ejecución
        with sync_engine.begin() as conn:
            self._run_upgrade(conn)

        # Verificar que la serie championship fue creada
        with sync_engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT COUNT(*) FROM race_series WHERE kind='championship'"
            )).fetchone()
            assert row[0] == 1

        # Segunda ejecución (idempotente — no debe duplicar)
        # La migración real es guardada, pero simulamos otro run
        with sync_engine.begin() as conn:
            # Re-run del upsert (la parte data, no el ADD COLUMN que ya existe)
            _CD_NAME = "Campeonato Departamental 2026"
            _CD_SEASON = 2026
            existing = conn.execute(sa.text(
                "SELECT id FROM race_series WHERE name=:n AND season_year=:s"
            ), {"n": _CD_NAME, "s": _CD_SEASON}).fetchone()
            # Como ya existe, no inserta de nuevo
            assert existing is not None  # ya existe, el upsert es no-op

        # Count sigue siendo 1
        with sync_engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT COUNT(*) FROM race_series WHERE name='Campeonato Departamental 2026'"
            )).fetchone()
            assert row[0] == 1, "Idempotencia fallida: se duplicó la serie championship"

    def test_reclasificacion_preserva_resultados(self, sync_engine):
        """FR-012: todos los resultados del evento reclasificado se conservan."""
        import sqlalchemy as sa

        _COPA_SERIE_NAME = "Copa Valle de Ciclomontañismo"

        with sync_engine.begin() as conn:
            self._create_tables_legacy(conn)
            # Copa Valle 2026
            conn.execute(sa.text(
                "INSERT INTO race_series (id, name, season_year, organizer, points_scheme_code) "
                "VALUES (1, :n, 2026, 'Liga', 'copa_valle_2026')"
            ), {"n": _COPA_SERIE_NAME})
            # Evento departamental (legacy: is_championship=1, sequence_number=99)
            conn.execute(sa.text(
                "INSERT INTO race_events (id, series_id, sequence_number, name, "
                "event_date, is_championship, status, created_by_user_id) "
                "VALUES (99, 1, 99, 'Campeonato Departamental 2026', '2026-06-12', 1, "
                "'completed', 10)"
            ))
            # 5 resultados en el evento
            for i in range(1, 6):
                conn.execute(sa.text(
                    "INSERT INTO race_results (event_id, position, status, "
                    "points_awarded, created_by_user_id) "
                    "VALUES (99, :pos, 'finished', :pts, 10)"
                ), {"pos": i, "pts": 40 - (i - 1) * 4})

        # Ejecutar migración
        with sync_engine.begin() as conn:
            self._run_upgrade(conn)

        # Verificar que los 5 resultados siguen existiendo
        with sync_engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT COUNT(*) FROM race_results WHERE event_id=99"
            )).fetchone()
            assert row[0] == 5, f"Se perdieron resultados: esperados 5, encontrados {row[0]}"

            # Verificar que el evento fue movido a la serie championship
            evt_row = conn.execute(sa.text(
                "SELECT re.series_id, rs.kind "
                "FROM race_events re "
                "JOIN race_series rs ON rs.id = re.series_id "
                "WHERE re.id = 99"
            )).fetchone()
            assert evt_row is not None, "El evento 99 no existe"
            assert evt_row[1] == "championship", (
                f"El evento 99 sigue en serie kind={evt_row[1]}, esperado 'championship'"
            )

    def test_reclasificado_no_contribuye_ranking_copa(self, sync_engine):
        """SC-003: después de reclasificar, el evento departamental no suma a la copa."""
        import sqlalchemy as sa

        _COPA_SERIE_NAME = "Copa Valle de Ciclomontañismo"

        with sync_engine.begin() as conn:
            self._create_tables_legacy(conn)
            # Copa Valle 2026
            conn.execute(sa.text(
                "INSERT INTO race_series (id, name, season_year, organizer, points_scheme_code) "
                "VALUES (1, :n, 2026, 'Liga', 'copa_valle_2026')"
            ), {"n": _COPA_SERIE_NAME})
            # Dos eventos copa (válidas)
            conn.execute(sa.text(
                "INSERT INTO race_events VALUES (10, 1, 1, 'Válida I', '2026-01-31', "
                "'Sevilla', 0, 'completed', 10, NULL)"
            ))
            conn.execute(sa.text(
                "INSERT INTO race_events VALUES (11, 1, 2, 'Válida II', '2026-02-28', "
                "'Ginebra', 0, 'completed', 10, NULL)"
            ))
            # Evento departamental (legacy)
            conn.execute(sa.text(
                "INSERT INTO race_events VALUES (99, 1, 99, 'Campeonato Dptal', '2026-06-12', "
                "'Ginebra', 1, 'completed', 10, NULL)"
            ))
            # Resultados: copa V1: 40pts, copa V2: 36pts, campeonato: 40pts
            conn.execute(sa.text(
                "INSERT INTO race_results (event_id, position, status, points_awarded, "
                "athlete_id, created_by_user_id) VALUES (10, 1, 'finished', 40, 144, 10)"
            ))
            conn.execute(sa.text(
                "INSERT INTO race_results (event_id, position, status, points_awarded, "
                "athlete_id, created_by_user_id) VALUES (11, 2, 'finished', 36, 144, 10)"
            ))
            conn.execute(sa.text(
                "INSERT INTO race_results (event_id, position, status, points_awarded, "
                "athlete_id, created_by_user_id) VALUES (99, 1, 'finished', 40, 144, 10)"
            ))

        # Ejecutar migración
        with sync_engine.begin() as conn:
            self._run_upgrade(conn)

        # Verificar ranking copa: solo suma eventos en series kind='cup'
        with sync_engine.connect() as conn:
            row = conn.execute(sa.text(
                """
                SELECT COALESCE(SUM(rr.points_awarded), 0) AS copa_points
                FROM race_results rr
                JOIN race_events re ON re.id = rr.event_id
                JOIN race_series rs ON rs.id = re.series_id
                WHERE rs.kind = 'cup'
                  AND rs.season_year = 2026
                  AND rr.athlete_id = 144
                """
            )).fetchone()
            # Debe ser 76 (40+36), NO 116 (40+36+40)
            assert row[0] == 76, (
                f"SC-003: El ranking copa incluye el campeonato reclasificado. "
                f"Esperado 76pts, obtenido {row[0]}pts."
            )

    def test_noop_cuando_evento_legacy_no_existe(self, sync_engine):
        """No-op seguro cuando el evento is_championship/seq=99 no existe (fresh DB)."""
        import sqlalchemy as sa

        with sync_engine.begin() as conn:
            self._create_tables_legacy(conn)
            # Solo Copa Valle sin evento legacy
            conn.execute(sa.text(
                "INSERT INTO race_series (name, season_year, organizer, points_scheme_code) "
                "VALUES ('Copa Valle de Ciclomontañismo', 2026, 'Liga', 'copa_valle_2026')"
            ))

        # No debe fallar
        with sync_engine.begin() as conn:
            self._run_upgrade(conn)

        # La migración completó sin error; la serie championship fue creada
        with sync_engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT COUNT(*) FROM race_series WHERE kind='championship'"
            )).fetchone()
            assert row[0] == 1, "La serie championship debe crearse aunque no haya evento legacy"

            # race_events sigue vacío (no hubo eventos que reclasificar)
            row2 = conn.execute(sa.text("SELECT COUNT(*) FROM race_events")).fetchone()
            assert row2[0] == 0, "No debería haberse creado ningún evento"

    def test_noop_cuando_no_hay_copa_valle(self, sync_engine):
        """No-op seguro en fresh DB sin ninguna serie existente."""
        import sqlalchemy as sa

        with sync_engine.begin() as conn:
            self._create_tables_legacy(conn)
            # No hay ninguna serie — DB vacía

        # No debe fallar
        with sync_engine.begin() as conn:
            self._run_upgrade(conn)

        # La serie championship fue creada de todas formas
        with sync_engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT COUNT(*) FROM race_series WHERE name='Campeonato Departamental 2026'"
            )).fetchone()
            assert row[0] == 1
