"""Invariantes de privacidad del módulo de perfil (specs/004-user-profile).

Verifica que ni los logs ni el enlace de confirmación exponen correo, nombre,
rol o el token en claro, y que el token se persiste hasheado (Ley 1581).
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.user import User, UserRole
from app.services import profile as svc
from app.services.auth import hash_password

EMAIL = "carlos.entrenador@test.com"
NEW_EMAIL = "nueva.direccion@test.com"
FIRST = "Carlos"
LAST = "Gomez"
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
                email=EMAIL,
                hashed_password=hash_password(PWD),
                first_name=FIRST,
                last_name=LAST,
                role=UserRole.coach,
                is_active=True,
                can_login=True,
            )
        )
        await s.flush()
        yield s


@pytest.mark.asyncio
async def test_logs_never_contain_email_name_or_raw_token(session, caplog):
    with caplog.at_level(logging.DEBUG, logger="app.services.profile"):
        user = await session.get(User, 1)
        _, url = await svc.request_email_change(user, PWD, NEW_EMAIL, session)
        raw_token = url.split("token=")[1]
        await svc.confirm_email_change(raw_token, session)
        await svc.change_password(user, "OldPass123", "NuevaClave789", session)

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert EMAIL not in blob
    assert NEW_EMAIL not in blob
    assert FIRST not in blob
    assert LAST not in blob
    assert raw_token not in blob
    assert "user_id=1" in blob  # solo id


@pytest.mark.asyncio
async def test_confirm_url_carries_only_opaque_token(session):
    user = await session.get(User, 1)
    _, url = await svc.request_email_change(user, PWD, NEW_EMAIL, session)
    assert EMAIL not in url
    assert NEW_EMAIL not in url
    assert FIRST not in url
    assert "coach" not in url


@pytest.mark.asyncio
async def test_token_stored_hashed_not_plaintext(session):
    user = await session.get(User, 1)
    _, url = await svc.request_email_change(user, PWD, NEW_EMAIL, session)
    raw_token = url.split("token=")[1]
    row = await svc._get_request_row(raw_token, session)
    assert row.token_hash != raw_token
    assert len(row.token_hash) == 64  # SHA-256 hex
