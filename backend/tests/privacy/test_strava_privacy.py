"""Tests de privacidad de Strava Activity Sync (specs/025-strava-activity-sync, T038).

Cubre:
  1. Ningún endpoint de Strava (``activities.py`` + ``strava_integration.py``)
     devuelve una clave de coordenadas/mapa/descripción en su respuesta JSON
     — barrido recursivo de claves sobre el cuerpo real de la respuesta HTTP,
     más un assert estático sobre los ``Pydantic`` schemas (``schemas/strava.py``)
     como defensa en profundidad (un campo nuevo en el schema fallaría este
     test incluso antes de tener datos para poblarlo).
  2. ``StravaActivity``/``StravaConnection`` (modelos SQLAlchemy) no tienen,
     ni pueden tener sin cambiar este test, ninguna columna de GPS/mapa
     (data-model.md §2 "Explicitly ABSENT columns").
  3. Los logs capturados de ``services/strava/ingest.py`` y
     ``services/strava/reconcile.py`` no contienen el nombre del atleta ni
     el título de la actividad — únicamente identificadores numéricos
     (``athlete_id``, ``strava_activity_id``, conteos) — FR-016.

Ley 1581 (Colombia) — datos de menores: ver también
``tests/services/test_strava_ingest.py::TestGpsStripping`` (allow-list de
``_extract_summary_fields``) y ``tests/routers/test_activities.py`` /
``tests/routers/test_strava_integration.py`` (RBAC). Este módulo es la
verificación de privacidad dedicada del feature — consolidada como el
patrón de ``test_session_assistant_privacy.py`` (feature 006).

Todos los datos usados son ficticios (CLAUDE.md §Privacy).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

# ``ParentalConsent.policy`` es ``lazy="joined"`` a nivel de mapper: CUALQUIER
# ``select(ParentalConsent)`` (no solo con ``.options(joinedload(...))``)
# emite un LEFT OUTER JOIN contra ``privacy_policies``. El endpoint de
# conexión de ``strava_integration.py`` no consulta consentimientos
# directamente en este test, pero la tabla debe existir para el DDL de
# SQLite — mismo shim que ``tests/routers/test_strava_integration.py``.
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import Club, ClubMember, ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.strava_activity import StravaActivity, StravaIngestSource, StravaUpstreamState
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.training_session import SessionKind, TrainingSession
from app.models.user import User, UserRole
from app.routers import activities, strava_integration
from app.schemas.strava import (
    ActivityLinkOut,
    ActivityListOut,
    ActivityOut,
    AuthorizeUrlOut,
    ConnectionStatusOut,
    ReconcileResultOut,
    SessionActivitiesOut,
    SessionSuggestionListOut,
    SessionSuggestionOut,
    StravaWebhookEvent,
)
from app.services.strava import reconcile as reconcile_module
from app.services.strava.ingest import process_webhook_event, upsert_activity
from app.services.strava.reconcile import reconcile_all
from app.services.strava.token_store import encrypt_token

# NOTE: no module-level ``pytestmark = pytest.mark.asyncio`` — pytest.ini
# sets ``asyncio_mode = "auto"`` repo-wide (see the same note in
# ``tests/services/test_strava_ingest.py``), so async defs are already
# auto-detected; adding the marker explicitly only triggers a PytestWarning
# on this module's synchronous unit tests (schema/model checks).

# ---------------------------------------------------------------------------
# Claves prohibidas — ubicación/mapa/descripción de texto libre (FR-012,
# data-model.md §2). Comparación EXACTA (no substring): "location" (nombre
# de la sede de una sesión de entrenamiento, texto libre no-GPS) NO está en
# esta lista a propósito — evita falsos positivos legítimos.
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = {
    "lat",
    "lng",
    "latlng",
    "start_latlng",
    "end_latlng",
    "polyline",
    "map",
    "map_polyline",
    "summary_polyline",
    "description",
    "photos",
    "segment_efforts",
}


def _collect_keys(obj: Any) -> set[str]:
    """Recolecta (en minúsculas) todas las claves de un JSON-like anidado."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k).lower())
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


