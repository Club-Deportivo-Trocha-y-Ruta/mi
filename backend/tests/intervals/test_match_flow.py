"""End-to-end plan-vs-actual match flow tests (feature 026, US2, T023-adjacent).

Exercises the full deferred-matching pipeline across BOTH routers involved
(``routers/activities.py::link_activity`` and ``routers/intervals.py``),
wired together exactly as production does — the link endpoint dispatches
``services/intervals/match_runner.run_match_deferred`` via the shared
``TaskDispatcher`` (research.md D6), and the match-detail/recalculate
endpoints on ``/api/intervals`` read the same ``interval_match_results`` /
``strava_activity_laps`` rows that job writes.

Covers:
  - Dispatch wiring: ``PATCH /api/activities/{id}/link`` dispatches
    ``run_match_deferred(structure_id, activity_id, MatchTrigger.link)``
    (positional args, ``routers/activities.py``); ``POST
    /api/intervals/structures`` dispatches the same job with
    ``triggered_by=MatchTrigger.structure_change`` (keyword args,
    ``routers/intervals.py::_dispatch_match_for_linked_activities``) for
    every activity already linked to the session. Both assertions use a
    recording fake dispatcher — mirrors ``tests/routers/
    test_strava_integration.py::_RecordingDispatcher`` — so the job itself
    is never executed on that path (matches the "link endpoint stays fast"
    performance budget, plan.md).
  - ``GET /api/intervals/sessions/{id}/match`` status envelope (contracts/
    api.md): ``computed`` (a real ``run_match_deferred`` run, laps + result
    persisted), ``no_activity`` (structure with nothing linked),
    ``computing`` (linked activity, no result row, no failure marker yet —
    the natural post-dispatch/pre-run state), ``failed`` (a real run whose
    stubbed ``StravaClient.get_activity_laps`` raises, exercising
    ``match_runner``'s in-process failure marker end-to-end through the
    GET).
  - ``POST /api/intervals/structures/{id}/recalculate``: ``202`` (dispatches
    ``triggered_by=manual``) and ``409`` (no linked activity).
  - Replace-on-refetch (data-model.md §5 "Refresh semantics"): a second real
    run with a different raw lap payload deletes and reinserts
    ``strava_activity_laps`` for that activity — no accumulation.
  - Unlink (``training_session_id: null``) deletes the
    ``interval_match_results`` row for that structure↔activity pair but
    never touches ``strava_activity_laps`` (D7 — laps are owned by the
    activity, not the match).

Why a standalone local ASGI app instead of ``app.main.app``
-------------------------------------------------------------
Same reasoning as ``tests/routers/test_activities.py``: ``activities.router``
is only mounted onto ``app.main.app`` when ``settings.strava_enabled`` is
``True`` **at import time**, which is environment-dependent (this repo's
local ``.env`` happens to set it, but that must not be a test-suite
assumption). This module needs BOTH ``activities.router`` (link/unlink) and
``intervals.router`` (structure/match/recalculate) mounted deterministically
in the same app, so it builds its own small ``FastAPI`` instance — the
routers still import the same ``get_db``/``get_current_user``/
``get_task_dispatcher`` function objects from ``app.dependencies``, so
overriding them here works exactly like it would in production. Does NOT use
``tests/intervals/conftest.py`` (bound to ``app.main.app``, and its table
subset lacks the Strava chain this file needs) — this module is fully
self-contained with its own engine/session/seed fixtures, deliberately
avoiding any fixture-name coupling with sibling test files in this directory.

Why ``run_match_deferred`` is invoked directly (not through the dispatcher)
-----------------------------------------------------------------------------
``TaskDispatcher`` with no injected ``BackgroundTasks`` (the test default)
schedules async targets via ``loop.create_task(...)`` and returns
immediately — fire-and-forget, no way to deterministically await completion
from the test. Router-level dispatch tests therefore only assert *what* was
queued (recording fake, matches the feature-025 convention). To exercise the
job's actual effects (laps persisted, match computed, failure marker set)
this file calls ``match_runner.run_match_deferred(...)`` directly and
``await``s it, after monkeypatching ``app.database.AsyncSessionLocal`` to the
test's own in-memory engine (the job opens its own session — see
``match_runner.run_match_deferred`` docstring) and stubbing
``StravaClient.get_activity_laps`` (T007 contract: the client passes the raw
Strava payload through verbatim; allow-listing happens in
``match_runner._allow_listed_lap``).

All data is fictitious (non-negotiable CLAUDE.md §Privacy) — no real TyR
athlete data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app import database as database_module
from app.dependencies import get_current_user, get_db, get_task_dispatcher
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import ClubMember, ClubRole
from app.models.interval_structure import (
    HRZone,
    IntervalBlockType,
    IntervalStructure,
    IntervalStructureBlock,
)
from app.models.parental_consent import ParentalConsent
from app.models.strava_activity import StravaActivity, StravaIngestSource
from app.models.strava_activity_lap import IntervalMatchResult, MatchTrigger, StravaActivityLap
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.interval_structure import AgeBand
from app.models.training_session import TrainingSession
from app.models.user import User, UserRole
from app.routers import activities
from app.routers import intervals as intervals_router
from app.services.intervals import match_runner
from app.services.strava.client import StravaAPIError, StravaClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Tables — Strava chain (feature 025) + interval training chain (feature 026)
# ---------------------------------------------------------------------------

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parental_consents",
    "strava_connections",
    "strava_activities",
    "training_sessions",
    "interval_structures",
    "interval_structure_blocks",
    "strava_activity_laps",
    "interval_match_results",
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Local ASGI app (see module docstring)
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(activities.router, prefix="/api")
    test_app.include_router(intervals_router.router, prefix="/api/intervals")
    return test_app


# ---------------------------------------------------------------------------
# DB fixtures — in-memory aiosqlite, subset of tables
# ---------------------------------------------------------------------------


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
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


# ---------------------------------------------------------------------------
# In-process failure marker isolation (match_runner._FAILED_RUNS is a
# module-level global — must not bleed between tests, see module docstring
# match_runner.has_failed()).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_match_runner_failure_state():
    match_runner._FAILED_RUNS.clear()
    yield
    match_runner._FAILED_RUNS.clear()


# ---------------------------------------------------------------------------
# Seed helpers (mirrors tests/routers/test_activities.py)
# ---------------------------------------------------------------------------


async def seed_user(session: AsyncSession, user_id: int, role: UserRole) -> User:
    u = User(
        id=user_id,
        email=f"{role.value}{user_id}@test.com",
        hashed_password="x",
        first_name="Test",
        last_name=f"User{user_id}",
        role=role,
        is_active=True,
        can_login=role != UserRole.athlete,
        created_at=_utc(),
    )
    session.add(u)
    await session.flush()
    return u


async def seed_club_member(
    session: AsyncSession, *, user_id: int, club_id: int, role: ClubRole = ClubRole.coach
) -> ClubMember:
    m = ClubMember(user_id=user_id, club_id=club_id, role_in_club=role)
    session.add(m)
    await session.flush()
    return m


async def seed_athlete(
    session: AsyncSession,
    athlete_id: int,
    *,
    club_id: int = 1,
    user_id: int | None = None,
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=user_id or (900 + athlete_id),
        first_name="Atleta",
        last_name=f"Ficticio{athlete_id}",
        birth_date=date(2012, 5, 1),
        sex=Sex.M,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def seed_connection(
    session: AsyncSession,
    *,
    athlete_id: int,
    strava_athlete_id: int,
    authorized_by_user_id: int,
    parent_user_id: int,
) -> StravaConnection:
    consent = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        consented_at=_utc(),
    )
    session.add(consent)
    await session.flush()

    conn = StravaConnection(
        athlete_id=athlete_id,
        strava_athlete_id=strava_athlete_id,
        status=StravaConnectionStatus.active,
        access_token_enc=b"enc-access",
        refresh_token_enc=b"enc-refresh",
        token_expires_at=_utc() + timedelta(hours=6),
        scope_granted="activity:read_all",
        authorized_by_user_id=authorized_by_user_id,
        consent_id=consent.id,
        connected_at=_utc(),
    )
    session.add(conn)
    await session.flush()
    return conn


async def seed_activity(
    session: AsyncSession,
    activity_id: int,
    *,
    strava_activity_id: int,
    athlete_id: int,
    connection_id: int,
    start_date_local: datetime,
    training_session_id: int | None = None,
    linked_by_user_id: int | None = None,
    name: str = "Salida ficticia",
) -> StravaActivity:
    resolved_linked_at = _utc() if training_session_id is not None else None
    resolved_linked_by = (
        (linked_by_user_id or 10) if training_session_id is not None else None
    )
    a = StravaActivity(
        id=activity_id,
        strava_activity_id=strava_activity_id,
        athlete_id=athlete_id,
        connection_id=connection_id,
        name=name,
        sport_type="Ride",
        start_date_utc=start_date_local.astimezone(timezone.utc)
        if start_date_local.tzinfo
        else start_date_local,
        start_date_local=start_date_local.replace(tzinfo=None)
        if start_date_local.tzinfo
        else start_date_local,
        elapsed_time_s=600,
        moving_time_s=590,
        distance_m=5000.0,
        total_elevation_gain_m=50.0,
        average_heartrate=145.0,
        max_heartrate=170.0,
        is_trainer=False,
        ingest_source=StravaIngestSource.webhook,
        training_session_id=training_session_id,
        linked_at=resolved_linked_at,
        linked_by_user_id=resolved_linked_by,
    )
    session.add(a)
    await session.flush()
    return a


async def seed_training_session(
    session: AsyncSession,
    session_id: int,
    *,
    club_id: int = 1,
    scheduled_date: date,
    created_by_user_id: int = 10,
    location: str = "Sede club",
    technical_focus: str = "Intervalos",
) -> TrainingSession:
    from datetime import time as _time

    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        scheduled_date=scheduled_date,
        scheduled_start_time=_time(16, 0),
        duration_min=90,
        location=location,
        technical_focus=technical_focus,
    )
    session.add(ts)
    await session.flush()
    return ts


async def seed_structure(
    session: AsyncSession,
    *,
    training_session_id: int,
    created_by_user_id: int = 10,
    band: AgeBand = AgeBand.BAND_13_15,
) -> IntervalStructure:
    """Insert a valid 3-block structure (warmup/work/cooldown, no repeat
    group) directly via the ORM — bypasses the API guardrail validation
    (owned by ``tests/intervals/test_structures.py`` /
    ``test_guardrail.py``), this file only needs *a* valid structure to
    correlate against.
    """
    structure = IntervalStructure(
        training_session_id=training_session_id,
        target_age_band=band,
        age_gate_confirmed=False,
        created_by_user_id=created_by_user_id,
    )
    session.add(structure)
    await session.flush()

    blocks = [
        IntervalStructureBlock(
            structure_id=structure.id,
            position=1,
            block_type=IntervalBlockType.WARMUP,
            duration_s=300,
            target_zone=HRZone.Z1,
            target_cadence_rpm=70,
        ),
        IntervalStructureBlock(
            structure_id=structure.id,
            position=2,
            block_type=IntervalBlockType.WORK,
            duration_s=120,
            target_zone=HRZone.Z2,
            target_cadence_rpm=85,
        ),
        IntervalStructureBlock(
            structure_id=structure.id,
            position=3,
            block_type=IntervalBlockType.COOLDOWN,
            duration_s=180,
            target_zone=HRZone.Z1,
            target_cadence_rpm=65,
        ),
    ]
    session.add_all(blocks)
    await session.flush()
    return structure


def _structure_create_payload(training_session_id: int) -> dict:
    """API body for POST /api/intervals/structures — same 3-block shape as
    ``seed_structure`` (warmup/work/cooldown, no repeat group, band 13-15)."""
    return {
        "training_session_id": training_session_id,
        "target_age_band": "13-15",
        "age_gate_confirmed": False,
        "blocks": [
            {
                "position": 1,
                "block_type": "warmup",
                "duration_s": 300,
                "target_zone": "Z1",
                "target_cadence_rpm": 70,
                "repeat_group": None,
                "repeat_count": None,
            },
            {
                "position": 2,
                "block_type": "work",
                "duration_s": 120,
                "target_zone": "Z2",
                "target_cadence_rpm": 85,
                "repeat_group": None,
                "repeat_count": None,
            },
            {
                "position": 3,
                "block_type": "cooldown",
                "duration_s": 180,
                "target_zone": "Z1",
                "target_cadence_rpm": 65,
                "repeat_group": None,
                "repeat_count": None,
            },
        ],
    }


def _matching_laps_payload() -> list[dict]:
    """Raw Strava laps (client-passthrough shape) that all land inside the
    ±30% tolerance of the 3 ``seed_structure`` blocks (300s/120s/180s) — so a
    real ``run_match_deferred`` produces an all-``cumplido`` result."""
    return [
        {
            "lap_index": 0,
            "elapsed_time": 310,
            "moving_time": 305,
            "average_heartrate": 140.0,
            "average_speed": 4.0,
        },
        {
            "lap_index": 1,
            "elapsed_time": 125,
            "moving_time": 120,
            "average_heartrate": 165.0,
            "average_speed": 5.5,
        },
        {
            "lap_index": 2,
            "elapsed_time": 170,
            "moving_time": 165,
            "average_heartrate": 138.0,
            "average_speed": 4.2,
        },
    ]


# ---------------------------------------------------------------------------
# Client factory + recording dispatcher (mirrors
# tests/routers/test_strava_integration.py)
# ---------------------------------------------------------------------------


def make_client(session: AsyncSession, *, user, dispatcher=None) -> AsyncClient:
    """Build an AsyncClient bound to a fresh local app with DB/auth overrides."""
    test_app = _build_app()

    async def _override_db():
        yield session
        await session.commit()

    async def _override_user():
        return user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_user

    if dispatcher is not None:
        test_app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        follow_redirects=False,
    )


class _RecordingDispatcher:
    """Fake TaskDispatcher: records dispatched calls, never executes them."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def dispatch(self, func, /, *args, **kwargs) -> None:
        self.calls.append((func, args, kwargs))


