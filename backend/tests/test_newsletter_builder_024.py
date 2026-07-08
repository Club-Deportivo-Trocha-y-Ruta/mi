"""Regression tests for feature 024 (newsletter audit fixes).

Covers the NEW/CORRECTED builder behavior documented in
``specs/024-newsletter-audit-fixes/{research.md,data-model.md,contracts/metrics-snapshot.md}``:

- A1 (R1): ``_build_race_block`` emits ``short_label`` — "CD" for a departmental
  championship result, "V{n}" for a cup válida.
- A5 (R5): ``_build_technical_block`` computes ``weekly_hours_avg`` /
  ``ltad_limit_hours`` / ``ltad_status`` from real month hours + athlete age;
  a month with zero executed sessions nulls all three.
- B6 (R6): ``focus_groups`` collapses near-duplicate descenso/curva free-text
  foci into fewer skill-family groups whose ``session_count`` sums to the
  number of sessions with a non-empty ``technical_focus``.
- B12 (R12): the attendance block emits ``streak_sessions`` (not the legacy
  ``streak_days``) and exactly one streak value.
- B13 (R13): ``_build_charts_context`` flags ``has_championship=True`` when a
  championship round appears in the progression history.
- B7 (R7): a race result whose ``category_code`` matches a seeded
  ``race_categories.label`` gets a non-null ``category_label``; an unmapped
  code falls back to ``None`` (template shows the raw code).

Two harnesses are used, matching existing repo conventions:

- A1/B7 exercise the real SQL path (``_build_race_block`` joins via pandas +
  an ``IN`` lookup against ``race_categories``) against a real in-memory
  aiosqlite DB restricted to the race + identity tables (same pattern as
  ``tests/technique/conftest.py`` / ``tests/strength/conftest.py``).
- A5/B6/B12 exercise ``_build_technical_block`` / ``_build_attendance_block``
  directly with a hand-rolled fake ``AsyncSession`` returning canned
  ``SimpleNamespace`` rows in call order (same convention as
  ``tests/services/training/test_newsletter_builder.py``), since those
  helpers only need session/attendance rows, not the race join graph.

All fixtures use fictitious names/dates per CLAUDE.md privacy rules.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.services.training.focus_grouping import group_focus_texts
from app.services.training.newsletter_builder import (
    _build_attendance_block,
    _build_charts_context,
    _build_race_block,
    _build_technical_block,
)

# ---------------------------------------------------------------------------
# Real aiosqlite harness — race tables only (A1, B7)
# ---------------------------------------------------------------------------

_RACE_TABLES = (
    "users",
    "clubs",
    "athletes",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
)


@pytest_asyncio.fixture
async def race_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _RACE_TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


async def _seed_identity(session) -> tuple[User, Club, Athlete]:
    """Fictitious coach/club/athlete triad shared by the race-block tests."""
    coach = User(
        id=1,
        email="entrenador.ficticio@trochyruta.test",
        first_name="Entrenador",
        last_name="Ficticio",
        role=UserRole.coach,
    )
    athlete_login = User(
        id=2,
        email=None,
        first_name="Juan",
        last_name="Perez Ficticio",
        role=UserRole.athlete,
        can_login=False,
    )
    club = Club(id=1, name="Club Trocha y Ruta Ficticio", code="TYR-FICT-024")
    athlete = Athlete(
        id=1,
        user_id=2,
        first_name="Juan",
        last_name="Perez Ficticio",
        birth_date=date(2012, 3, 15),
        sex=Sex.F,
        club_id=1,
        created_by=1,
    )
    session.add_all([coach, athlete_login, club, athlete])
    await session.flush()
    return coach, club, athlete


async def _seed_race_categories(session) -> None:
    session.add_all(
        [
            RaceCategory(
                id=1,
                code="PJUV_A_F",
                label="Prejuvenil A Femenino",
                sex=CategoryGender.F,
                age_min=13,
                age_max=13,
                sort_order=42,
            ),
            RaceCategory(
                id=2,
                code="INF_A",
                label="Infantil A",
                sex=CategoryGender.M,
                age_min=9,
                age_max=10,
                sort_order=30,
            ),
        ]
    )
    await session.flush()


# ---------------------------------------------------------------------------
# A1 — championship short_label vs cup válida short_label (R1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_race_block_championship_short_label_is_cd(race_session):
    """A departmental championship result gets short_label 'CD', not 'V1'."""
    await _seed_identity(race_session)
    await _seed_race_categories(race_session)

    championship_series = RaceSeries(
        id=1,
        name="Campeonato Departamental Valle Ficticio",
        season_year=2026,
        points_scheme_code="copa_valle_2026",
        kind=RaceSeriesKind.championship,
        level=RaceSeriesLevel.departmental,
    )
    race_session.add(championship_series)
    await race_session.flush()

    # Championships carry sequence_number=1 (spec 014) — this is exactly the
    # collision scenario R1 fixes: without short_label this would render "V1".
    event = RaceEvent(
        id=1,
        series_id=1,
        sequence_number=1,
        name="Campeonato Departamental Ficticio",
        event_date=date(2026, 6, 12),
        location="Ginebra Ficticia",
        is_championship=True,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
    )
    race_session.add(event)
    await race_session.flush()

    competitor = RaceCompetitor(
        id=1,
        normalized_name="juan perez ficticio",
        display_name="Juan Perez Ficticio",
        club_text="Club Trocha y Ruta Ficticio",
        athlete_id=1,
    )
    race_session.add(competitor)
    await race_session.flush()

    result = RaceResult(
        id=1,
        event_id=1,
        category_id=1,
        competitor_id=1,
        athlete_id=1,
        position=3,
        status=ResultStatus.FINISHED,
        race_time_ms=1_800_000,
        points_awarded=15,
        created_by_user_id=1,
    )
    race_session.add(result)
    await race_session.commit()

    block = await _build_race_block(race_session, athlete_id=1, year=2026, month=6)

    assert block["has_races"] is True
    assert len(block["results"]) == 1
    entry = block["results"][0]
    assert entry["short_label"] == "CD"
    assert entry["label"] == "Campeonato Departamental"


@pytest.mark.asyncio
async def test_build_race_block_cup_valida_short_label_is_v3(race_session):
    """A cup result for válida 3 gets short_label 'V3'."""
    await _seed_identity(race_session)
    await _seed_race_categories(race_session)

    cup_series = RaceSeries(
        id=1,
        name="Copa Valle Ficticia",
        season_year=2026,
        points_scheme_code="copa_valle_2026",
        kind=RaceSeriesKind.cup,
        level=RaceSeriesLevel.departmental,
    )
    race_session.add(cup_series)
    await race_session.flush()

    event = RaceEvent(
        id=1,
        series_id=1,
        sequence_number=3,
        name="Válida III Ficticia",
        event_date=date(2026, 4, 19),
        location="La Cumbre Ficticia",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
    )
    race_session.add(event)
    await race_session.flush()

    competitor = RaceCompetitor(
        id=1,
        normalized_name="juan perez ficticio",
        display_name="Juan Perez Ficticio",
        club_text="Club Trocha y Ruta Ficticio",
        athlete_id=1,
    )
    race_session.add(competitor)
    await race_session.flush()

    result = RaceResult(
        id=1,
        event_id=1,
        category_id=1,
        competitor_id=1,
        athlete_id=1,
        position=5,
        status=ResultStatus.FINISHED,
        race_time_ms=1_900_000,
        points_awarded=8,
        created_by_user_id=1,
    )
    race_session.add(result)
    await race_session.commit()

    block = await _build_race_block(race_session, athlete_id=1, year=2026, month=4)

    assert len(block["results"]) == 1
    entry = block["results"][0]
    assert entry["short_label"] == "V3"
    assert entry["label"] == "Válida 3"


# ---------------------------------------------------------------------------
# B7 — category_label resolution (R7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_race_block_category_label_resolves_known_code(race_session):
    """category_code 'PJUV_A_F' resolves to its seeded race_categories.label."""
    await _seed_identity(race_session)
    await _seed_race_categories(race_session)

    series = RaceSeries(
        id=1,
        name="Copa Valle Ficticia",
        season_year=2026,
        points_scheme_code="copa_valle_2026",
        kind=RaceSeriesKind.cup,
        level=RaceSeriesLevel.departmental,
    )
    race_session.add(series)
    await race_session.flush()

    event = RaceEvent(
        id=1,
        series_id=1,
        sequence_number=1,
        name="Válida I Ficticia",
        event_date=date(2026, 1, 31),
        location="Sevilla Ficticia",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
    )
    race_session.add(event)
    await race_session.flush()

    competitor = RaceCompetitor(
        id=1,
        normalized_name="juan perez ficticio",
        display_name="Juan Perez Ficticio",
        club_text="Club Trocha y Ruta Ficticio",
        athlete_id=1,
    )
    race_session.add(competitor)
    await race_session.flush()

    # category_id=1 → code "PJUV_A_F", seeded label "Prejuvenil A Femenino".
    result = RaceResult(
        id=1,
        event_id=1,
        category_id=1,
        competitor_id=1,
        athlete_id=1,
        position=2,
        status=ResultStatus.FINISHED,
        race_time_ms=1_700_000,
        points_awarded=18,
        created_by_user_id=1,
    )
    race_session.add(result)
    await race_session.commit()

    block = await _build_race_block(race_session, athlete_id=1, year=2026, month=1)

    entry = block["results"][0]
    assert entry["category_code"] == "PJUV_A_F"
    assert entry["category_label"] == "Prejuvenil A Femenino"


@pytest.mark.asyncio
async def test_build_race_block_category_label_none_for_unmapped_code(race_session, monkeypatch):
    """An unmapped category code falls back to category_label=None (raw code shown)."""
    await _seed_identity(race_session)
    await _seed_race_categories(race_session)

    # Add a third category whose code has NO counterpart the lookup will match
    # after we simulate a stale/unmapped code below.
    series = RaceSeries(
        id=1,
        name="Copa Valle Ficticia",
        season_year=2026,
        points_scheme_code="copa_valle_2026",
        kind=RaceSeriesKind.cup,
        level=RaceSeriesLevel.departmental,
    )
    race_session.add(series)
    await race_session.flush()

    event = RaceEvent(
        id=1,
        series_id=1,
        sequence_number=1,
        name="Válida I Ficticia",
        event_date=date(2026, 1, 31),
        location="Sevilla Ficticia",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
    )
    race_session.add(event)
    await race_session.flush()

    competitor = RaceCompetitor(
        id=1,
        normalized_name="juan perez ficticio",
        display_name="Juan Perez Ficticio",
        club_text="Club Trocha y Ruta Ficticio",
        athlete_id=1,
    )
    race_session.add(competitor)
    await race_session.flush()

    # category_id=2 → code "INF_A", seeded label "Infantil A" — but we monkeypatch
    # the resolver to simulate a code with no DB counterpart (e.g. a category
    # retired/renamed after the result was recorded), asserting the fallback
    # path (absent from the lookup dict) rather than relying on it existing.
    from app.services.training import newsletter_builder as builder_module

    original_lookup = builder_module._lookup_category_labels

    async def _lookup_without_inf_a(db, codes):
        resolved = await original_lookup(db, codes)
        resolved.pop("INF_A", None)
        return resolved

    monkeypatch.setattr(builder_module, "_lookup_category_labels", _lookup_without_inf_a)

    result = RaceResult(
        id=1,
        event_id=1,
        category_id=2,
        competitor_id=1,
        athlete_id=1,
        position=4,
        status=ResultStatus.FINISHED,
        race_time_ms=1_950_000,
        points_awarded=6,
        created_by_user_id=1,
    )
    race_session.add(result)
    await race_session.commit()

    block = await _build_race_block(race_session, athlete_id=1, year=2026, month=1)

    entry = block["results"][0]
    assert entry["category_code"] == "INF_A"
    assert entry["category_label"] is None


# ---------------------------------------------------------------------------
# Fake AsyncSession helpers for _build_technical_block / _build_attendance_block
# (A5, B6, B12) — mirrors tests/services/training/test_newsletter_builder.py
# ---------------------------------------------------------------------------


def _make_fake_db(responses: list[list[Any]]) -> Any:
    """Returns a fake AsyncSession whose execute() yields canned rows in order.

    ``responses`` is a list of "row lists" consumed one per call to
    ``db.execute(...)`` — call N returns ``responses[N]`` wrapped so that both
    ``.scalars().all()`` work as callers expect.
    """
    db = MagicMock()
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        rows = responses[call_count] if call_count < len(responses) else []
        call_count += 1
        result = MagicMock()
        result.scalars.return_value = result
        result.all.return_value = rows
        return result

    db.execute = _execute
    db.flush = AsyncMock()
    return db


def _session_obj(id_: int, *, technical_focus: str, duration_min: int = 90, date_: date | None = None) -> Any:
    from app.models.training_session import SessionStatus

    return SimpleNamespace(
        id=id_,
        club_id=1,
        scheduled_date=date_ or date(2026, 4, 1),
        status=SessionStatus.EXECUTED,
        duration_min=duration_min,
        technical_focus=technical_focus,
        location="Reserva Natural Ficticia",
    )


def _attendance_obj(session_id: int, status_, **rubric) -> Any:
    return SimpleNamespace(
        session_id=session_id,
        athlete_id=1,
        status=status_,
        rpe_omni=rubric.get("rpe_omni", 5),
        rubric_effort=rubric.get("rubric_effort", 4),
        rubric_attitude=rubric.get("rubric_attitude", 4),
        rubric_technique=rubric.get("rubric_technique", 4),
    )


def _make_athlete(birth_date: date) -> Any:
    return SimpleNamespace(id=1, club_id=1, birth_date=birth_date)


# ---------------------------------------------------------------------------
# A5 — LTAD weekly-hours compliance (R5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_technical_block_ltad_fields_computed_for_30_day_month():
    """27.5h total in a 30-day month + age ~13.9 -> weekly_hours_avg=6.4,
    ltad_limit_hours=13.9, ltad_status='ok' (weekly avg well under the limit)."""
    from app.models.training_session import AttendanceStatus

    month_start = date(2026, 4, 1)
    month_end = date(2026, 4, 30)
    assert calendar.monthrange(2026, 4)[1] == 30

    generation_date = date(2026, 4, 15)
    # 5078 days -> compute_age_decimal rounds to 13.9 exactly (documented derivation).
    birth_date = generation_date - timedelta(days=5078)
    from app.services.category import compute_age_decimal

    assert compute_age_decimal(birth_date, generation_date) == 13.9

    athlete = _make_athlete(birth_date)

    # 11 sessions * 150 min = 1650 min = 27.5h, all attended (PRESENTE).
    sessions = [
        _session_obj(i, technical_focus="Curvas cerradas", duration_min=150, date_=month_start)
        for i in range(1, 12)
    ]
    attendances = [
        _attendance_obj(s.id, AttendanceStatus.PRESENTE) for s in sessions
    ]

    db = _make_fake_db([sessions, attendances])

    block = await _build_technical_block(db, athlete, month_start, month_end, generation_date)

    assert block["total_training_hours"] == 27.5
    assert block["weekly_hours_avg"] == pytest.approx(6.4, abs=0.01)
    assert block["ltad_limit_hours"] == pytest.approx(13.9, abs=0.01)
    assert block["ltad_status"] == "ok"


@pytest.mark.asyncio
async def test_build_technical_block_no_sessions_nulls_ltad_fields():
    """A month with zero executed sessions nulls weekly_hours_avg/ltad_status
    but still resolves ltad_limit_hours from the athlete's age (informational)."""
    month_start = date(2026, 5, 1)
    month_end = date(2026, 5, 31)
    generation_date = date(2026, 5, 15)
    athlete = _make_athlete(date(2012, 3, 15))

    db = _make_fake_db([[]])  # sessions query returns empty -> early return

    block = await _build_technical_block(db, athlete, month_start, month_end, generation_date)

    assert block["total_training_hours"] == 0.0
    assert block["weekly_hours_avg"] is None
    assert block["ltad_status"] is None
    assert block["focus_groups"] == []


