"""Tests T022 — ``services/strava/ingest.py`` + ``services/strava/reconcile.py``
(feature 025).

Cubre (spec §T022):
  - Idempotencia del upsert (FR-005): la misma actividad entregada dos
    veces colapsa en una sola fila; una segunda entrega que completa
    campos actualiza en el lugar (no crea copia).
  - Data minimization por allow-list (FR-012, privacidad Ley 1581): un
    payload de Strava CON ``start_latlng``/``end_latlng``/``map``/
    ``description`` nunca persiste esos campos — el modelo no tiene
    columnas para ellos y ``_extract_summary_fields`` es un allow-list.
  - ``delete`` de Strava → ``upstream_state=removed_upstream`` sin borrar
    la fila ni el vínculo de sesión (FR-013).
  - Deauth de Strava (``object_type=athlete``, ``authorized=false``) →
    ``status=disconnected`` (FR-014).
  - Reconcile: avance del watermark ``last_sync_at`` en una corrida
    exitosa, y camino de token roto (``StravaAuthError`` durante el pull)
    → ``status=broken`` + contador ``connections_broken``, watermark NO
    avanzado.

Patrón de DB: SQLite async in-memory + StaticPool, igual que
``tests/models/test_strava_models.py`` (mismo subset de tablas). No se usa
MySQL real ni ``httpx`` real — ``StravaClient`` se sustituye por un doble
de prueba mínimo inyectado vía ``monkeypatch`` sobre la referencia que
``ingest.py``/``reconcile.py`` importan, porque ninguno de los dos módulos
expone un punto de inyección de transporte HTTP (a diferencia de
``StravaClient.__init__`` mismo, que sí acepta ``http_client=``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import Club
from app.models.parental_consent import ParentalConsent
from app.models.strava_activity import (
    StravaActivity,
    StravaIngestSource,
    StravaUpstreamState,
)
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.user import User, UserRole
from app.schemas.strava import StravaWebhookEvent
from app.services.strava import ingest as ingest_module
from app.services.strava import reconcile as reconcile_module
from app.services.strava.client import StravaAuthError, StravaClient
from app.services.strava.ingest import (
    _extract_summary_fields,
    process_webhook_event,
    upsert_activity,
)
from app.services.strava.reconcile import _summary_complete, reconcile_all
from app.services.strava.token_store import decrypt_token, encrypt_token

# NOTE: no module-level ``pytestmark = pytest.mark.asyncio`` — pytest.ini
# sets ``asyncio_mode = "auto"`` repo-wide, so async defs are already
# auto-detected; adding the marker explicitly only triggers a PytestWarning
# on the (intentionally) synchronous unit tests in this file.

_TABLES = [
    "users",
    "clubs",
    "athletes",
    "parental_consents",
    "strava_connections",
    "strava_activities",
]


# ---------------------------------------------------------------------------
# Settings — provide a valid Fernet key for token_store (feature 025 tests
# convention, mirrors tests/routers/test_strava_integration.py).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _strava_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "strava_token_encryption_key", Fernet.generate_key().decode()
    )


# ---------------------------------------------------------------------------
# DB fixtures — same pattern as tests/models/test_strava_models.py
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed helpers (ficticios — nunca datos reales de atletas del club)
# ---------------------------------------------------------------------------

_counter = 0


def _next_id() -> int:
    global _counter
    _counter += 1
    return _counter


async def _seed_athlete(session: AsyncSession) -> Athlete:
    n = _next_id()
    club = Club(name="Club Trocha y Ruta Ficticio", code=f"TYR-{n}")
    coach = User(
        email=f"coach{n}@ficticio.test",
        hashed_password="x",
        first_name="Coach",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    athlete_user = User(
        email=f"atleta{n}@ficticio.test",
        hashed_password="x",
        first_name="Juan",
        last_name="Pérez Ficticio",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([club, coach, athlete_user])
    await session.flush()

    athlete = Athlete(
        user_id=athlete_user.id,
        first_name="Juan",
        last_name="Pérez Ficticio",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=club.id,
        created_by=coach.id,
    )
    session.add(athlete)
    await session.flush()
    return athlete


async def _seed_consent(session: AsyncSession, athlete: Athlete) -> ParentalConsent:
    n = _next_id()
    parent = User(
        email=f"padre{n}@ficticio.test",
        hashed_password="x",
        first_name="Padre",
        last_name="Ficticio",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(parent)
    await session.flush()

    consent = ParentalConsent(
        parent_user_id=parent.id,
        athlete_id=athlete.id,
        consent_version="v1",
    )
    session.add(consent)
    await session.flush()
    return consent


async def _seed_connection(
    session: AsyncSession,
    athlete: Athlete,
    consent: ParentalConsent,
    *,
    status: StravaConnectionStatus = StravaConnectionStatus.active,
    token_expires_at: datetime | None = None,
    last_sync_at: datetime | None = None,
) -> StravaConnection:
    n = _next_id()
    now = datetime.now(timezone.utc)
    connection = StravaConnection(
        athlete_id=athlete.id,
        strava_athlete_id=900_000_000 + n,
        status=status,
        access_token_enc=encrypt_token("plain-access-token"),
        refresh_token_enc=encrypt_token("plain-refresh-token"),
        token_expires_at=token_expires_at or (now + timedelta(hours=6)),
        scope_granted="activity:read_all",
        authorized_by_user_id=consent.parent_user_id,
        consent_id=consent.id,
        connected_at=now,
        last_sync_at=last_sync_at,
    )
    session.add(connection)
    await session.flush()
    return connection


def _as_naive_utc(value: datetime) -> datetime:
    """Strip tzinfo for comparison — SQLite's ``DateTime`` column has no
    timezone awareness and silently drops it on the round-trip through
    ``db.refresh()``; this is a SQLite-in-memory test artifact, not the
    production (MySQL) behavior, so tests normalize rather than assert on
    tz-awareness itself."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _raw_activity(
    *,
    strava_id: int,
    extra: dict | None = None,
    distance_m: float | None = 15000.0,
    moving_time_s: int | None = 3600,
    elevation_m: float | None = 120.0,
) -> dict:
    """Minimal realistic Strava activity payload — optionally polluted with
    GPS/location fields to exercise the allow-list stripping."""
    payload = {
        "id": strava_id,
        "name": "Salida Ficticia XCO",
        "sport_type": "MountainBikeRide",
        "type": "Ride",
        "start_date": "2026-06-01T13:00:00Z",
        "start_date_local": "2026-06-01T08:00:00Z",
        "elapsed_time": 3700,
        "moving_time": moving_time_s,
        "distance": distance_m,
        "total_elevation_gain": elevation_m,
        "average_heartrate": 148.0,
        "max_heartrate": 172.0,
        "trainer": False,
    }
    if extra:
        payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# Idempotent upsert (FR-005)
