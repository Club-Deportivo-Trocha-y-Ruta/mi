"""Tests del router CRUD ``/api/race-analysis/race-events/*`` (Fase 1.7+).

Cubre los 4 endpoints nuevos del módulo race-events::

  POST   /api/race-analysis/race-events/                 (coach + admin)
  PATCH  /api/race-analysis/race-events/{race_event_id}  (coach + admin)
  DELETE /api/race-analysis/race-events/{race_event_id}  (admin only)
  GET    /api/race-analysis/race-events/                 (coach + admin, filtros)

El endpoint previo ``PATCH /{id}/conditions`` se cubre en
``test_race_event_conditions.py``; aquí solo se verifica que coexiste sin
regresión por la convivencia de rutas.

Estrategia
----------
- SQLite async in-memory + StaticPool — mismo patrón que ``test_race_imports.py``
  y ``test_race_event_conditions.py``.
- Sin tocar JWT real; override de ``get_current_user`` con stub.
- Fixtures por rol (coach / admin / parent / anon) para minimizar duplicación.
- Datos ficticios (nombres "Coach Ten", "Admin User", etc.) — nunca atletas reales.

Tabla resumen
-------------

POST /
| #  | Caso                                                       | Status |
|----|------------------------------------------------------------|--------|
| 1  | Happy path coach (sin condiciones)                         |  201   |
| 2  | Happy path admin                                           |  201   |
| 3  | POST con condiciones climaticas completas                  |  201   |
| 4  | POST sin condiciones → campos NULL en DB                   |  201   |
| 5  | (series_id, sequence_number) duplicado                     |  409   |
| 6  | series_id inexistente                                      |  422   |
| 7  | Sin token (anon)                                           | 401/403|
| 8  | Parent autenticado                                         |  403   |
| 9  | temperature_c = 51 (fuera de rango)                        |  422   |

PATCH /{id}
| 10 | Coach edita name + event_date                              |  200   |
| 11 | Partial PATCH: solo name → resto intacto                   |  200   |
| 12 | Body vacio `{}`                                            |  200   |
| 13 | sequence_number nuevo ya ocupado                           |  409   |
| 14 | sequence_number nuevo libre                                |  200   |
| 15 | status = cancelled                                         |  200   |
| 16 | Campo extra (extra='forbid')                               |  422   |
| 17 | Parent autenticado                                         |  403   |
| 18 | race_event_id inexistente                                  |  404   |

DELETE /{id}
| 19 | Admin sin dependencias                                     |  204   |
| 20 | Coach (admin only)                                         |  403   |
| 21 | Con race_results asociados                                 |  409   |
| 22 | Con calendar_event.race_event_id asociado                  |  409   |
| 23 | race_event_id inexistente                                  |  404   |

GET /
| 24 | Sin filtros → todos los eventos                            |  200   |
| 25 | Filtrado por season                                        |  200   |
| 26 | Filtrado por status=cancelled                              |  200   |
| 27 | Filtrado por location case-insensitive parcial             |  200   |
| 28 | has_results=true cuando hay RaceResult                     |  200   |
| 29 | has_calendar_event=true cuando hay CalendarEvent vinculado |  200   |
| 30 | conditions_completeness (empty / partial / complete)       |  200   |
| 31 | Parent autenticado                                         |  403   |
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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
from app.models.calendar_event import CalendarEvent, EventStatus, EventType
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus, SurfaceCondition
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers / Fixtures base
# ---------------------------------------------------------------------------


_COLLECTION_URL = "/api/race-analysis/race-events/"
_DETAIL_URL = "/api/race-analysis/race-events/{event_id}"


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    """Stub User equivalente al fixture de ``test_race_event_conditions.py``."""
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite in-memory con el subgrafo de tablas mínimo para los 4 endpoints.

    Incluye ``calendar_events`` + dependencias (``clubs``) porque algunos tests
    (DELETE con calendar vinculado y GET ``has_calendar_event``) necesitan
    insertar filas reales. Igualmente ``race_categories`` + ``race_competitors``
    + ``race_results`` para los tests de ``has_results`` y DELETE 409.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Imports explícitos para registrar metadata.
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.calendar_event import CalendarEvent as _CE  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_event_roster import RaceEventRoster as _RER  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "calendar_events",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_event_roster",
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def _override_db_factory(factory: async_sessionmaker[AsyncSession]):
    """Override de ``get_db`` que sigue el patrón commit/rollback del real."""

    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override_db


# ---------------------------------------------------------------------------
# Seeds — se usan distintos sets segun caso de prueba
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_minimal(db_session_factory):
    """Set base usado por casi todos los tests:

    - Usuarios: coach id=10, admin id=1, parent id=5.
    - Club id=1 (para CalendarEvent).
    - Serie id=1 (Copa Valle 2026) + Serie id=2 (Copa Valle 2025).
    - Evento id=100 (V-IV CALI 2026 — con condiciones completas).
    - Evento id=101 (V-V PALMIRA 2026 — sin condiciones).
    - Evento id=102 (V-I SEVILLA 2025 — temporada distinta, status cancelled).
    """
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="User",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent = User(
            id=5, email="parent@test.com", hashed_password="x",
            first_name="Padre", last_name="Ficticio",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club Trocha y Ruta", code="TYR")
        series_2026 = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        series_2025 = RaceSeries(
            id=2, name="Copa Valle de Ciclomontañismo", season_year=2025,
            organizer="Liga", points_scheme_code="copa_valle_2025",
        )
        # Evento con condiciones COMPLETAS (5 campos).
        evt_completo = RaceEvent(
            id=100,
            series_id=1,
            sequence_number=4,
            name="VALIDA IV CALI",
            event_date=date(2026, 5, 17),
            location="Cali",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
            climate="Soleado",
            temperature_c=Decimal("22.5"),
            surface_condition=SurfaceCondition.seca,
            altitude_msnm=1000,
            weather_notes="Sin viento",
        )
        # Evento SIN condiciones (todos NULL) → conditions_completeness=empty.
        evt_vacio = RaceEvent(
            id=101,
            series_id=1,
            sequence_number=5,
            name="VALIDA V PALMIRA",
            event_date=date(2026, 8, 1),
            location="Palmira",
            is_championship=False,
            status=RaceEventStatus.SCHEDULED,
            created_by_user_id=10,
        )
        # Evento temporada distinta + status=cancelled (para filtros).
        evt_otra_temp = RaceEvent(
            id=102,
            series_id=2,
            sequence_number=1,
            name="VALIDA I SEVILLA 2025",
            event_date=date(2025, 1, 31),
            location="Sevilla",
            is_championship=False,
            status=RaceEventStatus.CANCELLED,
            created_by_user_id=10,
        )
        session.add_all(
            [coach, admin, parent, club, series_2026, series_2025,
             evt_completo, evt_vacio, evt_otra_temp]
        )
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_with_result(db_session_factory, seed_minimal):
    """Agrega un ``RaceResult`` al evento 100 — bloquea DELETE y prende has_results."""
    async with db_session_factory() as session:
        category = RaceCategory(
            id=1, code="TET_CP", label="Tetero CP",
            sex=CategoryGender.M, sort_order=1, is_active=True,
        )
        competitor = RaceCompetitor(
            id=1, normalized_name="ficticio uno",
            display_name="Ficticio Uno", club_text="Club X",
        )
        result = RaceResult(
            event_id=100,
            category_id=1,
            competitor_id=1,
            position=1,
            status=ResultStatus.FINISHED,
            race_time_ms=218_000,
            points_awarded=40,
            created_by_user_id=10,
        )
        session.add_all([category, competitor, result])
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_with_calendar(db_session_factory, seed_minimal):
    """Inserta un CalendarEvent vinculado al race_event id=100."""
    async with db_session_factory() as session:
        cal = CalendarEvent(
            id=500,
            club_id=1,
            event_type=EventType.COMPETITION,
            status=EventStatus.SCHEDULED,
            title="VALIDA IV CALI (calendario)",
            start_at=datetime(2026, 5, 17, 7, 0, 0),
            end_at=datetime(2026, 5, 17, 12, 0, 0),
            race_event_id=100,
            created_by_user_id=10,
        )
        session.add(cal)
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_partial_conditions(db_session_factory):
    """Evento extra (id=103) con conditions parciales (solo 2 de 5 campos).

    Usado para verificar ``conditions_completeness="partial"`` sin alterar
    el set base ``seed_minimal``.
    """
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        evt_partial = RaceEvent(
            id=103,
            series_id=1,
            sequence_number=2,
            name="VALIDA II GINEBRA",
            event_date=date(2026, 2, 28),
            location="Ginebra",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
            climate="Nublado",
            temperature_c=Decimal("18.0"),
            # surface_condition / altitude_msnm / weather_notes → NULL
        )
        session.add_all([coach, series, evt_partial])
        await session.commit()
    yield


# ---------------------------------------------------------------------------
# Clientes HTTP por rol (reutilizables; cada uno depende de seed_minimal salvo
# que el test lo sobreescriba inyectando otro seed primero).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_minimal):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(sqlite_engine, db_session_factory, seed_minimal):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_minimal):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=5
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, seed_minimal):
    """Cliente sin auth — NO override de get_current_user (forza bearer scheme)."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# Variantes que requieren seeds extendidos (no se puede componer más de un