# ---------------------------------------------------------------------------
# Direct deferred-job runner (see module docstring "invoked directly")
# ---------------------------------------------------------------------------


async def _run_deferred_match(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    structure_id: int,
    strava_activity_id: int,
    triggered_by: MatchTrigger,
    laps: list[dict] | None = None,
    raise_exc: Exception | None = None,
) -> None:
    """Runs ``match_runner.run_match_deferred`` for real against the test's
    own in-memory engine, with ``StravaClient.get_activity_laps`` stubbed."""
    monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)

    async def _stub_get_activity_laps(self: StravaClient, activity_id: int) -> list[dict]:
        if raise_exc is not None:
            raise raise_exc
        return laps if laps is not None else []

    monkeypatch.setattr(StravaClient, "get_activity_laps", _stub_get_activity_laps)

    await match_runner.run_match_deferred(structure_id, strava_activity_id, triggered_by)


# ---------------------------------------------------------------------------
# Shared multi-entity setup
# ---------------------------------------------------------------------------


async def _seed_linked_scenario(session: AsyncSession, *, club_id: int = 1):
    """Coach + athlete + Strava connection + activity ALREADY linked to a
    session that already has a structure. Returns (coach, structure, activity,
    train_session)."""
    coach = await seed_user(session, 10, UserRole.coach)
    await seed_club_member(session, user_id=10, club_id=club_id)
    await seed_user(session, 20, UserRole.parent)
    athlete = await seed_athlete(session, 100, club_id=club_id)
    conn = await seed_connection(
        session,
        athlete_id=athlete.id,
        strava_athlete_id=555,
        authorized_by_user_id=20,
        parent_user_id=20,
    )
    train_session = await seed_training_session(
        session, 501, club_id=club_id, scheduled_date=date(2026, 3, 10)
    )
    structure = await seed_structure(
        session, training_session_id=train_session.id, created_by_user_id=10
    )
    activity = await seed_activity(
        session,
        1,
        strava_activity_id=9001,
        athlete_id=athlete.id,
        connection_id=conn.id,
        start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        training_session_id=train_session.id,
        linked_by_user_id=10,
    )
    await session.commit()
    return coach, structure, activity, train_session


