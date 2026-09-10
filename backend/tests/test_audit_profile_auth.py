"""T030 — auditoría de autenticación y perfil (`/api/auth`, `/api/profile`).

Cubre las cinco filas de la matriz §4.1 de
``specs/041-multi-coach-governance/contracts/audit-recording.md`` que hasta
ahora estaban sin instrumentar:

- ``POST /api/auth/parent-register``         → ``user``·``create`` +
  ``parent_athlete``·``link`` + ``parent_invite``·``update``
- ``POST /api/auth/password-reset/confirm``  → ``user``·``update``
- ``PATCH /api/profile/basic``               → ``user``·``update``
- ``POST /api/profile/change-password``      → ``user``·``update``
- ``POST /api/profile/change-email/confirm`` → ``user``·``update``

Dos rutas hermanas son exenciones genuinas de §4.14 y aquí se comprueba que
siguen sin escribir nada: ``password-reset/request`` y
``change-email/request`` (registrar la solicitud construiría un oráculo de
enumeración de cuentas).

Privacidad (CLAUDE.md, Ley 1581): las aserciones exigen que ninguna
contraseña, ningún token (de invitación, de reseteo o de cambio de correo) y
ninguna dirección de correo lleguen a ``changed_fields`` / ``diff_json`` /
``meta_json`` — ni siquiera hasheados.

Vía offline: motor sqlite in-memory propio (idioma de
``tests/routers/test_audit_log_api.py`` + ``tests/helpers/audit_tables.py``);
no usa el fixture ``client`` de ``tests/conftest.py``, que exige la base real.
"""
from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
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
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete import ParentAthlete
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.club import ClubRole
from app.models.email_change_request import EmailChangeRequest
from app.models.parent_invite import ParentInvite
from app.models.password_reset_token import PasswordResetToken
from app.models.privacy_policy import PrivacyPolicy
from app.models.user import User, UserRole
from app.services.auth import hash_password, verify_password

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

# Datos ficticios — ninguna persona real (CLAUDE.md, Ley 1581).
CLUB_ID = 1
COACH_ID = 701
PARENT_ID = 702
ATHLETE_ID = 751
ATHLETE_USER_ID = 1751
ATHLETE_FIRST_NAME = "Tomás Ficticio"
ATHLETE_LAST_NAME = "Arboleda"

PARENT_EMAIL = "familia.perfil@example.com"
NEW_EMAIL = "familia.nueva@example.com"
INVITE_EMAIL = "familia.invitada@example.com"

CURRENT_PASSWORD = "ClaveActual123"
NEW_PASSWORD = "ClaveNueva456"
INVITE_TOKEN = "token-de-invitacion-ficticio-041"
RESET_TOKEN = "token-de-reseteo-ficticio-041"
EMAIL_TOKEN = "token-de-correo-ficticio-041"

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "parental_consents",
    "password_reset_tokens",
    "email_change_requests",
    *AUDIT_TABLES,
)

_SECRETS = (
    CURRENT_PASSWORD,
    NEW_PASSWORD,
    INVITE_TOKEN,
    RESET_TOKEN,
    EMAIL_TOKEN,
    PARENT_EMAIL,
    NEW_EMAIL,
    INVITE_EMAIL,
    ATHLETE_FIRST_NAME,
    ATHLETE_LAST_NAME,
)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _assert_no_secrets(row: AuditLog) -> None:
    """Ni secretos ni PII en la fila: ni en claro ni hasheados."""
    blob = repr([row.changed_fields, row.diff_json, row.meta_json]).lower()
    for secret in _SECRETS:
        assert secret.lower() not in blob, f"secreto/PII en la fila: {secret!r}"
        assert _sha256(secret) not in blob, f"hash de un secreto en la fila: {secret!r}"


