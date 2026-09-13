"""Tests for the anthropometric analysis context builder (feature 042, T050).

Covers `backend/app/services/ai/anthro/context.py` (pipeline step 1) and the
longitudinal / allow-list helpers it consumes from
`backend/app/services/ai/context_builders.py`, per
`specs/042-traceable-growth-ai/contracts/analysis-context.md` and
`data-model.md` §2.2.

Fixtures use fictitious dates and no athlete names (CLAUDE.md privacy rule).
`Athlete`/`AnthropometricRecord` are plain `SimpleNamespace` stubs (same
pattern as `tests/test_ai_context_builder_privacy.py`) since `context.py`
never re-reads them from the DB. The `previous_analysis` tests (item 7) need
a real row in `athlete_ai_explanations` to prove the `schema_version="v2"`
SQL filter actually works, not just that `context.py` calls `db.execute` —
so those use a minimal in-memory aiosqlite session scoped to that one table.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import MaturationStatus, NutritionalStatus
from app.models.athlete import Sex
from app.services.ai.anthro import context as anthro_context
from app.services.ai.anthro.context import build_context
from app.services.ai.context_builders import (
    ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS,
    build_longitudinal_series,
    phase_crossing_corroborated,
    sanitize_insight_context,
    velocity_confidence,
)

_USE_CASE = "anthropometry_insight_v1"


# ---------------------------------------------------------------------------
# Fixture stubs — no DB, mirrors tests/test_ai_context_builder_privacy.py
# ---------------------------------------------------------------------------


def _athlete(birth_date: date = date(2013, 3, 15), sex: Sex = Sex.M) -> SimpleNamespace:
    return SimpleNamespace(id=1, birth_date=birth_date, sex=sex)


def _record(
    *,
    id: int,
    evaluation_date: date,
    height_cm: float = 150.0,
    weight_kg: float = 40.0,
    status: MaturationStatus = MaturationStatus.pre_phv,
    maturity_offset: float = -1.5,
    age_at_phv: float = 13.5,
    arm_span_cm: float | None = None,
    sitting_height_cm: float | None = None,
    height_percentile: float | None = None,
    weight_percentile: float | None = None,
    bmi_percentile: float | None = None,
    height_z_score: float | None = None,
    weight_z_score: float | None = None,
    bmi_z_score: float | None = None,
    bmi: float | None = None,
    nutritional_status: NutritionalStatus | None = None,
) -> SimpleNamespace:
    """Lightweight ``AnthropometricRecord`` stub with every attribute
    `context.py` / `growth_summary.build_growth_summary` may read."""

    def _dec(value: float | None) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None

    return SimpleNamespace(
        id=id,
        evaluation_date=evaluation_date,
        standing_height_cm=_dec(height_cm),
        weight_kg=_dec(weight_kg),
        maturation_status=status,
        maturity_offset=_dec(maturity_offset),
        age_at_phv=_dec(age_at_phv),
        arm_span_cm=_dec(arm_span_cm),
        sitting_height_cm=_dec(sitting_height_cm),
        height_percentile=_dec(height_percentile),
        weight_percentile=_dec(weight_percentile),
        bmi_percentile=_dec(bmi_percentile),
        height_z_score=_dec(height_z_score),
        weight_z_score=_dec(weight_z_score),
        bmi_z_score=_dec(bmi_z_score),
        bmi=_dec(bmi),
        nutritional_status=nutritional_status,
        growth_source=None,
    )


def _state(
    *,
    target_record,
    history_records: list | None = None,
    athlete: SimpleNamespace | None = None,
    audience: str = "family",
    club_id: int | None = None,
    db=None,
    reference_date: date | None = None,
) -> dict:
    return {
        "athlete": athlete or _athlete(),
        "target_record": target_record,
        "history_records": history_records if history_records is not None else [target_record],
        "audience": audience,
        "use_case": _USE_CASE,
        "club_id": club_id,
        "db": db,
        "reference_date": reference_date,
    }


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Minimal async db double — only what ``context.py`` needs (``execute``
    returning a canned scalar). Used where the test is not itself about the
    ``previous_analysis`` SQL filter (item 7 uses a real DB for that)."""

    def __init__(self, previous_row=None):
        self._previous_row = previous_row

    async def execute(self, stmt):  # noqa: ARG002 - stmt unused, canned response
        return _FakeResult(self._previous_row)


