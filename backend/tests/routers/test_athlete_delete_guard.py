"""Regresión T002 — guard interino admin-only en ``DELETE /api/athletes/{id}``.

Hasta que T040 reemplace el borrado por archivado, solo un admin puede
eliminar un atleta. Un coach (aunque tenga acceso al club del atleta) recibe
403 con el copy exacto exigido por la tarea; un parent sigue sin acceso al
endpoint en absoluto (fuera de ``require_role``).

Estrategia: SQLite async in-memory + StaticPool, override de ``get_db`` /
``get_current_user`` — mismo patrón que ``test_race_events_crud.py``. Datos
ficticios, ningún dato real de un menor.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

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

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.ai_explanation import AthleteAIExplanation  # noqa: F401
from app.models.anthropometry import AnthropometricRecord  # noqa: F401
from app.models.athlete import Athlete, ParentAthlete, Sex  # noqa: F401
from app.models.club import Club, ClubMember, ClubRole
from app.models.parent_invite import ParentInvite  # noqa: F401
from app.models.parental_consent import ParentalConsent  # noqa: F401
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES

_DELETE_URL = "/api/athletes/{athlete_id}"
_EXPECTED_DETAIL = "Solo un administrador puede eliminar un atleta por ahora."


def _make_user(role: UserRole, user_id: int, club_id: int | None = None) -> SimpleNamespace:
    memberships = []
    if club_id is not None and role == UserRole.coach:
        memberships = [
            SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)
        ]
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=memberships,
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    engine = create_async_engine(
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
            "parental_consents",
            "athlete_ai_explanations",
            "parent_invites",
            "anthropometric_records",
            "parent_athlete",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def _override_db_factory(factory: async_sessionmaker[AsyncSession]):
    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override_db


@pytest_asyncio.fixture
async def seed_minimal(db_session_factory):
    """Club id=1, coach id=10 (miembro del club), admin id=1, parent id=5,
    atleta id=200 en el club 1 (stub de usuario athlete id=200 asociado)."""
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="User",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent = User(
            id=5, email="parent@test.com", hashed_password="x",
            first_name="Padre", last_name="Ficticio",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        athlete_user = User(
            id=200, email="atleta200@test.internal", hashed_password="x",
            first_name="Atleta", last_name="Ficticio",
            role=UserRole.athlete, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club Trocha y Ruta", code="TYR")
        session.add_all([coach, admin, parent, athlete_user, club])
        await session.flush()
        session.add(
            ClubMember(user_id=10, club_id=1, role_in_club=ClubRole.coach)
        )
        session.add(
            Athlete(
                id=200,
                user_id=200,
                first_name="Atleta",
                last_name="Ficticio",
                birth_date=date(2013, 6, 15),
                sex=Sex.M,
                club_join_date=date(2024, 1, 1),
                club_id=1,
                created_by=10,
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_minimal):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10, club_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(sqlite_engine, db_session_factory, seed_minimal):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_minimal):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=5
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestDeleteAthleteAdminOnlyGuard:
    @pytest.mark.asyncio
    async def test_coach_gets_403_with_exact_message(self, coach_client, db_session_factory):
        """Coach con acceso al club del atleta igual recibe 403 con el copy exacto."""
        r = await coach_client.delete(_DELETE_URL.format(athlete_id=200))
        assert r.status_code == 403
        assert r.json()["detail"] == _EXPECTED_DETAIL

        # El atleta NO fue borrado.
        async with db_session_factory() as s:
            athlete = (
                await s.execute(select(Athlete).where(Athlete.id == 200))
            ).scalar_one_or_none()
            assert athlete is not None

    @pytest.mark.asyncio
    async def test_admin_can_still_delete(self, admin_client, db_session_factory):
        """El guard interino no afecta al admin — sigue pudiendo borrar."""
        r = await admin_client.delete(_DELETE_URL.format(athlete_id=200))
        assert r.status_code == 204

        async with db_session_factory() as s:
            athlete = (
                await s.execute(select(Athlete).where(Athlete.id == 200))
            ).scalar_one_or_none()
            assert athlete is None

    @pytest.mark.asyncio
    async def test_parent_gets_403(self, parent_client):
        """Parent no está en require_role([admin, coach]) — 403 antes de llegar al guard."""
        r = await parent_client.delete(_DELETE_URL.format(athlete_id=200))
        assert r.status_code == 403