# ---------------------------------------------------------------------------


class TestUpsertActivityIdempotent:
    async def test_double_delivery_of_same_activity_is_a_single_row(self, db) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent)
        await db.commit()

        raw = _raw_activity(strava_id=444555666)

        first = await upsert_activity(db, connection, raw, source=StravaIngestSource.webhook)
        await db.commit()
        second = await upsert_activity(
            db, connection, dict(raw), source=StravaIngestSource.webhook
        )
        await db.commit()

        assert first.id == second.id
        count = (
            await db.execute(select(func.count()).select_from(StravaActivity))
        ).scalar_one()
        assert count == 1

    async def test_later_delivery_completes_missing_fields_without_duplicating(
        self, db
    ) -> None:
        """A first (incomplete) webhook delivery, followed by a reconcile
        pull that completes the summary, must update the SAME row and flip
        ``summary_complete`` — never create a second row (FR-005, FR-015)."""
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent)
        await db.commit()

        incomplete_raw = _raw_activity(
            strava_id=777888999, distance_m=None, moving_time_s=None, elevation_m=None
        )
        first = await upsert_activity(
            db, connection, incomplete_raw, source=StravaIngestSource.webhook
        )
        await db.commit()
        assert first.summary_complete is False
        assert first.distance_m is None

        complete_raw = _raw_activity(strava_id=777888999)
        second = await upsert_activity(
            db, connection, complete_raw, source=StravaIngestSource.reconcile
        )
        await db.commit()

        assert second.id == first.id
        assert second.summary_complete is True
        assert second.distance_m == 15000.0
        count = (
            await db.execute(select(func.count()).select_from(StravaActivity))
        ).scalar_one()
        assert count == 1

    async def test_resurrects_removed_upstream_row_on_fresh_delivery(self, db) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent)
        await db.commit()

        raw = _raw_activity(strava_id=222333444)
        activity = await upsert_activity(db, connection, raw, source=StravaIngestSource.webhook)
        await db.commit()
        activity.upstream_state = StravaUpstreamState.removed_upstream
        await db.commit()

        resurrected = await upsert_activity(
            db, connection, raw, source=StravaIngestSource.reconcile
        )
        await db.commit()

        assert resurrected.id == activity.id
        assert resurrected.upstream_state == StravaUpstreamState.present


