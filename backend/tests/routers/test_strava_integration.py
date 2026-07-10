"""Router tests for ``strava_integration.py`` (specs/025-strava-activity-sync, T021).

Covers connection management (consent-by-action: connect succeeds with no
consent row, authorize-URL shape, disconnect), the OAuth callback (happy
path, invalid/expired state, scope downgrade, account conflict), and the
machine endpoints (webhook subscription validation, webhook event delivery
ACK, reconcile shared-secret gate).

Why a standalone ASGI app instead of ``app.main.app``
------------------------------------------------------
``app/main.py`` only mounts ``strava_integration.router`` when
``settings.strava_enabled`` is ``True`` **at import time** — and by the time
this test module is collected, ``tests/conftest.py`` (loaded first, for the
whole session) has already imported ``app.main`` with the *default*
(``False``) value from the repo's ``.env``. Flipping the flag afterwards
would not retroactively register the router on the already-built app
singleton, and reloading ``app.main`` would mutate global state shared with
every other test module in the session.

Instead we build a small local ``FastAPI`` app that mounts only
``strava_integration.router`` under the same ``/api`` prefix used in
production (contracts/api.md §A/§B) and drive it with its own
``dependency_overrides`` — the router module still imports the *same*
``get_db``/``get_current_user``/``get_task_dispatcher`` function objects from
``app.dependencies``, so overriding them here works exactly like it would on
the real app.

All outbound Strava HTTP is mocked at the service boundary
(``oauth.exchange_code``, ``StravaClient.deauthorize``,
``reconcile.reconcile_all``) — no real network calls happen in this suite.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

# ``ParentalConsent.policy`` is mapper-level ``lazy="joined"`` — creating the
# ``parental_consents`` table pulls in ``privacy_policies`` (whose
# ``content_html`` is MySQL ``LONGTEXT``, which SQLite has no compiler for).
# Registering a SQLite-only compile rule (TEXT is SQLite's native unbounded
# string type) is the standard SQLAlchemy escape hatch and only affects DDL
# compiled against the ``sqlite`` dialect in this test module's own in-memory
# engine — no product code changes. (The router itself no longer selects
# ParentalConsent — consent-by-action retired the consent lookup.)
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"

from app.config import settings
from app.dependencies import get_current_user, get_db, get_task_dispatcher
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.user import User, UserRole
from app.routers import strava_integration
from app.services.strava import oauth
from app.services.strava.client import StravaClient
from app.services.strava.token_store import encrypt_token

_TABLES = (
    "users",
    "clubs",
    "athletes",
    "privacy_policies",  # see LONGTEXT compiler shim above
    "parental_consents",
    "strava_connections",
    "strava_activities",
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Local ASGI app (see module docstring for why not app.main.app)
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(strava_integration.router, prefix="/api")
    return test_app


# ---------------------------------------------------------------------------
# DB fixtures — in-memory aiosqlite, subset of tables (mirrors tests/anxiety)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
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


# ---------------------------------------------------------------------------
# Settings — enable Strava + provide test-only secrets for the whole module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _strava_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "strava_enabled", True)
    monkeypatch.setattr(settings, "strava_client_id", "test-client-id")
    monkeypatch.setattr(settings, "strava_client_secret", "test-client-secret")
    monkeypatch.setattr(settings, "strava_webhook_verify_token", "test-verify-token")
    monkeypatch.setattr(settings, "strava_reconcile_token", "test-reconcile-token")
    monkeypatch.setattr(
        settings, "strava_token_encryption_key", Fernet.generate_key().decode()
    )
    # Aísla del .env real del host: si el desarrollador tiene
    # STRAVA_SUBSCRIPTION_ID configurado localmente (suscripción real creada),
    # se filtraría a estos tests y el guard anti-spoofing (§B) rechazaría los
    # eventos de prueba por subscription_id mismatch.
    monkeypatch.setattr(settings, "strava_subscription_id", "")


@pytest.fixture(autouse=True)
def _clear_app_overrides():
    yield
    # Belt-and-suspenders: each test builds its own app instance via
    # make_client(), so there is nothing to clear on app.main.app — but we
    # guard here in case a future test imports app.main.app by mistake.
    from app.main import app as real_app

    real_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def seed_user(session: AsyncSession, user_id: int, role: UserRole) -> User:
    u = User(
        id=user_id,
        email=f"{role.value}{user_id}@test.com",
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


async def seed_athlete(
    session: AsyncSession,
    athlete_id: int,
    *,
    club_id: int = 1,
    user_id: int = 900,
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=user_id,
        first_name="Atleta",
        last_name=f"N{athlete_id}",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def grant_sync_consent(
    session: AsyncSession,
    athlete_id: int,
    parent_user_id: int,
    *,
    withdrawn: bool = False,
) -> ParentalConsent:
    """Seed a plain ``parental_consents`` row (used only as an optional legacy
    ``consent_id`` reference — the connect flow no longer requires it)."""
    c = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        consented_at=_utc(),
        withdrawn_at=_utc() if withdrawn else None,
    )
    session.add(c)
    await session.flush()
    return c


async def seed_connection(
    session: AsyncSession,
    *,
    athlete_id: int,
    strava_athlete_id: int,
    authorized_by_user_id: int,
    consent_id: int | None = None,
    status: StravaConnectionStatus = StravaConnectionStatus.active,
) -> StravaConnection:
    conn = StravaConnection(
        athlete_id=athlete_id,
        strava_athlete_id=strava_athlete_id,
        status=status,
        access_token_enc=encrypt_token("plain-access-token"),
        refresh_token_enc=encrypt_token("plain-refresh-token"),
        token_expires_at=_utc() + timedelta(hours=6),
        scope_granted="activity:read_all",
        authorized_by_user_id=authorized_by_user_id,
        consent_id=consent_id,
        connected_at=_utc(),
    )
    session.add(conn)
    await session.flush()
    return conn


def coach_user_typed(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    """``verify_athlete_access`` compares ``role_in_club`` against the
    ``ClubRole`` enum, not a raw string — the membership stub must match."""
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        club_memberships=[SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)],
    )


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def make_client(
    session: AsyncSession,
    *,
    user,
    dispatcher=None,
) -> AsyncClient:
    """Build an AsyncClient bound to a fresh local app with DB/auth overrides."""
    test_app = _build_app()

    async def _override_db():
        yield session
        await session.commit()

    async def _override_user():
        return user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_user

    if dispatcher is not None:
        test_app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        follow_redirects=False,
    )


class _RecordingDispatcher:
    """Fake TaskDispatcher: records dispatched calls, never executes them."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def dispatch(self, func, /, *args, **kwargs) -> None:
        self.calls.append((func, args, kwargs))


