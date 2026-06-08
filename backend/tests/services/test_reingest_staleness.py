"""Tests for FR-018: re-ingestion staleness marking (PR5 / Wave D / US4).

Scenarios (T038):
A) Changed-SHA revision → IngestReport.is_revision=True + invalidate_runs_for_event
   marks stale_since on agent_runs and marks sent newsletters as outdated.
B) Identical-SHA re-ingest → no-op: is_revision=False, nothing marked stale.
C) No automatic re-run or resend: no AgentRun created, no newsletter sent by
   the invalidation path.

Test structure:
- Part 1 (FakeAsyncSession): narrow unit tests on the ingestor to verify
  IngestReport.is_revision flag under various SHA scenarios.  Uses the
  existing FakeAsyncSession fixture pattern from tests/services/race/conftest.py.
- Part 2 (aiosqlite): integration tests that exercise the full chain
  invalidate_runs_for_event(db, event_id) and confirm the DB state.
  Follows the pattern established in tests/services/race/test_run_staleness.py.

Privacy: no athlete names in log assertions; all IDs only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from itertools import count
from typing import Any, AsyncGenerator, Optional

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.models.user import UserRole
from app.schemas.race import EventMeta
from app.services.race.ingestor import RaceIngestor
from app.services.race.run_staleness import invalidate_runs_for_event

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _meta(valida_num: int = 4, season: int = 2026) -> EventMeta:
    return EventMeta(
        season=season,
        copa_code="copa_valle",
        valida_num=valida_num,
        name=f"VALIDA {valida_num} TEST",
        event_date=date(2026, 5, 17),
        location="CALI",
    )


def _results_one_row(bib: str = "401", time: str = "0:33:00") -> dict:
    """Minimal results dict with a single category / single row."""
    from app.services.race.pdf_parser import ResultsRow

    return {
        "INF_A": [
            ResultsRow(
                position=1,
                bib=bib,
                name="Corredor Prueba",
                city="Cali",
                club="Club Otro",
                time_raw=time,
                points=40,
            )
        ]
    }


# ===========================================================================
# Part 1 — FakeAsyncSession: IngestReport.is_revision flag
# ===========================================================================


@dataclass
class _Store:
    """Minimal in-memory store for the FakeAsyncSession used in Part 1."""

    series: dict[int, RaceSeries] = field(default_factory=dict)
    events: dict[int, RaceEvent] = field(default_factory=dict)
    categories: dict[int, RaceCategory] = field(default_factory=dict)
    competitors: dict[int, RaceCompetitor] = field(default_factory=dict)
    results: dict[int, RaceResult] = field(default_factory=dict)
    imports: dict[int, RaceImport] = field(default_factory=dict)
    pending: list[Any] = field(default_factory=list)
    snapshot: Optional[dict[str, dict]] = None
    _id_counters: dict[str, Any] = field(
        default_factory=lambda: {
            "series": count(1),
            "events": count(1),
            "categories": count(1),
            "competitors": count(1),
            "results": count(1),
            "imports": count(1),
        }
    )

    def next_id(self, table: str) -> int:
        return next(self._id_counters[table])

    def table_for(self, obj: Any) -> str:
        if isinstance(obj, RaceSeries):
            return "series"
        if isinstance(obj, RaceEvent):
            return "events"
        if isinstance(obj, RaceCategory):
            return "categories"
        if isinstance(obj, RaceCompetitor):
            return "competitors"
        if isinstance(obj, RaceResult):
            return "results"
        if isinstance(obj, RaceImport):
            return "imports"
        raise RuntimeError(f"FakeSession: type not supported {type(obj)!r}")

    def get_table_dict(self, table: str) -> dict:
        return getattr(self, table)


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Optional[Any]:
        if not self._rows:
            return None
        if len(self._rows) > 1:
            raise RuntimeError(f"scalar_one_or_none: got {len(self._rows)} rows")
        return self._rows[0]

    def scalars(self) -> "_FakeScalars":
        return _FakeScalars(self._rows)


class _FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Optional[Any]:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Minimal AsyncSession fake for Part 1 ingestor unit tests.

    Supports exactly the queries RaceIngestor issues, including the new
    _find_any_committed_import_for_event (WHERE event_id=X AND status=committed).
    """

    def __init__(self, store: Optional[_Store] = None) -> None:
        self.store = store or _Store()
        self._snapshot()

    def _snapshot(self) -> None:
        self.store.snapshot = {
            "series": dict(self.store.series),
            "events": dict(self.store.events),
            "categories": dict(self.store.categories),
            "competitors": dict(self.store.competitors),
            "results": dict(self.store.results),
            "imports": dict(self.store.imports),
        }

    async def execute(self, stmt: Any) -> _FakeResult:
        return _FakeResult(self._eval(stmt))

    def _eval(self, stmt: Any) -> list[Any]:
        from sqlalchemy.sql.selectable import Select

        if not isinstance(stmt, Select):
            raise RuntimeError(f"FakeSession: unsupported stmt {type(stmt)!r}")

        cols = stmt.selected_columns
        froms = list(stmt.get_final_froms())
        if not froms:
            raise RuntimeError("FakeSession: select without FROM")
        from_table = froms[0].name

        table_map = {
            "race_series": self.store.series,
            "race_events": self.store.events,
            "race_categories": self.store.categories,
            "race_competitors": self.store.competitors,
            "race_results": self.store.results,
            "race_imports": self.store.imports,
        }
        if from_table not in table_map:
            raise RuntimeError(f"FakeSession: unknown table {from_table!r}")
        store_dict = table_map[from_table]

        rows = list(store_dict.values())
        if stmt.whereclause is not None:
            rows = [r for r in rows if self._match(r, stmt.whereclause)]

        # Scalar projection: select(RaceResult.competitor_id)
        col_list = list(cols)
        if len(col_list) == 1 and col_list[0].name == "competitor_id":
            return [r.competitor_id for r in rows]

        return rows

    def _match(self, row: Any, clause: Any) -> bool:
        from sqlalchemy.sql import operators
        from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

        if isinstance(clause, BooleanClauseList):
            if clause.operator is operators.and_:
                return all(self._match(row, c) for c in clause.clauses)
            if clause.operator is operators.or_:
                return any(self._match(row, c) for c in clause.clauses)
            raise RuntimeError(f"FakeSession: unsupported boolean op {clause.operator}")

        if isinstance(clause, BinaryExpression):
            left = clause.left
            right = clause.right
            op = clause.operator
            if op is operators.eq:
                col_name = getattr(left, "name", None) or getattr(left, "key", None)
                if col_name is None:
                    raise RuntimeError(f"FakeSession: left without name: {left!r}")
                right_val = getattr(right, "value", right)
                lhs = getattr(row, col_name, None)
                # Handle str-enum comparison
                if hasattr(lhs, "value") and isinstance(right_val, str):
                    return lhs.value == right_val or lhs == right_val
                return lhs == right_val
            raise RuntimeError(f"FakeSession: unsupported op {op!r}")

        raise RuntimeError(f"FakeSession: unsupported clause {type(clause)!r}")

    def add(self, obj: Any) -> None:
        self.store.pending.append(obj)

    async def flush(self) -> None:
        for obj in list(self.store.pending):
            table = self.store.table_for(obj)
            if getattr(obj, "id", None) is None:
                obj.id = self.store.next_id(table)
            self.store.get_table_dict(table)[obj.id] = obj
        self.store.pending.clear()

    async def commit(self) -> None:
        await self.flush()
        self._snapshot()

    async def rollback(self) -> None:
        snap = self.store.snapshot or {}
        self.store.series = dict(snap.get("series", {}))
        self.store.events = dict(snap.get("events", {}))
        self.store.categories = dict(snap.get("categories", {}))
        self.store.competitors = dict(snap.get("competitors", {}))
        self.store.results = dict(snap.get("results", {}))
        self.store.imports = dict(snap.get("imports", {}))
        self.store.pending.clear()


