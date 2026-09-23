"""Feature 045 (T015) — per-row ``metrics`` on the competition results read.

``get_event_results`` attaches a ``MetricSet`` to every row through the one
metrics engine (``field_metrics.compute_category_metrics``):

- coach / admin → full set (winner and podium gaps included);
- parent        → family subset only (``FamilyMetricSet``, policy from
  ``services.race.audience``); winner/podium gaps are *omitted from the
  payload*, not nulled;
- metrics are computed over the WHOLE category, never over the rows the
  caller happens to be allowed to see;
- no per-row queries — the statement count does not grow with the rows.

Fixtures use fictitious names only.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

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
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.schemas.race_results import CoachMetricSet, FamilyMetricSet
from app.services.race.audience import FAMILY_EXCLUDED_METRIC_FIELDS
from app.services.race.field_metrics import MetricSet
from app.services.race.results_read import get_event_results
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.query_counting import count_selects

_URL = "/api/race-analysis/race-events/{event_id}/results"

_FAMILY_KEYS = {
    "field_size",
    "timed_finishers",
    "position",
    "percentile",
    "gap_to_median_pct",
}
_COACH_ONLY_KEYS = {
    "gap_to_winner_pct",
    "gap_to_winner_ms",
    "gap_to_podium_pct",
    "gap_to_podium_ms",
}

# Competitor ids (see ``_seed``).
_COMP_LEADER = 1  # club athlete 1 (parent 5) — P1 in INF_M
_COMP_SECOND = 2  # club athlete 2 (parent 6) — P2 in INF_M
_COMP_MINUS_LAPS = 7
_COMP_DNF = 8
_COMP_SMALL_FIELD = 9  # club athlete 3 (parent 5) — P1 in INF_F (only 4 timed)

_RIVAL_NAMES = ("Alfa", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel")


def _fake_user(role: UserRole, user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}_{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Engine / seed
# ---------------------------------------------------------------------------


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
            "race_series",
            "race_events",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_course_variants",
            "race_course_category_setups",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _result(
    event_id: int,
    category_id: int,
    competitor_id: int,
    *,
    position: int | None,
    status: ResultStatus = ResultStatus.FINISHED,
    race_time_ms: int | None = None,
    athlete_id: int | None = None,
    laps_behind: int | None = None,
) -> RaceResult:
    return RaceResult(
        event_id=event_id,
        category_id=category_id,
        competitor_id=competitor_id,
        athlete_id=athlete_id,
        position=position,
        status=status,
        race_time_ms=race_time_ms,
        laps_behind=laps_behind,
        points_awarded=0,
        created_by_user_id=10,
    )


async def _seed(session: AsyncSession) -> None:
    """Event 100: INF_M with 6 timed finishers + 1 MINUS_LAPS + 1 DNF, and
    INF_F with only 4 timed finishers. Event 101: a single INF_M result."""
    now = datetime.now(timezone.utc)

    def _user(uid: int, role: UserRole, can_login: bool = True) -> User:
        return User(
            id=uid, email=f"u{uid}@test.com", hashed_password="x",
            first_name=f"Nombre{uid}", last_name=f"Apellido{uid}",
            role=role, is_active=True, can_login=can_login, created_at=now,
        )

    def _athlete(aid: int, user_id: int) -> Athlete:
        return Athlete(
            id=aid, user_id=user_id, first_name=f"Ficticio{aid}",
            last_name="Prueba", birth_date=date(2012, 1, 1), sex="M",
            club_id=1, created_by=10,
        )

    session.add_all([
        _user(10, UserRole.coach),
        _user(5, UserRole.parent),
        _user(6, UserRole.parent),
        _user(7, UserRole.parent),  # parent with no linked children
        _user(20, UserRole.parent, can_login=False),
        _user(21, UserRole.parent, can_login=False),
        _user(22, UserRole.parent, can_login=False),
        Club(id=1, name="Club Ficticio", code="FIC"),
    ])
    await session.flush()
    session.add_all([
        _athlete(1, 20), _athlete(2, 21), _athlete(3, 22),
        RaceSeries(
            id=1, name="Copa Valle", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        ),
        RaceCategory(id=1, code="INF_M", label="Infantil Masculino",
                     sex=CategoryGender.M, sort_order=10, is_active=True),
        RaceCategory(id=2, code="INF_F", label="Infantil Femenino",
                     sex=CategoryGender.F, sort_order=11, is_active=True),
    ])
    await session.flush()
    session.add_all([
        ParentAthlete(id=1, parent_id=5, athlete_id=1, relationship_type="padre"),
        ParentAthlete(id=2, parent_id=5, athlete_id=3, relationship_type="padre"),
        ParentAthlete(id=3, parent_id=6, athlete_id=2, relationship_type="madre"),
        *[
            RaceEvent(
                id=eid, series_id=1, sequence_number=seq, name=f"VALIDA {seq}",
                event_date=date(2026, 5, 17), location="Cali",
                is_championship=False, status=RaceEventStatus.COMPLETED,
                created_by_user_id=10,
            )
            for eid, seq in ((100, 4), (101, 5))
        ],
    ])
    await session.flush()

    club_athlete = {_COMP_LEADER: 1, _COMP_SECOND: 2, _COMP_SMALL_FIELD: 3}
    for cid in range(1, 13):
        aid = club_athlete.get(cid)
        rival = _RIVAL_NAMES[cid % len(_RIVAL_NAMES)]
        session.add(
            RaceCompetitor(
                id=cid,
                normalized_name=f"competidor {cid}",
                display_name=f"Ficticio {rival} {cid}" if aid is None else f"Atleta Club {cid}",
                club_text="Club X" if aid is None else "Club Ficticio",
                athlete_id=aid,
            )
        )
    await session.flush()

    # INF_M (category 1): times 200/205/210/220/230/240 s → 6 timed finishers.
    inf_m_times = [200_000, 205_000, 210_000, 220_000, 230_000, 240_000]
    for pos, t in enumerate(inf_m_times, start=1):
        session.add(_result(100, 1, pos, position=pos, race_time_ms=t,
                            athlete_id=club_athlete.get(pos)))
    # DB constraint: only ``finished`` rows may carry a time.
    session.add(_result(100, 1, _COMP_MINUS_LAPS, position=7,
                        status=ResultStatus.MINUS_LAPS, laps_behind=1))
    session.add(_result(100, 1, _COMP_DNF, position=None, status=ResultStatus.DNF))

    # INF_F (category 2): only 4 timed finishers (< MIN_FIELD).
    for pos, (cid, t) in enumerate(
        ((_COMP_SMALL_FIELD, 300_000), (10, 310_000), (11, 320_000), (12, 330_000)),
        start=1,
    ):
        session.add(_result(100, 2, cid, position=pos, race_time_ms=t,
                            athlete_id=3 if cid == _COMP_SMALL_FIELD else None))

    # Event 101: a single result (baseline for the query-count comparison).
    session.add(_result(101, 1, 3, position=1, race_time_ms=250_000))
    await session.commit()


@pytest_asyncio.fixture
async def seeded(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        await _seed(s)


def _override_db(factory: async_sessionmaker[AsyncSession]):
    async def _dep():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _dep


async def _get(
    factory: async_sessionmaker[AsyncSession],
    role: UserRole,
    user_id: int,
    event_id: int = 100,
    **params: Any,
) -> dict[str, Any]:
    app.dependency_overrides[get_db] = _override_db(factory)
    app.dependency_overrides[get_current_user] = lambda: _fake_user(role, user_id)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(_URL.format(event_id=event_id), params=params)
        assert resp.status_code == 200, resp.text
        return {"json": resp.json(), "text": resp.text}
    finally:
        app.dependency_overrides.clear()


def _row(payload: dict[str, Any], competitor_id: int) -> dict[str, Any]:
    for category in payload["categories"]:
        for row in category["rows"]:
            if row["competitor_id"] == competitor_id:
                return row
    raise AssertionError(f"competitor {competitor_id} not in payload")


# ---------------------------------------------------------------------------
# Coach payload
# ---------------------------------------------------------------------------


class TestCoachMetrics:
    @pytest.mark.asyncio
    async def test_coach_row_carries_every_metric_field(self, factory, seeded):
        payload = (await _get(factory, UserRole.coach, 10))["json"]

        metrics = _row(payload, _COMP_LEADER)["metrics"]

        assert set(metrics) == _FAMILY_KEYS | _COACH_ONLY_KEYS

    @pytest.mark.asyncio
    async def test_coach_leader_and_second_values(self, factory, seeded):
        payload = (await _get(factory, UserRole.coach, 10))["json"]

        leader = _row(payload, _COMP_LEADER)["metrics"]
        second = _row(payload, _COMP_SECOND)["metrics"]

        # Parrilla counts the MINUS_LAPS rider; timed_finishers does not.
        assert (leader["field_size"], leader["timed_finishers"]) == (7, 6)
        assert leader["position"] == 1
        assert leader["percentile"] == 100
        assert leader["gap_to_median_pct"] == -7.0  # (200 − 215) ÷ 215
        assert leader["gap_to_winner_pct"] == 0.0
        assert leader["gap_to_winner_ms"] == 0
        assert leader["gap_to_podium_pct"] == -4.8  # (200 − 210) ÷ 210, P3 = 210 s
        assert leader["gap_to_podium_ms"] == -10_000

        assert second["position"] == 2
        assert second["percentile"] == 88  # 100 × (1 − 5 ÷ 40) = 87.5
        assert second["gap_to_winner_pct"] == 2.5
        assert second["gap_to_winner_ms"] == 5_000

    @pytest.mark.asyncio
    async def test_minus_laps_and_dnf_rows_have_no_time_metrics(self, factory, seeded):
        payload = (await _get(factory, UserRole.coach, 10))["json"]

        minus_laps = _row(payload, _COMP_MINUS_LAPS)["metrics"]
        dnf = _row(payload, _COMP_DNF)["metrics"]

        # MINUS_LAPS finished the race (in Parrilla, has a position) but is
        # not time-comparable.
        assert (minus_laps["field_size"], minus_laps["timed_finishers"]) == (7, 6)
        assert minus_laps["position"] == 7
        assert minus_laps["percentile"] is None
        assert minus_laps["gap_to_median_pct"] is None
        # DNF: same category aggregates, nothing personal.
        assert (dnf["field_size"], dnf["timed_finishers"]) == (7, 6)
        assert dnf["position"] is None
        assert dnf["percentile"] is None
        assert dnf["gap_to_winner_pct"] is None

    @pytest.mark.asyncio
    async def test_small_field_gates_percentile_and_median_but_not_winner_gap(
        self, factory, seeded
    ):
        """4 timed finishers < MIN_FIELD: percentile / median gap → null, but
        the official winner gap has no size gate (research R-04)."""
        payload = (await _get(factory, UserRole.coach, 10))["json"]

        metrics = _row(payload, _COMP_SMALL_FIELD)["metrics"]

        assert (metrics["field_size"], metrics["timed_finishers"]) == (4, 4)
        assert metrics["percentile"] is None
        assert metrics["gap_to_median_pct"] is None
        assert metrics["gap_to_winner_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_club_only_filter_does_not_shrink_the_metric_field(
        self, factory, seeded
    ):
        """``club_only`` decides which rows are returned, not what the
        category looks like: Parrilla stays 7, not the number of club rows."""
        payload = (await _get(factory, UserRole.coach, 10, club_only="true"))["json"]

        rows = [r for c in payload["categories"] for r in c["rows"]]
        assert rows and all(r["is_our_club"] for r in rows)
        leader = _row(payload, _COMP_LEADER)["metrics"]
        assert (leader["field_size"], leader["timed_finishers"]) == (7, 6)
        assert leader["percentile"] == 100


# ---------------------------------------------------------------------------
# Parent payload
# ---------------------------------------------------------------------------


class TestParentMetrics:
    @pytest.mark.asyncio
    async def test_parent_gets_only_the_family_fields(self, factory, seeded):
        result = await _get(factory, UserRole.parent, 5)

        metrics = _row(result["json"], _COMP_LEADER)["metrics"]

        assert set(metrics) == _FAMILY_KEYS
        # Excluded from the wire payload, not nulled: the keys are nowhere.
        for key in _COACH_ONLY_KEYS:
            assert key not in result["text"]

    @pytest.mark.asyncio
    async def test_parent_metrics_are_computed_over_the_whole_category(
        self, factory, seeded
    ):
        """Regression guard for the scoping pitfall: computing metrics over
        only the parent's rows would give ``field_size=1`` and no percentile."""
        payload = (await _get(factory, UserRole.parent, 5))["json"]

        metrics = _row(payload, _COMP_LEADER)["metrics"]

        assert (metrics["field_size"], metrics["timed_finishers"]) == (7, 6)
        assert metrics["position"] == 1
        assert metrics["percentile"] == 100
        assert metrics["gap_to_median_pct"] == -7.0

    @pytest.mark.asyncio
    async def test_parent_values_match_the_coach_values(self, factory, seeded):
        coach = (await _get(factory, UserRole.coach, 10))["json"]
        parent = (await _get(factory, UserRole.parent, 5))["json"]

        for comp_id in (_COMP_LEADER, _COMP_SMALL_FIELD):
            family = _row(parent, comp_id)["metrics"]
            full = _row(coach, comp_id)["metrics"]
            assert family == {k: full[k] for k in _FAMILY_KEYS}

    @pytest.mark.asyncio
    async def test_parent_only_sees_own_children_rows(self, factory, seeded):
        """Denied path: parent 6 (athlete 2) never receives athlete 1's row
        — nor any rival name — even though those rows fed the category
        metrics."""
        result = await _get(factory, UserRole.parent, 6)

        rows = [r for c in result["json"]["categories"] for r in c["rows"]]
        assert [r["competitor_id"] for r in rows] == [_COMP_SECOND]
        assert rows[0]["athlete_id"] == 2
        assert "Ficticio" not in result["text"].replace("Club Ficticio", "")
        assert "Atleta Club 1" not in result["text"]
        # …but their child's metrics still reflect the full category.
        assert rows[0]["metrics"]["field_size"] == 7

    @pytest.mark.asyncio
    async def test_parent_without_children_gets_no_rows(self, factory, seeded):
        payload = (await _get(factory, UserRole.parent, 7))["json"]

        assert payload["categories"] == []