# ===========================================================================
# A. Connection management — consent gate, authorize-URL, disconnect
# ===========================================================================


class TestConnect:
    async def test_connect_without_consent_row_succeeds(self, session):
        """Consent-by-action: authorizing the OAuth connection IS the consent,
        so connect must succeed with NO ``parental_consents`` row present."""
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100)
        await session.commit()

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post("/api/athletes/100/strava/connect")

        assert resp.status_code == 200, resp.text
        assert resp.json()["authorize_url"].startswith(settings.strava_oauth_base_url)

    async def test_connect_happy_path_returns_authorize_url(self, session):
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100)
        await session.commit()

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post("/api/athletes/100/strava/connect")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        url = body["authorize_url"]
        assert url.startswith(settings.strava_oauth_base_url)
        assert "client_id=test-client-id" in url
        assert "scope=activity%3Aread_all" in url
        assert "state=" in url

        # state round-trips to the requesting athlete/user (FR-001).
        state = url.split("state=")[1].split("&")[0]
        claims = oauth.verify_state(state)
        assert claims == {"athlete_id": 100, "user_id": 10}

    async def test_connect_disabled_master_switch_returns_503(
        self, session, monkeypatch: pytest.MonkeyPatch
    ):
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100)
        await session.commit()
        monkeypatch.setattr(settings, "strava_enabled", False)

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post("/api/athletes/100/strava/connect")

        assert resp.status_code == 503, resp.text

    async def test_connect_rbac_coach_wrong_club_returns_403(self, session):
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100, club_id=2)  # coach is only in club 1
        await session.commit()

        async with make_client(session, user=coach_user_typed(club_id=1)) as client:
            resp = await client.post("/api/athletes/100/strava/connect")

        assert resp.status_code == 403, resp.text

    async def test_connect_athlete_not_found_returns_404(self, session):
        await seed_user(session, 10, UserRole.coach)
        await session.commit()

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post("/api/athletes/999/strava/connect")

        assert resp.status_code == 404, resp.text


