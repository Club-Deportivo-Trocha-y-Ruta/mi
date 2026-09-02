"""Tests de ``POST /athletes/{id}/race-analysis/insights/{insight_id}/answer``.

Feature 037 (T104). Cobertura:

- Coach del club del atleta responde + califica → 200, persistido y
  escrubeado (nombre del atleta reemplazado en ``coach_answer_text``).
- Parent → 403 (mismo patrón que ``POST /season-summary`` / ``GET /runs``).
- Insight de otro atleta (mismo club, distinto ``athlete_id`` en el path)
  → 404.
- Body vacío (sin ``answer_text`` ni ``rating``) → 422.
- Detalle expone ``structured`` (dict de ``structured_json``).

Estrategia: SQLite async in-memory, mismo patrón que
``tests/routers/test_athlete_race_analysis.py``.
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
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
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
            "parent_athlete",
            "athlete_ai_insights",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_STRUCTURED = {
    "schema_version": "v3",
    "headline": "El ritmo de descenso mejoró frente a la válida anterior",
    "coach_question": "¿Hubo algo distinto en la semana previa: viaje, examen, molestia?",
    "observations": [
        {
            "claim": "El bloque de fuerza semanal coincide con menor tiempo de vuelta",
            "evidence": ["RPE medio 6.5 en la semana previa"],
            "domain": "training",
            "confidence": "medium",
        }
    ],
}


@pytest_asyncio.fixture
async def seeded_factory(
    session_factory,
) -> async_sessionmaker[AsyncSession]:
    """club1 + coach (club1) + coach2 (club2) + parent + athlete 144 + 145."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_club(s, club_id=2, code="club2")
        await create_user(s, user_id=10, role=UserRole.coach, email="coach1@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await create_user(s, user_id=11, role=UserRole.coach, email="coach2@test.com")
        await link_user_to_club(s, user_id=11, club_id=2, role_in_club=ClubRole.coach)
        await create_user(s, user_id=20, role=UserRole.parent, email="parent@test.com")

        await create_user(
            s,
            user_id=144,
            role=UserRole.athlete,
            can_login=False,
            first_name="Deportista",
            last_name="Uno",
        )
        await create_athlete(
            s, athlete_id=144, club_id=1, user_id=144, first_name="Deportista", last_name="Uno"
        )
        await create_user(
            s,
            user_id=145,
            role=UserRole.athlete,
            can_login=False,
            first_name="Deportista",
            last_name="Dos",
        )
        await create_athlete(
            s, athlete_id=145, club_id=1, user_id=145, first_name="Deportista", last_name="Dos"
        )
        await link_parent_to_athlete(s, parent_user_id=20, athlete_id=144)

        now = datetime.now(timezone.utc)
        insight_144 = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
            generated_at=now,
            structured_json=_STRUCTURED,
        )
        insight_145 = await create_insight(
            s,
            athlete_id=145,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
            generated_at=now,
        )
        await s.commit()
        s._test_insight_144_id = insight_144.id  # type: ignore[attr-defined]
        s._test_insight_145_id = insight_145.id  # type: ignore[attr-defined]
    return session_factory


def _make_user(user_id: int, role: UserRole, club_id: int | None = 1) -> SimpleNamespace:
    cm = (
        SimpleNamespace(
            club_id=club_id,
            role_in_club=(
                ClubRole.coach
                if role == UserRole.coach
                else ClubRole.admin
                if role == UserRole.admin
                else ClubRole.parent
            ),
        )
        if club_id is not None
        else None
    )
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"u{user_id}@test.com",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[cm] if cm else [],
    )


@pytest_asyncio.fixture
async def client_factory(seeded_factory):
    def _build(user: SimpleNamespace):
        async def _override_db():
            async with seeded_factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _build
    app.dependency_overrides.clear()


async def _get_insight_id(session_factory, athlete_id: int) -> int:
    async with session_factory() as s:
        from sqlalchemy import select

        from app.models.athlete_ai_insight import AthleteAiInsight

        result = await s.execute(
            select(AthleteAiInsight.id).where(
                AthleteAiInsight.athlete_id == athlete_id
            )
        )
        return int(result.scalars().first())


# ---------------------------------------------------------------------------
# Denied paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_insight_as_parent_returns_403(client_factory, seeded_factory):
    insight_id = await _get_insight_id(seeded_factory, 144)
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.post(
            f"/api/athletes/144/race-analysis/insights/{insight_id}/answer",
            json={"answer_text": "Todo normal", "rating": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_answer_insight_other_athlete_insight_returns_404(
    client_factory, seeded_factory
):
    """insight de athlete 145 respondido vía path /athletes/144/... → 404."""
    insight_id_145 = await _get_insight_id(seeded_factory, 145)
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            f"/api/athletes/144/race-analysis/insights/{insight_id_145}/answer",
            json={"answer_text": "Respuesta", "rating": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_answer_insight_empty_body_returns_422(client_factory, seeded_factory):
    insight_id = await _get_insight_id(seeded_factory, 144)
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            f"/api/athletes/144/race-analysis/insights/{insight_id}/answer",
            json={},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Happy path: persistido + scrubeado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_insight_persists_and_scrubs_pii(client_factory, seeded_factory):
    insight_id = await _get_insight_id(seeded_factory, 144)
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            f"/api/athletes/144/race-analysis/insights/{insight_id}/answer",
            json={
                "answer_text": "Deportista Uno tuvo un examen el jueves previo.",
                "rating": 1,
            },
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["coach_rating"] == 1
    # El nombre real del atleta (forbidden name) nunca debe llegar intacto.
    assert "Deportista Uno" not in (body["coach_answer_text"] or "")
    assert body["coach_answer_at"] is not None

    # Detalle expone structured (dict de structured_json).
    assert body["structured"]["headline"] == _STRUCTURED["headline"]
    assert body["headline"] == _STRUCTURED["headline"]


@pytest.mark.asyncio
async def test_answer_insight_rating_only(client_factory, seeded_factory):
    insight_id = await _get_insight_id(seeded_factory, 144)
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            f"/api/athletes/144/race-analysis/insights/{insight_id}/answer",
            json={"rating": -1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["coach_rating"] == -1
    assert body["coach_answer_text"] is None
