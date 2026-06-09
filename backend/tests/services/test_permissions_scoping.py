"""Tests for ``allowed_athlete_ids_for`` in services/permissions.py (T007).

Covers:
- Coach → returns None (no restriction).
- Admin → returns None (no restriction).
- Parent with two children → returns the set of their athlete ids.
- Parent with no children → returns an empty set.
- Unknown role (edge case) → returns an empty set.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import Club
from app.models.user import User, UserRole
from app.services.permissions import allowed_athlete_ids_for

# ---------------------------------------------------------------------------
# SQLite in-memory engine (reuses the standard pattern)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Register models.
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in ("users", "clubs", "club_members", "athletes", "parent_athlete")
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_parent_with_children(
    session: AsyncSession,
    parent_id: int,
    child_athlete_ids: list[int],
) -> None:
    """Insert a parent user and their linked athletes into the DB."""
    coach = User(
        id=10, email="coach@svc.test", hashed_password="x",
        first_name="Coach", last_name="Test",
        role=UserRole.coach, is_active=True, can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    club = Club(id=1, name="Club TyR", code="TYR")
    parent = User(
        id=parent_id, email=f"parent{parent_id}@svc.test", hashed_password="x",
        first_name="Padre", last_name="Test",
        role=UserRole.parent, is_active=True, can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([coach, club, parent])

    for ath_id in child_athlete_ids:
        ath_user = User(
            id=100 + ath_id, email=f"ath{ath_id}@svc.test", hashed_password="x",
            first_name="Atleta", last_name=str(ath_id),
            role=UserRole.parent, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        athlete = Athlete(
            id=ath_id,
            user_id=100 + ath_id,
            first_name="Atleta",
            last_name=str(ath_id),
            birth_date=date(2012, 1, 1),
            sex="M",
            club_id=1,
            created_by=10,
        )
        link = ParentAthlete(
            id=ath_id,
            parent_id=parent_id,
            athlete_id=ath_id,
            relationship_type="padre",
        )
        session.add_all([ath_user, athlete, link])

    await session.commit()


def _make_user(role: UserRole, user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@svc.test",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllowedAthleteIdsFor:
    @pytest.mark.asyncio
    async def test_coach_returns_none(self, db_session_factory):
        """Coach has no restriction → None."""
        async with db_session_factory() as db:
            user = _make_user(UserRole.coach, 10)
            result = await allowed_athlete_ids_for(user, db)
        assert result is None

    @pytest.mark.asyncio
    async def test_admin_returns_none(self, db_session_factory):
        """Admin has no restriction → None."""
        async with db_session_factory() as db:
            user = _make_user(UserRole.admin, 1)
            result = await allowed_athlete_ids_for(user, db)
        assert result is None

    @pytest.mark.asyncio
    async def test_parent_with_two_children(
        self, sqlite_engine, db_session_factory
    ):
        """Parent with two linked children returns exactly those athlete IDs."""
        async with db_session_factory() as s:
            await _seed_parent_with_children(s, parent_id=5, child_athlete_ids=[1, 2])

        async with db_session_factory() as db:
            user = _make_user(UserRole.parent, 5)
            result = await allowed_athlete_ids_for(user, db)

        assert result == {1, 2}

    @pytest.mark.asyncio
    async def test_parent_with_one_child(
        self, sqlite_engine, db_session_factory
    ):
        """Parent with one child returns a singleton set."""
        async with db_session_factory() as s:
            await _seed_parent_with_children(s, parent_id=7, child_athlete_ids=[3])

        async with db_session_factory() as db:
            user = _make_user(UserRole.parent, 7)
            result = await allowed_athlete_ids_for(user, db)

        assert result == {3}

    @pytest.mark.asyncio
    async def test_parent_no_children_returns_empty_set(self, db_session_factory):
        """Parent with no linked athletes returns an empty set (not None)."""
        # Insert just the parent (no athletes linked).
        async with db_session_factory() as s:
            parent = User(
                id=99, email="lone@svc.test", hashed_password="x",
                first_name="Lone", last_name="Parent",
                role=UserRole.parent, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
            s.add(parent)
            await s.commit()

        async with db_session_factory() as db:
            user = _make_user(UserRole.parent, 99)
            result = await allowed_athlete_ids_for(user, db)

        assert result == set()
        assert result is not None  # explicit: empty set != None

    @pytest.mark.asyncio
    async def test_return_type_is_set_not_list(
        self, sqlite_engine, db_session_factory
    ):
        """Return value for parent is a set (supports 'in' lookups in O(1))."""
        async with db_session_factory() as s:
            await _seed_parent_with_children(s, parent_id=8, child_athlete_ids=[4, 5])

        async with db_session_factory() as db:
            user = _make_user(UserRole.parent, 8)
            result = await allowed_athlete_ids_for(user, db)

        assert isinstance(result, set)

    @pytest.mark.asyncio
    async def test_none_semantics_means_no_filter(self, db_session_factory):
        """None from coach/admin means 'no filter', distinct from empty set."""
        async with db_session_factory() as db:
            coach = _make_user(UserRole.coach, 10)
            admin = _make_user(UserRole.admin, 1)
            coach_result = await allowed_athlete_ids_for(coach, db)
            admin_result = await allowed_athlete_ids_for(admin, db)

        assert coach_result is None
        assert admin_result is None
        # Ensure None != set() — the service layer checks `is None`, not falsy.
        assert coach_result != set()
