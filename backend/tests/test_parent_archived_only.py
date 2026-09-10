"""Un padre cuyo único atleta está archivado (feature 041, US2, contract
``athlete-archive.md`` §7 y §12.3).

Con el atleta filtrado dentro de ``parent_athlete_ids`` (C1), toda superficie
de padre debe devolver una colección vacía, nunca un ``404`` ni un ``500``.

Corre en la vía offline aiosqlite, con un engine propio — no usa el fixture
``client`` de ``conftest.py`` porque ese exige MySQL.

Ningún nombre en este archivo corresponde a una persona real (CLAUDE.md,
Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

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
from app.models.club import ClubRole
from app.models.privacy_policy import PrivacyPolicy
from app.models.user import User, UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio

CLUB_ID = 1
PARENT_ID = 700
ATHLETE_ID = 70
ATHLETE_USER_ID = 9970

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "parental_consents",
    "athlete_monthly_newsletters",
    *AUDIT_TABLES,
]


@pytest_asyncio.fixture
async def parent_engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def parent_session_factory(parent_engine: AsyncEngine):
    return async_sessionmaker(parent_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(parent_session_factory):
    async with parent_session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio Uno", code="cft-p-047")
        parent = await create_user(session, user_id=PARENT_ID, role=UserRole.parent, first_name="Padre", last_name="Ficticio")
        await link_user_to_club(session, user_id=PARENT_ID, club_id=CLUB_ID, role_in_club=ClubRole.parent)

        athlete = await create_athlete(
            session,
            athlete_id=ATHLETE_ID,
            first_name="Atleta Ficticio",
            last_name="Archivado",
            birth_date=date(2013, 5, 1),
            club_id=CLUB_ID,
            user_id=ATHLETE_USER_ID,
            created_by=parent.id,
        )
        await link_parent_to_athlete(session, parent_user_id=PARENT_ID, athlete_id=athlete.id)

        # El atleta ya está archivado antes de que el padre entre en escena.
        athlete.deleted_at = datetime.now(timezone.utc)
        athlete.deleted_by_user_id = PARENT_ID
        athlete.deleted_reason_code = "athlete_left_club"

        session.add(
            PrivacyPolicy(
                version="v1",
                effective_date=date(2026, 1, 1),
                title="Política ficticia",
                content_html="<p>contenido ficticio</p>",
                content_hash="0" * 64,
            )
        )

        await session.commit()

    return None


@pytest_asyncio.fixture
async def parent_client(parent_session_factory):
    @asynccontextmanager
    async def make_client(user_id: int):
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        async with parent_session_factory() as load_session:
            result = await load_session.execute(
                select(User).options(selectinload(User.club_memberships)).where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with parent_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    async with make_client(PARENT_ID) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. my-athletes -> 200 [], nunca 404
# ---------------------------------------------------------------------------


async def test_my_athletes_empty_list(scenario, parent_client):
    resp = await parent_client.get("/api/parent-athletes/my-athletes")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 2. Estado de consentimiento -> consents_per_athlete: [], sin 500
# ---------------------------------------------------------------------------


async def test_consent_status_empty(scenario, parent_client):
    resp = await parent_client.get("/api/me/consent")
    assert resp.status_code == 200
    assert resp.json()["consents_per_athlete"] == []


# ---------------------------------------------------------------------------
# 3. GET /api/athletes/{archived_id} como ese padre
# ---------------------------------------------------------------------------


async def test_parent_cannot_read_own_archived_athlete(scenario, parent_client):
    """contracts/athlete-archive.md §7: un padre sobre su propio atleta
    archivado recibe ``403`` con el texto de siempre, no ``404``.

    La familia ve exactamente la misma respuesta que ante cualquier atleta
    ajeno, así que la ficha archivada no se delata. Antes ``verify_athlete_access``
    evaluaba "archivado -> 404" para todo rol no-admin antes de separar padre de
    coach; ahora cada rama decide (``app/dependencies.py``).
    """
    resp = await parent_client.get(f"/api/athletes/{ATHLETE_ID}")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "No tienes acceso a este atleta"