# seed_minimal en la misma cadena de fixtures, así que se redefinen aquí).


@pytest_asyncio.fixture
async def admin_client_with_result(sqlite_engine, db_session_factory, seed_with_result):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client_with_calendar(
    sqlite_engine, db_session_factory, seed_with_calendar
):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_with_result(
    sqlite_engine, db_session_factory, seed_with_result
):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_with_calendar(
    sqlite_engine, db_session_factory, seed_with_calendar
):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_partial(
    sqlite_engine, db_session_factory, seed_partial_conditions
):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ===========================================================================
# POST /api/race-analysis/race-events/
# ===========================================================================


class TestCreateRaceEvent:
    @pytest.mark.asyncio
    async def test_happy_path_coach_minimal_payload(
        self, coach_client, db_session_factory
    ):
        """Coach crea evento sin condiciones → 201 y persiste con defaults."""
        payload = {
            "series_id": 1,
            "sequence_number": 6,
            "name": "VALIDA VI ROLDANILLO",
            "event_date": "2026-09-12",
            "location": "Roldanillo",
        }
        r = await coach_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["sequence_number"] == 6
        assert body["name"] == "VALIDA VI ROLDANILLO"
        assert body["status"] == "scheduled"   # default RaceEventStatus.SCHEDULED
        assert body["is_championship"] is False
        assert body["created_by_user_id"] == 10  # coach id del token override
        # Sin condiciones → NULL
        assert body["climate"] is None
        assert body["temperature_c"] is None
        assert body["surface_condition"] is None
        assert body["altitude_msnm"] is None
        assert body["weather_notes"] is None

        # Verificar en DB
        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == body["id"]))
            ).scalar_one()
            assert evt.status == RaceEventStatus.SCHEDULED
            assert evt.created_by_user_id == 10
            assert evt.climate is None

    @pytest.mark.asyncio
    async def test_happy_path_admin(self, admin_client):
        """Admin también puede crear (RBAC: coach + admin)."""
        payload = {
            "series_id": 1,
            "sequence_number": 7,
            "name": "VALIDA VII YUMBO",
            "event_date": "2026-10-18",
        }
        r = await admin_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 201, r.text
        assert r.json()["created_by_user_id"] == 1  # admin id

    @pytest.mark.asyncio
    async def test_post_con_condiciones_completas(
        self, coach_client, db_session_factory
    ):
        """POST con los 5 campos de clima → se persisten desde la creación.

        Verifica que ``_ConditionsFields`` es heredado correctamente por
        ``RaceEventCreate`` (POST hereda condiciones desde el inicio).
        """
        payload = {
            "series_id": 1,
            "sequence_number": 6,
            "name": "VALIDA VI ROLDANILLO",
            "event_date": "2026-09-12",
            "location": "Roldanillo",
            "climate": "Soleado y caluroso",
            "temperature_c": "27.5",
            "surface_condition": "seca",
            "altitude_msnm": 950,
            "weather_notes": "Polvo en sectores",
        }
        r = await coach_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["climate"] == "Soleado y caluroso"
        assert Decimal(body["temperature_c"]) == Decimal("27.5")
        assert body["surface_condition"] == "seca"
        assert body["altitude_msnm"] == 950
        assert body["weather_notes"] == "Polvo en sectores"

        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == body["id"]))
            ).scalar_one()
            assert evt.climate == "Soleado y caluroso"
            assert evt.temperature_c == Decimal("27.5")
            assert evt.surface_condition == SurfaceCondition.seca
            assert evt.altitude_msnm == 950
            assert evt.weather_notes == "Polvo en sectores"

    @pytest.mark.asyncio
    async def test_post_sin_condiciones_persiste_nulls(
        self, coach_client, db_session_factory
    ):
        """POST sin enviar campos de clima → todas las columnas quedan NULL.

        Cubre el caso "evento agendado a futuro" donde aún no se conoce el clima.
        """
        payload = {
            "series_id": 1,
            "sequence_number": 6,
            "name": "Futura VI",
            "event_date": "2026-09-12",
        }
        r = await coach_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 201, r.text
        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == r.json()["id"]))
            ).scalar_one()
            assert evt.climate is None
            assert evt.temperature_c is None
            assert evt.surface_condition is None
            assert evt.altitude_msnm is None
            assert evt.weather_notes is None
            # default explícito
            assert evt.status == RaceEventStatus.SCHEDULED

    @pytest.mark.asyncio
    async def test_post_secuencia_duplicada(self, coach_client):
        """(series_id=1, sequence_number=4) ya existe (evt id=100) → 409.

        El mensaje debe incluir el id del conflictivo para que el frontend
        pueda construir un mensaje contextualizado.
        """
        payload = {
            "series_id": 1,
            "sequence_number": 4,        # ← evt 100 ya usa este
            "name": "Conflicto IV",
            "event_date": "2026-05-17",
        }
        r = await coach_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 409, r.text
        assert "100" in r.json()["detail"]  # id del conflictivo

    @pytest.mark.asyncio
    async def test_post_series_id_inexistente(self, coach_client):
        """series_id=999 no existe → 422 (lo lanza ``_check_series_exists``)."""
        payload = {
            "series_id": 999,
            "sequence_number": 1,
            "name": "Huerfana",
            "event_date": "2026-09-12",
        }
        r = await coach_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 422
        assert "999" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_post_anon_sin_token(self, anon_client):
        """Sin bearer → 401/403 (depende del scheme)."""
        payload = {
            "series_id": 1,
            "sequence_number": 6,
            "name": "Anon",
            "event_date": "2026-09-12",
        }
        r = await anon_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_post_parent_forbidden(self, parent_client):
        """Parent autenticado → 403 (escritura es coach + admin)."""
        payload = {
            "series_id": 1,
            "sequence_number": 6,
            "name": "Padre intentando",
            "event_date": "2026-09-12",
        }
        r = await parent_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_post_temperatura_fuera_de_rango(self, coach_client):
        """temperature_c=51 > le=50 → 422 (validador heredado de ``_ConditionsFields``)."""
        payload = {
            "series_id": 1,
            "sequence_number": 6,
            "name": "Volcán",
            "event_date": "2026-09-12",
            "temperature_c": "51",
        }
        r = await coach_client.post(_COLLECTION_URL, json=payload)
        assert r.status_code == 422