# ---------------------------------------------------------------------------
# 1. Allow-list enforcement + no PII/absolute-date leakage (FR-003)
# ---------------------------------------------------------------------------

_EXPECTED_ALLOWED_KEYS = frozenset(
    {
        # 2.1 identity
        "age_decimal",
        "age_group",
        "sex",
        "category",
        "audience",
        "arm_span_cm",
        # 2.2 measurement_deltas
        "weeks_since_prev_measurement",
        "delta_height_cm",
        "delta_weight_kg",
        "delta_height_significant",
        "delta_weight_significant",
        "growth_velocity_cm_per_year",
        "velocity_confidence",
        "crossed_phv_phase",
        "prev_maturation_status",
        "phase_crossing_corroborated",
        # 2.3 longitudinal_series (per point)
        "weeks_offset_from_latest",
        "height_cm",
        "weight_kg",
        "maturation_status_at_point",
        "delta_height_cm_from_prior_point",
        # 2.4 growth_summary
        "stage",
        "maturity_offset",
        "age_at_phv",
        "months_from_phv",
        "expected_velocity_range_cm_year",
        "height_band",
        "weight_band",
        "nutritional_status",
        "alerts",
        "measurement_due_status",
        # 2.5 training_load_window
        "sessions_count_28d",
        "avg_rpe_28d",
        "hours_28d",
        # 2.6 previous_analysis
        "insight_schema_version",
        "summary_line",
        "confidence_level",
        "weeks_since",
    }
)


def test_allowlist_snapshot_matches_contract():
    """`ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS` == the reviewed literal
    set from `contracts/analysis-context.md` §2 — a change here must be a
    deliberate contract update, never an accidental widening."""
    assert ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS == _EXPECTED_ALLOWED_KEYS


def test_sanitize_drops_keys_outside_allowlist():
    dirty = {
        "age_decimal": 12.3,
        "height_z_score": 0.4,
        "weight_z_score": 0.2,
        "percentile": 65.5,
        "birth_date": "2013-03-15",
        "sitting_height_cm": 75.0,
    }
    clean = sanitize_insight_context(dirty)
    assert clean == {"age_decimal": 12.3}


async def test_build_context_never_leaks_forbidden_data():
    """FR-003: no z-score, percentile, raw band value or absolute date
    survives into the `AnalysisContext` or the rendered `*_block` text —
    however deep in the underlying records those values are stored."""
    older = _record(
        id=1,
        evaluation_date=date(2025, 1, 1),
        height_cm=140.0,
        weight_kg=32.0,
        status=MaturationStatus.pre_phv,
    )
    previous = _record(
        id=2,
        evaluation_date=date(2025, 7, 1),
        height_cm=146.0,
        weight_kg=36.0,
        status=MaturationStatus.pre_phv,
        height_z_score=0.777,
        weight_z_score=0.555,
        bmi_z_score=0.333,
        height_percentile=65.55,
        weight_percentile=57.33,
        bmi_percentile=54.21,
        bmi=17.83,
        nutritional_status=NutritionalStatus.talla_adecuada,
        sitting_height_cm=75.55,
    )
    target = _record(
        id=3,
        evaluation_date=date(2026, 3, 1),
        height_cm=151.0,
        weight_kg=40.0,
        status=MaturationStatus.circa_phv,
        height_z_score=0.888,
        weight_z_score=0.666,
        bmi_z_score=0.444,
        height_percentile=68.44,
        weight_percentile=60.22,
        bmi_percentile=55.11,
        bmi=18.09,
        nutritional_status=NutritionalStatus.talla_adecuada,
        sitting_height_cm=77.66,
        arm_span_cm=153.2,
    )

    result = await build_context(
        _state(
            target_record=target,
            history_records=[older, previous, target],
            reference_date=date(2026, 3, 1),
        )
    )

    context = result["analysis_context"]
    blocks = result["context_blocks"]

    forbidden_keys = {
        "height_z_score",
        "weight_z_score",
        "bmi_z_score",
        "height_percentile",
        "weight_percentile",
        "bmi_percentile",
        "sitting_height_cm",
        "birth_date",
        "evaluation_date",
        "value",
        "z_score",
        "percentile",
    }
    leaf_dicts = [
        context.identity,
        context.measurement_deltas or {},
        context.growth_summary,
        *context.longitudinal_series,
    ]
    for leaf in leaf_dicts:
        leaked = set(leaf.keys()) & forbidden_keys
        assert not leaked, f"Forbidden keys leaked into context: {leaked}"

    serialized = repr(context) + repr(blocks)
    forbidden_values = (
        "0.777",
        "0.555",
        "0.333",
        "0.888",
        "0.666",
        "0.444",
        "65.55",
        "57.33",
        "54.21",
        "68.44",
        "60.22",
        "55.11",
        "17.83",
        "18.09",
        "75.55",
        "77.66",
        "2025-01-01",
        "2025-07-01",
        "2026-03-01",
        "2013-03-15",
    )
    for forbidden_value in forbidden_values:
        assert forbidden_value not in serialized, f"Forbidden value leaked: {forbidden_value}"


