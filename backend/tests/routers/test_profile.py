"""Tests del router de perfil (specs/004-user-profile).

Usa un motor SQLite real + overrides de ``get_db``, ``get_current_user`` y
``get_notification_service`` (fake que captura envíos), por lo que corre sin
MySQL. Verifica los caminos felices y negativos del contrato HTTP.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db, get_notification_service
from app.main import app
from app.models.base import Base
from app.models.email_change_request import EmailChangeRequest  # noqa: F401 (asegura tabla registrada)
from app.models.user import User, UserRole
from app.services.auth import hash_password

PWD = "OldPass123"


class FakeNotificationService:
    """Captura las notificaciones en vez de enviarlas."""

    def __init__(self) -> None:
        self.sent: list[Any] = []

    async def send(self, request, dispatcher=None):  # noqa: ANN001
        self.sent.append(request)
        return None


@pytest_asyncio.fixture
async def setup(monkeypatch) -> AsyncGenerator[dict, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in ("users", "email_change_requests")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    session.add(
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
    session.add(
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
    await session.flush()

    notif = FakeNotificationService()

    async def _override_db():
        yield session

    async def _current_user():
        return await session.get(User, 1)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_notification_service] = lambda: notif

    yield {"session": session, "notif": notif}

    app.dependency_overrides.clear()
    await session.close()
    await engine.dispose()


# ---------------------------------------------------------------------------
# GET /me + PATCH /basic
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_my_profile(client, setup):
    resp = await client.get("/api/profile/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "carlos@test.com"
    assert body["first_name"] == "Carlos"
    # No filtra credenciales ni campos internos.
    assert "hashed_password" not in body
    assert "token_hash" not in body


@pytest.mark.asyncio
async def test_patch_basic_happy(client, setup):
    resp = await client.patch("/api/profile/basic", json={"phone": "+57 301 999 8888"})
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+57 301 999 8888"


@pytest.mark.asyncio
async def test_patch_basic_empty_name_422(client, setup):
    resp = await client.patch("/api/profile/basic", json={"first_name": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_basic_no_fields_422(client, setup):
    resp = await client.patch("/api/profile/basic", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# change-password
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_change_password_happy_sends_email(client, setup):
    resp = await client.post(
        "/api/profile/change-password",
        json={"current_password": PWD, "new_password": "NuevaClave456"},
    )
    assert resp.status_code == 200
    assert len(setup["notif"].sent) == 1


@pytest.mark.asyncio
async def test_change_password_wrong_current_400(client, setup):
    resp = await client.post(
        "/api/profile/change-password",
        json={"current_password": "mala", "new_password": "NuevaClave456"},
    )
    assert resp.status_code == 400
    assert setup["notif"].sent == []


@pytest.mark.asyncio
async def test_change_password_weak_422(client, setup):
    resp = await client.post(
        "/api/profile/change-password",
        json={"current_password": PWD, "new_password": "corta"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_change_password_equal_to_current_422(client, setup):
    resp = await client.post(
        "/api/profile/change-password",
        json={"current_password": PWD, "new_password": PWD},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# change-email/request — neutral + anti-enumeración
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_email_request_success_neutral(client, setup):
    resp = await client.post(
        "/api/profile/change-email/request",
        json={"current_password": PWD, "new_email": "nuevo@test.com"},
    )
    assert resp.status_code == 200
    assert len(setup["notif"].sent) == 1  # correo a la nueva dirección


@pytest.mark.asyncio
async def test_email_request_conflict_same_message_no_email(client, setup):
    # 'otro@test.com' ya existe → misma respuesta neutral, sin enviar correo.
    resp = await client.post(
        "/api/profile/change-email/request",
        json={"current_password": PWD, "new_email": "otro@test.com"},
    )
    assert resp.status_code == 200
    assert setup["notif"].sent == []


@pytest.mark.asyncio
async def test_email_request_wrong_password_400(client, setup):
    resp = await client.post(
        "/api/profile/change-email/request",
        json={"current_password": "mala", "new_email": "nuevo@test.com"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_email_request_invalid_email_422(client, setup):
    resp = await client.post(
        "/api/profile/change-email/request",
        json={"current_password": PWD, "new_email": "no-es-correo"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# change-email/confirm
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_email_confirm_happy(client, setup):
    # Emitimos vía servicio para capturar el token en claro.
    from app.services import profile as svc

    user = await setup["session"].get(User, 1)
    _, url = await svc.request_email_change(user, PWD, "nuevo@test.com", setup["session"])
    raw = url.split("token=")[1]

    resp = await client.post("/api/profile/change-email/confirm", json={"token": raw})
    assert resp.status_code == 200
    # Aviso a la dirección anterior.
    assert len(setup["notif"].sent) == 1
    refreshed = await setup["session"].get(User, 1)
    assert refreshed.email == "nuevo@test.com"


@pytest.mark.asyncio
async def test_email_confirm_unknown_404(client, setup):
    resp = await client.post(
        "/api/profile/change-email/confirm", json={"token": "inexistente"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_email_confirm_reused_410(client, setup):
    from app.services import profile as svc

    user = await setup["session"].get(User, 1)
    _, url = await svc.request_email_change(user, PWD, "nuevo@test.com", setup["session"])
    raw = url.split("token=")[1]
    await client.post("/api/profile/change-email/confirm", json={"token": raw})
    resp = await client.post("/api/profile/change-email/confirm", json={"token": raw})
    assert resp.status_code == 410
