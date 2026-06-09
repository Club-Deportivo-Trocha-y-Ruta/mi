"""Tests del servicio de restablecimiento de contraseña (specs/003-password-reset-login)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models.base import Base
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User, UserRole
from app.services import password_reset as svc
from app.services.auth import hash_password, verify_password


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
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _mk_user(
    session: AsyncSession,
    *,
    user_id: int = 1,
    email: str = "coach@test.local",
    password: str = "OldPass123",
    is_active: bool = True,
    can_login: bool = True,
) -> User:
    u = User(
        id=user_id,
        email=email,
        hashed_password=hash_password(password),
        first_name="Carlos",
        last_name="Gomez",
        role=UserRole.coach,
        is_active=is_active,
        can_login=can_login,
    )
    session.add(u)
    await session.flush()
    return u


@pytest.mark.asyncio
async def test_request_reset_eligible_creates_hashed_token(session):
    user = await _mk_user(session)
    result = await svc.request_reset("coach@test.local", session)
    assert result is not None
    returned_user, reset_url = result
    assert returned_user.id == user.id
    assert "token=" in reset_url

    rows = (await session.execute(__import__("sqlalchemy").select(PasswordResetToken))).scalars().all()
    assert len(rows) == 1
    raw_token = reset_url.split("token=")[1]
    # El token en claro NO se almacena; sí su hash SHA-256.
    assert rows[0].token_hash != raw_token
    assert rows[0].token_hash == svc._hash_token(raw_token)
    assert rows[0].used_at is None


@pytest.mark.asyncio
async def test_request_reset_unknown_email_returns_none(session):
    await _mk_user(session)
    assert await svc.request_reset("desconocido@test.local", session) is None


@pytest.mark.asyncio
async def test_request_reset_inactive_or_no_login_returns_none(session):
    await _mk_user(session, user_id=1, email="inactive@test.local", is_active=False)
    await _mk_user(session, user_id=2, email="nologin@test.local", can_login=False)
    assert await svc.request_reset("inactive@test.local", session) is None
    assert await svc.request_reset("nologin@test.local", session) is None


@pytest.mark.asyncio
async def test_new_request_invalidates_previous_tokens(session):
    await _mk_user(session)
    r1 = await svc.request_reset("coach@test.local", session)
    assert r1 is not None
    old_token = r1[1].split("token=")[1]
    await svc.request_reset("coach@test.local", session)
    # El primer token queda invalidado (410).
    with pytest.raises(HTTPException) as exc:
        await svc.validate_token(old_token, session)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_max(session, monkeypatch):
    monkeypatch.setattr(settings, "password_reset_max_per_window", 3)
    monkeypatch.setattr(settings, "password_reset_window_minutes", 15)
    await _mk_user(session)
    assert await svc.request_reset("coach@test.local", session) is not None
    assert await svc.request_reset("coach@test.local", session) is not None
    assert await svc.request_reset("coach@test.local", session) is not None
    # 4ª dentro de la ventana → bloqueada (None), sin crear token nuevo.
    assert await svc.request_reset("coach@test.local", session) is None


@pytest.mark.asyncio
async def test_consume_token_updates_password_and_consumes(session):
    await _mk_user(session, password="OldPass123")
    result = await svc.request_reset("coach@test.local", session)
    raw_token = result[1].split("token=")[1]

    user = await svc.consume_token(raw_token, "NewPass456", session)
    assert verify_password("NewPass456", user.hashed_password)
    assert not verify_password("OldPass123", user.hashed_password)

    # Token ya usado → 410 en segundo intento.
    with pytest.raises(HTTPException) as exc:
        await svc.consume_token(raw_token, "Another789", session)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_validate_token_unknown_404(session):
    with pytest.raises(HTTPException) as exc:
        await svc.validate_token("no-existe", session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_validate_token_expired_410(session):
    await _mk_user(session)
    result = await svc.request_reset("coach@test.local", session)
    raw_token = result[1].split("token=")[1]
    # Forzar expiración.
    row = await svc._get_token_row(raw_token, session)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await session.flush()
    with pytest.raises(HTTPException) as exc:
        await svc.validate_token(raw_token, session)
    assert exc.value.status_code == 410