class TestDisconnect:
    async def test_disconnect_returns_204(
        self, session, monkeypatch: pytest.MonkeyPatch
    ):
        await seed_user(session, 10, UserRole.coach)
        await seed_user(session, 20, UserRole.parent)
        await seed_athlete(session, 100)
        consent = await grant_sync_consent(session, 100, 20)
        await seed_connection(
            session,
            athlete_id=100,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            consent_id=consent.id,
        )
        await session.commit()

        deauth_calls: list[str] = []

        async def _fake_deauthorize(self, access_token: str) -> None:
            deauth_calls.append(access_token)

        monkeypatch.setattr(StravaClient, "deauthorize", _fake_deauthorize)

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.delete("/api/athletes/100/strava/connection")

        assert resp.status_code == 204, resp.text
        assert deauth_calls == ["plain-access-token"]

        conn = await session.get(StravaConnection, 1)
        assert conn.status == StravaConnectionStatus.disconnected
        assert conn.disconnected_at is not None

    async def test_disconnect_best_effort_survives_upstream_failure(
        self, session, monkeypatch: pytest.MonkeyPatch
    ):
        """FR-014: local disconnect MUST succeed even if the courtesy
        upstream deauthorize call fails.

        Raises a real ``httpx.HTTPError`` from the transport layer (not a
        replaced ``deauthorize`` method) so the assertion exercises
        ``StravaClient.deauthorize``'s own internal swallow-and-log
        behavior, not a test double standing in for it.
        """
        await seed_user(session, 10, UserRole.coach)
        await seed_user(session, 20, UserRole.parent)
        await seed_athlete(session, 100)
        consent = await grant_sync_consent(session, 100, 20)
        await seed_connection(
            session,
            athlete_id=100,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            consent_id=consent.id,
        )
        await session.commit()

        async def _raising_post(self, *args, **kwargs):
            raise httpx.ConnectError("Strava unreachable")

        monkeypatch.setattr(httpx.AsyncClient, "post", _raising_post)

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.delete("/api/athletes/100/strava/connection")

        assert resp.status_code == 204, resp.text
        conn = await session.get(StravaConnection, 1)
        assert conn.status == StravaConnectionStatus.disconnected

    async def test_disconnect_no_connection_returns_404(self, session):
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100)
        await session.commit()

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.delete("/api/athletes/100/strava/connection")

        assert resp.status_code == 404, resp.text


# ===========================================================================
# A. OAuth callback (public)
# ===========================================================================


class TestOAuthCallback:
    def _valid_state(self, athlete_id: int = 100, user_id: int = 10) -> str:
        return oauth.sign_state(athlete_id, user_id)

    async def test_callback_happy_path_activates_connection(
        self, session, monkeypatch: pytest.MonkeyPatch
    ):
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100)
        await session.commit()

        async def _fake_exchange_code(code: str) -> dict:
            assert code == "auth-code-123"
            return {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_at": int((_utc() + timedelta(hours=6)).timestamp()),
                "athlete": {"id": 999888},
            }

        monkeypatch.setattr(oauth, "exchange_code", _fake_exchange_code)

        state = self._valid_state()
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={
                    "state": state,
                    "code": "auth-code-123",
                    "scope": "read,activity:read_all",
                },
            )

        assert resp.status_code == 302, resp.text
        location = resp.headers["location"]
        assert location == "http://localhost:5173/athletes/100?strava=conectado"

        conn = await session.get(StravaConnection, 1)
        assert conn is not None
        assert conn.status == StravaConnectionStatus.active
        assert conn.strava_athlete_id == 999888
        assert conn.authorized_by_user_id == 10
        # Consent-by-action: no separate consent row is linked.
        assert conn.consent_id is None

    async def test_callback_invalid_state_returns_400(self, session):
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={"state": "not-a-real-token", "code": "x", "scope": "activity:read_all"},
            )

        assert resp.status_code == 400, resp.text

    async def test_callback_expired_state_returns_400(self, session):
        expired_state = jwt.encode(
            {
                "athlete_id": 100,
                "user_id": 10,
                "nonce": "abc",
                "type": "strava_oauth_state",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={"state": expired_state, "code": "x", "scope": "activity:read_all"},
            )

        assert resp.status_code == 400, resp.text

    async def test_callback_scope_downgrade_redirects_with_error(self, session):
        await seed_user(session, 10, UserRole.coach)
        await seed_athlete(session, 100)
        await session.commit()

        state = self._valid_state()
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={"state": state, "code": "x", "scope": "read"},
            )

        assert resp.status_code == 302, resp.text
        location = resp.headers["location"]
        assert "error=scope" in location
        assert "/athletes/100" in location

        # No connection row should have been created.
        conn = await session.get(StravaConnection, 1)
        assert conn is None

    async def test_callback_account_conflict_redirects_with_error(
        self, session, monkeypatch: pytest.MonkeyPatch
    ):
        # Athlete 200 already owns strava_athlete_id=999888.
        await seed_user(session, 10, UserRole.coach)
        await seed_user(session, 20, UserRole.parent)
        await seed_athlete(session, 100)
        await seed_athlete(session, 200, user_id=901)
        consent_200 = await grant_sync_consent(session, 200, 20)
        await seed_connection(
            session,
            athlete_id=200,
            strava_athlete_id=999888,
            authorized_by_user_id=20,
            consent_id=consent_200.id,
        )
        await grant_sync_consent(session, 100, 20)
        await session.commit()

        async def _fake_exchange_code(code: str) -> dict:
            return {
                "access_token": "a",
                "refresh_token": "b",
                "expires_at": int((_utc() + timedelta(hours=6)).timestamp()),
                "athlete": {"id": 999888},  # SAME strava account as athlete 200
            }

        monkeypatch.setattr(oauth, "exchange_code", _fake_exchange_code)

        state = self._valid_state(athlete_id=100, user_id=10)
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={"state": state, "code": "x", "scope": "activity:read_all"},
            )

        assert resp.status_code == 302, resp.text
        assert "error=cuenta_en_uso" in resp.headers["location"]

        # Athlete 100 must NOT have gotten a connection out of this.
        conn_100 = (
            await session.execute(
                StravaConnection.__table__.select().where(
                    StravaConnection.athlete_id == 100
                )
            )
        ).first()
        assert conn_100 is None

    async def test_callback_denied_by_user_redirects_with_error(self, session):
        state = self._valid_state()
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={"state": state, "error": "access_denied"},
            )

        assert resp.status_code == 302, resp.text
        assert "error=denegado" in resp.headers["location"]