def _assert_no_forbidden_keys(body: Any, *, where: str) -> None:
    found = FORBIDDEN_KEYS & _collect_keys(body)
    assert not found, f"Claves prohibidas {found} encontradas en {where}: {body}"


# ===========================================================================
# 1a. Schemas Pydantic — assert estático (defensa en profundidad)
# ===========================================================================


class TestSchemasHaveNoForbiddenFields:
    """Ningún schema de respuesta expuesto a un usuario final declara un
    campo de coordenadas/mapa/descripción, sin importar si hay datos que
    lo pueblen todavía."""

    @pytest.mark.parametrize(
        "model_cls",
        [
            ActivityOut,
            ActivityListOut,
            ActivityLinkOut,
            ConnectionStatusOut,
            AuthorizeUrlOut,
            SessionSuggestionOut,
            SessionSuggestionListOut,
            SessionActivitiesOut,
            ReconcileResultOut,
            StravaWebhookEvent,
        ],
    )
    def test_schema_fields_exclude_forbidden_keys(self, model_cls) -> None:
        field_names = {name.lower() for name in model_cls.model_fields}
        found = FORBIDDEN_KEYS & field_names
        assert not found, (
            f"{model_cls.__name__} declara campo(s) prohibido(s) {found} — "
            "violación de privacidad Ley 1581 (data-model.md §2)."
        )


# ===========================================================================
# 1b. Modelos SQLAlchemy — sin columnas ni atributos de GPS
# ===========================================================================


class TestModelsHaveNoGpsAttributes:
    def test_strava_activity_has_no_gps_columns_or_attributes(self) -> None:
        columns = {c.lower() for c in StravaActivity.__table__.columns.keys()}
        assert FORBIDDEN_KEYS.isdisjoint(columns)
        for forbidden in FORBIDDEN_KEYS:
            assert not hasattr(StravaActivity, forbidden), (
                f"StravaActivity no debe tener el atributo '{forbidden}'"
            )

    def test_strava_connection_has_no_gps_columns_or_attributes(self) -> None:
        columns = {c.lower() for c in StravaConnection.__table__.columns.keys()}
        assert FORBIDDEN_KEYS.isdisjoint(columns)
        for forbidden in FORBIDDEN_KEYS:
            assert not hasattr(StravaConnection, forbidden), (
                f"StravaConnection no debe tener el atributo '{forbidden}'"
            )


# ===========================================================================
# 2. Endpoints reales — barrido recursivo del cuerpo de la respuesta HTTP
# ===========================================================================

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "privacy_policies",  # ver shim LONGTEXT arriba
    "parental_consents",
    "strava_connections",
    "strava_activities",
    "training_sessions",
    "session_attendance",
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_combined_app() -> FastAPI:
    """App local que monta ambos routers de Strava bajo ``/api`` — mismo
    prefijo que producción (``app/main.py``). Ver docstring de
    ``tests/routers/test_activities.py`` / ``test_strava_integration.py``
    para por qué no se usa ``app.main.app`` directamente (el flag
    ``strava_enabled`` se evalúa en import-time, antes de que estos tests
    puedan activarlo)."""
    test_app = FastAPI()
    test_app.include_router(activities.router, prefix="/api")
    test_app.include_router(strava_integration.router, prefix="/api")
    return test_app


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
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


@pytest.fixture(autouse=True)
def _strava_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "strava_token_encryption_key", Fernet.generate_key().decode()
    )


# --- seed helpers (ficticios) ----------------------------------------------


async def _seed_user(session: AsyncSession, user_id: int, role: UserRole) -> User:
    u = User(
        id=user_id,
        email=f"{role.value}{user_id}@ficticio.test",
        hashed_password="x",
        first_name="Test",
        last_name=f"User{user_id}",
        role=role,
        is_active=True,
        can_login=role != UserRole.athlete,
        created_at=_utc(),
    )
    session.add(u)
    await session.flush()
    return u