def _seeded_fake_store() -> _Store:
    """Store with one RaceCategory (INF_A) ready for the ingestor."""
    store = _Store()
    cat = RaceCategory(
        id=store.next_id("categories"),
        code="INF_A",
        label="Infantil A",
        sex=CategoryGender.M,
        age_min=9,
        age_max=10,
        tier=CategoryTier.menores,
        sort_order=30,
        is_active=True,
    )
    store.categories[cat.id] = cat
    return store


@pytest.fixture
def fake_session() -> _FakeSession:
    return _FakeSession(store=_seeded_fake_store())


class TestIngestReportIsRevisionFlag:
    """Unit tests for IngestReport.is_revision via FakeAsyncSession."""

    @pytest.mark.asyncio
    async def test_first_ingest_is_not_revision(self, fake_session: _FakeSession) -> None:
        """First-ever ingest for an event: is_revision must be False."""
        ingestor = RaceIngestor(fake_session)
        report = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(),
            pdf_results_sha256="a" * 64,
            ingested_by_user_id=1,
        )
        assert report.is_revision is False
        assert report.results_inserted == 1

    @pytest.mark.asyncio
    async def test_identical_sha_reingest_is_not_revision(
        self, fake_session: _FakeSession
    ) -> None:
        """Identical-SHA re-ingest: no-op per FR-017, is_revision must be False."""
        sha = "b" * 64
        ingestor = RaceIngestor(fake_session)

        # First commit
        r1 = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(),
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
        )
        assert r1.results_inserted == 1
        assert r1.is_revision is False

        # Second attempt with same SHA → idempotent abort
        r2 = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(),
            pdf_results_sha256=sha,
            ingested_by_user_id=1,
        )
        assert r2.results_inserted == 0
        assert r2.is_revision is False
        assert any("sha256 ya commiteado" in w for w in r2.warnings)

    @pytest.mark.asyncio
    async def test_changed_sha_revision_sets_is_revision_true(
        self, fake_session: _FakeSession
    ) -> None:
        """Different-SHA for same event (revision): is_revision must be True.

        Strategy: pre-seed a committed RaceImport with event_id=1 (the id that
        the FakeSession will assign to the first RaceEvent it creates).  When the
        ingestor upserts that same event (same series + valida_num) and finds the
        prior committed import, it sets is_revision=True.
        """
        sha_old = "c" * 64
        sha_new = "d" * 64

        # First ingest (establishes the event and import)
        ingestor = RaceIngestor(fake_session)
        r1 = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(),
            pdf_results_sha256=sha_old,
            ingested_by_user_id=1,
        )
        assert r1.is_revision is False
        event_id_first = r1.event_id

        # Manually set event_id on the committed import so the revision detector
        # can find it (the router sets this in production; FakeSession does not).
        for imp in fake_session.store.imports.values():
            if imp.sha256 == sha_old and imp.status == RaceImportStatus.committed:
                imp.event_id = event_id_first
                break

        # Second ingest with a DIFFERENT SHA for the same event
        r2 = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(bib="402"),
            pdf_results_sha256=sha_new,
            ingested_by_user_id=1,
        )
        assert r2.is_revision is True
        assert r2.event_id == event_id_first

    @pytest.mark.asyncio
    async def test_is_revision_false_in_dry_run(
        self, fake_session: _FakeSession
    ) -> None:
        """dry_run=True never sets is_revision (D5: no auto side-effects)."""
        sha_old = "e" * 64
        sha_new = "f" * 64

        ingestor = RaceIngestor(fake_session)
        r1 = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(),
            pdf_results_sha256=sha_old,
            ingested_by_user_id=1,
        )
        assert r1.is_revision is False
        event_id_first = r1.event_id

        for imp in fake_session.store.imports.values():
            if imp.sha256 == sha_old and imp.status == RaceImportStatus.committed:
                imp.event_id = event_id_first
                break

        # dry_run: should NOT set is_revision even if a prior committed exists
        r_dry = await ingestor.ingest_event(
            meta=_meta(),
            results_by_category=_results_one_row(bib="403"),
            pdf_results_sha256=sha_new,
            ingested_by_user_id=1,
            dry_run=True,
        )
        assert r_dry.is_revision is False
        assert any("DRY_RUN" in w for w in r_dry.warnings)