# ===========================================================================
# PATCH /api/race-analysis/race-events/{id}  (metadata, no condiciones)
# ===========================================================================


class TestUpdateRaceEvent:
    @pytest.mark.asyncio
    async def test_patch_coach_name_y_event_date(
        self, coach_client, db_session_factory
    ):
        """Coach cambia name + event_date → 200 y persiste."""
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={
                "name": "VALIDA IV CALI (reprogramada)",
                "event_date": "2026-05-24",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "VALIDA IV CALI (reprogramada)"
        assert body["event_date"] == "2026-05-24"

        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            assert evt.name == "VALIDA IV CALI (reprogramada)"
            assert evt.event_date == date(2026, 5, 24)

    @pytest.mark.asyncio
    async def test_patch_parcial_solo_name_preserva_resto(
        self, coach_client, db_session_factory
    ):
        """Solo enviar ``name`` no debe afectar los demás campos."""
        async with db_session_factory() as s:
            before = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            prev_location = before.location
            prev_status = before.status
            prev_seq = before.sequence_number
            prev_event_date = before.event_date

        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"name": "Nuevo Nombre"},
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as s:
            after = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            assert after.name == "Nuevo Nombre"
            # Sin tocar
            assert after.location == prev_location
            assert after.status == prev_status
            assert after.sequence_number == prev_seq
            assert after.event_date == prev_event_date

    @pytest.mark.asyncio
    async def test_patch_body_vacio_es_idempotente(
        self, coach_client, db_session_factory
    ):
        """Body ``{}`` → 200 y nada cambia (mismo patrón que PATCH /conditions)."""
        async with db_session_factory() as s:
            before = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            snapshot = {
                "name": before.name,
                "event_date": before.event_date,
                "sequence_number": before.sequence_number,
                "location": before.location,
                "status": before.status,
            }

        r = await coach_client.patch(_DETAIL_URL.format(event_id=100), json={})
        assert r.status_code == 200, r.text

        async with db_session_factory() as s:
            after = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            assert after.name == snapshot["name"]
            assert after.event_date == snapshot["event_date"]
            assert after.sequence_number == snapshot["sequence_number"]
            assert after.location == snapshot["location"]
            assert after.status == snapshot["status"]

    @pytest.mark.asyncio
    async def test_patch_sequence_a_uno_ocupado(self, coach_client):
        """Intentar reutilizar sequence_number=5 (evt 101) sobre evt 100 → 409."""
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"sequence_number": 5},
        )
        assert r.status_code == 409, r.text
        assert "101" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_sequence_a_uno_libre(
        self, coach_client, db_session_factory
    ):
        """sequence_number=8 está libre en serie 1 → 200."""
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"sequence_number": 8},
        )
        assert r.status_code == 200, r.text
        assert r.json()["sequence_number"] == 8
        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            assert evt.sequence_number == 8

    @pytest.mark.asyncio
    async def test_patch_status_cancelled(self, coach_client, db_session_factory):
        """Cambiar status=cancelled → 200 (coach NO necesita ser admin)."""
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"status": "cancelled"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"
        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one()
            assert evt.status == RaceEventStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_patch_campo_extra_rechazado(self, coach_client):
        """``extra="forbid"`` impide actualizar campos no listados — incluido series_id."""
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"series_id": 2},   # no es campo permitido en RaceEventUpdate
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_parent_forbidden(self, parent_client):
        """Padre no puede editar metadata → 403."""
        r = await parent_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"name": "Hackeando"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_race_event_inexistente(self, coach_client):
        """ID inexistente → 404 con mensaje claro."""
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=9999),
            json={"name": "Fantasma"},
        )
        assert r.status_code == 404
        assert "9999" in r.json()["detail"]

    # ── PR6: propagación válida → calendar_event ligado ──────────────────

    @pytest.mark.asyncio
    async def test_patch_propaga_name_y_location_al_calendar(
        self, coach_client_with_calendar, db_session_factory
    ):
        """Cambiar name + location de la válida actualiza el calendar_event ligado.

        seed_with_calendar: CalendarEvent id=500, race_event_id=100,
        title="VALIDA IV CALI (calendario)", location=None.
        """
        r = await coach_client_with_calendar.patch(
            _DETAIL_URL.format(event_id=100),
            json={"name": "VALIDA IV CALI v2", "location": "Cali Centro"},
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as s:
            cal = (
                await s.execute(select(CalendarEvent).where(CalendarEvent.id == 500))
            ).scalar_one()
            assert cal.title == "VALIDA IV CALI v2"
            assert cal.location == "Cali Centro"

    @pytest.mark.asyncio
    async def test_patch_propaga_event_date_preservando_hora(
        self, coach_client_with_calendar, db_session_factory
    ):
        """Cambiar event_date mueve start_at/end_at preservando hora y duración.

        Calendar previo: 2026-05-17 07:00 → 12:00 (5h). Nueva fecha 2026-05-24.
        """
        r = await coach_client_with_calendar.patch(
            _DETAIL_URL.format(event_id=100),
            json={"event_date": "2026-05-24"},
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as s:
            cal = (
                await s.execute(select(CalendarEvent).where(CalendarEvent.id == 500))
            ).scalar_one()
            assert cal.start_at == datetime(2026, 5, 24, 7, 0, 0)
            assert cal.end_at == datetime(2026, 5, 24, 12, 0, 0)

    @pytest.mark.asyncio
    async def test_patch_sin_calendar_ligado_no_falla(
        self, coach_client, db_session_factory
    ):
        """PATCH de una válida SIN calendar_event ligado no debe fallar.

        El set base (seed_minimal) no tiene calendar_event para id=100 en
        este cliente; el cambio se aplica sin error.
        """
        r = await coach_client.patch(
            _DETAIL_URL.format(event_id=100),
            json={"name": "Sin calendario ligado"},
        )
        assert r.status_code == 200, r.text


# ===========================================================================
# DELETE /api/race-analysis/race-events/{id}  (admin only)
# ===========================================================================


class TestDeleteRaceEvent:
    @pytest.mark.asyncio
    async def test_delete_admin_sin_dependencias(
        self, admin_client, db_session_factory
    ):
        """Admin borra evento limpio (id=101, sin results ni calendar) → 204."""
        r = await admin_client.delete(_DETAIL_URL.format(event_id=101))
        assert r.status_code == 204
        # DELETE 204 → response body vacío.
        assert r.content == b""

        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 101))
            ).scalar_one_or_none()
            assert evt is None

    @pytest.mark.asyncio
    async def test_delete_coach_forbidden(self, coach_client):
        """Coach NO puede borrar — endpoint restringido a admin."""
        r = await coach_client.delete(_DETAIL_URL.format(event_id=101))
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_con_race_results_da_409(
        self, admin_client_with_result, db_session_factory
    ):
        """Evento 100 ya tiene un RaceResult → 409 + mensaje claro."""
        r = await admin_client_with_result.delete(_DETAIL_URL.format(event_id=100))
        assert r.status_code == 409
        assert "resultados" in r.json()["detail"].lower()

        # El evento sigue existiendo
        async with db_session_factory() as s:
            evt = (
                await s.execute(select(RaceEvent).where(RaceEvent.id == 100))
            ).scalar_one_or_none()
            assert evt is not None

    @pytest.mark.asyncio
    async def test_delete_con_calendar_event_da_409(
        self, admin_client_with_calendar, db_session_factory
    ):
        """Evento 100 está referenciado por calendar id=500 → 409 + id en mensaje."""
        r = await admin_client_with_calendar.delete(_DETAIL_URL.format(event_id=100))
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert "500" in detail   # id del calendar_event conflictivo
        assert "calendario" in detail.lower()

    @pytest.mark.asyncio
    async def test_delete_race_event_inexistente(self, admin_client):
        """ID inexistente → 404."""
        r = await admin_client.delete(_DETAIL_URL.format(event_id=9999))
        assert r.status_code == 404
        assert "9999" in r.json()["detail"]


