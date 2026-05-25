"""Tests del refactor A3: ``jti`` en JWT + revocación de refresh tokens.

Cubre:
- Cada refresh token nuevo tiene ``jti`` único.
- ``persist_refresh_token`` + ``is_refresh_revoked`` consistencia.
- ``revoke_refresh_token`` deja la fila revocada y enlaza ``replaced_by``.
- ``is_refresh_revoked`` con jti inexistente retorna False (compat).
- Access tokens también llevan ``jti``/``iat``/``nbf``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_refresh_revoked,
    persist_refresh_token,
    revoke_refresh_token,
    revoke_all_refresh_tokens_for_user,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Sólo creamos las tablas necesarias para este test.
    tables = [Base.metadata.tables["users"], Base.metadata.tables["refresh_tokens"]]
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=tables)
        )

    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_maker() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, user_id: int = 1):
    from app.models.user import User, UserRole

    user = User(
        id=user_id,
        email=f"u{user_id}@example.com",
        hashed_password="x",
        first_name="U",
        last_name=str(user_id),
        role=UserRole.coach,
        is_active=True,
        can_login=True,
    )
    db.add(user)
    await db.flush()
    return user


def test_access_token_carries_jti_iat_nbf():
    data = {"sub": "1", "role": "coach", "club_ids": []}
    token = create_access_token(data)
    payload = decode_token(token)
    assert "jti" in payload
    assert len(payload["jti"]) == 32
    assert "iat" in payload
    assert "nbf" in payload
    assert "exp" in payload
    assert payload["type"] == "access"


def test_refresh_token_returns_tuple_with_unique_jti():
    data = {"sub": "1", "role": "coach", "club_ids": []}
    token1, jti1, exp1 = create_refresh_token(data)
    token2, jti2, exp2 = create_refresh_token(data)
    assert jti1 != jti2
    payload1 = decode_token(token1)
    payload2 = decode_token(token2)
    assert payload1["jti"] == jti1
    assert payload2["jti"] == jti2
    assert payload1["type"] == "refresh"
    assert exp1 < exp2 or exp1 == exp2  # generados en orden temporal


@pytest.mark.asyncio
async def test_persist_and_check_not_revoked(db_session: AsyncSession):
    user = await _make_user(db_session, 1)
    _, jti, expires_at = create_refresh_token({"sub": str(user.id)})
    await persist_refresh_token(
        db_session, jti=jti, user_id=user.id, expires_at=expires_at
    )

    assert (await is_refresh_revoked(db_session, jti)) is False


@pytest.mark.asyncio
async def test_revoke_marks_token_revoked(db_session: AsyncSession):
    user = await _make_user(db_session, 1)
    _, jti, expires_at = create_refresh_token({"sub": str(user.id)})
    await persist_refresh_token(
        db_session, jti=jti, user_id=user.id, expires_at=expires_at
    )

    await revoke_refresh_token(db_session, jti)
    assert (await is_refresh_revoked(db_session, jti)) is True


@pytest.mark.asyncio
async def test_rotation_links_replaced_by(db_session: AsyncSession):
    """Rotación: viejo queda revocado con replaced_by = nuevo."""
    user = await _make_user(db_session, 1)
    _, old_jti, old_exp = create_refresh_token({"sub": str(user.id)})
    await persist_refresh_token(
        db_session, jti=old_jti, user_id=user.id, expires_at=old_exp
    )

    _, new_jti, new_exp = create_refresh_token({"sub": str(user.id)})
    await revoke_refresh_token(db_session, old_jti, replaced_by=new_jti)
    await persist_refresh_token(
        db_session, jti=new_jti, user_id=user.id, expires_at=new_exp
    )

    from app.models.refresh_token import RefreshToken
    from sqlalchemy import select

    old_row = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == old_jti)
        )
    ).scalar_one()
    new_row = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.jti == new_jti)
        )
    ).scalar_one()
    assert old_row.revoked_at is not None
    assert old_row.replaced_by_jti == new_jti
    assert new_row.revoked_at is None


@pytest.mark.asyncio
async def test_unknown_jti_is_not_revoked(db_session: AsyncSession):
    """Compat: tokens emitidos antes de A3 no están en la tabla; los
    aceptamos como vivos para no romper sesiones existentes."""
    assert (
        await is_refresh_revoked(db_session, "deadbeef" * 4)
    ) is False


@pytest.mark.asyncio
async def test_reuse_of_revoked_token_blocked(db_session: AsyncSession):
    """Después de revocar, el mismo jti se considera revocado en cada
    chequeo (no permite reuso)."""
    user = await _make_user(db_session, 1)
    _, jti, expires_at = create_refresh_token({"sub": str(user.id)})
    await persist_refresh_token(
        db_session, jti=jti, user_id=user.id, expires_at=expires_at
    )
    await revoke_refresh_token(db_session, jti)

    # Múltiples chequeos deben retornar True consistentemente.
    for _ in range(3):
        assert (await is_refresh_revoked(db_session, jti)) is True


@pytest.mark.asyncio
async def test_revoke_all_user_tokens(db_session: AsyncSession):
    """Logout total: revoca todos los refresh tokens vivos del usuario."""
    user = await _make_user(db_session, 1)
    jtis = []
    for _ in range(3):
        _, jti, exp = create_refresh_token({"sub": str(user.id)})
        await persist_refresh_token(
            db_session, jti=jti, user_id=user.id, expires_at=exp
        )
        jtis.append(jti)

    count = await revoke_all_refresh_tokens_for_user(db_session, user.id)
    assert count == 3
    for jti in jtis:
        assert (await is_refresh_revoked(db_session, jti)) is True
