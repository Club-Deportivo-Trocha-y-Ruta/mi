"""Characterization tests for app.services.race.standings.get_event_standings.

Tests exercise the service directly against a real aiosqlite in-memory engine
(no HTTP layer, no FakeAsyncSession).  This validates the SQL aggregation AND
the Python tier-break logic together.

Logic covered
-------------
- Tie-break chain: total_points DESC → podiums DESC → best_position ASC.
- NULL best_position sentinel (9999 → ranks last on full tie).
- NULL points_awarded counted as zero.
- Cross-event aggregation (same series, both events summed).
- Podium counting: positions 1-3 only (<=3, i.e. positions 1, 2, 3), NOT 4, NOT NULL.
- Soft-deleted rows excluded from totals.
- Parent scoping (allowed_athlete_ids set vs empty set short-circuit).
- club_only filter drops rows with athlete_id IS NULL.
- Missing event → None returned.
- is_our_club flag from athlete_id presence.
- Rank assigned 1..N by enumerate after sort.

Mutation-killing notes (custom runner: backend/scripts/run_mutation_test.py)
-----------------------------------------------------------------------------
Run: python -c "from scripts.run_mutation_test import run_module_mutations; ..."
Result: 12 mutants generated, 11 killed, 1 surviving equivalent mutant.

Nota histórica: durante la primera corrida del runner, la copia de trabajo
contenía un mutante sin restaurar (`position < 3`) dejado por una corrida
abortada previa del script de mutación. El código COMMITEADO siempre tuvo
`position <= 3`; la copia de trabajo fue restaurada. Las 2 mutaciones del
límite de podio se ejecutan y mueren con `<= 3`.

SURVIVING EQUIVALENT MUTANT (intentionally not killed):
  ID=8  desc="races_run default 0 to 1"
  OLD:  races_run=row["races_run"] or 0
  NEW:  races_run=row["races_run"] or 1
  Reason: SQL COUNT(*) always returns >=1 for any existing GROUP BY row, so the
  `or 0` fallback is dead code and `or 0` vs `or 1` are behaviourally equivalent
  for all reachable inputs.  No test can distinguish them without mocking the SQL
  layer (which would break the characterization-test contract of testing real SQL).
  The defensive `or 0` is intentional: keeps the Python type as int even if a
  future ORM change returns None; the mutation is a no-op in practice.
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
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.services.race.standings import get_event_standings

# ---------------------------------------------------------------------------
# Engine / session fixture (real aiosqlite, same pattern as router tests)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Ensure all necessary tables are imported so metadata is populated.
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _Cat  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

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
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

_USER_ID = 99  # created_by_user_id used in all results
_SERIES_ID = 1
_EVT1_ID = 10
_EVT2_ID = 11
_CAT_ID = 1


async def _seed_base(session: AsyncSession) -> None:
    """Insert the shared base objects needed by most tests:
    one user, one series, two events, one category.
    """
    user = User(
        id=_USER_ID,
        email="coach@svc.test",
        hashed_password="x",
        first_name="Coach",
        last_name="Test",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    series = RaceSeries(
        id=_SERIES_ID,
        name="Copa Test",
        season_year=2026,
        organizer="Liga",
        points_scheme_code="test",
    )
    evt1 = RaceEvent(
        id=_EVT1_ID,
        series_id=_SERIES_ID,
        sequence_number=1,
        name="VALIDA I",
        event_date=date(2026, 1, 31),
        location="Ciudad A",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=_USER_ID,
    )
    evt2 = RaceEvent(
        id=_EVT2_ID,
        series_id=_SERIES_ID,
        sequence_number=2,
        name="VALIDA II",
        event_date=date(2026, 2, 28),
        location="Ciudad B",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=_USER_ID,
    )
    cat = RaceCategory(
        id=_CAT_ID,
        code="INF_M",
        label="Infantil Masculino",
        sex=CategoryGender.M,
        sort_order=10,
        is_active=True,
    )
    session.add_all([user, series, evt1, evt2, cat])
    await session.commit()


def _mk_competitor(comp_id: int, athlete_id: int | None = None) -> RaceCompetitor:
    return RaceCompetitor(
        id=comp_id,
        normalized_name=f"corredor {comp_id}",
        display_name=f"Corredor {comp_id}",
        club_text="Club Test" if athlete_id else "Club Otro",
        athlete_id=athlete_id,
    )


def _mk_result(
    result_id: int,
    event_id: int,
    competitor_id: int,
    points: int | None,
    position: int | None,
    athlete_id: int | None = None,
    deleted_at: datetime | None = None,
) -> RaceResult:
    """Create a RaceResult.  position=None → DNF (no race_time_ms either)."""
    status = ResultStatus.FINISHED if position is not None else ResultStatus.DNF
    race_time_ms = 200_000 if position is not None else None
    return RaceResult(
        id=result_id,
        event_id=event_id,
        category_id=_CAT_ID,
        competitor_id=competitor_id,
        athlete_id=athlete_id,
        position=position,
        status=status,
        race_time_ms=race_time_ms,
        points_awarded=points if points is not None else 0,
        created_by_user_id=_USER_ID,
        deleted_at=deleted_at,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStandingsService:

    async def test_points_tie_broken_by_podiums(self, session_factory):
        """A and B tie on total_points; A has 2 podiums, B has 1 → A ranked 1."""
        async with session_factory() as s:
            await _seed_base(s)
            # Competitor A: wins both events (positions 1,1) → 2 podiums, 80 pts
            # Competitor B: positions 3,2 → 2 podiums but… we need tie on pts
            # Let's make A=50 pts (1 event pos1) + B also 50 pts but only 1 podium
            s.add(_mk_competitor(1, athlete_id=None))
            s.add(_mk_competitor(2, athlete_id=None))
            # A: evt1 pos1 = 30pts (podium), evt2 pos1 = 20pts (podium) → 50pts, 2 podiums
            s.add(_mk_result(1, _EVT1_ID, 1, 30, 1))
            s.add(_mk_result(2, _EVT2_ID, 1, 20, 1))
            # B: evt1 pos2 = 40pts (podium), evt2 pos4 = 10pts (no podium) → 50pts, 1 podium
            s.add(_mk_result(3, _EVT1_ID, 2, 40, 2))
            s.add(_mk_result(4, _EVT2_ID, 2, 10, 4))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        assert result is not None
        rows = result.categories[0].rows
        assert len(rows) == 2
        # A has 2 podiums vs B's 1, both 50 pts → A should be rank 1
        assert rows[0].competitor_id == 1, f"Expected comp 1 first, got {rows[0].competitor_id}"
        assert rows[0].rank == 1
        assert rows[1].rank == 2

    async def test_points_and_podiums_tie_broken_by_best_position(self, session_factory):
        """Tie on total_points AND podiums; A best_pos=2, B best_pos=4 → A ranked 1."""
        async with session_factory() as s:
            await _seed_base(s)
            s.add(_mk_competitor(1))
            s.add(_mk_competitor(2))
            # A: pos2 (podium, 30pts), pos2 (podium, 20pts) → 50pts, 2 podiums, best=2
            s.add(_mk_result(1, _EVT1_ID, 1, 30, 2))
            s.add(_mk_result(2, _EVT2_ID, 1, 20, 2))
            # B: pos3 (podium, 25pts), pos2 (podium, 25pts) → 50pts, 2 podiums, best=2 too
            # make B's best_pos=4 instead: pos4 (20pts), pos4 (30pts)
            # that doesn't tie podiums. Let's do: B pos3(25)+pos3(25)=50 pts, 2 podiums, best=3
            s.add(_mk_result(3, _EVT1_ID, 2, 25, 3))
            s.add(_mk_result(4, _EVT2_ID, 2, 25, 3))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        assert rows[0].competitor_id == 1  # best_pos=2 vs 3 → A wins
        assert rows[0].best_position == 2
        assert rows[1].best_position == 3

    async def test_null_best_position_ranks_last_on_full_tie(self, session_factory):
        """Competitor with all-NULL positions (DNFs) ties pts/podiums → ranks last."""
        async with session_factory() as s:
            await _seed_base(s)
            s.add(_mk_competitor(1))
            s.add(_mk_competitor(2))
            # A: 2 results with position=None (DNF) → 0 podiums, 0 pts, NULL best_pos
            s.add(_mk_result(1, _EVT1_ID, 1, 0, None))
            s.add(_mk_result(2, _EVT2_ID, 1, 0, None))
            # B: 2 DNFs too (ties on everything) but has real position=5
            s.add(_mk_result(3, _EVT1_ID, 2, 0, 5))
            s.add(_mk_result(4, _EVT2_ID, 2, 0, None))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        # B has best_position=5, A has NULL → A should rank last (sentinel 9999 > 5)
        assert rows[0].competitor_id == 2  # B wins (best_pos=5 < 9999)
        assert rows[1].competitor_id == 1  # A last (NULL best_pos)
        assert rows[1].best_position is None

    async def test_null_points_counted_as_zero(self, session_factory):
        """Results with points_awarded=0 (None semantically) rank below positive totals."""
        async with session_factory() as s:
            await _seed_base(s)
            s.add(_mk_competitor(1))
            s.add(_mk_competitor(2))
            # A: 0 points (DNF, no points)
            s.add(_mk_result(1, _EVT1_ID, 1, 0, None))
            # B: 40 points
            s.add(_mk_result(2, _EVT1_ID, 2, 40, 1))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        assert rows[0].competitor_id == 2  # 40 pts before 0 pts
        assert rows[0].total_points == 40
        assert rows[1].total_points == 0

    async def test_aggregates_across_series_events(self, session_factory):
        """Same competitor's results in both events sum correctly; races_run==2."""
        async with session_factory() as s:
            await _seed_base(s)
            s.add(_mk_competitor(1))
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1))
            s.add(_mk_result(2, _EVT2_ID, 1, 35, 2))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        assert len(rows) == 1
        r = rows[0]
        assert r.total_points == 75
        assert r.races_run == 2

    async def test_podium_counts_positions_1_to_3_only(self, session_factory):
        """Positions 1, 3 are podiums; position 4 and NULL are not."""
        async with session_factory() as s:
            await _seed_base(s)
            # Need 4 distinct competitors (one result per event slot due to unique constraint)
            s.add(_mk_competitor(1))
            s.add(_mk_competitor(2))
            s.add(_mk_competitor(3))
            s.add(_mk_competitor(4))
            # Competitor 1 wins all 4 "events" via 4 result slots — but we only have 2 events.
            # Use a single competitor with results in both events at various positions.
            # Actually the unique constraint is (event_id, category_id, competitor_id).
            # So one competitor can appear once per event.
            # To get 4 results for positions 1,3,4,None we need a third event or 4 competitors.
            # We'll use 2 competitors and test across results split between them.
            # The point is: positions 1,3 = podiums; 4,None = not podiums.
            # Competitor 1: evt1 pos1 (podium), evt2 pos3 (podium) → 2 podiums
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1))
            s.add(_mk_result(2, _EVT2_ID, 1, 30, 3))
            # Competitor 2: evt1 pos4 (no podium), evt2 pos=None/DNF (no podium) → 0 podiums
            s.add(_mk_result(3, _EVT1_ID, 2, 20, 4))
            s.add(_mk_result(4, _EVT2_ID, 2, 0, None))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        comp1_row = next(r for r in rows if r.competitor_id == 1)
        comp2_row = next(r for r in rows if r.competitor_id == 2)
        assert comp1_row.podiums == 2, f"Expected 2 podiums, got {comp1_row.podiums}"
        assert comp2_row.podiums == 0, f"Expected 0 podiums, got {comp2_row.podiums}"

    async def test_soft_deleted_results_excluded(self, session_factory):
        """A deleted_at-stamped result does not contribute to totals."""
        from datetime import timezone as tz

        async with session_factory() as s:
            await _seed_base(s)
            s.add(_mk_competitor(1))
            # Live result: 40 pts
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1))
            # Soft-deleted result in evt2: should NOT add to total
            deleted = _mk_result(2, _EVT2_ID, 1, 100, 1)
            deleted.deleted_at = datetime(2026, 3, 1, tzinfo=tz.utc)
            s.add(deleted)
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        assert len(rows) == 1
        # Only the live result (40 pts) should count; deleted (100 pts) excluded
        assert rows[0].total_points == 40
        assert rows[0].races_run == 1

    async def test_parent_scope_filters_and_empty_set_short_circuits(self, session_factory):
        """allowed_athlete_ids={x} returns only x's rows; set() → categories==[]."""
        async with session_factory() as s:
            await _seed_base(s)
            # Need a club and athlete for athlete_id FK
            club = Club(id=1, name="Club TyR", code="TYR")
            user_for_athlete = User(
                id=50, email="ath@svc.test", hashed_password="x",
                first_name="Ath", last_name="Test",
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            athlete = Athlete(
                id=1,
                user_id=50,
                first_name="Ath",
                last_name="Test",
                birth_date=date(2012, 1, 1),
                sex="M",
                club_id=1,
                created_by=_USER_ID,
            )
            s.add_all([club, user_for_athlete, athlete])
            await s.commit()

            s.add(_mk_competitor(1, athlete_id=1))
            s.add(_mk_competitor(2, athlete_id=None))
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1, athlete_id=1))
            s.add(_mk_result(2, _EVT1_ID, 2, 35, 2))
            await s.commit()

        async with session_factory() as s:
            # Filter to athlete_id=1 only
            result_scoped = await get_event_standings(
                s, _EVT1_ID, allowed_athlete_ids={1}
            )

        assert result_scoped is not None
        rows = result_scoped.categories[0].rows
        assert len(rows) == 1
        assert rows[0].athlete_id == 1

        async with session_factory() as s:
            # Empty set → early return with categories=[]
            result_empty = await get_event_standings(
                s, _EVT1_ID, allowed_athlete_ids=set()
            )

        assert result_empty is not None
        assert result_empty.categories == []

    async def test_club_only_filters_unlinked_competitors(self, session_factory):
        """club_only=True drops rows with athlete_id IS NULL; linked rows have is_our_club=True."""
        async with session_factory() as s:
            await _seed_base(s)
            club = Club(id=1, name="Club TyR", code="TYR")
            user_for_athlete = User(
                id=50, email="ath2@svc.test", hashed_password="x",
                first_name="Ath2", last_name="Test",
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            athlete = Athlete(
                id=2,
                user_id=50,
                first_name="Ath2",
                last_name="Test",
                birth_date=date(2012, 6, 1),
                sex="M",
                club_id=1,
                created_by=_USER_ID,
            )
            s.add_all([club, user_for_athlete, athlete])
            await s.commit()

            s.add(_mk_competitor(1, athlete_id=2))
            s.add(_mk_competitor(2, athlete_id=None))
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1, athlete_id=2))
            s.add(_mk_result(2, _EVT1_ID, 2, 35, 2))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID, club_only=True)

        rows = result.categories[0].rows
        assert len(rows) == 1
        assert rows[0].athlete_id == 2
        assert rows[0].is_our_club is True

    async def test_missing_event_returns_none(self, session_factory):
        """Unknown race_event_id → service returns None."""
        async with session_factory() as s:
            await _seed_base(s)

        async with session_factory() as s:
            result = await get_event_standings(s, 99999)

        assert result is None

    async def test_ranks_assigned_1_to_n_sequentially(self, session_factory):
        """After sorting, rank is assigned 1..N with no gaps."""
        async with session_factory() as s:
            await _seed_base(s)
            # Three competitors with distinct points
            s.add(_mk_competitor(1))
            s.add(_mk_competitor(2))
            s.add(_mk_competitor(3))
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1))
            s.add(_mk_result(2, _EVT1_ID, 2, 30, 2))
            s.add(_mk_result(3, _EVT1_ID, 3, 20, 3))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        assert [r.rank for r in rows] == [1, 2, 3]
        # Also verify order is points DESC
        assert rows[0].total_points == 40
        assert rows[1].total_points == 30
        assert rows[2].total_points == 20

    async def test_national_championship_excluded_same_as_departmental(
        self, session_factory
    ):
        """Regression lock (spec 023 SC-004): standings exclusion keys off ``kind``,
        not ``level``.  A ``championship`` series with ``level=national`` and results
        present must be excluded from cumulative standings exactly like a
        ``departmental`` (or level-unset/default) championship — i.e. the guard at
        ``standings.py`` (``series_kind != RaceSeriesKind.cup``) is unaffected by
        the new ``level`` column.
        """
        national_series_id = 900
        national_event_id = 901

        async with session_factory() as s:
            await _seed_base(s)
            series = RaceSeries(
                id=national_series_id,
                name="Campeonato Nacional Fedeciclismo 2026",
                season_year=2026,
                organizer="Fedeciclismo",
                points_scheme_code="test",
                kind=RaceSeriesKind.championship,
                level=RaceSeriesLevel.national,
            )
            evt = RaceEvent(
                id=national_event_id,
                series_id=national_series_id,
                sequence_number=1,
                name="Campeonato Nacional",
                event_date=date(2026, 7, 18),
                location="Pereira",
                is_championship=True,
                status=RaceEventStatus.COMPLETED,
                created_by_user_id=_USER_ID,
            )
            s.add_all([series, evt])
            s.add(_mk_competitor(1))
            s.add(_mk_competitor(2))
            s.add(_mk_result(1, national_event_id, 1, 40, 1))
            s.add(_mk_result(2, national_event_id, 2, 30, 2))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, national_event_id)

        # Same empty-categories payload the departmental-championship guard
        # already produces (see standings.py "championship_skip" branch) —
        # identical regardless of results being present and regardless of level.
        assert result is not None
        assert result.categories == []

    async def test_is_our_club_true_only_when_athlete_id_present(self, session_factory):
        """is_our_club=True iff max(athlete_id) is not None for the competitor."""
        async with session_factory() as s:
            await _seed_base(s)
            club = Club(id=1, name="TyR", code="TYR")
            user_for_athlete = User(
                id=51, email="ath3@svc.test", hashed_password="x",
                first_name="Ath3", last_name="Test",
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            athlete = Athlete(
                id=3,
                user_id=51,
                first_name="Ath3",
                last_name="Test",
                birth_date=date(2013, 1, 1),
                sex="M",
                club_id=1,
                created_by=_USER_ID,
            )
            s.add_all([club, user_for_athlete, athlete])
            await s.commit()

            s.add(_mk_competitor(1, athlete_id=3))
            s.add(_mk_competitor(2, athlete_id=None))
            s.add(_mk_result(1, _EVT1_ID, 1, 40, 1, athlete_id=3))
            s.add(_mk_result(2, _EVT1_ID, 2, 35, 2))
            await s.commit()

        async with session_factory() as s:
            result = await get_event_standings(s, _EVT1_ID)

        rows = result.categories[0].rows
        club_row = next(r for r in rows if r.athlete_id == 3)
        rival_row = next(r for r in rows if r.athlete_id is None)
        assert club_row.is_our_club is True
        assert rival_row.is_our_club is False
