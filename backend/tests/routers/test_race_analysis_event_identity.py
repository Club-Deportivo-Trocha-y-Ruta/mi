"""``POST /api/race-analysis/runs`` — hotfix "identidad de válida" (2026-09-16).

Cubre el ``race_event_id`` opcional de ``StartRunRequest`` (CONTRACT →
API, item 3 de ``~/.claude/plans/multicopa-identidad-valida.md``):

- ``race_event_id`` ancla el análisis a una competencia concreta, valida que
  pertenezca a la temporada indicada y DERIVA ``valida_nums`` de su
  ``sequence_number`` (nunca se adivina).
- Sin ``race_event_id``, un ``valida_nums`` cuyo número es ambiguo en la
  temporada (dos copas comparten ``sequence_number``) responde 409 en vez
  de mezclar datos de otra copa — el mismo bug que produjo el análisis
  cruzado Copa Valle/Copa Let's Go que motivó este hotfix.

Estrategia: SQLite real (mismo patrón que ``test_race_event_runs.py`` — las
queries ORM de ``group_launch.resolve_event_scope`` /
``resolve_events_for_season_valida`` necesitan un engine real).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.models import Base
from app.models.user import UserRole
from app.routers.race_analysis import _coach_or_admin
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id TEXT NOT NULL UNIQUE,
    graph_name      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    input_json      TEXT,
    final_output_json TEXT,
    error_message   TEXT,
    requested_by_user_id INTEGER,
    athlete_id      INTEGER,
    checkpoint_thread_id TEXT NOT NULL,
    explain_mode    INTEGER NOT NULL DEFAULT 0,
    stale_since     TEXT,
    decided_by_user_id INTEGER,
    decided_at      TEXT,
    created_at      TEXT,
    updated_at      TEXT
)
"""


