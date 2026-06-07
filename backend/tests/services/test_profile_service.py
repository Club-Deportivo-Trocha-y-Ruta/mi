"""Tests del servicio de perfil (specs/004-user-profile).

Cubren: información básica, cambio de contraseña (re-auth) y cambio de correo
con verificación previa (emisión, no-op, conflicto neutral, rate-limit,
confirmación, expiración/uso, conflicto en confirmación). SQLite en memoria.
"""

from __future__ import annotations

from datetime import timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models.base import Base
from app.models.user import User, UserRole
from app.schemas.profile import ProfileBasicUpdate
from app.services import profile as svc
from app.services.auth import hash_password, verify_password

PWD = "OldPass123"


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in ("users", "email_change_requests")]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(
            User(
                id=1,
                email="carlos@test.com",
                hashed_password=hash_password(PWD),
                first_name="Carlos",
                last_name="Gomez",
                role=UserRole.coach,
                is_active=True,
                can_login=True,
            )
        )
        # Segunda cuenta para probar conflicto de correo.
        s.add(
            User(
                id=2,
                email="otro@test.com",
                hashed_password=hash_password("x"),
                first_name="Ana",
                last_name="Diaz",
                role=UserRole.parent,
                is_active=True,
                can_login=True,
            )
        )
        await s.flush()
        yield s


async def _user(session) -> User:
    return await session.get(User, 1)


# ---------------------------------------------------------------------------
# Información básica
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_basic_info_applies_only_provided(session):
    user = await _user(session)
    await svc.update_basic_info(
        user, ProfileBasicUpdate(phone="+57 300 111 2222"), session
    )
    assert user.phone == "+57 300 111 2222"
    assert user.first_name == "Carlos"  # sin cambios
    assert user.email == "carlos@test.com"  # nunca tocado


# ---------------------------------------------------------------------------
# Cambio de contraseña
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_change_password_happy(session):
    user = await _user(session)
    await svc.change_password(user, PWD, "BrandNew456", session)
    assert verify_password("BrandNew456", user.hashed_password)


@pytest.mark.asyncio
async def test_change_password_wrong_current_rejected(session):
    user = await _user(session)
    with pytest.raises(HTTPException) as exc:
        await svc.change_password(user, "incorrecta", "BrandNew456", session)
    assert exc.value.status_code == 400
    assert verify_password(PWD, user.hashed_password)  # sin cambios


# ---------------------------------------------------------------------------
# Cambio de correo — solicitud
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_email_change_issues_token_without_changing_email(session):
    user = await _user(session)
    result = await svc.request_email_change(user, PWD, "Nuevo@Test.com", session)
    assert result is not None
    new_email, confirm_url = result
    assert new_email == "nuevo@test.com"  # normalizado a minúsculas
    assert "token=" in confirm_url
    assert user.email == "carlos@test.com"  # NO cambia aún


@pytest.mark.asyncio
async def test_request_email_change_wrong_password(session):
    user = await _user(session)
    with pytest.raises(HTTPException) as exc:
        await svc.request_email_change(user, "mala", "nuevo@test.com", session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_request_email_change_conflict_is_neutral_none(session):
    user = await _user(session)
    # 'otro@test.com' ya pertenece a la cuenta 2 → None (sin enviar nada).
    result = await svc.request_email_change(user, PWD, "otro@test.com", session)
    assert result is None


@pytest.mark.asyncio
async def test_request_email_change_same_email_is_noop(session):
    user = await _user(session)
    result = await svc.request_email_change(user, PWD, "carlos@test.com", session)
    assert result is None


@pytest.mark.asyncio
async def test_request_email_change_rate_limited(session):
    user = await _user(session)
    for i in range(settings.email_change_max_per_window):
        r = await svc.request_email_change(user, PWD, f"dst{i}@test.com", session)
        assert r is not None
    # Una más excede el límite → None.
    over = await svc.request_email_change(user, PWD, "dstX@test.com", session)
    assert over is None


# ---------------------------------------------------------------------------
# Cambio de correo — confirmación
# ---------------------------------------------------------------------------
async def _issue(session) -> str:
    user = await _user(session)
    _, url = await svc.request_email_change(user, PWD, "nuevo@test.com", session)
    return url.split("token=")[1]


@pytest.mark.asyncio
async def test_confirm_applies_change_and_returns_old(session):
    raw = await _issue(session)
    user, old_email = await svc.confirm_email_change(raw, session)
    assert user.email == "nuevo@test.com"
    assert old_email == "carlos@test.com"


@pytest.mark.asyncio
async def test_confirm_token_single_use(session):
    raw = await _issue(session)
    await svc.confirm_email_change(raw, session)
    with pytest.raises(HTTPException) as exc:
        await svc.confirm_email_change(raw, session)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_confirm_unknown_token_404(session):
    with pytest.raises(HTTPException) as exc:
        await svc.confirm_email_change("inexistente", session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_confirm_expired_token_410(session):
    raw = await _issue(session)
    row = await svc._get_request_row(raw, session)
    row.expires_at = row.expires_at - timedelta(hours=2)
    await session.flush()
    with pytest.raises(HTTPException) as exc:
        await svc.confirm_email_change(raw, session)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_confirm_conflict_if_email_taken_after_request(session):
    raw = await _issue(session)
    # Otra cuenta toma la dirección destino antes de confirmar.
    other = await session.get(User, 2)
    other.email = "nuevo@test.com"
    await session.flush()
    with pytest.raises(HTTPException) as exc:
        await svc.confirm_email_change(raw, session)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_new_request_invalidates_previous(session):
    raw1 = await _issue(session)
    # Nueva solicitud invalida la anterior.
    user = await _user(session)
    await svc.request_email_change(user, PWD, "otra@test.com", session)
    with pytest.raises(HTTPException) as exc:
        await svc.confirm_email_change(raw1, session)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_token_stored_hashed(session):
    raw = await _issue(session)
    row = await svc._get_request_row(raw, session)
    assert row.token_hash != raw
    assert len(row.token_hash) == 64