# ===========================================================================
# B. Machine endpoints — webhook + reconcile
# ===========================================================================


class TestWebhookValidation:
    async def test_webhook_get_echoes_challenge_200(self, session):
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "echo-me-123",
                    "hub.verify_token": "test-verify-token",
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"hub.challenge": "echo-me-123"}

    async def test_webhook_get_bad_token_returns_403(self, session):
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/integrations/strava/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "echo-me-123",
                    "hub.verify_token": "wrong-token",
                },
            )

        assert resp.status_code == 403, resp.text


class TestWebhookEventDelivery:
    async def test_webhook_post_returns_200_immediately(self, session):
        """The 2-second ACK rule (contracts/api.md §B): the endpoint must
        respond 200 {} without doing any DB work synchronously — processing
        is handed off to the dispatcher (recorded, never executed here)."""
        dispatcher = _RecordingDispatcher()
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 123456,
            "owner_id": 999888,
            "subscription_id": 1,
            "event_time": int(_utc().timestamp()),
            "updates": {},
        }

        async with make_client(session, user=coach_user_typed(), dispatcher=dispatcher) as client:
            resp = await client.post("/api/integrations/strava/webhook", json=payload)

        assert resp.status_code == 200, resp.text
        assert resp.json() == {}
        assert len(dispatcher.calls) == 1

        # No DB writes should have happened synchronously (nothing to see
        # here since processing never ran) — the strava_connections table
        # stays empty.
        rows = (await session.execute(StravaConnection.__table__.select())).all()
        assert rows == []

    async def test_webhook_post_duplicate_delivery_is_also_ack_200(self, session):
        """Replays are a no-op at the ingest layer (idempotent upsert); the
        webhook endpoint itself always ACKs 200 regardless of dedup state."""
        dispatcher = _RecordingDispatcher()
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 123456,
            "owner_id": 999888,
            "subscription_id": 1,
            "event_time": int(_utc().timestamp()),
            "updates": {},
        }

        async with make_client(session, user=coach_user_typed(), dispatcher=dispatcher) as client:
            first = await client.post("/api/integrations/strava/webhook", json=payload)
            second = await client.post("/api/integrations/strava/webhook", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert len(dispatcher.calls) == 2  # both delivered/dispatched; ingest dedups downstream

    async def test_webhook_post_missing_field_returns_422(self, session):
        dispatcher = _RecordingDispatcher()
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            # object_id missing
            "owner_id": 999888,
            "subscription_id": 1,
            "event_time": int(_utc().timestamp()),
        }

        async with make_client(session, user=coach_user_typed(), dispatcher=dispatcher) as client:
            resp = await client.post("/api/integrations/strava/webhook", json=payload)

        assert resp.status_code == 422, resp.text
        assert dispatcher.calls == []


class TestReconcile:
    async def test_reconcile_without_header_returns_403(self, session):
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post("/api/integrations/strava/reconcile")

        assert resp.status_code == 403, resp.text

    async def test_reconcile_with_wrong_token_returns_403(self, session):
        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post(
                "/api/integrations/strava/reconcile",
                headers={"X-Reconcile-Token": "not-the-secret"},
            )

        assert resp.status_code == 403, resp.text

    async def test_reconcile_with_valid_token_returns_200(
        self, session, monkeypatch: pytest.MonkeyPatch
    ):
        from app.routers import strava_integration as router_module

        async def _fake_reconcile_all(db) -> dict:
            return {
                "connections_processed": 3,
                "activities_upserted": 7,
                "connections_broken": 0,
            }

        monkeypatch.setattr(router_module, "reconcile_all", _fake_reconcile_all)

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.post(
                "/api/integrations/strava/reconcile",
                headers={"X-Reconcile-Token": "test-reconcile-token"},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "connections_processed": 3,
            "activities_upserted": 7,
            "connections_broken": 0,
        }