# ---------------------------------------------------------------------------
# B6 — focus_groups grouping (R6)
# ---------------------------------------------------------------------------


def test_group_focus_texts_collapses_near_duplicate_descenso_curva_foci():
    """Near-duplicate free-text foci collapse into fewer skill-family groups;
    the sum of session_count across groups equals the number of non-empty
    technical_focus entries."""
    raw_foci = [
        "curvas cerradas",
        "trazado de curva amplia",
        "descenso técnico con raíces",
        "bajada en terreno con rocas",
        "frenado progresivo",
        "",  # blank — must not be counted
        "   ",  # whitespace-only — must not be counted
    ]

    groups = group_focus_texts(raw_foci)

    total_non_empty = sum(1 for f in raw_foci if f and f.strip())
    assert sum(g.session_count for g in groups) == total_non_empty

    by_slug = {g.slug: g.session_count for g in groups}
    # "curvas cerradas" + "trazado de curva amplia" -> both match curvas keywords.
    assert by_slug["curvas"] == 2
    # "descenso ... raíces" + "bajada ... rocas" -> both match presion_terreno.
    assert by_slug["presion_terreno"] == 2
    assert by_slug["frenado"] == 1
    # Fewer groups than raw (non-blank) entries -> real collapsing happened.
    assert len(groups) < total_non_empty