# ---------------------------------------------------------------------------
# 2. Velocity thresholds (FR-004)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weeks", "expected"),
    [
        (0, None),
        (7, None),
        (8, "early_signal"),
        (25, "early_signal"),
        (26, "reliable"),
        (27, "reliable"),
    ],
)
def test_velocity_confidence_boundaries(weeks, expected):
    assert velocity_confidence(weeks) == expected


def test_velocity_confidence_none_when_no_previous_measurement():
    assert velocity_confidence(None) is None


async def _deltas_after_days(days: int) -> dict:
    previous = _record(id=1, evaluation_date=date(2025, 1, 1))
    target = _record(id=2, evaluation_date=date(2025, 1, 1) + timedelta(days=days))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[previous, target],
            reference_date=target.evaluation_date,
        )
    )
    return result["analysis_context"].measurement_deltas


async def test_no_velocity_figure_at_all_under_8_weeks():
    deltas = await _deltas_after_days(7 * 7)  # 7 weeks
    assert "growth_velocity_cm_per_year" not in deltas
    assert "velocity_confidence" not in deltas


async def test_velocity_present_and_early_signal_at_8_week_boundary():
    deltas = await _deltas_after_days(8 * 7)  # 8 weeks exactly
    assert "growth_velocity_cm_per_year" in deltas
    assert deltas["velocity_confidence"] == "early_signal"


async def test_velocity_still_early_signal_at_25_weeks():
    deltas = await _deltas_after_days(25 * 7)
    assert deltas["velocity_confidence"] == "early_signal"


async def test_velocity_reliable_at_26_week_boundary():
    deltas = await _deltas_after_days(26 * 7)
    assert deltas["velocity_confidence"] == "reliable"


# ---------------------------------------------------------------------------
# 3. Phase-crossing corroboration (FR-005) — both halves of the conjunction
# ---------------------------------------------------------------------------


def test_phase_crossing_corroborated_when_stable_and_interval_met():
    # Pre-PHV re-test interval is 90 days (measurement_alerts.MEASUREMENT_INTERVALS).
    assert (
        phase_crossing_corroborated("Pre-PHV", date(2025, 4, 1), "Pre-PHV", date(2025, 1, 1))
        is True
    )  # span = 90 days, exactly the Pre-PHV interval


def test_phase_crossing_not_corroborated_without_an_older_reading():
    assert phase_crossing_corroborated("Pre-PHV", date(2025, 4, 1), None, None) is False


def test_phase_crossing_not_corroborated_when_older_phase_differs():
    """Conjunction half 1 fails: interval is met (90 days) but the older
    reading shows a DIFFERENT phase — the prior phase was not stable."""
    assert (
        phase_crossing_corroborated("Pre-PHV", date(2025, 4, 1), "Circa-PHV", date(2025, 1, 1))
        is False
    )


def test_phase_crossing_not_corroborated_when_interval_too_short():
    """Conjunction half 2 fails: phase matches but only 31 days separate the
    two readings — short of the Pre-PHV 90-day re-test interval."""
    assert (
        phase_crossing_corroborated("Pre-PHV", date(2025, 4, 1), "Pre-PHV", date(2025, 3, 1))
        is False
    )


