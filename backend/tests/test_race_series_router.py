"""Tests backend spec 023 — National Championship Level (T006).

Cubre POST/GET /api/race-analysis/race-series con el nuevo campo ``level``:

  (1) POST kind='championship', level='national' -> 201, level=='national'.
  (2) POST sin level -> 201, level=='departmental' (default, retrocompatible).
  (3) POST level='galactic' (inválido) -> 422.
  (4) organizer enviado por el cliente se persiste tal cual (NO se reemplaza
      por "Liga Vallecaucana de Ciclismo" — decisión D5 del plan 023).
  (5) GET lista incluye 'level' en cada item.

Nota (T006, pre-T009): el router aún no persiste ni ecoa ``level`` en las
respuestas (``RaceSeries(...)`` no recibe ``level=body.level`` y
``RaceSeriesRead(...)`` no incluye ``level=``). Como ``RaceSeriesRead.level``
es un campo requerido sin default, construirlo sin ``level`` lanza
``pydantic.ValidationError`` sin capturar -> 500 Internal Server Error.
Se espera que los casos (1) y (5) FALLEN hasta que T009 aterrice el fix en
``app/routers/race_series.py``.

Estrategia: SQLite async in-memory + StaticPool; override get_db /
get_current_user. Copiado de ``backend/tests/routers/test_race_series_014.py``.

Privacidad invariante: nunca se usan datos ficticios de menores; race_series
es metadata pública de federación.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
from app.models.user import User, UserRole

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "race_series",
    "race_events",
    "race_imports",
    "race_categories",
    "race_competitors",
    "race_results",
]

_SERIES_URL = "/api/race-analysis/race-series/"


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="Ficticio",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Importar modelos para registrar metadata
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def _make_override_db(factory: async_sessionmaker[AsyncSession]):
    async def _override():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _override


async def _seed_base_users(session: AsyncSession, coach_id: int = 10) -> None:
    """Inserta coach + admin en la DB."""
    coach = User(
        id=coach_id,
        email=f"coach{coach_id}@ficticio.test",
        hashed_password="x",
        first_name="Coach",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    admin = User(
        id=1,
        email="admin@ficticio.test",
        hashed_password="x",
        first_name="Admin",
        last_name="Ficticio",
        role=UserRole.admin,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([coach, admin])
    await session.flush()


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_factory):
    """Cliente HTTP como coach id=10, sin seed previo (cada test lo hace)."""
    app.dependency_overrides[get_db] = _make_override_db(db_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


class TestRaceSeriesLevelT006:
    """T006: POST/GET /race-series con el nuevo campo ``level`` (spec 023)."""

    @pytest.mark.asyncio
    async def test_post_championship_level_national(self, coach_client, db_factory):
        """POST kind='championship', level='national' -> 201, level=='national'."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Nacional MTB 2026",
            "season_year": 2026,
            "kind": "championship",
            "organizer": "Federación Colombiana de Ciclismo",
            "level": "national",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["level"] == "national"

    @pytest.mark.asyncio
    async def test_post_sin_level_default_departmental(self, coach_client, db_factory):
        """POST sin 'level' -> 201, level=='departmental' (default retrocompatible)."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Departamental Ficticio 2026",
            "season_year": 2026,
            "kind": "championship",
            "organizer": "Liga Vallecaucana de Ciclismo",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["level"] == "departmental"

    @pytest.mark.asyncio
    async def test_post_level_invalido_422(self, coach_client, db_factory):
        """POST level='galactic' (fuera del enum) -> 422."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Inválido 2026",
            "season_year": 2026,
            "kind": "championship",
            "level": "galactic",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_post_organizer_cliente_no_reemplazado(self, coach_client, db_factory):
        """El organizer enviado por el cliente se persiste verbatim — NO se
        reemplaza por 'Liga Vallecaucana de Ciclismo' (decisión D5, plan 023:
        el default Valle solo aplica al flujo de import de copas, no aquí)."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Nacional Organizer Test 2026",
            "season_year": 2026,
            "kind": "championship",
            "organizer": "Federación Colombiana de Ciclismo",
            "level": "national",
        }
        r = await coach_client.post(_SERIES_URL, json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["organizer"] == "Federación Colombiana de Ciclismo"
        assert data["organizer"] != "Liga Vallecaucana de Ciclismo"

    @pytest.mark.asyncio
    async def test_get_lista_incluye_level(self, coach_client, db_factory):
        """GET /race-series -> cada item de la lista incluye 'level'."""
        async with db_factory() as s:
            await _seed_base_users(s)
            await s.commit()

        body = {
            "name": "Campeonato Nacional GET Test 2026",
            "season_year": 2026,
            "kind": "championship",
            "organizer": "Federación Colombiana de Ciclismo",
            "level": "national",
        }
        r_post = await coach_client.post(_SERIES_URL, json=body)
        assert r_post.status_code == 201, r_post.text

        r = await coach_client.get(_SERIES_URL, params={"season": 2026})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 1
        for item in items:
            assert "level" in item, f"'level' ausente en item: {item}"