@pytest.mark.asyncio
async def test_build_technical_block_focus_groups_sum_matches_session_count():
    """focus_groups emitted by the builder sum to the number of sessions with
    a non-empty technical_focus (some sessions have none)."""
    from app.models.training_session import AttendanceStatus

    month_start = date(2026, 6, 1)
    month_end = date(2026, 6, 30)
    generation_date = date(2026, 6, 15)
    athlete = _make_athlete(date(2012, 3, 15))

    sessions = [
        _session_obj(1, technical_focus="curvas cerradas", date_=month_start),
        _session_obj(2, technical_focus="trazado de curva amplia", date_=month_start),
        _session_obj(3, technical_focus="descenso técnico", date_=month_start),
        _session_obj(4, technical_focus="", date_=month_start),  # empty focus
    ]
    attendances = [
        _attendance_obj(s.id, AttendanceStatus.PRESENTE) for s in sessions
    ]

    db = _make_fake_db([sessions, attendances])

    block = await _build_technical_block(db, athlete, month_start, month_end, generation_date)

    sessions_with_focus = sum(1 for s in sessions if s.technical_focus)
    assert sum(g["session_count"] for g in block["focus_groups"]) == sessions_with_focus
    assert sessions_with_focus == 3


# ---------------------------------------------------------------------------
# B12 — streak_sessions rename (R12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_attendance_block_emits_streak_sessions_key_exactly_once():
    """The attendance block key is 'streak_sessions' (not the legacy
    'streak_days'), and there is exactly one streak value in the block."""
    from app.models.training_session import AttendanceStatus

    month_start = date(2026, 4, 1)
    month_end = date(2026, 4, 30)
    athlete = _make_athlete(date(2012, 3, 15))

    sessions = [_session_obj(i, technical_focus="Frenado", date_=month_start) for i in range(1, 4)]
    attendances = [_attendance_obj(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    # Call order inside _build_attendance_block:
    #   1. sessions of the month
    #   2. SessionAttendance for those sessions
    #   3. sessions of the previous month (_get_prev_month_attendance)
    #   4. SessionAttendance of the previous month
    db = _make_fake_db([sessions, attendances, [], []])

    block = await _build_attendance_block(db, athlete, month_start, month_end, 2026, 4)

    assert "streak_sessions" in block
    assert "streak_days" not in block
    # Exactly one streak-shaped key in the block.
    streak_keys = [k for k in block if k.startswith("streak")]
    assert streak_keys == ["streak_sessions"]
    assert block["streak_sessions"] == 3


# ---------------------------------------------------------------------------
# B13 — championship no-points footnote flag (R13)
# ---------------------------------------------------------------------------


def test_build_charts_context_has_championship_true_when_history_has_one():
    race_block = {
        "progression_history": [
            {
                "valida_num": 1,
                "event_date": "2026-01-31",
                "position": 3,
                "points_awarded": 15,
                "gap_to_winner_pct": 4.2,
                "series_kind": "cup",
                "series_level": "departmental",
                "label": "V1",
            },
            {
                "valida_num": 1,
                "event_date": "2026-06-12",
                "position": 2,
                "points_awarded": 0,
                "gap_to_winner_pct": 1.1,
                "series_kind": "championship",
                "series_level": "departmental",
                "label": "CD",
            },
        ]
    }

    ctx = _build_charts_context(race_block)

    assert ctx["has_championship"] is True
    assert ctx["has_data"] is True


def test_build_charts_context_has_championship_false_when_only_cups():
    race_block = {
        "progression_history": [
            {
                "valida_num": 1,
                "event_date": "2026-01-31",
                "position": 3,
                "points_awarded": 15,
                "gap_to_winner_pct": 4.2,
                "series_kind": "cup",
                "series_level": "departmental",
                "label": "V1",
            },
        ]
    }

    ctx = _build_charts_context(race_block)

    assert ctx["has_championship"] is False


def test_build_charts_context_has_championship_false_when_no_history():
    ctx = _build_charts_context({"progression_history": []})

    assert ctx["has_championship"] is False
    assert ctx["has_data"] is False