async def test_build_context_marks_corroborated_crossing():
    older = _record(id=1, evaluation_date=date(2025, 1, 1), status=MaturationStatus.pre_phv)
    previous = _record(id=2, evaluation_date=date(2025, 4, 1), status=MaturationStatus.pre_phv)
    target = _record(id=3, evaluation_date=date(2025, 7, 1), status=MaturationStatus.circa_phv)
    result = await build_context(
        _state(
            target_record=target,
            history_records=[older, previous, target],
            reference_date=date(2025, 7, 1),
        )
    )
    deltas = result["analysis_context"].measurement_deltas
    assert deltas["crossed_phv_phase"] is True
    assert deltas["phase_crossing_corroborated"] is True


async def test_build_context_marks_uncorroborated_crossing_without_older_record():
    previous = _record(id=1, evaluation_date=date(2025, 4, 1), status=MaturationStatus.pre_phv)
    target = _record(id=2, evaluation_date=date(2025, 7, 1), status=MaturationStatus.circa_phv)
    result = await build_context(
        _state(
            target_record=target,
            history_records=[previous, target],
            reference_date=date(2025, 7, 1),
        )
    )
    deltas = result["analysis_context"].measurement_deltas
    assert deltas["crossed_phv_phase"] is True
    assert deltas["phase_crossing_corroborated"] is False


# ---------------------------------------------------------------------------
# 4. History compaction above 16 points (Edge Case spec.md:126)
# ---------------------------------------------------------------------------


def test_compaction_above_16_points_folds_oldest_into_one_yearly_checkpoint():
    ref = date(2026, 1, 1)
    recent = [
        _record(id=100 + i, evaluation_date=ref - timedelta(days=14 * i), height_cm=150.0 + i)
        for i in range(15)
    ]
    older_fixture = [
        (date(2020, 2, 1), 128.0, MaturationStatus.pre_phv),
        (date(2020, 5, 1), 130.0, MaturationStatus.pre_phv),
        (date(2020, 8, 1), 132.0, MaturationStatus.pre_phv),
        (date(2020, 11, 1), 134.0, MaturationStatus.pre_phv),
        (date(2020, 12, 15), 136.0, MaturationStatus.circa_phv),
    ]
    older = [
        _record(id=200 + i, evaluation_date=d, height_cm=h, status=s)
        for i, (d, h, s) in enumerate(older_fixture)
    ]

    series = build_longitudinal_series(recent + older, reference_date=ref)

    # Nothing dropped: 15 kept per-point + exactly 1 yearly checkpoint
    # standing in for the 5 oldest records (all calendar year 2020).
    assert len(series) == 16
    checkpoint = series[15]

    for point in series:
        assert isinstance(point["weeks_offset_from_latest"], int)
        assert "sitting_height_cm" not in point
        assert "arm_span_cm" not in point
        assert not any(isinstance(v, date) for v in point.values())

    expected_avg_height = round(sum(h for _, h, _ in older_fixture) / len(older_fixture), 1)
    assert checkpoint["height_cm"] == expected_avg_height
    # 4 of 5 compacted records are Pre-PHV — the majority status wins.
    assert checkpoint["maturation_status_at_point"] == "Pre-PHV"
    expected_weeks = max(int((ref - date(2020, 12, 15)).days / 7), 0)
    assert checkpoint["weeks_offset_from_latest"] == expected_weeks

    assert series[-1]["delta_height_cm_from_prior_point"] is None
    assert all(p["delta_height_cm_from_prior_point"] is not None for p in series[:-1])


def test_compaction_creates_one_checkpoint_per_calendar_year():
    ref = date(2026, 1, 1)
    recent = [
        _record(id=100 + i, evaluation_date=ref - timedelta(days=14 * i), height_cm=150.0)
        for i in range(15)
    ]
    older = [
        _record(id=300, evaluation_date=date(2019, 6, 1), height_cm=120.0),
        _record(id=301, evaluation_date=date(2020, 6, 1), height_cm=125.0),
    ]
    series = build_longitudinal_series(recent + older, reference_date=ref)
    assert len(series) == 17  # 15 per-point + checkpoints for 2020 and 2019
    # Checkpoints are most-recent-year-first: 2020 (fewer weeks ago) then 2019.
    assert series[15]["weeks_offset_from_latest"] < series[16]["weeks_offset_from_latest"]


