"""Tests de ``app.services.race.history`` (feature 044, US6 — FR-030..039).

Fixtures 100% ficticias (nunca nombres reales). Pura: sin DB, objetos ORM
instanciados en memoria — mismo patrón que ``test_field_metrics.py``, al que
``build_history_points`` delega el cálculo de campo por temporada.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.services.race.history import (
    HISTORY_CAVEATS,
    MIN_FIELD,
    build_history_points,
    build_season_completions,
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_ATHLETE_ID = 144
_CAT_A = 10
_CAT_B = 11


def _series(sid: int, season: int, kind=RaceSeriesKind.cup) -> RaceSeries:
    return RaceSeries(
        id=sid,
        name="Copa Valle",
        season_year=season,
        organizer="Liga Vallecaucana",
        points_scheme_code=f"copa_valle_{season}",
        kind=kind,
        level=RaceSeriesLevel.departmental,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _event(eid: int, series_id: int, seq: int, d: date, championship: bool = False) -> RaceEvent:
    return RaceEvent(
        id=eid,
        series_id=series_id,
        sequence_number=seq,
        name=f"Válida ficticia {seq}",
        event_date=d,
        location="Pista ficticia",
        is_championship=championship,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _category(cid: int, code: str, label: str) -> RaceCategory:
    return RaceCategory(
        id=cid,
        code=code,
        label=label,
        sex=CategoryGender.MIXED,
        sort_order=1,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _result(
    rid: int,
    event_id: int,
    category_id: int,
    competitor_id: int,
    *,
    athlete_id: int | None = None,
    position: int | None,
    status: ResultStatus = ResultStatus.FINISHED,
    time_ms: int | None,
    laps_behind: int | None = None,
    category_label_raw: str | None = None,
    points_awarded: int = 0,
) -> RaceResult:
    return RaceResult(
        id=rid,
        event_id=event_id,
        category_id=category_id,
        competitor_id=competitor_id,
        athlete_id=athlete_id,
        position=position,
        status=status,
        race_time_ms=time_ms,
        laps_behind=laps_behind,
        category_label_raw=category_label_raw,
        points_awarded=points_awarded,
        created_by_user_id=1,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _setup(event_id: int, category_id: int, *, laps: int, lap_distance_m: int) -> SimpleNamespace:
    """Duck-typed fake — ``derive_figures`` solo necesita ``.laps`` y
    ``.variant.lap_distance_m``/``.elevation_gain_m`` (ver su docstring)."""
    return SimpleNamespace(
        race_event_id=event_id,
        category_id=category_id,
        laps=laps,
        variant=SimpleNamespace(lap_distance_m=lap_distance_m, elevation_gain_m=None),
    )


@pytest.fixture()
def dataset():
    """Un atleta, 2024 en categoría A (6 válidas, umbrales de campo variados,
    DNF, DNS, "posición sin tiempo", vuelta perdida) y 2025 con cambio real
    de categoría (A → B) más un renombre de catálogo que NO debe levantar la
    bandera.
    """
    series_2024 = _series(1, 2024)
    series_2025 = _series(2, 2025)
    series = [series_2024, series_2025]

    events = [
        _event(101, 1, 1, date(2024, 2, 1)),  # V1: campo de 4 (<5) → sin percentil
        _event(102, 1, 2, date(2024, 3, 1)),  # V2: campo de 5 (=5) → con percentil/mediana
        _event(104, 1, 4, date(2024, 5, 1)),  # V4: DNF del atleta
        _event(105, 1, 5, date(2024, 6, 1)),  # V5: posición sin tiempo
        _event(106, 1, 6, date(2024, 7, 1)),  # V6: perdió vuelta (minus_laps)
        _event(107, 1, 7, date(2024, 8, 1)),  # V7: DNS del atleta
        _event(201, 2, 1, date(2025, 2, 1)),  # 2025-1: cambio real de categoría A→B
        _event(202, 2, 2, date(2025, 3, 1)),  # 2025-2: mismo category_id, catálogo renombrado
    ]

    categories = [
        _category(_CAT_A, "INF_A", "Infantil A"),
        _category(_CAT_B, "PJUV_A", "Prejuvenil A"),
    ]

    results: list[RaceResult] = []
    rid = 1

    # --- V1: campo de 4, atleta 2º ---------------------------------------
    for comp_id, pos, t, ath in [(1, 2, 3_100_000, _ATHLETE_ID), (2, 1, 3_000_000, None), (3, 3, 3_200_000, None), (4, 4, 3_300_000, None)]:
        results.append(_result(rid, 101, _CAT_A, comp_id, athlete_id=ath, position=pos, time_ms=t, points_awarded=18 if ath else 0))
        rid += 1

    # --- V2: campo de 5, atleta gana (1º) ---------------------------------
    for comp_id, pos, t, ath in [
        (1, 1, 2_900_000, _ATHLETE_ID),
        (2, 2, 3_000_000, None),
        (3, 3, 3_100_000, None),
        (4, 4, 3_200_000, None),
        (5, 5, 3_300_000, None),
    ]:
        results.append(_result(rid, 102, _CAT_A, comp_id, athlete_id=ath, position=pos, time_ms=t, points_awarded=25 if ath else 0))
        rid += 1

    # --- V4: DNF del atleta + 3 finishers ---------------------------------
    results.append(_result(rid, 104, _CAT_A, 1, athlete_id=_ATHLETE_ID, position=None, status=ResultStatus.DNF, time_ms=None))
    rid += 1
    for comp_id, pos, t in [(2, 1, 2_950_000), (3, 2, 3_050_000), (4, 3, 3_150_000)]:
        results.append(_result(rid, 104, _CAT_A, comp_id, position=pos, time_ms=t))
        rid += 1

    # --- V5: FINISHED con posición pero sin tiempo (laps_behind satisface el
    # check constraint real de `race_results`) — campo real de 4 para que la
    # posición 3 sea consistente. ------------------------------------------
    results.append(
        _result(rid, 105, _CAT_A, 1, athlete_id=_ATHLETE_ID, position=3, time_ms=None, laps_behind=1)
    )
    rid += 1
    for comp_id, pos, t in [(2, 1, 2_920_000), (3, 2, 3_010_000), (4, 4, 3_180_000)]:
        results.append(_result(rid, 105, _CAT_A, comp_id, position=pos, time_ms=t))
        rid += 1

    # --- V6: el atleta perdió una vuelta (minus_laps, sin tiempo comparable)
    # — mismo criterio, campo real de 4. -------------------------------------
    results.append(
        _result(
            rid, 106, _CAT_A, 1, athlete_id=_ATHLETE_ID, position=4,
            status=ResultStatus.MINUS_LAPS, time_ms=None, laps_behind=1,
        )
    )
    rid += 1
    for comp_id, pos, t in [(2, 1, 2_930_000), (3, 2, 3_020_000), (4, 3, 3_110_000)]:
        results.append(_result(rid, 106, _CAT_A, comp_id, position=pos, time_ms=t))
        rid += 1

    # --- V7: DNS del atleta ------------------------------------------------
    results.append(
        _result(rid, 107, _CAT_A, 1, athlete_id=_ATHLETE_ID, position=None, status=ResultStatus.DNS, time_ms=None)
    )
    rid += 1

    # --- 2025-1: cambio REAL de categoría (A → B) --------------------------
    results.append(
        _result(rid, 201, _CAT_B, 1, athlete_id=_ATHLETE_ID, position=2, time_ms=3_000_000, category_label_raw="Prejuvenil A")
    )
    rid += 1

    # --- 2025-2: MISMO category_id que 2025-1, pero el catálogo fue
    # renombrado entre las dos válidas (etiqueta congelada distinta) — NO
    # debe levantar `category_changed` porque `category_id` no cambió.
    results.append(
        _result(rid, 202, _CAT_B, 1, athlete_id=_ATHLETE_ID, position=1, time_ms=2_950_000, category_label_raw="Pre-Juvenil A (renombrada)")
    )
    rid += 1

    setups = [_setup(102, _CAT_A, laps=4, lap_distance_m=5000)]

    return {
        "results": results,
        "events": events,
        "series": series,
        "categories": categories,
        "setups": setups,
    }


def _by_event(points):
    return {p.event_id: p for p in points}


class TestFieldThresholds:
    def test_field_below_five_hides_percentile(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p1 = _by_event(points)[101]
        assert p1.field_size == 4
        assert p1.percentile is None

    def test_field_of_five_shows_percentile(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p2 = _by_event(points)[102]
        assert p2.field_size == 5
        assert p2.percentile == 100.0

    def test_timed_finishers_below_five_hides_gap_to_median(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p1 = _by_event(points)[101]
        assert p1.timed_finishers == 4
        assert p1.gap_to_median_pct is None

    def test_timed_finishers_of_five_shows_gap_to_median(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p2 = _by_event(points)[102]
        assert p2.timed_finishers == 5
        assert p2.gap_to_median_pct is not None

    def test_min_field_constant_is_five(self):
        assert MIN_FIELD == 5


class TestNonFinishers:
    def test_dnf_has_no_position_or_time(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p4 = _by_event(points)[104]
        assert p4.status == "dnf"
        assert p4.position is None
        assert p4.gap_to_winner_pct is None
        assert p4.avg_speed_kmh is None

    def test_dns_has_no_position_or_field_membership(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p7 = _by_event(points)[107]
        assert p7.status == "dns"
        assert p7.position is None

    def test_position_without_time_has_no_time_derived_figures(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p5 = _by_event(points)[105]
        assert p5.status == "finished"
        assert p5.position == 3
        assert p5.gap_to_winner_pct is None
        assert p5.gap_to_median_pct is None
        assert p5.avg_speed_kmh is None

    def test_lapped_athlete_counts_as_field_member_but_has_no_time_figures(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p6 = _by_event(points)[106]
        assert p6.status == "minus_laps"
        assert p6.position == 4
        assert p6.gap_to_median_pct is None
        assert p6.gap_to_winner_pct is None


class TestSeasonStartExcludesDNS:
    def test_started_excludes_dns_finished_counts_finished_and_minus_laps(self, dataset):
        seasons = build_season_completions(
            dataset["results"], dataset["events"], dataset["series"], _ATHLETE_ID
        )
        s2024 = next(s for s in seasons if s.season == 2024)
        # 6 filas propias en 2024 (V1,V2,V4-DNF,V5,V6,V7-DNS); DNS no cuenta
        # como salida → started=5. finished cuenta FINISHED+MINUS_LAPS: V1,
        # V2, V5 (finished sin tiempo SÍ cuenta) y V6 (minus_laps) = 4.
        assert s2024.started == 5
        assert s2024.finished == 4


class TestCategoryChange:
    def test_real_category_change_raises_flag(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p_2025_1 = _by_event(points)[201]
        assert p_2025_1.category_changed is True
        assert p_2025_1.previous_category_label == "Infantil A"

    def test_catalogue_rename_with_same_category_id_does_not_raise_flag(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p_2025_2 = _by_event(points)[202]
        assert p_2025_2.category_changed is False
        assert p_2025_2.previous_category_label is None
        # La etiqueta congelada del propio punto sí refleja el renombre.
        assert p_2025_2.category_label == "Pre-Juvenil A (renombrada)"

    def test_first_point_of_the_series_never_flags_a_change(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        assert points[0].category_changed is False


class TestCourseSpeed:
    def test_speed_present_only_where_a_setup_exists(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        by_event = _by_event(points)
        assert by_event[102].avg_speed_kmh is not None
        assert by_event[101].avg_speed_kmh is None


class TestNoCrossSeasonAggregate:
    def test_no_points_total_field_exists_on_the_point_schema(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        for p in points:
            assert not hasattr(p, "total_points")
            assert not hasattr(p, "career_points")

    def test_chronological_order_across_seasons(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        dates = [p.event_date for p in points]
        assert dates == sorted(dates)


class TestSkippedValida:
    def test_no_synthetic_entry_for_an_unraced_event(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        # V3 (event_id=103) nunca existió en el dataset — el atleta no
        # compitió esa válida. No debe aparecer ningún punto para ella.
        assert 103 not in _by_event(points)


class TestUnrelatedAthlete:
    def test_no_points_for_an_athlete_with_no_own_results(self, dataset):
        points = build_history_points(**dataset, athlete_id=999_999)
        assert points == []


class TestSeriesKindFilter:
    def test_all_points_default_to_cup_only(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        assert all(p.series_kind == "cup" for p in points)

    def test_championship_filter_excludes_every_cup_point(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID, series_kind="championship")
        assert points == []


class TestCaveats:
    def test_caveats_constant_has_the_five_standing_codes_in_order(self):
        assert HISTORY_CAVEATS == (
            "different_courses",
            "weather_surface",
            "small_fields",
            "non_finishers_excluded",
            "three_rider_categories",
        )


class TestNoThirdPartyLeak:
    def test_no_history_point_carries_a_competitor_id_attribute(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        for p in points:
            assert not hasattr(p, "competitor_id")
