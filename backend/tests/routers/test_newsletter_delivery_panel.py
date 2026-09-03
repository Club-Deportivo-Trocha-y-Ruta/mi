"""Tests de `delivery: list[DeliveryRow]` en `GET .../monthly-newsletters/{id}`
(feature 038, T401 — el panel de entrega del studio necesita
delivered_at/opened_at/bounced, no solo sent_at/web_read_at).

Mismo patrón que ``test_athlete_monthly_newsletter_v2_router.py``: DB real
(SQLite in-memory) + ``AsyncClient`` contra ``app.main.app``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent
from app.models.user import User, UserRole

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "athlete_monthly_newsletters",
    "newsletter_delivery_events",
    "parent_athlete",
)

_SNAPSHOT = {"email_blocks": {}, "pdf_only_blocks": {}}


@pytest_asyncio.fixture
async def engine():
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
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def seed(session):
    from app.models.club import Club

    now = datetime.now(timezone.utc)
    admin = User(
        id=1, email="admin@test.local", first_name="Admin", last_name="Test",
        role=UserRole.admin, is_active=True, can_login=True, created_at=now,
    )
    club = Club(id=1, name="Club Test", code="CT1", created_at=now)
    session.add_all([admin, club])
    await session.flush()

    athlete_user = User(
        id=2, email=None, first_name="Atleta", last_name="Ficticio",
        role=UserRole.athlete, is_active=True, can_login=False, created_at=now,
    )
    session.add(athlete_user)
    await session.flush()

    athlete = Athlete(
        id=5, user_id=2, first_name="Atleta", last_name="Ficticio",
        birth_date=date(2013, 5, 1), sex=Sex.M, club_id=1, created_by=1,
    )
    session.add(athlete)

    parent = User(
        id=200, email="padre@test.local", first_name="Padre", last_name="Test",
        role=UserRole.parent, is_active=True, can_login=True, created_at=now,
    )
    session.add(parent)
    await session.flush()
    session.add(
        ParentAthlete(
            parent_id=200, athlete_id=5, relationship_type=FamilyRelationship.padre,
        )
    )

    nl = AthleteMonthlyNewsletter(
        id=1, athlete_id=5, year=2026, month=6, status=NewsletterStatus.sent,
        metrics_snapshot=_SNAPSHOT, sent_at=now,
        generated_by_user_id=1,
    )
    session.add(nl)
    await session.flush()

    session.add_all(
        [
            NewsletterDeliveryEvent(
                newsletter_id=1, parent_user_id=200, event_type=DeliveryEventType.sent,
                provider_message_id="resend_msg_1", occurred_at=now,
            ),
            NewsletterDeliveryEvent(
                newsletter_id=1, parent_user_id=None, event_type=DeliveryEventType.delivered,
                provider_message_id="resend_msg_1", provider_event_id="evt_delivered",
                occurred_at=now,
            ),
            NewsletterDeliveryEvent(
                newsletter_id=1, parent_user_id=None, event_type=DeliveryEventType.opened,
                provider_message_id="resend_msg_1", provider_event_id="evt_opened",
                occurred_at=now,
            ),
        ]
    )
    await session.commit()
    return SimpleNamespace(admin=admin, newsletter_id=nl.id)


@pytest_asyncio.fixture
async def client_factory(session):
    made: list[AsyncClient] = []

    def _make(user) -> AsyncClient:
        async def _override_db():
            yield session

        async def _override_user():
            return user

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        made.append(client)
        return client

    yield _make
    for c in made:
        await c.aclose()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delivery_includes_delivered_and_opened(seed, client_factory):
    client = client_factory(seed.admin)
    async with client as c:
        resp = await c.get(f"/api/athletes/5/monthly-newsletters/{seed.newsletter_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["delivery"]) == 1
    row = body["delivery"][0]
    assert row["parent_user_id"] == 200
    assert row["email_masked"] == "p***@test.local"
    assert row["delivered_at"] is not None
    assert row["opened_at"] is not None
    assert row["bounced"] is False
