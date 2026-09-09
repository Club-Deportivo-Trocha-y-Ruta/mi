"""Unit tests T007 — ``app/models/mixins.py`` (feature 041, data-model.md §5).

Uses a throwaway ``DeclarativeBase``/schema instead of the real app models so
this test never registers extra tables on ``app.models.Base.metadata`` — the
route-registry/model-coverage tests of other features iterate that metadata
and must not see a table invented only for this unit test.

Covers:
  - ``UpdatedByMixin`` adds a nullable ``updated_by_user_id`` FK to
    ``users.id`` with ``ondelete=SET NULL``.
  - ``ActorTimestampMixin`` adds both ``updated_by_user_id`` and a nullable
    ``updated_at`` that defaults on insert and bumps on update.
  - The FK actually enforces ``SET NULL`` on delete of the referenced user
    (SQLite requires ``PRAGMA foreign_keys=ON`` for this, set explicitly).
  - Two mapped classes reusing the same mixin do not share a single
    ``Column`` object (the exact failure ``@declared_attr`` avoids).
"""
from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import Integer, String, event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.models.mixins import ActorTimestampMixin, UpdatedByMixin


class _LocalBase(DeclarativeBase):
    pass


class _LocalUser(_LocalBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255))


class _ActorOnlyThing(_LocalBase, UpdatedByMixin):
    """Stands in for a table that already has its own ``updated_at``."""

    __tablename__ = "actor_only_things"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))


class _ActorTimestampThing(_LocalBase, ActorTimestampMixin):
    __tablename__ = "actor_timestamp_things"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # SQLite ignores FK constraints unless explicitly enabled per connection.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(_LocalBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def test_mixins_declare_distinct_column_objects() -> None:
    """Each mapped class must own its own Column, not a shared aliased one.

    A plain class-level ``mapped_column(ForeignKey(...))`` reused across two
    classes raises at mapper-configuration time (already exercised by
    importing the two models above); this asserts the columns are in fact
    two different objects, not merely that import succeeded.
    """
    actor_only_col = _ActorOnlyThing.__table__.c.updated_by_user_id
    actor_timestamp_col = _ActorTimestampThing.__table__.c.updated_by_user_id
    assert actor_only_col is not actor_timestamp_col


def test_updated_by_mixin_column_shape() -> None:
    col = _ActorOnlyThing.__table__.c.updated_by_user_id
    assert col.nullable is True
    fk = next(iter(col.foreign_keys))
    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "SET NULL"


def test_actor_timestamp_mixin_adds_updated_at() -> None:
    assert "updated_at" not in _ActorOnlyThing.__table__.c
    col = _ActorTimestampThing.__table__.c.updated_at
    assert col.nullable is True


@pytest.mark.asyncio
async def test_updated_by_user_id_persists_and_defaults_null(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = _LocalUser(email="coach@ficticio.test")
        session.add(user)
        await session.flush()

        untouched = _ActorOnlyThing(name="sin-actor")
        attributed = _ActorTimestampThing(name="con-actor", updated_by_user_id=user.id)
        session.add_all([untouched, attributed])
        await session.commit()

        refreshed_untouched = await session.get(_ActorOnlyThing, untouched.id)
        refreshed_attributed = await session.get(_ActorTimestampThing, attributed.id)
        assert refreshed_untouched.updated_by_user_id is None
        assert refreshed_attributed.updated_by_user_id == user.id
        assert isinstance(refreshed_attributed.updated_at, datetime)


@pytest.mark.asyncio
async def test_updated_at_defaults_and_bumps_on_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        thing = _ActorTimestampThing(name="original")
        session.add(thing)
        await session.commit()
        first_updated_at = thing.updated_at
        assert first_updated_at is not None

        thing.name = "editado"
        await session.commit()
        await session.refresh(thing)
        assert thing.updated_at is not None
        # SQLite round-trips DateTime as naive (no tzinfo), matching this
        # project's "naive UTC" storage convention (data-model.md §1) —
        # strip tzinfo from both sides before comparing.
        assert thing.updated_at.replace(tzinfo=None) >= first_updated_at.replace(
            tzinfo=None
        )


@pytest.mark.asyncio
async def test_updated_by_user_id_set_null_on_user_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = _LocalUser(email="borrado@ficticio.test")
        session.add(user)
        await session.flush()

        thing = _ActorOnlyThing(name="con-actor-borrado", updated_by_user_id=user.id)
        session.add(thing)
        await session.commit()

        await session.delete(user)
        await session.commit()
        # The identity map still holds the pre-cascade in-Python object;
        # force a real re-read of the row the DB just rewrote via ON DELETE
        # SET NULL.
        row = (
            await session.execute(
                select(_ActorOnlyThing)
                .where(_ActorOnlyThing.id == thing.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert row.updated_by_user_id is None