# ===========================================================================
# A. Dispatch wiring — link trigger + structure-change trigger
# ===========================================================================


class TestDispatchTriggers:
    async def test_link_dispatches_match_job_with_link_trigger(self, session):
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        )
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        structure = await seed_structure(
            session, training_session_id=train_session.id, created_by_user_id=10
        )
        await session.commit()

        dispatcher = _RecordingDispatcher()
        async with make_client(session, user=coach, dispatcher=dispatcher) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": train_session.id},
            )

        assert resp.status_code == 200, resp.text
        assert len(dispatcher.calls) == 1
        func, args, kwargs = dispatcher.calls[0]
        assert func is match_runner.run_match_deferred
        # routers/activities.py::link_activity dispatches with POSITIONAL args.
        assert args == (structure.id, activity.id, MatchTrigger.link)
        assert kwargs == {}

    async def test_link_to_session_without_structure_does_not_dispatch(self, session):
        """No structure on the target session → nothing to compare, no job
        queued (guards the ``target_structure_id is not None`` branch)."""
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        )
        # No interval structure attached to this session.
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        await session.commit()

        dispatcher = _RecordingDispatcher()
        async with make_client(session, user=coach, dispatcher=dispatcher) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": train_session.id},
            )

        assert resp.status_code == 200, resp.text
        assert dispatcher.calls == []

    async def test_structure_create_dispatches_structure_change_for_linked_activity(
        self, session
    ):
        """Structure created AFTER the activity is already linked (research.md
        D6 trigger 2) — ``POST /api/intervals/structures`` dispatches the
        same job with ``triggered_by=structure_change``, keyword args
        (``routers/intervals.py::_dispatch_match_for_linked_activities``)."""
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
            training_session_id=train_session.id,
            linked_by_user_id=10,
        )
        await session.commit()

        dispatcher = _RecordingDispatcher()
        async with make_client(session, user=coach, dispatcher=dispatcher) as client:
            resp = await client.post(
                "/api/intervals/structures",
                json=_structure_create_payload(train_session.id),
            )

        assert resp.status_code == 201, resp.text
        structure_id = resp.json()["id"]

        assert len(dispatcher.calls) == 1
        func, args, kwargs = dispatcher.calls[0]
        assert func is match_runner.run_match_deferred
        assert args == ()
        assert kwargs == {
            "structure_id": structure_id,
            "strava_activity_id": activity.id,
            "triggered_by": MatchTrigger.structure_change,
        }

    async def test_structure_create_without_linked_activity_does_not_dispatch(
        self, session
    ):
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        await session.commit()

        dispatcher = _RecordingDispatcher()
        async with make_client(session, user=coach, dispatcher=dispatcher) as client:
            resp = await client.post(
                "/api/intervals/structures",
                json=_structure_create_payload(train_session.id),
            )

        assert resp.status_code == 201, resp.text
        assert dispatcher.calls == []