# ---------------------------------------------------------------------------
# Service level: schema types + no per-row queries
# ---------------------------------------------------------------------------


class TestServiceLevel:
    @pytest.mark.asyncio
    async def test_metric_schema_type_follows_the_audience(self, factory, seeded):
        async with factory() as db:
            coach = await get_event_results(db, 100)
            parent = await get_event_results(db, 100, allowed_athlete_ids={1})

        assert coach is not None and parent is not None
        assert all(
            type(r.metrics) is CoachMetricSet
            for c in coach.categories
            for r in c.rows
        )
        assert all(
            type(r.metrics) is FamilyMetricSet
            for c in parent.categories
            for r in c.rows
        )

    def test_wire_schemas_agree_with_the_audience_policy(self):
        """Drift guard: ``audience.py`` decides what a family may see; the
        schemas only type it. If a metric is added to the engine, or the
        policy changes, the family schema must follow — otherwise a field
        would silently be missing for families, or leak."""
        engine_fields = set(MetricSet.__annotations__)

        assert set(CoachMetricSet.model_fields) == engine_fields
        assert set(FamilyMetricSet.model_fields) == (
            engine_fields - FAMILY_EXCLUDED_METRIC_FIELDS
        )
        # And the spec's data-model §1 columns, spelled out.
        assert set(FamilyMetricSet.model_fields) == _FAMILY_KEYS
        assert engine_fields - _FAMILY_KEYS == _COACH_ONLY_KEYS

    @pytest.mark.asyncio
    async def test_no_per_row_queries(self, engine, factory, seeded):
        """One statement budget regardless of rows: the 12-row / 2-category
        event costs exactly what the 1-row event costs, for coach and parent
        scope alike (event check + course setups + results)."""
        async with factory() as db:
            async with count_selects(engine) as one_row:
                await get_event_results(db, 101)
            async with count_selects(engine) as many_rows:
                await get_event_results(db, 100)
            async with count_selects(engine) as parent_scope:
                await get_event_results(db, 100, allowed_athlete_ids={1, 3})

        assert many_rows[0] == one_row[0] <= 3
        assert parent_scope[0] == many_rows[0]