def test_compaction_not_triggered_at_or_below_16_points():
    ref = date(2026, 1, 1)
    records = [
        _record(id=i, evaluation_date=ref - timedelta(days=14 * i), height_cm=150.0)
        for i in range(16)
    ]
    series = build_longitudinal_series(records, reference_date=ref)
    assert len(series) == 16
    # No compaction: every point still carries its own week offset, no
    # averaging happened (heights are exactly the per-record fixture values).
    assert all(point["height_cm"] == 150.0 for point in series)


# ---------------------------------------------------------------------------
# 5. Edge cases from spec.md
# ---------------------------------------------------------------------------


async def test_first_measurement_ever_has_no_deltas_and_no_previous_analysis():
    target = _record(id=1, evaluation_date=date(2026, 1, 1))
    result = await build_context(
        _state(target_record=target, history_records=[target], reference_date=date(2026, 1, 1))
    )
    context = result["analysis_context"]
    blocks = result["context_blocks"]

    assert context.measurement_deltas is None
    assert context.previous_analysis is None
    assert blocks["measurement_deltas_block"] is None
    assert blocks["previous_analysis_block"] is None
    # Longitudinal series and growth summary are still populated from the
    # single available record — a first measurement is not "no data".
    assert len(context.longitudinal_series) == 1
    assert context.growth_summary  # non-empty


async def test_no_training_window_in_28_days_degrades_to_none(monkeypatch):
    async def _fake_load_training_window(*args, **kwargs):
        return None

    monkeypatch.setattr(anthro_context, "load_training_window", _fake_load_training_window)
    target = _record(id=1, evaluation_date=date(2026, 1, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            club_id=7,
            db=_FakeDB(),
            reference_date=date(2026, 1, 1),
        )
    )
    assert result["analysis_context"].training_load_window is None
    assert result["context_blocks"]["training_load_block"] is None


async def test_training_window_skipped_entirely_without_club_id(monkeypatch):
    called = False

    async def _fake_load_training_window(*args, **kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(anthro_context, "load_training_window", _fake_load_training_window)
    target = _record(id=1, evaluation_date=date(2026, 1, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            club_id=None,
            db=_FakeDB(),
            reference_date=date(2026, 1, 1),
        )
    )
    assert called is False
    assert result["analysis_context"].training_load_window is None


async def test_training_window_populated_maps_loader_fields(monkeypatch):
    async def _fake_load_training_window(db, athlete_id, club_id, date_from, date_to):
        return {"sessions_in_window": 5, "rpe_mean": 6.5, "training_hours": 4.25}

    monkeypatch.setattr(anthro_context, "load_training_window", _fake_load_training_window)
    target = _record(id=1, evaluation_date=date(2026, 1, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            club_id=7,
            db=_FakeDB(),
            reference_date=date(2026, 1, 1),
        )
    )
    window = result["analysis_context"].training_load_window
    assert window == {"sessions_count_28d": 5, "avg_rpe_28d": 6.5, "hours_28d": 4.25}
    assert "5" in result["context_blocks"]["training_load_block"]


async def test_no_previous_v2_insight_declared_as_absent_not_invented():
    """No prior structured row at all: `previous_analysis` is `None`, never
    a fabricated "no prior data" summary (FR-009)."""
    target = _record(id=1, evaluation_date=date(2026, 1, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            db=_FakeDB(previous_row=None),
            reference_date=date(2026, 1, 1),
        )
    )
    assert result["analysis_context"].previous_analysis is None
    assert result["context_blocks"]["previous_analysis_block"] is None


# ---------------------------------------------------------------------------
# 6. Expected-velocity anchor sourced from the growth summary (FR-007)
# ---------------------------------------------------------------------------


async def test_expected_velocity_anchor_comes_from_growth_summary_not_hardcoded(monkeypatch):
    sentinel_range = (99.0, 100.0)

    def _fake_get_expected_velocity_range(stage, sex):
        return sentinel_range

    monkeypatch.setattr(
        anthro_context, "get_expected_velocity_range", _fake_get_expected_velocity_range
    )
    target = _record(id=1, evaluation_date=date(2026, 1, 1), status=MaturationStatus.pre_phv)
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            db=_FakeDB(),
            reference_date=date(2026, 1, 1),
        )
    )
    growth_summary = result["analysis_context"].growth_summary
    assert growth_summary["expected_velocity_range_cm_year"] == sentinel_range
    block = result["context_blocks"]["growth_summary_block"]
    assert "99.0" in block
    assert "100.0" in block