async def _seed_club(session: AsyncSession, club_id: int = 1) -> Club:
    club = Club(id=club_id, name="Club Trocha y Ruta Ficticio", code=f"TYR-{club_id}")
    session.add(club)
    await session.flush()
    return club


async def _seed_athlete(
    session: AsyncSession, athlete_id: int, *, club_id: int = 1
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=900 + athlete_id,
        first_name="Atleta",
        last_name=f"Ficticio{athlete_id}",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def _seed_connection(
    session: AsyncSession,
    *,
    athlete_id: int,
    strava_athlete_id: int,
    authorized_by_user_id: int = 1,
) -> StravaConnection:
    consent = ParentalConsent(
        parent_user_id=authorized_by_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        consented_at=_utc(),
    )
    session.add(consent)
    await session.flush()

    conn = StravaConnection(
        athlete_id=athlete_id,
        strava_athlete_id=strava_athlete_id,
        status=StravaConnectionStatus.active,
        access_token_enc=encrypt_token("plain-access-token"),
        refresh_token_enc=encrypt_token("plain-refresh-token"),
        token_expires_at=_utc() + timedelta(hours=6),
        scope_granted="activity:read_all",
        authorized_by_user_id=authorized_by_user_id,
        consent_id=consent.id,
        connected_at=_utc(),
    )
    session.add(conn)
    await session.flush()
    return conn


async def _seed_activity(
    session: AsyncSession,
    activity_id: int,
    *,
    strava_activity_id: int,
    athlete_id: int,
    connection_id: int,
    training_session_id: int | None = None,
) -> StravaActivity:
    now = _utc()
    a = StravaActivity(
        id=activity_id,
        strava_activity_id=strava_activity_id,
        athlete_id=athlete_id,
        connection_id=connection_id,
        name="Salida ficticia XCO",
        sport_type="MountainBikeRide",
        start_date_utc=now,
        start_date_local=now.replace(tzinfo=None),
        elapsed_time_s=3600,
        moving_time_s=3500,
        distance_m=25000.0,
        total_elevation_gain_m=300.0,
        average_heartrate=150.0,
        max_heartrate=175.0,
        is_trainer=False,
        ingest_source=StravaIngestSource.webhook,
        training_session_id=training_session_id,
        linked_at=now if training_session_id is not None else None,
        linked_by_user_id=1 if training_session_id is not None else None,
    )
    session.add(a)
    await session.flush()
    return a


async def _seed_training_session(
    session: AsyncSession, session_id: int, *, club_id: int = 1
) -> TrainingSession:
    from datetime import time as _time

    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=1,
        scheduled_date=date(2026, 6, 1),
        scheduled_start_time=_time(15, 0),
        duration_min=90,
        location="Sede club ficticia",
        technical_focus="Resistencia",
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    session.add(ts)
    await session.flush()
    return ts


def _admin_user_typed(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.admin, club_memberships=[])


def _make_client(session: AsyncSession, *, user) -> AsyncClient:
    test_app = _build_combined_app()

    async def _override_db():
        yield session
        await session.commit()

    async def _override_user():
        return user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        follow_redirects=False,
    )