# ===========================================================================
# Part 2 — aiosqlite: full chain invalidate_runs_for_event (service tests)
# ===========================================================================
#
# These tests mirror test_run_staleness.py patterns to verify that the
# invalidate_runs_for_event service correctly:
# (a) sets stale_since on affected AgentRuns
# (b) marks sent newsletters as NewsletterStatus.outdated
# (c) does NOT create new runs or resend newsletters (no-auto-rerun / D5)

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
    "athlete_ai_insights",
    "agent_runs",
    "athlete_monthly_newsletters",
]


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
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_revision(session_factory: async_sessionmaker[AsyncSession]):
    """Scenario: event 7 has an AI run with an insight, plus a sent newsletter.

    This mirrors a state where:
    - A round was ingested (event_id=7)
    - An AI analysis run was completed (AgentRun id=10)
    - An insight was generated linking the run to event 7 (athlete 200, season 2026)
    - A monthly newsletter was sent to the parent
    After a revision re-ingest over event 7, the run and newsletter must be
    marked stale/outdated respectively.
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, name="TyR", code="tyr")
        await create_user(s, user_id=10, role=UserRole.coach, email="coach@test.com")
        await create_user(
            s, user_id=200, role=UserRole.athlete, can_login=False, email="a200@test.com"
        )
        await create_athlete(
            s, athlete_id=200, first_name="Atleta", last_name="Revision",
            club_id=1, user_id=200
        )
        await create_race_series(s, series_id=2, season_year=2026)
        await create_race_category(s, category_id=110, code="PJUV_A")
        await create_race_event(
            s, event_id=7, series_id=2, sequence_number=4,
            name="V4 Cali", event_date=date(2026, 5, 17), location="Cali"
        )
        await create_race_competitor(
            s, competitor_id=600, normalized_name="atleta revision",
            display_name="Atleta Revision", athlete_id=200
        )
        await create_race_result(
            s, event_id=7, category_id=110, competitor_id=600, athlete_id=200
        )

        # AgentRun completed (not stale yet)
        s.add(
            AgentRun(
                id=10,
                external_run_id="run-revision-test",
                graph_name="race-analyst",
                prompt_version="race_analyst_v2",
                started_at=_utcnow(),
                status=AgentRunStatus.completed,
                requested_by_user_id=10,
                athlete_id=200,
                checkpoint_thread_id="run-revision-test",
                stale_since=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        await s.flush()

        # Insight linking run 10 to event 7
        s.add(
            AthleteAiInsight(
                id=20,
                athlete_id=200,
                event_id=7,
                agent_run_id=10,
                generated_by_user_id=10,
                season=2026,
                valida_num=4,
                use_case="race_analysis_v2",
                summary_text="análisis prueba",
                recommendations_json=[],
                metrics_snapshot_json={},
                principles_cited_json=[],
                model="gemini",
                prompt_version="race_analyst_v2",
                coach_approved=True,
                generated_at=_utcnow(),
                is_active=1,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        # Sent newsletter for athlete 200, year 2026, month 5
        s.add(
            AthleteMonthlyNewsletter(
                id=30,
                athlete_id=200,
                year=2026,
                month=5,
                status=NewsletterStatus.sent,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        # Draft newsletter for a different month — must NOT be touched
        s.add(
            AthleteMonthlyNewsletter(
                id=31,
                athlete_id=200,
                year=2026,
                month=8,
                status=NewsletterStatus.draft,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        await s.commit()

    return session_factory


class TestRevisionStalenessChain:
    """Integration tests: invalidate_runs_for_event on a revision."""

    @pytest.mark.asyncio
    async def test_revision_marks_run_stale_and_newsletter_outdated(
        self, seeded_revision: async_sessionmaker[AsyncSession]
    ) -> None:
        """FR-018 core: confirmed revision triggers stale_since + outdated."""
        async with seeded_revision() as s:
            counts = await invalidate_runs_for_event(s, event_id=7)
            await s.commit()

        assert counts["runs_marked"] == 1
        assert counts["newsletters_outdated"] == 1

        async with seeded_revision() as s:
            run = await s.get(AgentRun, 10)
            assert run is not None
            assert run.stale_since is not None, "stale_since must be set after revision"

            nl_sent = await s.get(AthleteMonthlyNewsletter, 30)
            assert nl_sent is not None
            assert nl_sent.status == NewsletterStatus.outdated, (
                "sent newsletter must be marked outdated after revision"
            )

            nl_draft = await s.get(AthleteMonthlyNewsletter, 31)
            assert nl_draft is not None
            assert nl_draft.status == NewsletterStatus.draft, (
                "draft newsletter from a different month must NOT be touched"
            )

    @pytest.mark.asyncio
    async def test_revision_idempotent_no_double_marking(
        self, seeded_revision: async_sessionmaker[AsyncSession]
    ) -> None:
        """Calling invalidate_runs_for_event twice is idempotent (FR-017)."""
        async with seeded_revision() as s:
            await invalidate_runs_for_event(s, event_id=7)
            await s.commit()

        async with seeded_revision() as s:
            counts2 = await invalidate_runs_for_event(s, event_id=7)
            await s.commit()

        # Already stale → runs_marked=0 on second call
        assert counts2["runs_marked"] == 0

    @pytest.mark.asyncio
    async def test_no_auto_rerun_or_resend(
        self, seeded_revision: async_sessionmaker[AsyncSession]
    ) -> None:
        """D5 + D3: invalidate_runs_for_event must NOT create new runs or resend.

        After invalidation:
        - No new AgentRun rows must appear (D5: re-trigger is always manual).
        - Newsletter status is 'outdated', NOT 'sent' again (D3: no auto-resend).
        """
        from sqlalchemy import select as _select, func

        async with seeded_revision() as s:
            await invalidate_runs_for_event(s, event_id=7)
            await s.commit()

        async with seeded_revision() as s:
            # Count AgentRun rows — must still be exactly 1 (no new run created)
            run_count_result = await s.execute(
                _select(func.count()).select_from(AgentRun)
            )
            run_count = run_count_result.scalar()
            assert run_count == 1, "D5: no new AgentRun must be created automatically"

            # Newsletter status must be 'outdated', not re-sent
            nl = await s.get(AthleteMonthlyNewsletter, 30)
            assert nl is not None
            assert nl.status == NewsletterStatus.outdated
            assert nl.status != NewsletterStatus.sent

    @pytest.mark.asyncio
    async def test_event_with_no_runs_no_error(
        self, engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """invalidate_runs_for_event on an event with no AI insights is a no-op."""
        # Seed an event with no runs/insights
        async with session_factory() as s:
            await create_club(s, club_id=5, name="TyR5", code="tyr5")
            await create_user(s, user_id=50, role=UserRole.coach, email="coach5@test.com")
            await create_race_series(s, series_id=10, season_year=2026)
            await create_race_event(
                s, event_id=50, series_id=10, sequence_number=1,
                name="V1 Empty", event_date=date(2026, 1, 31), location="Sevilla",
                created_by_user_id=50,
            )
            await s.commit()

        async with session_factory() as s:
            counts = await invalidate_runs_for_event(s, event_id=50)
            await s.commit()

        assert counts["runs_marked"] == 0
        assert counts["newsletters_outdated"] == 0

    @pytest.mark.asyncio
    async def test_only_sent_newsletters_marked_outdated(
        self, seeded_revision: async_sessionmaker[AsyncSession]
    ) -> None:
        """Only newsletters in 'sent' status must be marked outdated (D3).

        draft / approved newsletters tied to the same athlete must remain
        untouched — they have not yet been delivered to parents.
        """
        async with seeded_revision() as s:
            await invalidate_runs_for_event(s, event_id=7)
            await s.commit()

        async with seeded_revision() as s:
            # draft newsletter (month 8) must still be draft
            nl_draft = await s.get(AthleteMonthlyNewsletter, 31)
            assert nl_draft is not None
            assert nl_draft.status == NewsletterStatus.draft