# ---------------------------------------------------------------------------
# GPS/location stripping — data minimization (FR-012)
# ---------------------------------------------------------------------------


class TestGpsStripping:
    def test_extract_summary_fields_ignores_gps_and_map_keys(self) -> None:
        """Unit-level: the allow-list function itself never reads GPS/map
        keys off the raw payload, regardless of what Strava sends."""
        raw = _raw_activity(
            strava_id=1,
            extra={
                "start_latlng": [3.4372, -76.5225],
                "end_latlng": [3.4373, -76.5226],
                "map": {"id": "a1", "polyline": "abc123", "summary_polyline": "xyz"},
                "description": "Salida secreta cerca de la casa",
                "photos": {"count": 2, "primary": {"urls": {"600": "https://x"}}},
                "segment_efforts": [{"id": 1, "name": "Subida"}],
            },
        )
        fields = _extract_summary_fields(raw)

        forbidden_keys = {
            "start_latlng",
            "end_latlng",
            "map",
            "map_polyline",
            "description",
            "photos",
            "segment_efforts",
        }
        assert forbidden_keys.isdisjoint(fields.keys())

    async def test_upsert_activity_persists_no_gps_or_location_data(self, db) -> None:
        """End-to-end: a payload WITH lat/lng/map/description fields upserts
        to a row that structurally cannot carry any of them (schema-level
        guarantee, data-model.md §2)."""
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent)
        await db.commit()

        raw = _raw_activity(
            strava_id=333222111,
            extra={
                "start_latlng": [3.4372, -76.5225],
                "end_latlng": [3.4373, -76.5226],
                "map": {"id": "a1", "polyline": "abc123"},
                "description": "Ruta con ubicación exacta de la casa",
                "photos": {"count": 1},
            },
        )

        activity = await upsert_activity(db, connection, raw, source=StravaIngestSource.webhook)
        await db.commit()

        forbidden_columns = {
            "start_latlng",
            "end_latlng",
            "map_polyline",
            "description",
            "photos",
        }
        assert forbidden_columns.isdisjoint(set(StravaActivity.__table__.columns.keys()))
        for forbidden in forbidden_columns:
            assert not hasattr(activity, forbidden)

        # Sanity: the legitimate summary fields DID persist.
        assert activity.distance_m == 15000.0
        assert activity.average_heartrate == 148.0


# ---------------------------------------------------------------------------
# Webhook dispatch: delete → removed_upstream (FR-013)
# ---------------------------------------------------------------------------


class TestWebhookActivityDelete:
    async def test_delete_flags_removed_upstream_and_preserves_session_link(
        self, db
    ) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent)
        await db.commit()

        now = datetime.now(timezone.utc)
        activity = StravaActivity(
            strava_activity_id=123123123,
            athlete_id=athlete.id,
            connection_id=connection.id,
            name="Salida Ficticia XCO",
            sport_type="MountainBikeRide",
            start_date_utc=now,
            start_date_local=now,
            elapsed_time_s=3600,
            ingest_source=StravaIngestSource.webhook,
            upstream_state=StravaUpstreamState.present,
            training_session_id=None,
            linked_by_user_id=None,
        )
        db.add(activity)
        await db.commit()

        event = StravaWebhookEvent(
            object_type="activity",
            aspect_type="delete",
            object_id=123123123,
            owner_id=connection.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
        )
        await process_webhook_event(event, db)
        await db.commit()
        await db.refresh(activity)

        assert activity.upstream_state == StravaUpstreamState.removed_upstream
        # The row itself is never hard-deleted.
        count = (
            await db.execute(select(func.count()).select_from(StravaActivity))
        ).scalar_one()
        assert count == 1

    async def test_delete_of_unknown_activity_is_a_noop(self, db) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent)
        await db.commit()

        event = StravaWebhookEvent(
            object_type="activity",
            aspect_type="delete",
            object_id=999_999_999,  # never synced
            owner_id=connection.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
        )
        # Must not raise.
        await process_webhook_event(event, db)
        await db.commit()

    async def test_unknown_owner_id_is_a_noop(self, db) -> None:
        """A webhook event for a Strava account with no local connection
        (e.g. never connected, or already disconnected+purged) is silently
        ignored — it must never raise."""
        event = StravaWebhookEvent(
            object_type="activity",
            aspect_type="create",
            object_id=1,
            owner_id=123_456_789_999,  # no matching StravaConnection
            subscription_id=1,
            event_time=1_800_000_000,
        )
        await process_webhook_event(event, db)  # must not raise

    async def test_activity_event_skipped_when_connection_not_active(self, db) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(
            db, athlete, consent, status=StravaConnectionStatus.disconnected
        )
        await db.commit()

        event = StravaWebhookEvent(
            object_type="activity",
            aspect_type="create",
            object_id=1,
            owner_id=connection.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
        )
        await process_webhook_event(event, db)  # must not raise, must not fetch

        count = (
            await db.execute(select(func.count()).select_from(StravaActivity))
        ).scalar_one()
        assert count == 0