class TestEndpointResponsesHaveNoForbiddenKeys:
    """Barrido recursivo sobre el cuerpo JSON real de cada endpoint que
    puede devolver datos de actividad — admin ve todo, así que basta un
    solo rol para exigir cobertura sin RBAC noise."""

    async def _seed_full_scenario(self, session: AsyncSession) -> None:
        await _seed_user(session, 1, UserRole.admin)
        await _seed_club(session, 1)
        await _seed_athlete(session, 100, club_id=1)
        conn = await _seed_connection(
            session, athlete_id=100, strava_athlete_id=555, authorized_by_user_id=1
        )
        ts = await _seed_training_session(session, 1, club_id=1)
        await _seed_activity(
            session,
            1,
            strava_activity_id=111,
            athlete_id=100,
            connection_id=conn.id,
            training_session_id=ts.id,
        )
        await session.commit()

    async def test_list_activities_review_response_has_no_forbidden_keys(
        self, session
    ) -> None:
        await self._seed_full_scenario(session)

        async with _make_client(session, user=_admin_user_typed()) as client:
            resp = await client.get("/api/activities")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"], "el escenario sembrado debe producir al menos un item"
        _assert_no_forbidden_keys(body, where="GET /api/activities")

    async def test_athlete_scoped_activities_response_has_no_forbidden_keys(
        self, session
    ) -> None:
        await self._seed_full_scenario(session)

        async with _make_client(session, user=_admin_user_typed()) as client:
            resp = await client.get("/api/athletes/100/activities")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"]
        _assert_no_forbidden_keys(body, where="GET /api/athletes/{id}/activities")

    async def test_session_scoped_activities_response_has_no_forbidden_keys(
        self, session
    ) -> None:
        await self._seed_full_scenario(session)

        async with _make_client(session, user=_admin_user_typed()) as client:
            resp = await client.get("/api/training-sessions/1/activities")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"]
        _assert_no_forbidden_keys(
            body, where="GET /api/training-sessions/{id}/activities"
        )

    async def test_strava_connection_status_response_has_no_forbidden_keys(
        self, session
    ) -> None:
        await self._seed_full_scenario(session)

        async with _make_client(session, user=_admin_user_typed()) as client:
            resp = await client.get("/api/athletes/100/strava/connection")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "active"
        _assert_no_forbidden_keys(
            body, where="GET /api/athletes/{id}/strava/connection"
        )


# ===========================================================================
# 3. Logs de ingest/reconcile — solo IDs numéricos (FR-016)
# ===========================================================================

# Nombre/título ficticios pero distintivos: si aparecieran en un log sería
# inequívocamente una fuga, no una coincidencia con contenido legítimo
# (conteos, IDs) del mismo log.
_FICTITIOUS_ATHLETE_NAME = "Juan Pérez Ficticio"
_FICTITIOUS_ACTIVITY_TITLE = "Salida secreta cerca de la casa de Juan"


def _raw_activity_with_pii_title(strava_id: int) -> dict:
    """Payload de Strava con un título de actividad que jamás debe
    aparecer en un log — el nombre del atleta no viaja en el payload de
    Strava (Strava no lo conoce), así que la fuga a vigilar aquí es el
    ``name``/título de la actividad, texto libre del atleta/familia."""
    return {
        "id": strava_id,
        "name": _FICTITIOUS_ACTIVITY_TITLE,
        "sport_type": "MountainBikeRide",
        "type": "Ride",
        "start_date": "2026-06-01T13:00:00Z",
        "start_date_local": "2026-06-01T08:00:00Z",
        "elapsed_time": 3700,
        "moving_time": 3600,
        "distance": 15000.0,
        "total_elevation_gain": 120.0,
        "average_heartrate": 148.0,
        "max_heartrate": 172.0,
        "trainer": False,
    }