# ===========================================================================
# GET /api/race-analysis/race-events/  (listado con filtros)
# ===========================================================================


class TestListRaceEvents:
    @pytest.mark.asyncio
    async def test_list_sin_filtros_devuelve_todos(self, coach_client):
        """Sin filtros → 3 eventos del seed_minimal (100, 101, 102), ordenados
        por event_date asc.
        """
        r = await coach_client.get(_COLLECTION_URL)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3
        ids = [item["id"] for item in body["items"]]
        # event_date asc: 2025-01-31 (102), 2026-05-17 (100), 2026-08-01 (101)
        assert ids == [102, 100, 101]
        # Cada item tiene flags derivados con default sano
        for item in body["items"]:
            assert "has_results" in item
            assert "has_calendar_event" in item
            assert "conditions_completeness" in item

    @pytest.mark.asyncio
    async def test_list_filtrado_por_season_2026(self, coach_client):
        """``?season=2026`` excluye al evento 102 (serie 2025)."""
        r = await coach_client.get(_COLLECTION_URL, params={"season": 2026})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        ids = sorted(item["id"] for item in body["items"])
        assert ids == [100, 101]

    @pytest.mark.asyncio
    async def test_list_filtrado_por_status_cancelled(self, coach_client):
        """Solo evento 102 está cancelled."""
        r = await coach_client.get(_COLLECTION_URL, params={"status": "cancelled"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 102

    @pytest.mark.asyncio
    async def test_list_filtrado_por_location_case_insensitive_parcial(
        self, coach_client
    ):
        """``?location=cal`` debe matchear "Cali" (ilike)."""
        r = await coach_client.get(_COLLECTION_URL, params={"location": "cal"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 100
        assert body["items"][0]["location"] == "Cali"

    @pytest.mark.asyncio
    async def test_list_has_results_true_cuando_hay_race_result(
        self, coach_client_with_result
    ):
        """El evento 100 tiene un RaceResult → has_results=True; los otros False."""
        r = await coach_client_with_result.get(_COLLECTION_URL)
        assert r.status_code == 200
        flags = {item["id"]: item["has_results"] for item in r.json()["items"]}
        assert flags[100] is True
        assert flags[101] is False
        assert flags[102] is False

    @pytest.mark.asyncio
    async def test_list_has_calendar_event_true_cuando_hay_calendar(
        self, coach_client_with_calendar
    ):
        """Calendario 500 vinculado al evt 100 → has_calendar_event=True."""
        r = await coach_client_with_calendar.get(_COLLECTION_URL)
        assert r.status_code == 200
        flags = {
            item["id"]: item["has_calendar_event"] for item in r.json()["items"]
        }
        assert flags[100] is True
        assert flags[101] is False
        assert flags[102] is False

    @pytest.mark.asyncio
    async def test_list_conditions_completeness_tres_estados(
        self, coach_client_partial
    ):
        """Cobertura de los 3 valores de ``conditions_completeness``.

        El fixture ``seed_partial_conditions`` solo inserta el evento id=103
        (con 2 de 5 campos). Como NO se compone con seed_minimal, la lista
        contiene un único evento → solo cubrimos "partial". Para "complete"
        y "empty" probamos sobre la lista principal con ``coach_client``.
        """
        r = await coach_client_partial.get(_COLLECTION_URL)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == 103
        assert item["conditions_completeness"] == "partial"

    @pytest.mark.asyncio
    async def test_list_conditions_completeness_complete_y_empty(
        self, coach_client
    ):
        """Sobre el seed base: evt 100 → complete (5/5), evt 101/102 → empty."""
        r = await coach_client.get(_COLLECTION_URL)
        assert r.status_code == 200
        completeness = {
            item["id"]: item["conditions_completeness"]
            for item in r.json()["items"]
        }
        assert completeness[100] == "complete"
        assert completeness[101] == "empty"
        assert completeness[102] == "empty"

    @pytest.mark.asyncio
    async def test_list_parent_forbidden(self, parent_client):
        """Padres no acceden al listado de eventos administrativos."""
        r = await parent_client.get(_COLLECTION_URL)
        assert r.status_code == 403
