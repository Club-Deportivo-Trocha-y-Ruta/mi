"""Tests de auditoría (feature 041, T029) para actores no-HTTP y máquinas.

Cubre contracts/audit-recording.md §4.11/§4.12 y §3.3: el webhook de Resend
(``actor_kind=webhook``), el callback OAuth de Strava (GET mutante,
``actor_kind=user`` resuelto desde el ``state`` firmado) y un job disparado
por script (``actor_kind=system``, ``backfill_anthropometry``).

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.dependencies import get_db
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.anthropometry import MaturationStatus
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.audit_log import AuditActorKind, AuditLog
from app.models.club import Club
from app.models.newsletter_delivery_event import NewsletterDeliveryEvent
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 1. Webhook — POST /api/webhooks/resend (actor_kind=webhook)
# ---------------------------------------------------------------------------


class TestResendWebhookAudit:
    async def _build_app(self) -> FastAPI:
        from app.routers.webhooks_resend import router as resend_router

        test_app = FastAPI()
        test_app.include_router(resend_router, prefix="/api/webhooks")
        return test_app

    def _svix_headers(self, secret: str, body: bytes) -> dict[str, str]:
        svix_id = "msg_test_1"
        svix_timestamp = str(int(time.time()))
        raw = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
        padded = raw + "=" * (-len(raw) % 4)
        secret_bytes = base64.b64decode(padded)
        signed_content = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + body
        expected = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(expected).decode("utf-8")
        return {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": f"v1,{expected_b64}",
        }

    async def test_delivered_event_records_webhook_audit_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "whsec_" + base64.b64encode(b"0" * 32).decode("utf-8")
        monkeypatch.setattr(settings, "resend_webhook_secret", secret)

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        tables = [
            Base.metadata.tables[t]
            for t in (
                "clubs",
                "users",
                "athletes",
                "athlete_monthly_newsletters",
                "newsletter_delivery_events",
                *AUDIT_TABLES,
            )
        ]
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            session.add(Club(id=1, name="Club Ficticio 041", code="cft-041-t029", is_active=True))
            session.add(
                User(
                    id=9001,
                    first_name="Atleta",
                    last_name="Ficticio",
                    role=UserRole.athlete,
                    is_active=True,
                    can_login=False,
                )
            )
            session.add(
                Athlete(
                    id=200,
                    user_id=9001,
                    first_name="Deportista",
                    last_name="Ficticio",
                    birth_date=date(2013, 6, 20),
                    sex=Sex.F,
                    club_id=1,
                    created_by=1,
                )
            )
            session.add(
                AthleteMonthlyNewsletter(
                    id=1, athlete_id=200, year=2026, month=8, status=NewsletterStatus.sent
                )
            )
            session.add(
                NewsletterDeliveryEvent(
                    newsletter_id=1,
                    parent_user_id=None,
                    event_type="sent",
                    provider_message_id="email-abc",
                    provider_event_id="msg_sent_seed",
                    occurred_at=_utc(),
                )
            )
            await session.commit()

        body = (
            b'{"type":"email.delivered","created_at":"2026-09-09T12:00:00Z",'
            b'"data":{"email_id":"email-abc"}}'
        )
        headers = self._svix_headers(secret, body)

        test_app = await self._build_app()

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with session_factory() as session:
                yield session
                await session.commit()

        test_app.dependency_overrides[get_db] = _override_db

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/webhooks/resend", content=body, headers=headers
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "processed"

        async with session_factory() as session:
            result = await session.execute(select(AuditLog))
            rows = result.scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.actor_kind == AuditActorKind.webhook
        assert row.actor_user_id is None
        assert row.entity_type == "athlete_monthly_newsletter"
        assert row.entity_id == 1
        assert row.athlete_id == 200
        assert row.club_id == 1
        assert row.meta_json == {"job": "resend_webhook", "event_type": "delivered"}

        await engine.dispose()


# ---------------------------------------------------------------------------
# 2. Strava OAuth callback — GET mutante (actor_kind=user, resuelto de state)
# ---------------------------------------------------------------------------


class TestStravaCallbackAudit:
    @pytest.fixture(autouse=True)
    def _strava_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "strava_enabled", True)
        monkeypatch.setattr(settings, "strava_client_id", "test-client-id")
        monkeypatch.setattr(settings, "strava_client_secret", "test-client-secret")
        monkeypatch.setattr(
            settings, "strava_token_encryption_key", Fernet.generate_key().decode()
        )
        monkeypatch.setattr(settings, "strava_subscription_id", "")

    async def test_callback_success_records_link_audit_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.dependencies import get_current_user
        from app.routers import strava_integration
        from app.services.strava import oauth

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        tables = [
            Base.metadata.tables[t]
            for t in ("clubs", "users", "athletes", "strava_connections", *AUDIT_TABLES)
        ]
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            session.add(Club(id=1, name="Club Ficticio 041", code="cft-041-cb", is_active=True))
            session.add(
                User(
                    id=10,
                    email="coach10@test.local",
                    hashed_password="x",
                    first_name="Test",
                    last_name="Coach",
                    role=UserRole.coach,
                    is_active=True,
                    can_login=True,
                )
            )
            session.add(
                User(
                    id=9001,
                    first_name="Atleta",
                    last_name="Ficticio",
                    role=UserRole.athlete,
                    is_active=True,
                    can_login=False,
                )
            )
            session.add(
                Athlete(
                    id=300,
                    user_id=9001,
                    first_name="Deportista",
                    last_name="Ficticio",
                    birth_date=date(2012, 3, 1),
                    sex=Sex.M,
                    club_id=1,
                    created_by=1,
                )
            )
            await session.commit()

        state = oauth.build_authorize_url(300, 10).split("state=")[1].split("&")[0]

        async def _fake_exchange_code(code: str) -> dict:
            return {
                "athlete": {"id": 777},
                "expires_at": int(time.time()) + 3600,
                "access_token": "plain-access-token",
                "refresh_token": "plain-refresh-token",
            }

        monkeypatch.setattr(oauth, "exchange_code", _fake_exchange_code)

        test_app = FastAPI()
        test_app.include_router(strava_integration.router, prefix="/api")

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with session_factory() as session:
                yield session
                await session.commit()

        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[get_current_user] = lambda: None

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                "/api/integrations/strava/callback",
                params={"state": state, "code": "auth-code", "scope": "activity:read_all"},
            )

        assert resp.status_code == 302, resp.text
        assert "strava=conectado" in resp.headers["location"]

        async with session_factory() as session:
            result = await session.execute(select(AuditLog))
            rows = result.scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.actor_kind == AuditActorKind.user
        assert row.actor_user_id == 10
        assert row.entity_type == "strava_connection"
        assert row.action.value == "link"
        assert row.athlete_id == 300
        assert row.club_id == 1

        await engine.dispose()


# ---------------------------------------------------------------------------
# 3. Job disparado por script — backfill_anthropometry (actor_kind=system)
# ---------------------------------------------------------------------------


class TestAnthropometryBackfillAudit:
    async def test_backfill_records_system_audit_row_per_updated_record(self) -> None:
        from app.models.anthropometry import AnthropometricRecord
        from app.scripts.backfill_anthropometry import backfill_anthropometry

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        tables = [
            Base.metadata.tables[t]
            for t in (
                "clubs",
                "users",
                "athletes",
                "anthropometric_records",
                *AUDIT_TABLES,
            )
        ]
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        birth_date = date(2013, 1, 1)
        eval_date = date(2026, 1, 1)

        async with session_factory() as session:
            session.add(Club(id=1, name="Club Ficticio 041", code="cft-041-bf", is_active=True))
            session.add(
                User(
                    id=9001,
                    first_name="Atleta",
                    last_name="Ficticio",
                    role=UserRole.athlete,
                    is_active=True,
                    can_login=False,
                )
            )
            session.add(
                Athlete(
                    id=400,
                    user_id=9001,
                    first_name="Deportista",
                    last_name="Ficticio",
                    birth_date=birth_date,
                    sex=Sex.M,
                    club_id=1,
                    created_by=1,
                )
            )
            session.add(
                AnthropometricRecord(
                    id=1,
                    athlete_id=400,
                    evaluation_date=eval_date,
                    weight_kg=40,
                    standing_height_cm=150,
                    sitting_height_cm=80,
                    leg_length_cm=70,
                    leg_sitting_ratio=1.14,
                    maturity_offset=-1.0,
                    age_at_phv=13.0,
                    maturation_status=MaturationStatus.pre_phv,
                    evaluated_by=1,
                )
            )
            await session.commit()

        async with session_factory() as session:
            summary = await backfill_anthropometry(session)

        assert summary.scanned == 1

        async with session_factory() as session:
            result = await session.execute(select(AuditLog))
            rows = result.scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.actor_kind == AuditActorKind.system
        assert row.actor_user_id is None
        assert row.entity_type == "anthropometric_record"
        assert row.entity_id == 1
        assert row.athlete_id == 400
        assert row.club_id == 1
        assert row.meta_json == {
            "job": "anthropometry_backfill",
            "event_date": "2026-01-01",
        }
        assert "bmi" in row.changed_fields

        await engine.dispose()
