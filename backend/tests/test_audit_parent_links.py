"""T030 — auditoría de los vínculos familiares (`/api/parent-athletes`).

Cubre las tres rutas de mayor valor de la matriz §4.4 de
``specs/041-multi-coach-governance/contracts/audit-recording.md``:

- ``POST /api/parent-athletes``            → ``parent_athlete``·``link``
- ``POST /api/parent-athletes/invite``     → ``parent_invite``·``create``
- ``DELETE /api/parent-athletes/{id}``     → ``parent_athlete``·``unlink``

Además de la fila y su forma, se verifica la regla dura de privacidad
(CLAUDE.md, Ley 1581): ni el nombre del menor ni el correo del padre ni el
token de invitación aparecen en ``changed_fields`` / ``diff_json`` /
``meta_json``.

Vía offline: motor sqlite in-memory propio con el subconjunto de tablas que
estas rutas tocan (idioma de ``tests/routers/test_audit_log_api.py`` +
``tests/helpers/audit_tables.py``). No usa el fixture ``client`` de
``tests/conftest.py``, que exige la base real.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
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
from app.models.athlete import FamilyRelationship, ParentAthlete
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.club import ClubRole
from app.models.parent_invite import ParentInvite
from app.models.user import User, UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

# Datos ficticios — ninguna persona real (CLAUDE.md, Ley 1581).
CLUB_ID = 1
COACH_ID = 801
PARENT_ID = 802
ATHLETE_ID = 851
ATHLETE_USER_ID = 1851
ATHLETE_FIRST_NAME = "Valentina Ficticia"
ATHLETE_LAST_NAME = "Montoya"
PARENT_EMAIL = "familia.ficticia@example.com"

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    *AUDIT_TABLES,
)


@pytest_asyncio.fixture
async def links_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Motor sqlite con solo las tablas que tocan estas rutas."""
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
async def links_session_factory(
    links_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(links_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def links_scenario(
    links_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Club con un coach, un padre (miembro del mismo club) y un atleta."""
    async with links_session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio", code="cf-041")
        await create_user(
            session,
            user_id=COACH_ID,
            role=UserRole.coach,
            first_name="Coach",
            last_name="Ficticio",
        )
        await create_user(
            session,
            user_id=PARENT_ID,
            role=UserRole.parent,
            email=PARENT_EMAIL,
            first_name="Familia",
            last_name="Ficticia",
        )
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
            birth_date=date(2013, 4, 11),
            club_id=CLUB_ID,
            user_id=ATHLETE_USER_ID,
            created_by=COACH_ID,
        )
        await session.commit()
    yield links_session_factory


@pytest_asyncio.fixture
async def links_client_factory(
    links_session_factory: async_sessionmaker[AsyncSession],
    links_scenario: async_sessionmaker[AsyncSession],
):
    """Fábrica ``make_client(user_id)`` con ``club_memberships`` reales."""

    @asynccontextmanager
    async def make_client(user_id: int):
        async with links_session_factory() as load_session:
            actor = (
                await load_session.execute(
                    select(User)
                    .options(selectinload(User.club_memberships))
                    .where(User.id == user_id)
                )
            ).scalar_one()

        async def _override_db():
            async with links_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


async def _audit_rows(
    factory: async_sessionmaker[AsyncSession],
) -> list[AuditLog]:
    async with factory() as session:
        result = await session.execute(select(AuditLog).order_by(AuditLog.id))
        return list(result.scalars().all())


def _assert_no_pii(row: AuditLog) -> None:
    """Ley 1581: ni nombre del menor, ni correo, ni token en la fila."""
    blob = repr(
        [row.changed_fields, row.diff_json, row.meta_json, row.reason_code]
    ).lower()
    for forbidden in (
        ATHLETE_FIRST_NAME.lower(),
        ATHLETE_LAST_NAME.lower(),
        PARENT_EMAIL.lower(),
        "montoya",
        "@example.com",
    ):
        assert forbidden not in blob, f"PII en la fila de auditoría: {forbidden!r}"


# ---------------------------------------------------------------------------
# POST /api/parent-athletes → parent_athlete·link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_parent_athlete_records_link_row(
    links_scenario: async_sessionmaker[AsyncSession],
    links_client_factory,
) -> None:
    async with links_client_factory(COACH_ID) as client:
        resp = await client.post(
            "/api/parent-athletes",
            json={
                "parent_id": PARENT_ID,
                "athlete_id": ATHLETE_ID,
                "relationship": "madre",
            },
        )
    assert resp.status_code == 201, resp.text

    rows = await _audit_rows(links_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "parent_athlete"
    assert row.action == AuditAction.link
    assert row.actor_user_id == COACH_ID
    assert row.actor_kind == AuditActorKind.user
    assert row.actor_role == UserRole.coach
    assert row.club_id == CLUB_ID
    assert row.athlete_id == ATHLETE_ID
    assert row.entity_id == resp.json()["id"]
    assert row.changed_fields == ["athlete_id", "parent_id", "relationship_type"]
    assert row.diff_json is None
    assert row.meta_json == {"parent_user_id": PARENT_ID}
    assert row.request_id and len(row.request_id) == 32
    _assert_no_pii(row)


# ---------------------------------------------------------------------------
# POST /api/parent-athletes/invite → parent_invite·create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_invite_records_create_row_without_token(
    links_scenario: async_sessionmaker[AsyncSession],
    links_client_factory,
) -> None:
    async with links_client_factory(COACH_ID) as client:
        resp = await client.post(
            "/api/parent-athletes/invite",
            json={"athlete_id": ATHLETE_ID, "email": PARENT_EMAIL},
        )
    assert resp.status_code == 201, resp.text

    rows = await _audit_rows(links_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "parent_invite"
    assert row.action == AuditAction.create
    assert row.actor_user_id == COACH_ID
    assert row.club_id == CLUB_ID
    assert row.athlete_id == ATHLETE_ID
    assert row.changed_fields == ["athlete_id", "email", "expires_at"]
    assert row.diff_json is None
    assert row.meta_json is None
    _assert_no_pii(row)

    # El token del enlace jamás llega a la fila, ni siquiera hasheado.
    async with links_scenario() as session:
        invite = (await session.execute(select(ParentInvite))).scalar_one()
    assert invite.token not in repr([row.changed_fields, row.meta_json, row.diff_json])
    assert row.entity_id == invite.id


@pytest.mark.asyncio
async def test_generate_invite_twice_does_not_manufacture_a_second_create(
    links_scenario: async_sessionmaker[AsyncSession],
    links_client_factory,
) -> None:
    """Regla R7 (§1.4): reutilizar una invitación vigente no crea historia."""
    payload = {"athlete_id": ATHLETE_ID, "email": PARENT_EMAIL}
    async with links_client_factory(COACH_ID) as client:
        first = await client.post("/api/parent-athletes/invite", json=payload)
        second = await client.post("/api/parent-athletes/invite", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201

    rows = await _audit_rows(links_scenario)
    assert [r.action for r in rows] == [AuditAction.create]


# ---------------------------------------------------------------------------
# DELETE /api/parent-athletes/{relation_id} → parent_athlete·unlink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_parent_athlete_records_unlink_row(
    links_scenario: async_sessionmaker[AsyncSession],
    links_client_factory,
) -> None:
    async with links_scenario() as session:
        relation = ParentAthlete(
            parent_id=PARENT_ID,
            athlete_id=ATHLETE_ID,
            relationship_type=FamilyRelationship.madre,
        )
        session.add(relation)
        await session.commit()
        relation_id = relation.id

    async with links_client_factory(COACH_ID) as client:
        resp = await client.delete(f"/api/parent-athletes/{relation_id}")
    assert resp.status_code == 204, resp.text

    rows = await _audit_rows(links_scenario)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "parent_athlete"
    assert row.action == AuditAction.unlink
    assert row.entity_id == relation_id
    assert row.actor_user_id == COACH_ID
    assert row.club_id == CLUB_ID
    assert row.athlete_id == ATHLETE_ID
    assert row.changed_fields == ["athlete_id", "parent_id"]
    assert row.meta_json == {"parent_user_id": PARENT_ID}
    _assert_no_pii(row)

    # La fila sobrevive al borrado del vínculo (append-only, §5).
    async with links_scenario() as session:
        remaining = (
            await session.execute(
                select(ParentAthlete).where(ParentAthlete.id == relation_id)
            )
        ).scalar_one_or_none()
    assert remaining is None


@pytest.mark.asyncio
async def test_denied_unlink_writes_no_audit_row(
    links_scenario: async_sessionmaker[AsyncSession],
    links_client_factory,
) -> None:
    """Camino denegado (§9): un 404 no deja rastro en el historial."""
    async with links_client_factory(COACH_ID) as client:
        resp = await client.delete("/api/parent-athletes/999999")
    assert resp.status_code == 404
    assert await _audit_rows(links_scenario) == []
