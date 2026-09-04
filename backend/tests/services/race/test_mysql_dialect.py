"""MySQL 8.4 dialect test lane — wave 1 (raw-SQL divergence detection).

This module exercises the highest-risk raw-SQL (``text()``) call sites in the
race module against a *real* MySQL 8.4 instance.  It NEVER runs in the default
``pytest -q`` invocation — tests are gated behind the ``mysql`` marker.

How to run
----------
1. Start a throwaway MySQL 8.4 container::

       docker run -d --name mysql-plan005 \\
           -e MYSQL_ROOT_PASSWORD=testroot \\
           -e MYSQL_DATABASE=trocha_ruta_test \\
           -p 3306:3306 mysql:8.4

2. Wait for readiness::

       until docker exec mysql-plan005 mysqladmin ping -h 127.0.0.1 \\
           -uroot -ptestroot --silent 2>/dev/null; do sleep 2; done

3. Run the lane::

       TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
           pytest -m mysql -q

Safety rule
-----------
The ``mysql_engine`` fixture (defined in ``tests/conftest.py``) refuses to run
against a database whose name does NOT end with ``_test``.  This prevents
accidental writes to dev/prod data.

Session scope note
------------------
``mysql_session`` is session-scoped (one session for the whole test run) because
the ``mysql_engine`` is also session-scoped (single asyncio event loop).  A
per-function teardown ``rollback()`` would hit a "Task attached to a different
loop" error with aiomysql.  Tests therefore use unique integer ID prefixes to
avoid constraint collisions; all data is cleaned up when ``mysql_engine`` drops
all tables at teardown.

Modules still uncovered (wave 2+)
----------------------------------
- ``app/services/race/agents/analyst.py`` (5 raw-SQL sites)
- ``app/services/race/agents/chat.py`` (4 raw-SQL sites)
- ``app/services/race/agents/_llm.py`` (2 raw-SQL sites)
- ``app/services/race/ai/nodes/load_race_data.py`` (1 raw-SQL site)
- ``app/services/race/ai/nodes/budget_guard.py`` (1 raw-SQL site under ai/)

``build_evolution`` (feature 039, T018) now has its own case below —
verifica que los campos derivados de grupo de comparación
(``series_id``/``series_name``/``series_level``, ``groups``) sobrevivan al
dialecto MySQL, donde ``race_series.kind``/``level`` pueden volver como
string plano en vez del enum de Python (aiosqlite conserva el enum).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import pytest

from app.models.race_result import ResultStatus
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.models.user import UserRole
from app.schemas.athlete_race_analysis import EvolutionMetric
from app.services.race.ai.anonymizer import make_pseudonym
from app.services.race.ai.db import set_db_factory
from app.services.race.ai.nodes.recall_memory import recall_memory
from app.services.race.ai.nodes.rehydrate_names import _fetch_athlete_name
from app.services.race.analytics_charts import (
    _build_pseudonym,
    build_distribution,
    build_evolution,
)
from app.services.race.standings import get_event_standings
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)


# ---------------------------------------------------------------------------
# Helper: wire a session into the race-AI db_factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _db_factory_ctx(session):
    """Minimal async context manager wrapping a live session as db_factory."""
    yield session


# ---------------------------------------------------------------------------
# Test 1: recall_memory truncation and ordering on MySQL
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_recall_memory_truncates_long_summaries_mysql(mysql_session):
    """Summary texts > 500 chars must be truncated to exactly 500 by the node.

    This verifies that the Python-side truncation in recall_memory works
    correctly when the rows come back from a real MySQL TEXT column rather
    than the fake session.  Also validates that ORDER BY generated_at DESC
    produces the newest-first ordering MySQL guarantees.

    IDs: 501-502 (club/user/athlete prefix 5xx).
    """
    # Seed minimal required rows (athlete + user + club) so FK constraints pass.
    # IDs in the 5xx range for this test.
    await create_club(mysql_session, club_id=501, code="tyr501")
    await create_user(mysql_session, user_id=501, role=UserRole.coach)
    await create_user(mysql_session, user_id=502, role=UserRole.athlete, can_login=False)
    await create_athlete(mysql_session, athlete_id=501, club_id=501, user_id=502, created_by=501)
    await mysql_session.commit()

    short_text = "Corto resumen."
    long_text = "L" * 700  # deliberately > 500 chars

    t_old = datetime(2026, 1, 1, 10, 0, 0)
    t_new = datetime(2026, 3, 1, 10, 0, 0)

    await create_insight(
        mysql_session,
        athlete_id=501,
        summary_text=short_text,
        coach_approved=True,
        is_active=None,   # not-active sentinel (avoid unique conflict with valida 2)
        generated_at=t_old,
        generated_by_user_id=501,
        season=2026,
        valida_num=1,
    )
    await create_insight(
        mysql_session,
        athlete_id=501,
        summary_text=long_text,
        coach_approved=True,
        is_active=1,
        generated_at=t_new,
        generated_by_user_id=501,
        season=2026,
        valida_num=2,
    )
    await mysql_session.commit()

    # Wire this session into the db_factory used by recall_memory.
    def _factory():
        return _db_factory_ctx(mysql_session)

    set_db_factory(_factory)
    try:
        result = await recall_memory({"athlete_id": 501})
    finally:
        set_db_factory(None)

    memories = result["memory"]
    assert len(memories) >= 1, f"Expected >=1 memory, got {memories}"
    # Every returned summary must be at most 500 chars.
    for m in memories:
        assert len(m) <= 500, f"Summary not truncated: len={len(m)}"
    # The long text must be truncated to exactly 500 chars.
    long_truncated = [m for m in memories if len(m) == 500]
    assert long_truncated, "Long summary was not truncated to 500 chars on MySQL"
    # ORDER BY generated_at DESC: newest (long_text, t_new) first.
    assert memories[0] == long_text[:500], (
        "MySQL ORDER BY generated_at DESC: newest summary must be first"
    )


# ---------------------------------------------------------------------------
# Test 2: rehydrate_names — athlete name lookup on MySQL
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_rehydrate_names_fetch_athlete_name_mysql(mysql_session):
    """_fetch_athlete_name must return 'FirstName LastName' from MySQL athletes table.

    Verifies the raw-SQL SELECT in rehydrate_names.py works on MySQL including
    the column access via row._mapping (SQLAlchemy Row object).

    IDs: 601-602 (club/user/athlete prefix 6xx).
    """
    await create_club(mysql_session, club_id=601, code="tyr601")
    await create_user(mysql_session, user_id=601, role=UserRole.coach)
    await create_user(
        mysql_session,
        user_id=602,
        role=UserRole.athlete,
        can_login=False,
        first_name="Maria",
        last_name="Lopez",
    )
    await create_athlete(
        mysql_session,
        athlete_id=601,
        first_name="Maria",
        last_name="Lopez",
        club_id=601,
        user_id=602,
        created_by=601,
    )
    await mysql_session.commit()

    name = await _fetch_athlete_name(mysql_session, 601)
    assert name == "Maria Lopez", f"Expected 'Maria Lopez', got {name!r}"


# ---------------------------------------------------------------------------
# Test 3: build_distribution — SUM type handling on MySQL
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_build_distribution_mysql_sum_types(mysql_session):
    """build_distribution must not raise TypeError on MySQL Decimal SUM results.

    MySQL SUM(integer_col) returns Decimal; the code coerces via int() calls.
    This test seeds 5 runners and verifies: sample_size is int, mean_ms is
    float, the athlete is identified as is_self, and display_name is hidden.

    IDs: 701-702 (club/user/athlete prefix 7xx), event 701, category 701.
    """
    await create_club(mysql_session, club_id=701, code="tyr701")
    await create_user(mysql_session, user_id=701, role=UserRole.coach)
    await create_user(mysql_session, user_id=702, role=UserRole.athlete, can_login=False)
    await create_athlete(mysql_session, athlete_id=701, club_id=701, user_id=702, created_by=701)
    await create_race_series(mysql_session, series_id=701, season_year=2026)
    await create_race_category(mysql_session, category_id=701, code="INF_B_MYSQL")
    await create_race_event(
        mysql_session,
        event_id=701,
        series_id=701,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        created_by_user_id=701,
    )
    await mysql_session.commit()

    # Seed 5 runners; athlete is position 3.
    times_ms = [1_800_000, 1_810_000, 1_820_000, 1_830_000, 1_840_000]
    athlete_pos = 3

    for i, t in enumerate(times_ms, start=1):
        cid = 7010 + i
        is_athlete = (i == athlete_pos)
        await create_race_competitor(
            mysql_session,
            competitor_id=cid,
            normalized_name=f"runner701_{i}",
            display_name=f"Runner701 {i}",
            athlete_id=701 if is_athlete else None,
        )
        await create_race_result(
            mysql_session,
            event_id=701,
            category_id=701,
            competitor_id=cid,
            athlete_id=701 if is_athlete else None,
            position=i,
            race_time_ms=t,
            status=ResultStatus.FINISHED,
            created_by_user_id=701,
        )
    await mysql_session.commit()

    resp = await build_distribution(
        mysql_session,
        athlete_id=701,
        season=2026,
        valida_num=1,
        include_display_name=False,
    )

    assert resp.sample_size == 5, f"sample_size={resp.sample_size}, expected 5"
    assert isinstance(resp.sample_size, int), f"sample_size type: {type(resp.sample_size)}"
    assert resp.mean_ms is not None, "mean_ms must not be None with 5 runners"
    assert isinstance(resp.mean_ms, float), f"mean_ms must be float, got {type(resp.mean_ms)}"
    self_points = [p for p in resp.points if p.is_self]
    assert len(self_points) == 1, f"Expected 1 is_self point, got {len(self_points)}"
    assert all(p.display_name is None for p in resp.points), "display_name must be None"


# ---------------------------------------------------------------------------
# Test 4: SELECT ... FOR UPDATE executes without error on MySQL
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_with_for_update_executes_on_mysql(mysql_session):
    """SELECT ... FOR UPDATE must succeed on MySQL 8.4 InnoDB.

    SQLite silently ignores FOR UPDATE.  This test verifies the construct
    reaches MySQL and is accepted (lock grammar accepted by InnoDB).
    No rows are needed — a WHERE with a non-existent ID suffices.
    """
    from sqlalchemy import select
    from app.models.athlete_ai_insight import AthleteAiInsight

    stmt = (
        select(AthleteAiInsight)
        .where(AthleteAiInsight.athlete_id == 99999)
        .with_for_update()
    )
    result = await mysql_session.execute(stmt)
    rows = result.scalars().all()
    # Expect empty result — we just need the statement to parse and execute.
    assert rows == [], f"Expected empty list, got {rows}"


# ---------------------------------------------------------------------------
# Test 5: standings podium CAST aggregation — consistent counts on MySQL
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_standings_podium_cast_mysql(mysql_session):
    """get_event_standings podium_case must return correct counts on MySQL.

    The standings service uses ``func.cast(and_(...), Integer)`` inside
    ``func.sum()`` to count podium finishes.  On MySQL, SUM returns Decimal
    which the service coerces via ``or 0``.  This test seeds 3 competitors
    (P1, P2, P4) and verifies: the two podium finishers get podiums > 0 and
    the P4 finisher gets podiums == 0.

    IDs: 801+ (event 801, series 801, category 801, competitors 8011-8013).
    """
    await create_club(mysql_session, club_id=801, code="tyr801")
    await create_user(mysql_session, user_id=801, role=UserRole.coach)
    await create_race_series(
        mysql_session, series_id=801, season_year=2026, name="Copa Valle MySQL Test"
    )
    await create_race_category(
        mysql_session, category_id=801, code="PJUV_A_MYSQL", sort_order=999
    )
    await create_race_event(
        mysql_session,
        event_id=801,
        series_id=801,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        created_by_user_id=801,
    )
    await mysql_session.commit()

    # competitor 8011 → P1 (podium)
    await create_race_competitor(
        mysql_session, competitor_id=8011, normalized_name="c1_test", display_name="C1"
    )
    await create_race_result(
        mysql_session,
        event_id=801, category_id=801, competitor_id=8011,
        position=1, race_time_ms=1_800_000,
        status=ResultStatus.FINISHED, created_by_user_id=801,
    )
    # competitor 8012 → P4 (not podium)
    await create_race_competitor(
        mysql_session, competitor_id=8012, normalized_name="c2_test", display_name="C2"
    )
    await create_race_result(
        mysql_session,
        event_id=801, category_id=801, competitor_id=8012,
        position=4, race_time_ms=1_840_000,
        status=ResultStatus.FINISHED, created_by_user_id=801,
    )
    # competitor 8013 → P2 (podium)
    await create_race_competitor(
        mysql_session, competitor_id=8013, normalized_name="c3_test", display_name="C3"
    )
    await create_race_result(
        mysql_session,
        event_id=801, category_id=801, competitor_id=8013,
        position=2, race_time_ms=1_810_000,
        status=ResultStatus.FINISHED, created_by_user_id=801,
    )
    await mysql_session.commit()

    result = await get_event_standings(mysql_session, race_event_id=801)

    assert result is not None, "get_event_standings returned None"
    assert len(result.categories) == 1, f"Expected 1 category, got {len(result.categories)}"
    cat = result.categories[0]
    assert len(cat.rows) == 3, f"Expected 3 rows, got {len(cat.rows)}"

    podium_rows = [r for r in cat.rows if r.podiums and r.podiums > 0]
    assert len(podium_rows) == 2, (
        f"Expected 2 rows with podiums>0, got {len(podium_rows)}. "
        f"rows: {[(r.competitor_id, r.podiums) for r in cat.rows]}"
    )
    p4_row = next((r for r in cat.rows if r.competitor_id == 8012), None)
    assert p4_row is not None, "P4 competitor not found in standings"
    assert (p4_row.podiums or 0) == 0, f"P4 should have 0 podiums, got {p4_row.podiums}"


# ---------------------------------------------------------------------------
# Test 6: pseudonym stability — pure-Python, verified on MySQL session
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_pseudonym_stable_and_namespaced(mysql_session):
    """make_pseudonym must produce stable values; analytics _build_pseudonym differs.

    make_pseudonym (athlete-level) and _build_pseudonym (competitor-level, from
    analytics_charts.py) use different namespaces — their outputs must differ
    for the same numeric ID so pseudonyms from different contexts don't collide
    in the same report.

    This test runs in the mysql lane to confirm these pure-Python functions
    operate identically regardless of DB dialect.  No DB rows are needed.
    """
    athlete_id = 42
    p1 = make_pseudonym(athlete_id)
    p2 = make_pseudonym(athlete_id)
    assert p1 == p2, "make_pseudonym must be stable (same input → same output)"

    comp_pseudo = _build_pseudonym(8888)
    assert comp_pseudo.startswith("C"), (
        f"analytics_charts._build_pseudonym must start with 'C', got: {comp_pseudo}"
    )

    # Different namespaces must not collide for typical IDs.
    assert make_pseudonym(1) != _build_pseudonym(1), (
        "Athlete pseudonym and competitor pseudonym must differ (different namespaces)"
    )


# ---------------------------------------------------------------------------
# Test 7: build_evolution — grupos de comparación (feature 039, T018)
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_build_evolution_returns_series_fields_and_groups_mysql(mysql_session):
    """``build_evolution`` debe exponer ``series_id``/``series_name``/
    ``series_level`` en cada punto y una lista ``groups`` no vacía bajo
    MySQL 8.4 (feature 039).

    Pre-implementación (TDD-rojo): ``EvolutionPoint``/``EvolutionResponse``
    no tienen estos campos todavía — el acceso por atributo debe lanzar
    ``AttributeError``.

    IDs: 901+ (club/user/athlete 901, copa 9010, campeonato 9020,
    categoría 901, eventos 90101/90201).
    """
    await create_club(mysql_session, club_id=901, code="tyr901")
    await create_user(mysql_session, user_id=901, role=UserRole.coach)
    await create_user(mysql_session, user_id=902, role=UserRole.athlete, can_login=False)
    await create_athlete(
        mysql_session, athlete_id=901, club_id=901, user_id=902, created_by=901,
    )
    await create_race_category(mysql_session, category_id=901, code="INF_A_MYSQL039")

    await create_race_series(
        mysql_session,
        series_id=9010,
        season_year=2026,
        name="Copa MySQL Test",
        kind=RaceSeriesKind.cup,
    )
    await create_race_series(
        mysql_session,
        series_id=9020,
        season_year=2026,
        name="Campeonato Departamental MySQL Test",
        kind=RaceSeriesKind.championship,
        level=RaceSeriesLevel.departmental,
    )

    await create_race_event(
        mysql_session,
        event_id=90101,
        series_id=9010,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        created_by_user_id=901,
    )
    await create_race_event(
        mysql_session,
        event_id=90201,
        series_id=9020,
        sequence_number=1,
        event_date=date(2026, 6, 20),
        created_by_user_id=901,
    )
    await mysql_session.commit()

    # Pelotón mínimo por evento: ganador (P1) + el atleta (P2).
    for event_id in (90101, 90201):
        winner_cid = event_id * 10 + 1
        await create_race_competitor(
            mysql_session,
            competitor_id=winner_cid,
            normalized_name=f"winner{event_id}",
            display_name=f"Winner {event_id}",
        )
        await create_race_result(
            mysql_session,
            event_id=event_id,
            category_id=901,
            competitor_id=winner_cid,
            position=1,
            race_time_ms=1_800_000,
            status=ResultStatus.FINISHED,
            created_by_user_id=901,
        )
        athlete_cid = event_id * 10 + 2
        await create_race_competitor(
            mysql_session,
            competitor_id=athlete_cid,
            normalized_name=f"athlete{event_id}",
            display_name=f"Athlete {event_id}",
            athlete_id=901,
        )
        await create_race_result(
            mysql_session,
            event_id=event_id,
            category_id=901,
            competitor_id=athlete_cid,
            athlete_id=901,
            position=2,
            race_time_ms=1_810_000,
            status=ResultStatus.FINISHED,
            created_by_user_id=901,
        )
    await mysql_session.commit()

    result = await build_evolution(
        mysql_session,
        athlete_id=901,
        season=2026,
        metric=EvolutionMetric.RANKING,
    )

    assert len(result.series) == 2, f"Esperaba 2 puntos, obtuve {len(result.series)}"
    expected_names = {"Copa MySQL Test", "Campeonato Departamental MySQL Test"}
    for point in result.series:
        assert point.series_id in (9010, 9020), (
            f"series_id inesperado: {point.series_id!r}"
        )
        assert point.series_name in expected_names, (
            f"series_name inesperado: {point.series_name!r}"
        )
        assert point.series_level in ("departmental", "national"), (
            f"series_level inesperado: {point.series_level!r}"
        )

    assert result.groups, "groups no debe estar vacío"
    group_series_ids = {g.series_id for g in result.groups}
    assert group_series_ids == {9010, 9020}, (
        f"groups debe cubrir ambas series (copa + campeonato). Recibí: {group_series_ids}"
    )
