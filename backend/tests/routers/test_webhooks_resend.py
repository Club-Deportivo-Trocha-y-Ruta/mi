"""Tests del webhook de Resend para señales de entrega (feature 038, T401, P3).

Cubre:
- ``resend_webhook_secret`` vacío -> 404 en cualquier llamada (feature apagada).
- Firma Svix válida -> procesa el evento e inserta `newsletter_delivery_events`.
- Firma inválida -> 400.
- Replay del mismo `svix-id` -> ignorado (idempotencia por `provider_event_id`).
- `email_id` (data.email_id) desconocido -> ignorado sin error (200).
- Ningún log emitido durante el procesamiento contiene el email del padre.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

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

from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.models import Base
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
)

_TEST_SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
_PARENT_EMAIL = "padre@test.com"


# ---------------------------------------------------------------------------
# Helper de firma (réplica del algoritmo del router, para armar requests
# válidas en los tests)
# ---------------------------------------------------------------------------


def _sign(secret: str, svix_id: str, svix_timestamp: str, body: bytes) -> str:
    raw = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    padded = raw + "=" * (-len(raw) % 4)
    secret_bytes = base64.b64decode(padded)
    signed_content = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + body
    digest = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("utf-8")


def _headers(secret: str, body: bytes, *, svix_id: str = "msg_1") -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = _sign(secret, svix_id, timestamp, body)
    return {
        "svix-id": svix_id,
        "svix-timestamp": timestamp,
        "svix-signature": signature,
    }


# ---------------------------------------------------------------------------
# Engine + seeded factory + client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "parent_athlete",
            "anthropometric_records",
            "athlete_monthly_newsletters",
            "newsletter_delivery_events",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(session_factory):
    """1 club, 1 padre, 1 atleta vinculado, 1 boletín `sent` con
    `provider_message_id="resend_msg_abc"` (evento `sent` en
    `newsletter_delivery_events`).
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_user(s, user_id=200, role=UserRole.parent, email=_PARENT_EMAIL)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await link_parent_to_athlete(s, parent_user_id=200, athlete_id=144)

        now = datetime.now(timezone.utc)
        nl = AthleteMonthlyNewsletter(
            id=1,
            athlete_id=144,
            year=2026,
            month=6,
            status=NewsletterStatus.sent,
            metrics_snapshot={"email_blocks": {}, "pdf_only_blocks": {}},
            sent_at=now,
            generated_by_user_id=10,
        )
        s.add(nl)
        s.add(
            NewsletterDeliveryEvent(
                newsletter_id=1,
                parent_user_id=200,
                event_type=DeliveryEventType.sent,
                provider_message_id="resend_msg_abc",
                occurred_at=now,
            )
        )
        await s.commit()
    return session_factory


@pytest_asyncio.fixture
async def client(seeded_factory) -> AsyncGenerator[AsyncClient, None]:
    async def _override_db():
        async with seeded_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def with_secret(monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", _TEST_SECRET)
    yield _TEST_SECRET


@pytest.fixture
def without_secret(monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", "")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_secret_configured_returns_404(client, without_secret):
    body = json.dumps(
        {"type": "email.delivered", "created_at": "2026-06-10T10:00:00Z", "data": {"email_id": "resend_msg_abc"}}
    ).encode()
    resp = await client.post(
        "/api/webhooks/resend",
        content=body,
        headers=_headers("whsec_" + base64.b64encode(b"x" * 32).decode(), body),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_valid_signature_processes_delivered_event(client, with_secret, seeded_factory):
    body = json.dumps(
        {
            "type": "email.delivered",
            "created_at": "2026-06-10T10:00:00Z",
            "data": {"email_id": "resend_msg_abc"},
        }
    ).encode()
    resp = await client.post(
        "/api/webhooks/resend",
        content=body,
        headers=_headers(with_secret, body, svix_id="evt_delivered_1"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    async with seeded_factory() as s:
        result = await s.execute(
            select(NewsletterDeliveryEvent).where(
                NewsletterDeliveryEvent.event_type == DeliveryEventType.delivered
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].newsletter_id == 1
        assert rows[0].provider_message_id == "resend_msg_abc"
        assert rows[0].provider_event_id == "evt_delivered_1"


@pytest.mark.asyncio
async def test_invalid_signature_returns_400(client, with_secret):
    body = json.dumps(
        {"type": "email.opened", "created_at": "2026-06-10T10:00:00Z", "data": {"email_id": "resend_msg_abc"}}
    ).encode()
    headers = _headers(with_secret, body)
    headers["svix-signature"] = "v1,invalid-signature-value"
    resp = await client.post("/api/webhooks/resend", content=body, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_replay_same_svix_id_is_ignored(client, with_secret, seeded_factory):
    body = json.dumps(
        {"type": "email.opened", "created_at": "2026-06-10T10:00:00Z", "data": {"email_id": "resend_msg_abc"}}
    ).encode()
    headers = _headers(with_secret, body, svix_id="evt_replay_1")

    first = await client.post("/api/webhooks/resend", content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["status"] == "processed"

    second = await client.post("/api/webhooks/resend", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    async with seeded_factory() as s:
        result = await s.execute(
            select(NewsletterDeliveryEvent).where(
                NewsletterDeliveryEvent.event_type == DeliveryEventType.opened
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_unknown_email_id_is_ignored(client, with_secret, seeded_factory):
    body = json.dumps(
        {
            "type": "email.bounced",
            "created_at": "2026-06-10T10:00:00Z",
            "data": {"email_id": "unknown_message_id"},
        }
    ).encode()
    resp = await client.post(
        "/api/webhooks/resend",
        content=body,
        headers=_headers(with_secret, body, svix_id="evt_unknown_1"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    async with seeded_factory() as s:
        result = await s.execute(
            select(NewsletterDeliveryEvent).where(
                NewsletterDeliveryEvent.event_type == DeliveryEventType.bounced
            )
        )
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_no_log_contains_recipient_email(client, with_secret, caplog):
    body = json.dumps(
        {"type": "email.clicked", "created_at": "2026-06-10T10:00:00Z", "data": {"email_id": "resend_msg_abc"}}
    ).encode()
    with caplog.at_level(logging.INFO):
        resp = await client.post(
            "/api/webhooks/resend",
            content=body,
            headers=_headers(with_secret, body, svix_id="evt_clicked_1"),
        )
    assert resp.status_code == 200
    for record in caplog.records:
        assert _PARENT_EMAIL not in record.getMessage()
