"""Router tests for ``GET /api/dashboard/coach-summary`` (feature 031, T010-T014).

Covers:
- Happy path: mixed current/outdated/missing consents, stale/fresh insights,
  weekly-load minutes per age band.
- Band-attribution edge case: one joint session convoking both age bands
  counts its full ``duration_min`` toward each band.
- Empty-band case: a band with zero athletes is omitted, never zeroed.
- Week-boundary case: a session dated right across the Sunday-night/Monday
  ``America/Bogota`` boundary lands in the correct ISO week.
- RBAC-negative (parent → 403; coach with a foreign ``club_id`` → 403) and
  validation-negative (non-integer ``club_id`` → 422).
- Partial-failure isolation: one sub-aggregate raising still yields 200 with
  only that field null.
- Query-count/no-N+1 regression, using ``tests/helpers/query_counting.py``.
- Privacy invariant: no athlete-identifying key anywhere in the payload.

Strategy: SQLite async in-memory with ``app.main.app`` + dependency
overrides for ``get_db``/``get_current_user`` — same pattern as
``tests/routers/test_season_panorama.py`` (the closest existing precedent
for a club-scoped coach/admin aggregate endpoint). ``dashboard.router`` is
unconditionally mounted in ``app.main`` (unlike ``activities.router``), so
no local ASGI app is needed.

All data is fictitious (CLAUDE.md §Privacy) — no real TyR athlete data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

# ``ParentalConsent.policy`` is mapper-level ``lazy="joined"`` — creating the
# ``parental_consents`` table pulls in ``privacy_policies`` (whose
# ``content_html`` is MySQL ``LONGTEXT``, which SQLite has no compiler for).
# Same escape hatch as tests/routers/test_strava_integration.py: register a
# SQLite-only compile rule (TEXT is SQLite's native unbounded string type).
# Only affects DDL compiled against the ``sqlite`` dialect in this module's
# own in-memory engine — no product code changes.
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"

import app.services.dashboard_summary as dashboard_summary
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete import Sex
from app.models.club import ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.privacy_policy import PrivacyPolicy
from app.models.training_session import SessionAttendance, SessionStatus, TrainingSession
from app.models.user import UserRole
from app.services.category import compute_age_decimal
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_user,
    link_user_to_club,
)
from tests.helpers.query_counting import count_selects

pytestmark = pytest.mark.asyncio

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "privacy_policies",
    "parental_consents",
    "agent_runs",
    "athlete_ai_insights",
    "training_sessions",
    "session_attendance",
)

_BOGOTA = ZoneInfo("America/Bogota")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# DB fixtures — in-memory aiosqlite, subset of tables (mirrors
# tests/routers/test_activities.py / tests/routers/test_season_panorama.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
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
# Fake users — SimpleNamespace with an explicit ``club_memberships`` list,
# same convention as test_season_panorama.py: avoids async lazy-loading the
# real ORM relationship outside of a session.
# ---------------------------------------------------------------------------


def coach_user(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        club_memberships=[SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)],
    )


def admin_user(user_id: int = 99) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.admin, club_memberships=[])


def parent_user(user_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.parent, club_memberships=[])


def make_client(session: AsyncSession, *, user) -> AsyncClient:
    """Bind an AsyncClient to the real ``app.main.app`` with DB/auth overrides."""

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Deterministic "now" for compute_weekly_load — subclasses ``datetime`` so
# ``datetime.now(_BOGOTA_TZ)`` resolves to a fixed instant regardless of the
# machine's real clock (mirrors the freezegun-style trick, no new dependency
# added — repo has none available).
# ---------------------------------------------------------------------------


def _freeze_now(monkeypatch: pytest.MonkeyPatch, fixed: datetime) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    monkeypatch.setattr(dashboard_summary, "datetime", _FrozenDatetime)


# Canonical frozen instant for most tests: Wednesday 2026-07-15, mid-week —
# unambiguous ISO week Mon 2026-07-13..Sun 2026-07-19.
_FROZEN_WED = datetime(2026, 7, 15, 12, 0, tzinfo=_BOGOTA)
_WEEK_START = date(2026, 7, 13)
_WEEK_END = date(2026, 7, 19)

# Birth dates landing comfortably mid-band as of _FROZEN_WED (not near a
# 10/13/16 boundary, so rounding in compute_age_decimal can't tip the band).
_BIRTH_10_12 = date(2015, 1, 1)  # ~11.5 y/o on 2026-07-15
_BIRTH_13_15 = date(2012, 1, 1)  # ~14.5 y/o on 2026-07-15

assert 10 <= compute_age_decimal(_BIRTH_10_12, reference_date=_FROZEN_WED.date()) < 13
assert 13 <= compute_age_decimal(_BIRTH_13_15, reference_date=_FROZEN_WED.date()) < 16


# ---------------------------------------------------------------------------
# Seed helpers specific to this feature (consents / policies / sessions /
# agent runs) — training-session shape mirrors
# tests/routers/test_activities.py::seed_training_session.
# ---------------------------------------------------------------------------


async def seed_policy(
    session: AsyncSession,
    policy_id: int,
    *,
    version: str,
    effective_date: date,
    deprecated_at: date | None = None,
) -> PrivacyPolicy:
    p = PrivacyPolicy(
        id=policy_id,
        version=version,
        effective_date=effective_date,
        deprecated_at=deprecated_at,
        title=f"Política {version}",
        content_html="<p>contenido</p>",
        content_hash=f"hash-{version}",
    )
    session.add(p)
    await session.flush()
    return p


async def seed_consent(
    session: AsyncSession,
    *,
    athlete_id: int,
    policy_id: int,
    parent_user_id: int = 20,
    withdrawn_at: datetime | None = None,
) -> ParentalConsent:
    c = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        policy_id=policy_id,
        consented_at=_utc(),
        withdrawn_at=withdrawn_at,
    )
    session.add(c)
    await session.flush()
    return c


async def seed_training_session(
    session: AsyncSession,
    session_id: int,
    *,
    club_id: int = 1,
    scheduled_date: date,
    duration_min: int = 90,
    status: SessionStatus = SessionStatus.PLANNED,
    created_by_user_id: int = 10,
) -> TrainingSession:
    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        status=status,
        scheduled_date=scheduled_date,
        scheduled_start_time=datetime(2026, 1, 1, 15, 0).time(),
        duration_min=duration_min,
        location="Sede club",
        technical_focus="Resistencia",
    )
    session.add(ts)
    await session.flush()
    return ts


async def seed_attendance(
    session: AsyncSession, *, session_id: int, athlete_id: int
) -> SessionAttendance:
    from app.models.training_session import AttendanceStatus

    att = SessionAttendance(
        session_id=session_id,
        athlete_id=athlete_id,
        status=AttendanceStatus.PRESENTE,
    )
    session.add(att)
    await session.flush()
    return att


async def seed_agent_run(
    session: AsyncSession,
    run_id: int,
    *,
    athlete_id: int,
    requested_by_user_id: int = 10,
    stale_since: datetime | None = None,
) -> AgentRun:
    run = AgentRun(
        id=run_id,
        external_run_id=f"run-{run_id}",
        graph_name="race-analyst",
        prompt_version="race_analyst_v2",
        started_at=_utc(),
        status=AgentRunStatus.completed,
        requested_by_user_id=requested_by_user_id,
        athlete_id=athlete_id,
        checkpoint_thread_id=f"run-{run_id}",
        stale_since=stale_since,
        created_at=_utc(),
        updated_at=_utc(),
    )
    session.add(run)
    await session.flush()
    return run


# ===========================================================================
# A. Happy path (T010): mixed consents/insights + weekly load
# ===========================================================================


class TestHappyPath:
    async def _seed(self, session: AsyncSession) -> None:
        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await create_user(session, user_id=20, role=UserRole.parent)

        # Políticas: una vieja (deprecada) y la activa.
        await seed_policy(
            session, 1, version="v1", effective_date=date(2025, 1, 1),
            deprecated_at=date(2026, 1, 1),
        )
        await seed_policy(session, 2, version="v2", effective_date=date(2026, 1, 1))

        # Atletas — banda 10-12: 101 (consentimiento vigente), 102
        # (consentimiento con política vieja → pendiente), 103 (sin
        # consentimiento → pendiente).
        for athlete_id in (101, 102, 103):
            await create_user(session, user_id=900 + athlete_id, role=UserRole.athlete, can_login=False)
            await create_athlete(
                session, athlete_id=athlete_id, first_name="Atleta", last_name=str(athlete_id),
                birth_date=_BIRTH_10_12, sex=Sex.M, club_id=1,
                user_id=900 + athlete_id, created_by=10,
            )
        await seed_consent(session, athlete_id=101, policy_id=2)
        await seed_consent(session, athlete_id=102, policy_id=1)  # política vieja → pendiente
        # 103: sin fila de consentimiento → pendiente

        # Atletas — banda 13-15: 104 (vigente), 105 (insight stale), 106
        # (insight fresco).
        for athlete_id in (104, 105, 106):
            await create_user(session, user_id=900 + athlete_id, role=UserRole.athlete, can_login=False)
            await create_athlete(
                session, athlete_id=athlete_id, first_name="Atleta", last_name=str(athlete_id),
                birth_date=_BIRTH_13_15, sex=Sex.F, club_id=1,
                user_id=900 + athlete_id, created_by=10,
            )
            await seed_consent(session, athlete_id=athlete_id, policy_id=2)

        await seed_agent_run(session, 1, athlete_id=105, stale_since=_utc())
        await create_insight(session, athlete_id=105, agent_run_id=1, is_active=1, generated_by_user_id=10)
        await seed_agent_run(session, 2, athlete_id=106, stale_since=None)
        await create_insight(session, athlete_id=106, agent_run_id=2, is_active=1, generated_by_user_id=10)

        # Sesiones planificadas de la semana Mon 2026-07-13..Sun 2026-07-19.
        await seed_training_session(session, 201, scheduled_date=date(2026, 7, 14), duration_min=90)
        await seed_attendance(session, session_id=201, athlete_id=101)

        await seed_training_session(session, 202, scheduled_date=date(2026, 7, 15), duration_min=60)
        await seed_attendance(session, session_id=202, athlete_id=104)

        # Sesión conjunta (band-attribution edge case): convoca a un atleta
        # de cada banda; sus 120 min deben sumarse a AMBAS bandas.
        await seed_training_session(session, 203, scheduled_date=date(2026, 7, 16), duration_min=120)
        await seed_attendance(session, session_id=203, athlete_id=102)
        await seed_attendance(session, session_id=203, athlete_id=105)

        # Excluida — status distinto de "planned".
        await seed_training_session(
            session, 204, scheduled_date=date(2026, 7, 17), duration_min=45,
            status=SessionStatus.EXECUTED,
        )
        await seed_attendance(session, session_id=204, athlete_id=101)

        # Excluida — fuera de la semana (siguiente lunes).
        await seed_training_session(session, 205, scheduled_date=date(2026, 7, 20), duration_min=200)
        await seed_attendance(session, session_id=205, athlete_id=101)

        # Excluida — fuera de la semana (domingo anterior).
        await seed_training_session(session, 206, scheduled_date=date(2026, 7, 12), duration_min=200)
        await seed_attendance(session, session_id=206, athlete_id=104)

        await session.commit()

    async def test_happy_path_counts_and_weekly_load(self, session, monkeypatch):
        _freeze_now(monkeypatch, _FROZEN_WED)
        await self._seed(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["consents_pending"] == 2  # 102 (política vieja) + 103 (sin consentimiento)
        assert data["insights_stale"] == 1  # 105

        bands = {b["age_band"]: b for b in data["weekly_load"]}
        assert set(bands) == {"10-12", "13-15"}

        band_10_12 = bands["10-12"]
        assert band_10_12["planned_minutes"] == 210  # 90 (201) + 120 (203, joint)
        assert band_10_12["cap_minutes"] == 600
        assert band_10_12["athlete_count"] == 3

        band_13_15 = bands["13-15"]
        assert band_13_15["planned_minutes"] == 180  # 60 (202) + 120 (203, joint)
        assert band_13_15["cap_minutes"] == 780
        assert band_13_15["athlete_count"] == 3

    async def test_band_attribution_joint_session_counts_toward_both_bands(
        self, session, monkeypatch
    ):
        """Regression for the band-attribution edge case: session 203 convokes
        one athlete from each band and must contribute its full 120 minutes
        to BOTH bands, not split or double-counted within a band."""
        _freeze_now(monkeypatch, _FROZEN_WED)
        await self._seed(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        bands = {b["age_band"]: b for b in resp.json()["weekly_load"]}
        # If session 203 leaked into only one band, or were double-counted,
        # these exact totals would drift.
        assert bands["10-12"]["planned_minutes"] == 210
        assert bands["13-15"]["planned_minutes"] == 180


class TestEmptyBand:
    async def test_band_with_zero_athletes_is_omitted_not_zeroed(self, session, monkeypatch):
        _freeze_now(monkeypatch, _FROZEN_WED)
        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await seed_policy(session, 1, version="v1", effective_date=date(2026, 1, 1))

        # Solo un atleta, banda 10-12 — el club no tiene atletas 13-15.
        await create_user(session, user_id=901, role=UserRole.athlete, can_login=False)
        await create_athlete(
            session, athlete_id=1, birth_date=_BIRTH_10_12, sex=Sex.M,
            club_id=1, user_id=901, created_by=10,
        )
        await seed_consent(session, athlete_id=1, policy_id=1)
        await session.commit()

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 200, resp.text
        bands = resp.json()["weekly_load"]
        assert len(bands) == 1
        assert bands[0]["age_band"] == "10-12"
        # No debe aparecer una entrada "13-15" en cero — se omite por
        # completo, no se incluye con planned_minutes=0.
        assert all(b["age_band"] != "13-15" for b in bands)


class TestWeekBoundary:
    async def test_session_near_sunday_night_monday_bogota_boundary(
        self, session, monkeypatch
    ):
        """Freezes "now" to Sunday 21:00 America/Bogota (Monday 02:00 UTC) —
        a naive/UTC-based "today" would wrongly think the new ISO week has
        already started. The correct Bogota-aware week is
        Mon 2026-07-06..Sun 2026-07-12."""
        fixed_sunday_night_bogota = datetime(2026, 7, 12, 21, 0, tzinfo=_BOGOTA)
        _freeze_now(monkeypatch, fixed_sunday_night_bogota)

        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await seed_policy(session, 1, version="v1", effective_date=date(2026, 1, 1))

        await create_user(session, user_id=901, role=UserRole.athlete, can_login=False)
        await create_athlete(
            session, athlete_id=1, birth_date=_BIRTH_10_12, sex=Sex.M,
            club_id=1, user_id=901, created_by=10,
        )
        await seed_consent(session, athlete_id=1, policy_id=1)

        # Dentro de la semana correcta (domingo, último día de la semana
        # Bogota-aware) — DEBE contar.
        await seed_training_session(session, 301, scheduled_date=date(2026, 7, 12), duration_min=50)
        await seed_attendance(session, session_id=301, athlete_id=1)

        # Ya en la semana siguiente según Bogota (aunque en UTC "ahora" ya
        # es lunes) — NO debe contar.
        await seed_training_session(session, 302, scheduled_date=date(2026, 7, 13), duration_min=200)
        await seed_attendance(session, session_id=302, athlete_id=1)

        await session.commit()

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 200, resp.text
        bands = {b["age_band"]: b for b in resp.json()["weekly_load"]}
        assert bands["10-12"]["planned_minutes"] == 50


# ===========================================================================
# B. RBAC-negative / validation-negative (T011)
# ===========================================================================


class TestRbacAndValidation:
    async def _seed_minimal(self, session: AsyncSession) -> None:
        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await create_user(session, user_id=20, role=UserRole.parent)
        await session.commit()

    async def test_parent_role_forbidden(self, session):
        await self._seed_minimal(session)

        async with make_client(session, user=parent_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 403

    async def test_coach_foreign_club_id_forbidden(self, session):
        await self._seed_minimal(session)

        async with make_client(session, user=coach_user(club_id=1)) as client:
            resp = await client.get("/api/dashboard/coach-summary", params={"club_id": 2})

        assert resp.status_code == 403

    async def test_non_integer_club_id_unprocessable(self, session):
        await self._seed_minimal(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get(
                "/api/dashboard/coach-summary", params={"club_id": "not-an-int"}
            )

        assert resp.status_code == 422


# ===========================================================================
# C. Partial-failure isolation (T012)
# ===========================================================================


class TestPartialFailureIsolation:
    async def test_consents_sub_aggregate_failure_isolated(self, session, monkeypatch):
        """Forces the internal ``get_active_policy`` call inside
        ``compute_consents_pending``'s own try/except to raise — the other
        two sub-aggregates must still populate and the endpoint must still
        return 200."""
        _freeze_now(monkeypatch, _FROZEN_WED)

        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await seed_policy(session, 1, version="v1", effective_date=date(2026, 1, 1))

        await create_user(session, user_id=901, role=UserRole.athlete, can_login=False)
        await create_athlete(
            session, athlete_id=1, birth_date=_BIRTH_10_12, sex=Sex.M,
            club_id=1, user_id=901, created_by=10,
        )
        await seed_consent(session, athlete_id=1, policy_id=1)

        await seed_training_session(session, 401, scheduled_date=date(2026, 7, 14), duration_min=90)
        await seed_attendance(session, session_id=401, athlete_id=1)
        await session.commit()

        async def _raise_get_active_policy(db):
            raise RuntimeError("boom — simulated failure inside consents_pending")

        monkeypatch.setattr(dashboard_summary, "get_active_policy", _raise_get_active_policy)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["consents_pending"] is None
        assert data["insights_stale"] == 0
        assert data["weekly_load"] == [
            {
                "age_band": "10-12",
                "planned_minutes": 90,
                "cap_minutes": 600,
                "athlete_count": 1,
            }
        ]


# ===========================================================================
# D. Query-count / no-N+1 regression (T013)
# ===========================================================================


class TestQueryCount:
    async def _seed_many(self, session: AsyncSession) -> None:
        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await seed_policy(session, 1, version="v1", effective_date=date(2026, 1, 1))

        athlete_ids = list(range(1, 16))  # ~15 athletes
        for i, athlete_id in enumerate(athlete_ids):
            birth_date = _BIRTH_10_12 if i % 2 == 0 else _BIRTH_13_15
            await create_user(session, user_id=900 + athlete_id, role=UserRole.athlete, can_login=False)
            await create_athlete(
                session, athlete_id=athlete_id, birth_date=birth_date, sex=Sex.M,
                club_id=1, user_id=900 + athlete_id, created_by=10,
            )
            # La mayoría con consentimiento vigente; algunos sin él.
            if i % 3 != 0:
                await seed_consent(session, athlete_id=athlete_id, policy_id=1)

        # ~10 sesiones planificadas esta semana, cada una con 1-2 convocados.
        for i in range(10):
            session_id = 500 + i
            await seed_training_session(
                session, session_id,
                scheduled_date=date(2026, 7, 13) + timedelta(days=i % 7),
                duration_min=60,
            )
            await seed_attendance(session, session_id=session_id, athlete_id=athlete_ids[i % len(athlete_ids)])
            await seed_attendance(
                session, session_id=session_id, athlete_id=athlete_ids[(i + 1) % len(athlete_ids)]
            )

        # 5 insights activos, alguno stale.
        for j in range(5):
            run_id = 600 + j
            athlete_id = athlete_ids[j]
            stale_since = _utc() if j % 2 == 0 else None
            await seed_agent_run(session, run_id, athlete_id=athlete_id, stale_since=stale_since)
            await create_insight(
                session, athlete_id=athlete_id, agent_run_id=run_id, is_active=1,
                generated_by_user_id=10, valida_num=j,
            )

        await session.commit()

    async def test_query_count_no_n_plus_one(self, session, engine, monkeypatch):
        _freeze_now(monkeypatch, _FROZEN_WED)
        await self._seed_many(session)

        async with count_selects(engine) as counter:
            async with make_client(session, user=coach_user()) as client:
                resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 200, resp.text

        observed = counter[0]
        assert observed <= 12, (
            f"N+1 regression detected: GET /api/dashboard/coach-summary issued "
            f"{observed} SELECT statements (ceiling is 12) for ~15 athletes / "
            "10 sessions / 5 insights. Check that each sub-aggregate in "
            "app/services/dashboard_summary.py stays a single grouped query."
        )
        assert observed >= 3, (
            f"Too few SELECTs ({observed}) — the measurement harness may be broken."
        )


# ===========================================================================
# E. Privacy invariant (T014)
# ===========================================================================


_FORBIDDEN_KEYS = {
    "name",
    "first_name",
    "last_name",
    "athlete_name",
    "athlete_id",
    "birth_date",
    "email",
    "athlete",
    "athletes",
}


def _walk_keys(obj: Any, found: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(k)
            _walk_keys(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_keys(item, found)


class TestPrivacyInvariant:
    async def test_no_athlete_identifying_key_in_payload(self, session, monkeypatch):
        _freeze_now(monkeypatch, _FROZEN_WED)

        await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_user(session, user_id=10, role=UserRole.coach)
        await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await seed_policy(session, 1, version="v1", effective_date=date(2026, 1, 1))

        distinctive_name = "Zzyxatleta-Privacidad-9182"
        await create_user(session, user_id=901, role=UserRole.athlete, can_login=False)
        await create_athlete(
            session, athlete_id=1, first_name=distinctive_name, last_name="Apellido",
            birth_date=_BIRTH_10_12, sex=Sex.M, club_id=1, user_id=901, created_by=10,
        )
        # Sin consentimiento (pendiente) — ejercita el path de conteo.
        await seed_training_session(session, 701, scheduled_date=date(2026, 7, 14), duration_min=90)
        await seed_attendance(session, session_id=701, athlete_id=1)
        await session.commit()

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/dashboard/coach-summary")

        assert resp.status_code == 200, resp.text
        raw_text = resp.text
        data = resp.json()

        assert distinctive_name not in raw_text
        assert "Apellido" not in raw_text

        found_keys: set[str] = set()
        _walk_keys(data, found_keys)
        leaked = found_keys & _FORBIDDEN_KEYS
        assert not leaked, f"Athlete-identifying key(s) leaked in payload: {leaked}"