# ---------------------------------------------------------------------------
# Webhook dispatch: athlete deauth → disconnected (FR-014)
# ---------------------------------------------------------------------------


class TestWebhookAthleteDeauth:
    async def test_authorized_false_disconnects_connection(self, db) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent, status=StravaConnectionStatus.active)
        await db.commit()

        event = StravaWebhookEvent(
            object_type="athlete",
            aspect_type="update",
            object_id=connection.strava_athlete_id,
            owner_id=connection.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
            updates={"authorized": "false"},
        )
        await process_webhook_event(event, db)
        await db.commit()
        await db.refresh(connection)

        assert connection.status == StravaConnectionStatus.disconnected
        assert connection.disconnected_at is not None

    async def test_authorized_true_update_is_ignored(self, db) -> None:
        """Any other athlete-scope update (or ``authorized: true``, a no-op
        re-affirmation) must leave the connection untouched."""
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent, status=StravaConnectionStatus.active)
        await db.commit()

        event = StravaWebhookEvent(
            object_type="athlete",
            aspect_type="update",
            object_id=connection.strava_athlete_id,
            owner_id=connection.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
            updates={"authorized": "true"},
        )
        await process_webhook_event(event, db)
        await db.commit()
        await db.refresh(connection)

        assert connection.status == StravaConnectionStatus.active
        assert connection.disconnected_at is None


# ---------------------------------------------------------------------------
# Webhook dispatch: activity create → fetch + upsert
# ---------------------------------------------------------------------------


class _FakeStravaClientForCreate:
    """Minimal double for ``StravaClient`` used only for the create/update
    dispatch branch — ``ingest.py`` constructs the real client directly with
    no injection point, so this replaces the class reference itself."""

    def __init__(self, connection: StravaConnection, db: AsyncSession) -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeStravaClientForCreate":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def get_activity(self, activity_id: int) -> dict:
        return _raw_activity(strava_id=activity_id)


class TestWebhookActivityCreate:
    async def test_create_event_fetches_and_upserts_activity(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ingest_module, "StravaClient", _FakeStravaClientForCreate)

        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(db, athlete, consent, status=StravaConnectionStatus.active)
        await db.commit()

        event = StravaWebhookEvent(
            object_type="activity",
            aspect_type="create",
            object_id=666777888,
            owner_id=connection.strava_athlete_id,
            subscription_id=1,
            event_time=1_800_000_000,
        )
        await process_webhook_event(event, db)
        await db.commit()

        row = await db.scalar(
            select(StravaActivity).where(StravaActivity.strava_activity_id == 666777888)
        )
        assert row is not None
        assert row.upstream_state == StravaUpstreamState.present
        assert row.athlete_id == athlete.id


# ---------------------------------------------------------------------------
# Reconcile: watermark advance (happy path, FR-004/SC-002)
# ---------------------------------------------------------------------------


class _FakeStravaClientForReconcile:
    def __init__(self, connection: StravaConnection, db: AsyncSession) -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeStravaClientForReconcile":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def list_athlete_activities(self, after, per_page: int = 50):
        for strava_id in (111000111, 222000222):
            yield _raw_activity(strava_id=strava_id)

    async def get_activity(self, activity_id: int) -> dict:
        return _raw_activity(strava_id=activity_id)


