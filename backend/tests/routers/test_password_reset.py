"""Tests del router de restablecimiento de contraseña (specs/003-password-reset-login).

Usa un engine SQLite real + override de get_db y un NotificationService falso
que registra los envíos (sin red).
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db, get_notification_service
from app.main import app
from app.models.base import Base
from app.models.user import User, UserRole
from app.schemas.notification import NotificationResult
from app.services.auth import hash_password, verify_password


class FakeNotificationService:
    """Registra los NotificationRequest sin enviar nada."""

    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, request, dispatcher=None) -> NotificationResult:
        self.sent.append(request)
        return NotificationResult(success=True, message_id="fake")


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in ("users", "password_reset_tokens")]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def fake_emails(session_factory):
    fake = FakeNotificationService()

    async def _override_db():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_notification_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(fake_emails) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_user(session_factory, **kw) -> None:
    async with session_factory() as s:
        s.add(
            User(
                id=kw.get("user_id", 1),
                email=kw.get("email", "coach@test.com"),
                hashed_password=hash_password(kw.get("password", "OldPass123")),
                first_name="Carlos",
                last_name="Gomez",
                role=UserRole.coach,
                is_active=kw.get("is_active", True),
                can_login=kw.get("can_login", True),
            )
        )
        await s.commit()


NEUTRAL = "Si el correo está registrado"


@pytest.mark.asyncio
async def test_request_known_email_dispatches_email(client, fake_emails, session_factory):
    await _seed_user(session_factory)
    resp = await client.post(
        "/api/auth/password-reset/request", json={"email": "coach@test.com"}
    )
    assert resp.status_code == 200
    assert NEUTRAL in resp.json()["message"]
    assert len(fake_emails.sent) == 1
    assert fake_emails.sent[0].template.value == "password_reset"


@pytest.mark.asyncio
async def test_request_unknown_email_same_message_no_dispatch(
    client, fake_emails, session_factory
):
    await _seed_user(session_factory)
    resp = await client.post(
        "/api/auth/password-reset/request", json={"email": "nadie@test.com"}
    )
    assert resp.status_code == 200
    assert NEUTRAL in resp.json()["message"]
    assert fake_emails.sent == []


@pytest.mark.asyncio
async def test_request_inactive_neutral_no_dispatch(client, fake_emails, session_factory):
    await _seed_user(session_factory, email="off@test.com", is_active=False)
    resp = await client.post(
        "/api/auth/password-reset/request", json={"email": "off@test.com"}
    )
    assert resp.status_code == 200
    assert fake_emails.sent == []


@pytest.mark.asyncio
async def test_request_invalid_email_422(client):
    resp = await client.post("/api/auth/password-reset/request", json={"email": "  "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_full_flow_validate_and_confirm(client, fake_emails, session_factory):
    await _seed_user(session_factory, password="OldPass123")
    await client.post(
        "/api/auth/password-reset/request", json={"email": "coach@test.com"}
    )
    raw_token = fake_emails.sent[0].context["reset_url"].split("token=")[1]

    # validate
    v = await client.get(f"/api/auth/password-reset/validate?token={raw_token}")
    assert v.status_code == 200 and v.json()["valid"] is True

    # confirm
    c = await client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "NewPass456"},
    )
    assert c.status_code == 200
    # No emite tokens de sesión (sin auto-login).
    assert "access_token" not in c.json()
    # Email de confirmación enviado.
    assert any(m.template.value == "password_changed" for m in fake_emails.sent)

    # La contraseña realmente cambió.
    async with session_factory() as s:
        user = await s.get(User, 1)
        assert verify_password("NewPass456", user.hashed_password)
        assert not verify_password("OldPass123", user.hashed_password)

    # Token ya usado → 410.
    again = await client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "Another789"},
    )
    assert again.status_code == 410


@pytest.mark.asyncio
async def test_confirm_weak_password_422(client, fake_emails, session_factory):
    await _seed_user(session_factory)
    await client.post(
        "/api/auth/password-reset/request", json={"email": "coach@test.com"}
    )
    raw_token = fake_emails.sent[0].context["reset_url"].split("token=")[1]
    resp = await client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_unknown_token_404(client):
    resp = await client.get("/api/auth/password-reset/validate?token=nope")
    assert resp.status_code == 404
