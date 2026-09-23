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
from app.services.race import field_metrics
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

    return {
        "results": results,
        "events": events,
        "series": series,
        "categories": categories,
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


def _lapped_field_dataset(*, own_time_ms: int, own_position: int) -> dict:
    """Una válida con Parrilla de 5 (4 cronometrados + 1 MINUS_LAPS) — el
    denominador del percentil es ``timed_finishers`` (4), no ``field_size``."""
    series = [_series(1, 2024)]
    events = [_event(301, 1, 1, date(2024, 4, 1))]
    categories = [_category(_CAT_A, "INF_A", "Infantil A")]
    results = [
        _result(1, 301, _CAT_A, 1, athlete_id=_ATHLETE_ID, position=own_position, time_ms=own_time_ms),
        _result(2, 301, _CAT_A, 2, position=1, time_ms=2_900_000),
        _result(3, 301, _CAT_A, 3, position=2, time_ms=3_000_000),
        _result(4, 301, _CAT_A, 4, position=3, time_ms=3_100_000),
        _result(
            5, 301, _CAT_A, 5, position=5, status=ResultStatus.MINUS_LAPS,
            time_ms=None, laps_behind=1,
        ),
    ]
    return {"results": results, "events": events, "series": series, "categories": categories}


class TestEngineIsTheSingleSource:
    """T012 (feature 045): ``history.py`` no cuenta ni re-puertea — lee del
    motor ``field_metrics`` los valores ya cerrados."""

    def test_percentile_is_gated_by_timed_finishers_not_by_parrilla(self):
        points = build_history_points(
            **_lapped_field_dataset(own_time_ms=3_200_000, own_position=4),
            athlete_id=_ATHLETE_ID,
        )
        (p,) = points
        assert p.field_size == 5  # Parrilla incluye al MINUS_LAPS
        assert p.timed_finishers == 4
        assert p.percentile is None
        assert p.gap_to_median_pct is None

    def test_percentile_is_time_based_not_position_based(self):
        dataset = _lapped_field_dataset(own_time_ms=3_200_000, own_position=4)
        # Quinto cronometrado (el MINUS_LAPS se reemplaza por un FINISHED lento)
        # para superar la puerta: tiempos 2.9 / 3.0 / 3.1 / 3.2 / 4.0.
        dataset["results"][-1] = _result(5, 301, _CAT_A, 5, position=5, time_ms=4_000_000)
        (p,) = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        assert p.timed_finishers == 5
        # 100 × (1 − (3.2 − 2.9) ÷ (4.0 − 2.9)) = 72.7 → 73. Por posición saldría 25.
        assert p.percentile == 73.0

    def test_gap_to_podium_pct_uses_the_official_third_place_time(self, dataset):
        by_event = _by_event(build_history_points(**dataset, athlete_id=_ATHLETE_ID))
        # V1: P3 = 3_200_000, atleta 3_100_000 → -3.125 % → -3.1.
        assert by_event[101].gap_to_podium_pct == -3.1
        # V2: P3 = 3_100_000, atleta 2_900_000 → -6.45 % → -6.5.
        assert by_event[102].gap_to_podium_pct == -6.5

    def test_gap_to_podium_pct_is_none_without_own_time_or_third_place_time(self, dataset):
        by_event = _by_event(build_history_points(**dataset, athlete_id=_ATHLETE_ID))
        assert by_event[104].gap_to_podium_pct is None  # DNF
        assert by_event[105].gap_to_podium_pct is None  # FINISHED sin tiempo
        assert by_event[106].gap_to_podium_pct is None  # MINUS_LAPS

    def test_every_metric_equals_the_engine_output(self, dataset):
        """SC-002 en pequeño: mismo (evento, categoría) → mismos números."""
        by_event = _by_event(build_history_points(**dataset, athlete_id=_ATHLETE_ID))
        engine = field_metrics.compute_field_metrics(
            dataset["results"], dataset["events"], dataset["series"],
            dataset["categories"], competitor_id=1, season=2024,
        )
        assert engine  # sanity: el motor sí produjo entradas
        for event_id, metrics in engine.items():
            p = by_event[event_id]
            assert p.field_size == metrics["field_size"]
            assert p.timed_finishers == metrics["timed_finishers"]
            assert p.percentile == metrics["percentile"]
            assert p.gap_to_median_pct == metrics["gap_to_median_pct"]
            assert p.gap_to_winner_pct == metrics["gap_pct"]
            assert p.gap_to_podium_pct == metrics["gap_to_podium_pct"]


class TestNonFinishers:
    def test_dnf_has_no_position_or_time(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        p4 = _by_event(points)[104]
        assert p4.status == "dnf"
        assert p4.position is None
        assert p4.gap_to_winner_pct is None

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


class TestWithholdBefore:
    """Filtro puro de la compuerta de familia (T080)."""

    def test_drops_own_and_field_rows_of_earlier_events_only(self):
        from app.services.race.history import withhold_before

        events = [
            SimpleNamespace(id=1, event_date=date(2024, 2, 1)),
            SimpleNamespace(id=2, event_date=date(2024, 3, 1)),
            SimpleNamespace(id=3, event_date=None),
        ]
        results = [SimpleNamespace(id=i, event_id=e) for i, e in enumerate((1, 1, 2, 2, 3))]
        kept = withhold_before(results, events, date(2024, 3, 1))
        assert [r.event_id for r in kept] == [2, 2]


def _aged_category(cid: int, code: str, label: str, *, sex=CategoryGender.M, age_min: int | None) -> RaceCategory:
    cat = _category(cid, code, label)
    cat.sex = sex
    cat.age_min = age_min
    return cat


def _two_valida_points(prev: RaceCategory, new: RaceCategory, *, same_season: bool = False):
    """Dos válidas del atleta: la primera en ``prev``, la segunda en ``new``."""
    series = [_series(1, 2024), _series(2, 2025)]
    events = [
        _event(101, 1, 1, date(2024, 2, 1)),
        _event(201, 1 if same_season else 2, 2 if same_season else 1, date(2025, 2, 1)),
    ]
    results = [
        _result(1, 101, prev.id, 1, athlete_id=_ATHLETE_ID, position=1, time_ms=3_000_000),
        _result(2, 201, new.id, 1, athlete_id=_ATHLETE_ID, position=1, time_ms=3_000_000),
    ]
    return build_history_points(
        results, events, series, [prev, new], _ATHLETE_ID
    )


class TestCategoryChangeKind:
    """``category_change_kind`` (FR-042, revisión UX T083)."""

    def test_older_band_same_sex_is_promotion(self):
        points = _two_valida_points(
            _aged_category(20, "INF_A", "Infantil A", age_min=11),
            _aged_category(21, "PJUV_A", "Prejuvenil A", age_min=13),
        )
        assert [p.category_change_kind for p in points] == [None, "promotion"]

    @pytest.mark.parametrize("prev_age,new_age", [(None, 13), (11, None), (None, None)])
    def test_unknown_ages_are_other(self, prev_age, new_age):
        points = _two_valida_points(
            _aged_category(20, "INF_A", "Infantil A", age_min=prev_age),
            _aged_category(21, "PJUV_A", "Prejuvenil A", age_min=new_age),
        )
        assert points[1].category_change_kind == "other"

    def test_sex_change_is_other(self):
        points = _two_valida_points(
            _aged_category(20, "INF_A", "Infantil A", sex=CategoryGender.MIXED, age_min=11),
            _aged_category(21, "PJUV_V", "Prejuvenil Varones", sex=CategoryGender.M, age_min=13),
        )
        assert points[1].category_change_kind == "other"

    def test_younger_band_is_other(self):
        points = _two_valida_points(
            _aged_category(20, "PJUV_A", "Prejuvenil A", age_min=13),
            _aged_category(21, "INF_A", "Infantil A", age_min=11),
        )
        assert points[1].category_change_kind == "other"

    def test_season_specific_restructure_is_other(self):
        # MASTER B se parte en B1/B2 para 2025: misma edad mínima → no es subir.
        points = _two_valida_points(
            _aged_category(20, "MASTER_B", "Master B", age_min=40),
            _aged_category(21, "MASTER_B1", "Master B1", age_min=40),
        )
        assert points[1].category_changed is True
        assert points[1].category_change_kind == "other"

    def test_restructure_within_the_same_season_is_other(self):
        points = _two_valida_points(
            _aged_category(20, "MASTER_B", "Master B", age_min=None),
            _aged_category(21, "MASTER_B2", "Master B2", age_min=45),
            same_season=True,
        )
        assert points[1].category_change_kind == "other"

    def test_no_change_is_none(self, dataset):
        points = build_history_points(**dataset, athlete_id=_ATHLETE_ID)
        by_event = _by_event(points)
        assert all(p.category_change_kind is None for p in points if not p.category_changed)
        # Catálogo del fixture sin edades → el cambio real A → B cae en "other".
        assert by_event[201].category_change_kind == "other"