class TestReconcileWatermark:
    async def test_reconcile_all_advances_watermark_and_upserts_activities(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(reconcile_module, "StravaClient", _FakeStravaClientForReconcile)

        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(
            db, athlete, consent, status=StravaConnectionStatus.active, last_sync_at=None
        )
        await db.commit()

        before = datetime.now(timezone.utc)
        result = await reconcile_all(db)
        await db.commit()
        await db.refresh(connection)

        assert result["connections_processed"] == 1
        assert result["activities_upserted"] == 2
        assert result["connections_broken"] == 0
        assert connection.last_sync_at is not None
        assert _as_naive_utc(connection.last_sync_at) >= _as_naive_utc(before)

        count = (
            await db.execute(select(func.count()).select_from(StravaActivity))
        ).scalar_one()
        assert count == 2

    async def test_reconcile_all_skips_non_active_connections(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If the fake client were ever invoked for a non-active connection,
        # this test would still pass silently — the meaningful assertion is
        # the zeroed summary below (nothing was processed at all).
        monkeypatch.setattr(reconcile_module, "StravaClient", _FakeStravaClientForReconcile)

        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        await _seed_connection(db, athlete, consent, status=StravaConnectionStatus.disconnected)
        await db.commit()

        result = await reconcile_all(db)

        assert result == {
            "connections_processed": 0,
            "activities_upserted": 0,
            "connections_broken": 0,
        }


# ---------------------------------------------------------------------------
# Reconcile: broken-token path
# ---------------------------------------------------------------------------


class _FakeStravaClientBrokenToken:
    """Simulates a refresh failure surfacing as ``StravaAuthError`` mid-pull
    — mirrors what the real ``StravaClient._ensure_fresh_access_token``
    does on a revoked refresh token (marks the connection ``broken`` before
    raising)."""

    def __init__(self, connection: StravaConnection, db: AsyncSession) -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeStravaClientBrokenToken":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def list_athlete_activities(self, after, per_page: int = 50):
        self._connection.status = StravaConnectionStatus.broken
        self._connection.last_error = "refresh_401"
        raise StravaAuthError("No se pudo renovar el token de Strava.")
        yield  # pragma: no cover - unreachable, keeps this an async generator


class TestReconcileBrokenToken:
    async def test_refresh_failure_marks_connection_broken_and_counts_it(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(reconcile_module, "StravaClient", _FakeStravaClientBrokenToken)

        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(
            db,
            athlete,
            consent,
            status=StravaConnectionStatus.active,
            token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            last_sync_at=None,
        )
        await db.commit()

        result = await reconcile_all(db)
        await db.commit()
        await db.refresh(connection)

        assert connection.status == StravaConnectionStatus.broken
        assert connection.last_error == "refresh_401"
        assert result["connections_processed"] == 1
        assert result["connections_broken"] == 1
        assert result["activities_upserted"] == 0
        # The watermark must NOT advance for a connection whose pull never
        # completed — advancing it would silently skip the un-pulled window
        # on the next (post-reconnect) run.
        assert connection.last_sync_at is None

    async def test_one_broken_connection_does_not_abort_the_others(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A refresh failure on connection N must not roll back or skip
        connection N+1 in the same batch (module docstring: flush per
        connection, never one shared transaction)."""

        # Plain-function factory (not a class) dispatching to the
        # broken-token double for the first athlete processed and to the
        # healthy double for the second — ``reconcile.py`` only ever calls
        # ``StravaClient(connection, db)`` positionally, so any callable
        # with that signature is a valid stand-in.
        router_state: dict[str, int | None] = {"broken_athlete_id": None}

        def _client_factory(connection: StravaConnection, db: AsyncSession):
            if router_state["broken_athlete_id"] is None:
                router_state["broken_athlete_id"] = connection.athlete_id
            if connection.athlete_id == router_state["broken_athlete_id"]:
                return _FakeStravaClientBrokenToken(connection, db)
            return _FakeStravaClientForReconcile(connection, db)

        monkeypatch.setattr(reconcile_module, "StravaClient", _client_factory)

        athlete1 = await _seed_athlete(db)
        consent1 = await _seed_consent(db, athlete1)
        await _seed_connection(db, athlete1, consent1, status=StravaConnectionStatus.active)

        athlete2 = await _seed_athlete(db)
        consent2 = await _seed_consent(db, athlete2)
        await _seed_connection(db, athlete2, consent2, status=StravaConnectionStatus.active)
        await db.commit()

        result = await reconcile_all(db)

        assert result["connections_processed"] == 2
        assert result["connections_broken"] == 1
        assert result["activities_upserted"] == 2  # from the healthy connection only


# ---------------------------------------------------------------------------
# Pure-function unit coverage
# ---------------------------------------------------------------------------


class TestSummaryCompleteHeuristic:
    def test_meta_resource_state_is_incomplete(self) -> None:
        assert _summary_complete({"resource_state": 1}) is False

    def test_core_stats_present_is_complete(self) -> None:
        assert (
            _summary_complete({"elapsed_time": 100, "moving_time": 90, "distance": 500.0})
            is True
        )

    def test_missing_core_stat_is_incomplete(self) -> None:
        assert _summary_complete({"elapsed_time": 100, "moving_time": 90}) is False

    def test_missing_heartrate_alone_is_still_complete(self) -> None:
        """No HR sensor is a legitimate, permanent state — not incompleteness."""
        assert (
            _summary_complete(
                {
                    "elapsed_time": 100,
                    "moving_time": 90,
                    "distance": 500.0,
                    "average_heartrate": None,
                    "max_heartrate": None,
                }
            )
            is True
        )


# ---------------------------------------------------------------------------
# Integration bug: oauth.refresh_access_token() ↔ StravaClient contract
# mismatch (found while writing "token exchange + refresh rotation" tests)
# ---------------------------------------------------------------------------


class TestStravaClientRefreshIntegrationBug:
    @pytest.mark.xfail(
        reason=(
            "BUG (T013/T014 contract mismatch): "
            "oauth.refresh_access_token() returns Strava's raw dict "
            "(documented explicitly in its own docstring: 'return Strava's "
            "raw token response dict'), but "
            "StravaClient._ensure_fresh_access_token() reads the result via "
            "ATTRIBUTE access (result.access_token / result.refresh_token / "
            "result.expires_at) per client.py's module docstring, which "
            "promises a 'TokenRefreshResult' object with those attributes. "
            "A dict has no such attributes, so EVERY real token refresh "
            "raises an unhandled AttributeError (not StravaOAuthError, not "
            "StravaAuthError — the attribute access happens AFTER the "
            "try/except around the oauth call). Strava access tokens expire "
            "every 6h, so this will fire on the daily reconcile job and on "
            "any webhook-triggered activity fetch for a connection whose "
            "token has gone stale — i.e. the feature breaks itself within "
            "hours of a family connecting. Fix: either make "
            "oauth.refresh_access_token() return a small dataclass/object "
            "with those three attributes, or change client.py to read "
            "result['access_token'] / result['refresh_token'] / "
            "datetime.fromtimestamp(result['expires_at'], tz=timezone.utc)."
        ),
        strict=True,
    )
    async def test_strava_client_refresh_rotates_tokens_end_to_end(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        athlete = await _seed_athlete(db)
        consent = await _seed_consent(db, athlete)
        connection = await _seed_connection(
            db,
            athlete,
            consent,
            status=StravaConnectionStatus.active,
            # Well past the 5-minute refresh skew — forces a refresh.
            token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        await db.commit()

        rotated_response = {
            "access_token": "AT_ROTATED_NEW",
            "refresh_token": "RT_ROTATED_NEW",
            "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=6)).timestamp()),
            "expires_in": 21600,
            "token_type": "Bearer",
        }

        async def _fake_refresh(refresh_token: str) -> dict:
            return rotated_response

        # Patch the reference StravaClient actually calls: `oauth.refresh_access_token`.
        import app.services.strava.client as client_module

        monkeypatch.setattr(client_module.oauth, "refresh_access_token", _fake_refresh)

        async with StravaClient(connection, db) as client:
            await client.get_activity(1)  # never reaches the HTTP layer — fails in refresh

        await db.commit()
        await db.refresh(connection)

        assert connection.status == StravaConnectionStatus.active
        assert decrypt_token(connection.access_token_enc) == "AT_ROTATED_NEW"
        assert decrypt_token(connection.refresh_token_enc) == "RT_ROTATED_NEW"
