"""Tests del helper ``services.athletes.parents``.

Verifica que ``get_primary_parent_with_email`` resuelve en una sola
query SQL (en lugar del antiguo N+1 del router ``athletes.create``) y
respeta los filtros de soft-delete y email NULL.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.club import Club
from app.models.user import User, UserRole
from app.services.athletes.parents import get_primary_parent_with_email


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Sólo creamos las tablas necesarias para este test: el catálogo
    # completo de modelos incluye LONGTEXT (MySQL) que SQLite no acepta.
    tables = [
        Base.metadata.tables[name]
        for name in ("users", "clubs", "athletes", "parent_athlete")
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_maker() as session:
        yield session
    await engine.dispose()


async def _make_user(
    db: AsyncSession,
    *,
    email: str | None,
    role: UserRole = UserRole.parent,
    can_login: bool = True,
    deleted_at: datetime | None = None,
) -> User:
    user = User(
        email=email,
        hashed_password="x",
        first_name="P",
        last_name="X",
        role=role,
        is_active=True,
        can_login=can_login,
        deleted_at=deleted_at,
    )
    db.add(user)
    await db.flush()
    return user


_club_counter = [0]


async def _make_club(db: AsyncSession) -> Club:
    _club_counter[0] += 1
    club = Club(name=f"Test Club {_club_counter[0]}", code=f"TC{_club_counter[0]}")
    db.add(club)
    await db.flush()
    return club


async def _make_athlete(db: AsyncSession) -> Athlete:
    # Athlete necesita user_id, club_id NOT NULL — creamos también el
    # User del atleta y un Club mínimo.
    club = await _make_club(db)
    creator = await _make_user(db, email="coach@example.com", role=UserRole.coach)
    athlete_user = await _make_user(
        db, email=None, role=UserRole.athlete, can_login=False
    )
    ath = Athlete(
        user_id=athlete_user.id,
        first_name="Ath",
        last_name="Lete",
        birth_date=date(2014, 1, 1),
        sex=Sex.M,
        club_id=club.id,
        created_by=creator.id,
    )
    db.add(ath)
    await db.flush()
    return ath


async def _link(
    db: AsyncSession,
    parent: User,
    athlete: Athlete,
    rel: FamilyRelationship = FamilyRelationship.padre,
) -> ParentAthlete:
    pa = ParentAthlete(
        parent_id=parent.id,
        athlete_id=athlete.id,
        relationship_type=rel,
    )
    db.add(pa)
    await db.flush()
    return pa


@pytest.mark.asyncio
async def test_returns_parent_with_email(db_session: AsyncSession):
    parent = await _make_user(db_session, email="parent@example.com")
    athlete = await _make_athlete(db_session)
    await _link(db_session, parent, athlete)

    found = await get_primary_parent_with_email(db_session, athlete.id)
    assert found is not None
    assert found.id == parent.id
    assert found.email == "parent@example.com"


@pytest.mark.asyncio
async def test_returns_none_when_no_parent_linked(db_session: AsyncSession):
    athlete = await _make_athlete(db_session)
    found = await get_primary_parent_with_email(db_session, athlete.id)
    assert found is None


@pytest.mark.asyncio
async def test_skips_parent_without_email(db_session: AsyncSession):
    """Si el único padre vinculado no tiene email, retorna None."""
    parent = await _make_user(db_session, email=None)
    athlete = await _make_athlete(db_session)
    await _link(db_session, parent, athlete)

    found = await get_primary_parent_with_email(db_session, athlete.id)
    assert found is None


@pytest.mark.asyncio
async def test_skips_soft_deleted_parent(db_session: AsyncSession):
    """Padres con ``deleted_at`` no son seleccionables."""
    deleted_parent = await _make_user(
        db_session,
        email="deleted@example.com",
        deleted_at=datetime.now(timezone.utc),
    )
    athlete = await _make_athlete(db_session)
    await _link(db_session, deleted_parent, athlete)

    found = await get_primary_parent_with_email(db_session, athlete.id)
    assert found is None


@pytest.mark.asyncio
async def test_picks_first_parent_with_email_when_multiple(
    db_session: AsyncSession,
):
    """Si hay varios, devuelve uno (el primero según JOIN). LIMIT 1 garantiza
    no-N+1 incluso con muchos padres."""
    p1 = await _make_user(db_session, email="p1@example.com")
    p2 = await _make_user(db_session, email="p2@example.com")
    athlete = await _make_athlete(db_session)
    await _link(db_session, p1, athlete, FamilyRelationship.padre)
    await _link(db_session, p2, athlete, FamilyRelationship.madre)

    found = await get_primary_parent_with_email(db_session, athlete.id)
    assert found is not None
    assert found.email in {"p1@example.com", "p2@example.com"}


@pytest.mark.asyncio
async def test_single_query_for_lookup(db_session: AsyncSession):
    """Smoke check: la función no incurre en N+1 — basta con UNA llamada
    a ``execute`` (1 JOIN). Usamos un contador a través de un patch
    ligero sobre la sesión."""
    parent = await _make_user(db_session, email="parent@example.com")
    athlete = await _make_athlete(db_session)
    await _link(db_session, parent, athlete)

    original_execute = db_session.execute
    calls: list[int] = []

    async def counting_execute(*args, **kwargs):
        calls.append(1)
        return await original_execute(*args, **kwargs)

    db_session.execute = counting_execute  # type: ignore[method-assign]
    try:
        found = await get_primary_parent_with_email(db_session, athlete.id)
    finally:
        db_session.execute = original_execute  # type: ignore[method-assign]

    assert found is not None
    assert len(calls) == 1