# ===========================================================================
# B. GET .../match — status envelope: computed / no_activity / computing / failed
# ===========================================================================


class TestMatchStatuses:
    async def test_status_computed_after_real_run(
        self, session, session_factory, monkeypatch: pytest.MonkeyPatch
    ):
        coach, structure, activity, train_session = await _seed_linked_scenario(session)

        await _run_deferred_match(
            monkeypatch,
            session_factory,
            structure_id=structure.id,
            strava_activity_id=activity.id,
            triggered_by=MatchTrigger.manual,
            laps=_matching_laps_payload(),
        )

        async with make_client(session, user=coach) as client:
            resp = await client.get(
                f"/api/intervals/sessions/{train_session.id}/match"
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        assert body["structure_id"] == structure.id
        assert body["activity"]["id"] == activity.id
        assert len(body["blocks"]) == 3
        assert all(b["status"] == "cumplido" for b in body["blocks"])
        assert body["summary"] == {
            "cumplido": 3,
            "fuera_tolerancia": 0,
            "libre": 0,
            "sin_dato": 0,
            "extra": 0,
        }
        assert body["extra_laps"] == []

    async def test_status_no_activity(self, session):
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        structure = await seed_structure(
            session, training_session_id=train_session.id, created_by_user_id=10
        )
        await session.commit()

        async with make_client(session, user=coach) as client:
            resp = await client.get(
                f"/api/intervals/sessions/{train_session.id}/match"
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "no_activity"
        assert body["structure_id"] == structure.id
        assert body["activity"] is None
        assert body["blocks"] == []

    async def test_status_computing_before_job_runs(self, session):
        """Activity linked, structure exists, but the deferred job has not
        run yet — no result row, no failure marker (the state right after a
        dispatch, before the background task executes)."""
        coach, structure, activity, train_session = await _seed_linked_scenario(session)

        async with make_client(session, user=coach) as client:
            resp = await client.get(
                f"/api/intervals/sessions/{train_session.id}/match"
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computing"
        assert body["activity"]["id"] == activity.id
        assert body["blocks"] == []

    async def test_status_failed_after_real_run_raises(
        self, session, session_factory, monkeypatch: pytest.MonkeyPatch
    ):
        coach, structure, activity, train_session = await _seed_linked_scenario(session)

        await _run_deferred_match(
            monkeypatch,
            session_factory,
            structure_id=structure.id,
            strava_activity_id=activity.id,
            triggered_by=MatchTrigger.manual,
            raise_exc=StravaAPIError("Error simulado de la API de Strava."),
        )

        async with make_client(session, user=coach) as client:
            resp = await client.get(
                f"/api/intervals/sessions/{train_session.id}/match"
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "failed"
        assert body["activity"]["id"] == activity.id
        assert body["retry_available"] is True

        # No IntervalMatchResult was persisted for the failed run.
        result = await session.execute(
            select_match_result(structure.id, activity.id)
        )
        assert result.scalar_one_or_none() is None


def select_match_result(structure_id: int, activity_id: int):
    from sqlalchemy import select

    return select(IntervalMatchResult).where(
        IntervalMatchResult.structure_id == structure_id,
        IntervalMatchResult.strava_activity_id == activity_id,
    )


# ===========================================================================
# C. POST .../recalculate — 202 (dispatch manual) / 409 (no linked activity)
# ===========================================================================


class TestRecalculate:
    async def test_recalculate_returns_202_and_dispatches_manual_trigger(self, session):
        coach, structure, activity, _train_session = await _seed_linked_scenario(session)

        dispatcher = _RecordingDispatcher()
        async with make_client(session, user=coach, dispatcher=dispatcher) as client:
            resp = await client.post(
                f"/api/intervals/structures/{structure.id}/recalculate",
                json={},
            )

        assert resp.status_code == 202, resp.text
        assert resp.json() == {"status": "computing"}

        assert len(dispatcher.calls) == 1
        func, args, kwargs = dispatcher.calls[0]
        assert func is match_runner.run_match_deferred
        assert kwargs == {
            "structure_id": structure.id,
            "strava_activity_id": activity.id,
            "triggered_by": MatchTrigger.manual,
        }

    async def test_recalculate_without_linked_activity_returns_409(self, session):
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        structure = await seed_structure(
            session, training_session_id=train_session.id, created_by_user_id=10
        )
        await session.commit()

        dispatcher = _RecordingDispatcher()
        async with make_client(session, user=coach, dispatcher=dispatcher) as client:
            resp = await client.post(
                f"/api/intervals/structures/{structure.id}/recalculate",
                json={},
            )

        assert resp.status_code == 409, resp.text
        assert "vinculada" in resp.json()["detail"].lower()
        assert dispatcher.calls == []


# ===========================================================================
# D. Replace-on-refetch of laps (data-model.md §5 "Refresh semantics")
# ===========================================================================


class TestLapsReplaceOnRefetch:
    async def test_second_run_replaces_laps_not_accumulates(
        self, session, session_factory, monkeypatch: pytest.MonkeyPatch
    ):
        _coach, structure, activity, _train_session = await _seed_linked_scenario(session)

        await _run_deferred_match(
            monkeypatch,
            session_factory,
            structure_id=structure.id,
            strava_activity_id=activity.id,
            triggered_by=MatchTrigger.link,
            laps=_matching_laps_payload(),
        )

        from sqlalchemy import select

        first_laps = (
            await session.execute(
                select(StravaActivityLap).where(
                    StravaActivityLap.strava_activity_id == activity.id
                )
            )
        ).scalars().all()
        assert {lap.lap_index for lap in first_laps} == {0, 1, 2}

        # Second run, different device payload entirely (fewer laps, new
        # lap_index values) — must REPLACE, not accumulate.
        second_payload = [
            {
                "lap_index": 5,
                "elapsed_time": 400,
                "moving_time": 395,
                "average_heartrate": 150.0,
                "average_speed": 3.8,
            },
            {
                "lap_index": 6,
                "elapsed_time": 50,
                "moving_time": 48,
                "average_heartrate": 130.0,
                "average_speed": 3.0,
            },
        ]
        await _run_deferred_match(
            monkeypatch,
            session_factory,
            structure_id=structure.id,
            strava_activity_id=activity.id,
            triggered_by=MatchTrigger.manual,
            laps=second_payload,
        )

        # The delete-then-insert replace (data-model.md §5) happened on a
        # DIFFERENT session (the job opens its own); this test's ``session``
        # already cached the first run's StravaActivityLap instances in its
        # identity map. On sqlite, the reused-after-delete autoincrement ids
        # collide with those cached PKs, so a plain re-query would silently
        # return the STALE first-run objects instead of the fresh rows —
        # ``populate_existing()`` forces the query to overwrite the cached
        # attributes synchronously (an ``expire_all()`` + lazy-reload would
        # need a greenlet context that a plain attribute access after
        # ``await session.execute(...)`` does not have).
        second_laps = (
            await session.execute(
                select(StravaActivityLap)
                .where(StravaActivityLap.strava_activity_id == activity.id)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
        assert {lap.lap_index for lap in second_laps} == {5, 6}
        assert len(second_laps) == 2  # not 5 (2 + the original 3)

        # UNIQUE(structure_id, strava_activity_id) — still exactly one
        # persisted match result (upsert, not a duplicate row).
        result_rows = (
            await session.execute(select_match_result(structure.id, activity.id))
        ).scalars().all()
        assert len(result_rows) == 1
        assert result_rows[0].triggered_by == MatchTrigger.manual


# ===========================================================================
# E. Unlink — deletes the match result, preserves laps (D7)
# ===========================================================================


class TestUnlinkPreservesLaps:
    async def test_unlink_deletes_match_result_but_keeps_laps(
        self, session, session_factory, monkeypatch: pytest.MonkeyPatch
    ):
        coach, structure, activity, train_session = await _seed_linked_scenario(session)

        await _run_deferred_match(
            monkeypatch,
            session_factory,
            structure_id=structure.id,
            strava_activity_id=activity.id,
            triggered_by=MatchTrigger.link,
            laps=_matching_laps_payload(),
        )

        # Sanity: both the match result and the laps exist before unlinking.
        pre_result = (
            await session.execute(select_match_result(structure.id, activity.id))
        ).scalar_one_or_none()
        assert pre_result is not None

        from sqlalchemy import select

        pre_laps = (
            await session.execute(
                select(StravaActivityLap).where(
                    StravaActivityLap.strava_activity_id == activity.id
                )
            )
        ).scalars().all()
        assert len(pre_laps) == 3

        async with make_client(session, user=coach) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": None},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["link"] is None

        post_result = (
            await session.execute(select_match_result(structure.id, activity.id))
        ).scalar_one_or_none()
        assert post_result is None, (
            "Unlink must delete the IntervalMatchResult row for this "
            "structure<->activity pair (D7)."
        )

        post_laps = (
            await session.execute(
                select(StravaActivityLap).where(
                    StravaActivityLap.strava_activity_id == activity.id
                )
            )
        ).scalars().all()
        assert len(post_laps) == 3, (
            "Unlink must NOT delete strava_activity_laps — laps are owned "
            "by the activity, not the match (D7)."
        )
        assert {lap.lap_index for lap in post_laps} == {0, 1, 2}

        # Structure itself is untouched (still readable) — only the derived
        # match result was deleted.
        async with make_client(session, user=coach) as client:
            structure_resp = await client.get(
                f"/api/intervals/sessions/{train_session.id}/structure"
            )
        assert structure_resp.status_code == 200, structure_resp.text