def _make_coach(user_id: int = 10, club_ids: tuple[int, ...] = (1,)) -> SimpleNamespace:
    from app.models.club import ClubRole

    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="Coach",
        email=f"coach{user_id}@test.local",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach) for cid in club_ids
        ],
    )


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    from app.models.user import User as _U  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    table_names = [
        "users",
        "clubs",
        "club_members",
        "athletes",
        "parent_athlete",
        "race_series",
        "race_events",
        *AUDIT_TABLES,
    ]
    tables = [Base.metadata.tables[t] for t in table_names]

    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        from sqlalchemy import text as _text

        await conn.execute(_text(_AGENT_RUNS_DDL))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Club + coach + atleta (sin padres → consentimiento IA auto-otorgado)
    + dos copas (A id=1, B id=2) con Válida 4 en 2026, una serie de otra
    temporada y un evento sin sequence_number."""
    from app.models.user import User
    from app.models.club import Club, ClubMember, ClubRole
    from app.models.athlete import Athlete, Sex
    from app.models.race_series import RaceSeries
    from app.models.race_event import RaceEvent, RaceEventStatus

    async with session_factory() as session:
        coach = User(
            id=10,
            email="coach10@test.local",
            hashed_password="x",
            first_name="Coach",
            last_name="Test",
            role=UserRole.coach,
            is_active=True,
            can_login=True,
            created_at=_utc_now(),
        )
        session.add(coach)
        club = Club(id=1, name="Club Test", code="CLT", created_at=_utc_now(), is_active=True)
        session.add(club)
        await session.flush()
        session.add(ClubMember(user_id=10, club_id=1, role_in_club=ClubRole.coach, joined_at=_utc_now()))

        athlete_user = User(
            id=100,
            email="atleta100@test.local",
            hashed_password="x",
            first_name="Atleta",
            last_name="Ficticio",
            role=UserRole.coach,
            is_active=True,
            can_login=False,
            created_at=_utc_now(),
        )
        session.add(athlete_user)
        await session.flush()
        athlete = Athlete(
            id=50,
            user_id=100,
            first_name="Atleta",
            last_name="Ficticio",
            birth_date=date(2013, 6, 1),
            sex=Sex.M,
            club_id=1,
            created_by=10,
        )
        session.add(athlete)
        await session.flush()

        series_a = RaceSeries(
            id=1, name="Copa A Test", season_year=2026,
            organizer="Liga", points_scheme_code="copa_a",
        )
        series_b = RaceSeries(
            id=2, name="Copa B Test", season_year=2026,
            organizer="Liga", points_scheme_code="copa_b",
        )
        series_other_season = RaceSeries(
            id=3, name="Copa Vieja Test", season_year=2025,
            organizer="Liga", points_scheme_code="copa_vieja",
        )
        session.add_all([series_a, series_b, series_other_season])
        await session.flush()

        event_a4 = RaceEvent(
            id=100, series_id=1, sequence_number=4, name="Copa A V4",
            event_date=date(2026, 4, 1), status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_b4 = RaceEvent(
            id=200, series_id=2, sequence_number=4, name="Copa B V4",
            event_date=date(2026, 4, 8), status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_other_season = RaceEvent(
            id=300, series_id=3, sequence_number=1, name="Vieja V1",
            event_date=date(2025, 4, 1), status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        session.add_all([event_a4, event_b4, event_other_season])
        await session.commit()

    return {"athlete_id": 50}


@pytest_asyncio.fixture
async def http_client(session_factory):
    from app.services.race.ai import runner as runner_mod

    class _NopGraph:
        async def ainvoke(self, value: Any, config: Any = None) -> dict:
            return {}

    runner_mod.set_graph_factory(lambda: _NopGraph())
    await runner_mod._reset_for_tests()

    async def _override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[_coach_or_admin] = lambda: _make_coach()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest.fixture
def ai_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_enabled", True)
    return settings


class TestRaceEventIdAnchors:
    async def test_race_event_id_derives_valida_nums_and_anchors_state(
        self, http_client, session_factory, monkeypatch, ai_on
    ):
        from app.routers import race_analysis as ra_mod

        seed = await _seed(session_factory)
        captured_states: list[dict] = []
        _orig_submit = ra_mod.submit_run

        async def _capture(run_id: str, state: dict, *, on_complete=None):
            captured_states.append(state)
            return await _orig_submit(run_id, state, on_complete=on_complete)

        monkeypatch.setattr(ra_mod, "submit_run", _capture)

        resp = await http_client.post(
            "/api/race-analysis/runs",
            json={
                "athlete_id": seed["athlete_id"],
                "season": 2026,
                "race_event_id": 200,  # Copa B V4
            },
        )

        assert resp.status_code == 201, resp.text
        assert len(captured_states) == 1
        state = captured_states[0]
        assert state["event_id"] == 200
        assert state["valida_nums"] == [4]

    async def test_race_event_id_wrong_season_is_422(
        self, http_client, session_factory, ai_on
    ):
        seed = await _seed(session_factory)
        resp = await http_client.post(
            "/api/race-analysis/runs",
            json={
                "athlete_id": seed["athlete_id"],
                "season": 2026,
                "race_event_id": 300,  # temporada 2025
            },
        )
        assert resp.status_code == 422, resp.text

    async def test_race_event_id_unknown_is_404(
        self, http_client, session_factory, ai_on
    ):
        seed = await _seed(session_factory)
        resp = await http_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": seed["athlete_id"], "season": 2026, "race_event_id": 99999},
        )
        assert resp.status_code == 404, resp.text


class TestAmbiguousValidaNumWithoutAnchor:
    async def test_ambiguous_valida_num_returns_409(
        self, http_client, session_factory, ai_on
    ):
        """Copa A y Copa B comparten Válida 4 → sin race_event_id, 409."""
        seed = await _seed(session_factory)
        resp = await http_client.post(
            "/api/race-analysis/runs",
            json={
                "athlete_id": seed["athlete_id"],
                "season": 2026,
                "valida_nums": [4],
            },
        )
        assert resp.status_code == 409, resp.text
        assert "ambigu" in resp.json()["detail"].lower()

    async def test_unambiguous_valida_num_still_201(
        self, http_client, session_factory, ai_on
    ):
        """Un valida_num que no colisiona con ninguna otra copa sigue funcionando."""
        seed = await _seed(session_factory)
        resp = await http_client.post(
            "/api/race-analysis/runs",
            json={
                "athlete_id": seed["athlete_id"],
                "season": 2026,
                "valida_nums": [7],  # ninguna copa sembrada usa el 7
            },
        )
        assert resp.status_code == 201, resp.text
