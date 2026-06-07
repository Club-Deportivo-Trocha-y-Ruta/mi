"""Invariantes de privacidad del flujo de restablecimiento (specs/003-password-reset-login).

Verifica que ni las respuestas ni los logs exponen correo, nombre, rol o el
token en claro (Ley 1581 — datos sensibles de menores y titulares).
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
from app.services import password_reset as svc
from app.services.auth import hash_password

EMAIL = "carlos.entrenador@test.com"
FIRST = "Carlos"
LAST = "Gomez"


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
        s.add(
            User(
                id=1,
                email=EMAIL,
                hashed_password=hash_password("OldPass123"),
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
    with caplog.at_level(logging.DEBUG, logger="app.services.password_reset"):
        result = await svc.request_reset(EMAIL, session)
        raw_token = result[1].split("token=")[1]
        await svc.consume_token(raw_token, "NewPass456", session)

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert EMAIL not in blob
    assert FIRST not in blob
    assert LAST not in blob
    assert raw_token not in blob
    # Solo se permite referenciar al usuario por id.
    assert "user_id=1" in blob


@pytest.mark.asyncio
async def test_reset_url_carries_only_opaque_token(session):
    result = await svc.request_reset(EMAIL, session)
    reset_url = result[1]
    assert EMAIL not in reset_url
    assert FIRST not in reset_url
    assert "coach" not in reset_url  # rol no expuesto


@pytest.mark.asyncio
async def test_token_stored_hashed_not_plaintext(session):
    result = await svc.request_reset(EMAIL, session)
    raw_token = result[1].split("token=")[1]
    row = await svc._get_token_row(raw_token, session)
    assert row.token_hash != raw_token
    assert len(row.token_hash) == 64  # SHA-256 hex
    # La fila no almacena datos personales.
    assert not hasattr(row, "email") or getattr(row, "email", None) is None
