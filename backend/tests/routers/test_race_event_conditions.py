"""Tests del router ``PATCH /api/race-analysis/race-events/{id}/conditions``.

Cobertura del contrato HTTP (B3 — Fase 1.7 condiciones de carrera):

| Caso                                                              | Status |
|-------------------------------------------------------------------|--------|
| coach actualiza los 5 campos                                      |  200   |
| partial update (solo 1 campo) — resto se mantiene intacto         |  200   |
| body vacío `{}`                                                   |  200   |
| parent autenticado                                                |  403   |
| admin actualiza                                                   |  200   |
| sin token                                                         |  401/403 |
| race_event_id inexistente                                         |  404   |
| campo extra rechazado (extra='forbid')                            |  422   |
| temperature_c fuera de rango                                      |  422   |
| surface_condition valor no enum                                   |  422   |
| backwards-compat: evento sin condiciones previas + PATCH          |  200   |

Estrategia: SQLite async in-memory + StaticPool (idéntico a
``test_race_imports.py``). No mockeamos la DB; usamos las tablas reales.
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
from app.models.race_event import RaceEvent, RaceEventStatus, SurfaceCondition
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Fixtures (mismo patrón que test_race_imports.py)
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    """Stub User para override de ``get_current_user`` sin tocar JWT."""
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
    """SQLite in-memory con sólo las tablas mínimas para este router."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Importar modelos requeridos para que metadata los registre
    from app.models.user import User as _U  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in ("users", "race_series", "race_events")
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_event(db_session_factory):
    """Inserta un RaceEvent base CON condiciones — usado en happy paths/partial."""
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
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=100,
            series_id=1,
            sequence_number=4,
            name="VALIDA IV CALI",
            event_date=date(2026, 5, 17),
            location="CALI",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
            climate="Soleado",
            temperature_c=Decimal("22.5"),
            surface_condition=SurfaceCondition.seca,
            altitude_msnm=1000,
            weather_notes="Notas previas",
        )
        session.add_all([coach, admin, series, event])
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_event_without_conditions(db_session_factory):
    """RaceEvent legado SIN ningún campo de condiciones — backwards-compat."""
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle", season_year=2025,
            organizer="Liga", points_scheme_code="copa_valle_2025",
        )
        # Evento "antiguo" — NO setea ninguno de los campos delta Paso 2 Fase 1.7
        event = RaceEvent(
            id=200,
            series_id=1,
            sequence_number=1,
            name="VALIDA I SEVILLA",
            event_date=date(2025, 1, 31),
            location="SEVILLA",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        session.add_all([coach, series, event])
        await session.commit()
    yield


def _override_db_factory(factory: async_sessionmaker[AsyncSession]):
    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _override_db


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_event):
    """Cliente HTTP autenticado como coach id=10."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(sqlite_engine, db_session_factory, seed_event):
    """Cliente HTTP autenticado como admin id=1."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_event):
    """Cliente HTTP parent — debe ser bloqueado por require_role."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=5
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, seed_event):
    """Cliente sin auth — NO override de get_current_user."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_legacy_event(
    sqlite_engine, db_session_factory, seed_event_without_conditions
):
    """Cliente coach con RaceEvent legado (sin condiciones previas)."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ===========================================================================
# Constantes / helpers
# ===========================================================================


_PATCH_URL = "/api/race-analysis/race-events/{event_id}/conditions"


# ===========================================================================
# RBAC
# ===========================================================================


class TestRbac:
    @pytest.mark.asyncio
    async def test_parent_forbidden(self, parent_client):
        """Padre autenticado recibe 403 de require_role."""
        r = await parent_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"climate": "Soleado"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, admin_client):
        """Admin tiene permisos."""
        r = await admin_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"climate": "Soleado y caluroso"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["climate"] == "Soleado y caluroso"

    @pytest.mark.asyncio
    async def test_anon_unauthorized(self, anon_client):
        """Sin bearer token: HTTP 401 (o 403 según el scheme — ambos válidos)."""
        r = await anon_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"climate": "Soleado"},
        )
        assert r.status_code in (401, 403)


# ===========================================================================
# Happy paths
# ===========================================================================


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_full_update_all_five_fields(
        self, coach_client, db_session_factory
    ):
        """Coach envía los 5 campos → response + DB reflejan los nuevos valores."""
        payload = {
            "climate": "Nublado con lloviznas",
            "temperature_c": "18.5",
            "surface_condition": "humeda",
            "altitude_msnm": 1500,
            "weather_notes": "Viento sostenido del SO 15 km/h",
        }
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100), json=payload
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["race_event_id"] == 100
        assert body["climate"] == "Nublado con lloviznas"
        # Pydantic serializa Decimal como string; comparamos contra "18.5"
        assert Decimal(body["temperature_c"]) == Decimal("18.5")
        assert body["surface_condition"] == "humeda"
        assert body["altitude_msnm"] == 1500
        assert body["weather_notes"] == "Viento sostenido del SO 15 km/h"
        assert "updated_at" in body

        # Verificar persistencia en DB
        async with db_session_factory() as session:
            event = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 100)
                )
            ).scalar_one()
            assert event.climate == "Nublado con lloviznas"
            assert event.temperature_c == Decimal("18.5")
            assert event.surface_condition == SurfaceCondition.humeda
            assert event.altitude_msnm == 1500
            assert event.weather_notes == "Viento sostenido del SO 15 km/h"

    @pytest.mark.asyncio
    async def test_partial_update_preserves_other_fields(
        self, coach_client, db_session_factory
    ):
        """Solo enviamos surface_condition; el resto debe permanecer intacto.

        El seed inicial tiene climate='Soleado', temperature_c=22.5,
        surface_condition=seca, altitude_msnm=1000, weather_notes='Notas previas'.
        """
        # Leer estado previo de la DB
        async with db_session_factory() as session:
            before = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 100)
                )
            ).scalar_one()
            previous_climate = before.climate
            previous_temp = before.temperature_c
            previous_altitude = before.altitude_msnm
            previous_notes = before.weather_notes

        # PATCH solo surface_condition
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"surface_condition": "barro"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["surface_condition"] == "barro"
        # Resto intacto en la respuesta
        assert body["climate"] == previous_climate
        assert Decimal(body["temperature_c"]) == previous_temp
        assert body["altitude_msnm"] == previous_altitude
        assert body["weather_notes"] == previous_notes

        # Verificar persistencia: el resto SIGUE igual en DB (no nulificado)
        async with db_session_factory() as session:
            after = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 100)
                )
            ).scalar_one()
            assert after.surface_condition == SurfaceCondition.barro
            assert after.climate == previous_climate
            assert after.temperature_c == previous_temp
            assert after.altitude_msnm == previous_altitude
            assert after.weather_notes == previous_notes

    @pytest.mark.asyncio
    async def test_empty_body_returns_200_no_changes(
        self, coach_client, db_session_factory
    ):
        """Body `{}` → 200 sin modificaciones a la BD."""
        # Snapshot estado previo
        async with db_session_factory() as session:
            before = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 100)
                )
            ).scalar_one()
            snapshot = {
                "climate": before.climate,
                "temperature_c": before.temperature_c,
                "surface_condition": before.surface_condition,
                "altitude_msnm": before.altitude_msnm,
                "weather_notes": before.weather_notes,
            }

        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100), json={}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["race_event_id"] == 100
        # Response refleja el estado actual (no cambió)
        assert body["climate"] == snapshot["climate"]

        # DB intacta
        async with db_session_factory() as session:
            after = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 100)
                )
            ).scalar_one()
            assert after.climate == snapshot["climate"]
            assert after.temperature_c == snapshot["temperature_c"]
            assert after.surface_condition == snapshot["surface_condition"]
            assert after.altitude_msnm == snapshot["altitude_msnm"]
            assert after.weather_notes == snapshot["weather_notes"]

    @pytest.mark.asyncio
    async def test_backwards_compat_legacy_event_gets_conditions(
        self, coach_client_legacy_event, db_session_factory
    ):
        """RaceEvent creado antes de la feature → PATCH agrega valores OK."""
        # Pre-condición: las columnas vienen en NULL
        async with db_session_factory() as session:
            legacy = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 200)
                )
            ).scalar_one()
            assert legacy.climate is None
            assert legacy.temperature_c is None
            assert legacy.surface_condition is None
            assert legacy.altitude_msnm is None
            assert legacy.weather_notes is None

        r = await coach_client_legacy_event.patch(
            _PATCH_URL.format(event_id=200),
            json={
                "climate": "Frio",
                "temperature_c": "8.0",
                "surface_condition": "mixta",
                "altitude_msnm": 1700,
                "weather_notes": "Neblina mañanera",
            },
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as session:
            event = (
                await session.execute(
                    select(RaceEvent).where(RaceEvent.id == 200)
                )
            ).scalar_one()
            assert event.climate == "Frio"
            assert event.temperature_c == Decimal("8.0")
            assert event.surface_condition == SurfaceCondition.mixta
            assert event.altitude_msnm == 1700
            assert event.weather_notes == "Neblina mañanera"


# ===========================================================================
# 404 — recurso inexistente
# ===========================================================================


class TestNotFound:
    @pytest.mark.asyncio
    async def test_404_unknown_race_event_id(self, coach_client):
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=9999),
            json={"climate": "X"},
        )
        assert r.status_code == 404
        assert "9999" in r.json()["detail"]


# ===========================================================================
# Validación de body (422)
# ===========================================================================


class TestValidation:
    @pytest.mark.asyncio
    async def test_extra_field_rejected_by_extra_forbid(self, coach_client):
        """`extra='forbid'` → cualquier campo extra dispara 422."""
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"temperatura": 22},  # nombre español: NO es un campo válido
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_temperature_out_of_range_high(self, coach_client):
        """temperature_c > 50 → 422."""
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"temperature_c": "51"},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_temperature_out_of_range_negative(self, coach_client):
        """temperature_c < 0 → 422."""
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"temperature_c": "-1"},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_surface_condition_not_in_enum(self, coach_client):
        """Valor que no está en el enum → 422."""
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"surface_condition": "lodo"},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_altitude_below_zero(self, coach_client):
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"altitude_msnm": -10},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_altitude_above_5000(self, coach_client):
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"altitude_msnm": 5001},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_climate_over_60_chars(self, coach_client):
        """climate con >60 caracteres → 422."""
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"climate": "x" * 61},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_weather_notes_over_2000_chars(self, coach_client):
        r = await coach_client.patch(
            _PATCH_URL.format(event_id=100),
            json={"weather_notes": "x" * 2001},
        )
        assert r.status_code == 422