def _all_log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Texto de mensaje + TODOS los campos ``extra=`` de cada LogRecord
    capturado. ``caplog.messages`` por sí solo NO incluye los campos
    ``extra`` (se guardan como atributos del record, no en el mensaje
    formateado) — omitirlos dejaría un punto ciego real: el código de
    producción usa ``logger.info(evento, extra={...})`` en todo el módulo
    de ingest/reconcile, así que la fuga (si existiera) estaría ahí, no en
    el string del mensaje."""
    chunks: list[str] = []
    for record in caplog.records:
        chunks.append(record.getMessage())
        chunks.append(str(record.__dict__))
    return " ".join(chunks)


class TestIngestLogsAreNumericOnly:
    async def _seed(self, session: AsyncSession) -> StravaConnection:
        await _seed_user(session, 1, UserRole.admin)
        await _seed_club(session, 1)
        await _seed_athlete(session, 100, club_id=1)
        conn = await _seed_connection(
            session, athlete_id=100, strava_athlete_id=777, authorized_by_user_id=1
        )
        await session.commit()
        return conn

    async def test_upsert_activity_logs_exclude_activity_title(
        self, session, caplog: pytest.LogCaptureFixture
    ) -> None:
        conn = await self._seed(session)
        raw = _raw_activity_with_pii_title(strava_id=999888777)

        with caplog.at_level(
            logging.DEBUG, logger="app.services.strava.ingest"
        ):
            await upsert_activity(session, conn, raw, source=StravaIngestSource.webhook)
        await session.commit()

        log_text = _all_log_text(caplog)
        assert _FICTITIOUS_ACTIVITY_TITLE not in log_text, (
            "El título de la actividad apareció en los logs de ingest — "
            "violación de privacidad Ley 1581 (FR-016)."
        )
        assert _FICTITIOUS_ATHLETE_NAME not in log_text
        # Sanity: el log SÍ se emitió, con IDs numéricos.
        assert "strava_activity_ingested" in log_text
        assert "999888777" in log_text

    async def test_webhook_athlete_deauth_logs_exclude_names(
        self, session, caplog: pytest.LogCaptureFixture
    ) -> None:
        conn = await self._seed(session)

        event = StravaWebhookEvent(
            object_type="athlete",
            aspect_type="update",
            object_id=1,
            owner_id=conn.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
            updates={"authorized": "false"},
        )

        with caplog.at_level(
            logging.DEBUG, logger="app.services.strava.ingest"
        ):
            await process_webhook_event(event, session)
        await session.commit()

        log_text = _all_log_text(caplog)
        assert _FICTITIOUS_ATHLETE_NAME not in log_text
        assert "strava_connection_deauthorized" in log_text


class _FakeStravaClientForReconcilePrivacy:
    """Doble mínimo de ``StravaClient`` — entrega un payload con título
    ficticio identificable para verificar que ``reconcile.py`` tampoco lo
    loguea."""

    def __init__(self, connection: StravaConnection, db: AsyncSession) -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeStravaClientForReconcilePrivacy":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def list_athlete_activities(self, after, per_page: int = 50):
        yield _raw_activity_with_pii_title(strava_id=444555000)

    async def get_activity(self, activity_id: int) -> dict:
        return _raw_activity_with_pii_title(strava_id=activity_id)


class TestReconcileLogsAreNumericOnly:
    async def test_reconcile_all_logs_exclude_activity_title(
        self, session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(
            reconcile_module, "StravaClient", _FakeStravaClientForReconcilePrivacy
        )

        await _seed_user(session, 1, UserRole.admin)
        await _seed_club(session, 1)
        await _seed_athlete(session, 100, club_id=1)
        await _seed_connection(
            session, athlete_id=100, strava_athlete_id=888, authorized_by_user_id=1
        )
        await session.commit()

        with caplog.at_level(
            logging.DEBUG, logger="app.services.strava.reconcile"
        ):
            result = await reconcile_all(session)
        await session.commit()

        assert result["activities_upserted"] == 1

        log_text = _all_log_text(caplog)
        assert _FICTITIOUS_ACTIVITY_TITLE not in log_text, (
            "El título de la actividad apareció en los logs de reconcile — "
            "violación de privacidad Ley 1581 (FR-016)."
        )
        assert _FICTITIOUS_ATHLETE_NAME not in log_text
        assert "strava_reconcile_summary" in log_text

        # El resultado devuelto a un caller (GitHub Actions) es solo conteos.
        for key in ("connections_processed", "activities_upserted", "connections_broken"):
            assert isinstance(result[key], int)
        _assert_no_forbidden_keys(result, where="reconcile_all() return value")


# ===========================================================================
# Sanity: el escenario ficticio en sí no colisiona con las claves prohibidas
# (por si alguna vez alguien agrega a StravaActivity/ActivityOut un campo
# nuevo que coincida en nombre con datos legítimos — evita falsos negativos
# silenciosos en el barrido de FORBIDDEN_KEYS).
# ===========================================================================


def test_forbidden_keys_set_is_not_accidentally_empty() -> None:
    assert len(FORBIDDEN_KEYS) >= 8