# ---------------------------------------------------------------------------
# 7. previous_analysis reads only schema_version="v2" rows (§2.6)
# ---------------------------------------------------------------------------

_EXPLANATIONS_TABLE = "athlete_ai_explanations"


@pytest_asyncio.fixture
async def explanations_engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    table = Base.metadata.tables[_EXPLANATIONS_TABLE]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[table]))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def explanations_session(explanations_engine) -> AsyncSession:
    factory = async_sessionmaker(explanations_engine, expire_on_commit=False)
    async with factory() as s:
        yield s


def _explanation_row(
    *,
    athlete_id: int,
    record_id: int,
    schema_version: str | None,
    generated_at: datetime,
    structured_json: dict | None = None,
    use_case: str = _USE_CASE,
) -> AthleteAIExplanation:
    return AthleteAIExplanation(
        athlete_id=athlete_id,
        anthropometric_record_id=record_id,
        use_case=use_case,
        text="placeholder — no PII, fixture only",
        model="fake-model",
        provider="fake",
        generated_at=generated_at,
        age_group="10-12",
        maturation_status="Pre-PHV",
        schema_version=schema_version,
        structured_json=structured_json,
        generated_by_user_id=1,
    )


async def test_previous_analysis_ignores_legacy_null_schema_row(explanations_session):
    legacy = _explanation_row(
        athlete_id=1,
        record_id=1,
        schema_version=None,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured_json=None,
    )
    explanations_session.add(legacy)
    await explanations_session.commit()

    target = _record(id=2, evaluation_date=date(2026, 2, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            db=explanations_session,
            reference_date=date(2026, 2, 1),
            athlete=_athlete(),
        )
    )
    assert result["analysis_context"].previous_analysis is None


async def test_previous_analysis_reads_only_the_v2_row_when_both_exist(explanations_session):
    legacy = _explanation_row(
        athlete_id=1,
        record_id=1,
        schema_version=None,
        generated_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        structured_json=None,
    )
    structured = _explanation_row(
        athlete_id=1,
        record_id=2,
        schema_version="v2",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured_json={
            "summary_line": "Crecimiento estable esta quincena.",
            "confidence": {"level": "medium", "reason": "datos suficientes para esta lectura"},
        },
    )
    explanations_session.add_all([legacy, structured])
    await explanations_session.commit()

    target = _record(id=3, evaluation_date=date(2026, 2, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            db=explanations_session,
            reference_date=date(2026, 2, 1),
            athlete=_athlete(),
        )
    )
    previous = result["analysis_context"].previous_analysis
    assert previous is not None
    assert previous["summary_line"] == "Crecimiento estable esta quincena."
    assert previous["confidence_level"] == "medium"
    # This is the INSIGHT PAYLOAD version (data-model.md §0), distinct from
    # the ROW discriminator ("v2") that was just filtered on above.
    assert previous["insight_schema_version"] == "v1"
    assert "weeks_since" in previous
    assert isinstance(previous["weeks_since"], int)
    # No absolute date crosses into the context — only a relative offset.
    assert "2026-01-01" not in repr(previous)


async def test_previous_analysis_none_when_no_structured_row_exists(explanations_session):
    target = _record(id=1, evaluation_date=date(2026, 1, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            db=explanations_session,
            reference_date=date(2026, 1, 1),
            athlete=_athlete(),
        )
    )
    assert result["analysis_context"].previous_analysis is None


async def test_previous_analysis_none_when_structured_json_incomplete(explanations_session):
    """A `schema_version="v2"` row whose payload lacks summary/confidence
    (corrupt or partially-written) is treated as absent, never guessed at
    (FR-009)."""
    incomplete = _explanation_row(
        athlete_id=1,
        record_id=1,
        schema_version="v2",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured_json={"summary_line": None},
    )
    explanations_session.add(incomplete)
    await explanations_session.commit()

    target = _record(id=2, evaluation_date=date(2026, 2, 1))
    result = await build_context(
        _state(
            target_record=target,
            history_records=[target],
            db=explanations_session,
            reference_date=date(2026, 2, 1),
            athlete=_athlete(),
        )
    )
    assert result["analysis_context"].previous_analysis is None