@pytest_asyncio.fixture
async def auth_engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def auth_session_factory(
    auth_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(auth_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def auth_scenario(
    auth_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Club con coach, un padre con contraseña conocida, atleta e invitación."""
    now = datetime.now(timezone.utc)
    async with auth_session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio", code="cf-041b")
        await create_user(
            session,
            user_id=COACH_ID,
            role=UserRole.coach,
            first_name="Coach",
            last_name="Ficticio",
        )
        parent = await create_user(
            session,
            user_id=PARENT_ID,
            role=UserRole.parent,
            email=PARENT_EMAIL,
            first_name="Familia",
            last_name="Ficticia",
        )
        parent.hashed_password = hash_password(CURRENT_PASSWORD)
        await link_user_to_club(
            session, user_id=COACH_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach
        )
        await link_user_to_club(
            session, user_id=PARENT_ID, club_id=CLUB_ID, role_in_club=ClubRole.parent
        )
        await create_athlete(
            session,
            athlete_id=ATHLETE_ID,
            first_name=ATHLETE_FIRST_NAME,
            last_name=ATHLETE_LAST_NAME,
            birth_date=date(2012, 9, 2),
            club_id=CLUB_ID,
            user_id=ATHLETE_USER_ID,
            created_by=COACH_ID,
        )
        session.add(
            ParentInvite(
                athlete_id=ATHLETE_ID,
                email=INVITE_EMAIL,
                token=INVITE_TOKEN,
                expires_at=now + timedelta(hours=48),
                used=False,
                created_by=COACH_ID,
            )
        )
        session.add(
            PrivacyPolicy(
                version="v1.2",
                effective_date=date(2026, 5, 15),
                title="Política ficticia",
                content_html="<p>ficticia</p>",
                content_hash="0" * 64,
            )
        )
        session.add(
            PasswordResetToken(
                user_id=PARENT_ID,
                token_hash=_sha256(RESET_TOKEN),
                expires_at=now + timedelta(hours=1),
            )
        )
        session.add(
            EmailChangeRequest(
                user_id=PARENT_ID,
                new_email=NEW_EMAIL,
                token_hash=_sha256(EMAIL_TOKEN),
                expires_at=now + timedelta(hours=1),
            )
        )
        await session.commit()
    yield auth_session_factory


@pytest_asyncio.fixture
async def auth_client_factory(
    auth_session_factory: async_sessionmaker[AsyncSession],
    auth_scenario: async_sessionmaker[AsyncSession],
):
    """Fábrica ``make_client(user_id=None)``; sin id monta un cliente público."""

    @asynccontextmanager
    async def make_client(user_id: int | None = None):
        actor: User | None = None
        if user_id is not None:
            async with auth_session_factory() as load_session:
                actor = (
                    await load_session.execute(
                        select(User)
                        .options(selectinload(User.club_memberships))
                        .where(User.id == user_id)
                    )
                ).scalar_one()

        async def _override_db():
            async with auth_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        if actor is not None:
            app.dependency_overrides[get_current_user] = lambda: actor
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


async def _audit_rows(factory: async_sessionmaker[AsyncSession]) -> list[AuditLog]:
    async with factory() as session:
        result = await session.execute(select(AuditLog).order_by(AuditLog.id))
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# POST /api/auth/parent-register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parent_register_records_three_rows_under_one_request_id(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    async with auth_client_factory() as client:
        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": INVITE_TOKEN,
                "first_name": "Familia",
                "last_name": "Invitada",
                "password": NEW_PASSWORD,
                "relationship_type": "madre",
            },
        )
    assert resp.status_code == 201, resp.text
    new_user_id = resp.json()["id"]

    rows = await _audit_rows(auth_scenario)
    by_entity = {row.entity_type: row for row in rows}
    assert set(by_entity) == {"user", "parent_athlete", "parent_invite"}

    # FR-002: una sola petición → un solo request_id compartido.
    assert len({row.request_id for row in rows}) == 1

    # El actor es el propio interesado, sin sesión iniciada todavía (§3.2):
    # actor_kind sigue siendo `user` y actor_user_id NUNCA queda nulo (R3).
    for row in rows:
        assert row.actor_kind == AuditActorKind.user
        assert row.actor_user_id == new_user_id
        assert row.actor_role == UserRole.parent
        assert row.club_id == CLUB_ID
        _assert_no_secrets(row)

    user_row = by_entity["user"]
    assert user_row.action == AuditAction.create
    assert user_row.entity_id == new_user_id
    assert user_row.athlete_id is None
    assert "email" in user_row.changed_fields
    assert user_row.diff_json is None

    link_row = by_entity["parent_athlete"]
    assert link_row.action == AuditAction.link
    assert link_row.athlete_id == ATHLETE_ID
    assert link_row.meta_json == {"parent_user_id": new_user_id}

    invite_row = by_entity["parent_invite"]
    assert invite_row.action == AuditAction.update
    assert invite_row.changed_fields == ["used", "used_by"]
    assert invite_row.athlete_id == ATHLETE_ID

    async with auth_scenario() as session:
        link = (
            await session.execute(
                select(ParentAthlete).where(ParentAthlete.parent_id == new_user_id)
            )
        ).scalar_one()
    assert link_row.entity_id == link.id


# ---------------------------------------------------------------------------
# POST /api/auth/password-reset/{request,confirm}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_reset_confirm_records_user_update_without_club(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    async with auth_client_factory() as client:
        resp = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": RESET_TOKEN, "new_password": NEW_PASSWORD},
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(auth_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "user"
    assert row.action == AuditAction.update
    assert row.entity_id == PARENT_ID
    assert row.actor_user_id == PARENT_ID
    assert row.actor_kind == AuditActorKind.user
    # CLUB_OPTIONAL (§1.7): fila del rastro personal, invisible en el club.
    assert row.club_id is None
    assert row.athlete_id is None
    assert row.changed_fields == ["hashed_password"]
    assert row.diff_json is None
    _assert_no_secrets(row)


@pytest.mark.asyncio
async def test_password_reset_request_stays_exempt(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    """§4.14: registrar la solicitud sería un oráculo de enumeración."""
    async with auth_client_factory() as client:
        resp = await client.post(
            "/api/auth/password-reset/request", json={"email": PARENT_EMAIL}
        )
    assert resp.status_code == 200
    assert await _audit_rows(auth_scenario) == []


# ---------------------------------------------------------------------------
# PATCH /api/profile/basic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_basic_records_names_only(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    async with auth_client_factory(PARENT_ID) as client:
        resp = await client.patch(
            "/api/profile/basic",
            json={"first_name": "Familia Editada", "phone": "3001234567"},
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(auth_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "user"
    assert row.action == AuditAction.update
    assert row.entity_id == PARENT_ID
    assert row.actor_user_id == PARENT_ID
    assert row.club_id is None
    assert row.changed_fields == ["first_name", "phone"]
    # Ni el nombre ni el teléfono están en VALUE_ALLOWLIST[user] (§2.5).
    assert row.diff_json is None
    assert "Familia Editada" not in repr(row.changed_fields)
    assert "3001234567" not in repr([row.changed_fields, row.diff_json, row.meta_json])


@pytest.mark.asyncio
async def test_profile_basic_noop_writes_no_row(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    """Regla R7 (§1.4): un PATCH que no cambia nada no fabrica historia."""
    async with auth_client_factory(PARENT_ID) as client:
        resp = await client.patch("/api/profile/basic", json={"first_name": "Familia"})
    assert resp.status_code == 200, resp.text
    assert await _audit_rows(auth_scenario) == []


# ---------------------------------------------------------------------------
# POST /api/profile/change-password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_records_column_name_only(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    async with auth_client_factory(PARENT_ID) as client:
        resp = await client.post(
            "/api/profile/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(auth_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "user"
    assert row.action == AuditAction.update
    assert row.entity_id == PARENT_ID
    assert row.club_id is None
    assert row.changed_fields == ["hashed_password"]
    assert row.diff_json is None
    _assert_no_secrets(row)

    async with auth_scenario() as session:
        parent = (
            await session.execute(select(User).where(User.id == PARENT_ID))
        ).scalar_one()
    assert verify_password(NEW_PASSWORD, parent.hashed_password or "")


@pytest.mark.asyncio
async def test_change_password_with_wrong_current_writes_no_row(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    async with auth_client_factory(PARENT_ID) as client:
        resp = await client.post(
            "/api/profile/change-password",
            json={"current_password": "no-es-la-actual", "new_password": NEW_PASSWORD},
        )
    assert resp.status_code == 400
    assert await _audit_rows(auth_scenario) == []


# ---------------------------------------------------------------------------
# POST /api/profile/change-email/{request,confirm}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_email_confirm_records_email_field_never_the_address(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    async with auth_client_factory() as client:
        resp = await client.post(
            "/api/profile/change-email/confirm", json={"token": EMAIL_TOKEN}
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(auth_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "user"
    assert row.action == AuditAction.update
    assert row.entity_id == PARENT_ID
    assert row.actor_user_id == PARENT_ID
    assert row.club_id is None
    assert row.changed_fields == ["email"]
    assert row.diff_json is None
    _assert_no_secrets(row)


@pytest.mark.asyncio
async def test_change_email_request_stays_exempt(
    auth_scenario: async_sessionmaker[AsyncSession],
    auth_client_factory,
) -> None:
    """§4.14: la solicitud solo escribe un token pendiente; la cuenta no cambia."""
    async with auth_client_factory(PARENT_ID) as client:
        resp = await client.post(
            "/api/profile/change-email/request",
            json={"current_password": CURRENT_PASSWORD, "new_email": NEW_EMAIL},
        )
    assert resp.status_code == 200, resp.text
    assert await _audit_rows(auth_scenario) == []
