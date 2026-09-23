"""Tests de ``app.services.race.field_metrics.compute_field_metrics`` (feature 037).

Fixtures 100% ficticias (spec 037: nombres reales nunca en fixtures de test).
Dataset: 1 competidor propio (``competitor_id=1``) + 4 pares TyR/otros por
válida, 3 válidas de copa + 1 campeonato, una válida con DNF, y una válida
donde <50% de los finishers tienen prior_index (cobertura baja).

No usa DB: ``compute_field_metrics`` es pura (recibe listas ORM ya cargadas),
así que los objetos se instancian en memoria sin sesión.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, get_protocol_members

import pytest

from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.services.race.field_metrics import (
    MIN_FIELD,
    MetricInput,
    compute_category_metrics,
    compute_field_metrics,
)

_SEASON = 2026
_CAT_ID = 1
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _series(sid: int, kind=RaceSeriesKind.cup, name="Copa Valle") -> RaceSeries:
    return RaceSeries(
        id=sid,
        name=name,
        season_year=_SEASON,
        organizer="Liga Vallecaucana",
        points_scheme_code="STD",
        kind=kind,
        level=RaceSeriesLevel.departmental,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _event(eid: int, series_id: int, seq: int, d: date, championship=False) -> RaceEvent:
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


def _category() -> RaceCategory:
    return RaceCategory(
        id=_CAT_ID,
        code="INF_A",
        label="Infantil A",
        sex=CategoryGender.MIXED,
        sort_order=1,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _result(
    rid: int,
    event_id: int,
    competitor_id: int,
    position: int | None,
    time_ms: int | None,
    status: ResultStatus = ResultStatus.FINISHED,
) -> RaceResult:
    return RaceResult(
        id=rid,
        event_id=event_id,
        category_id=_CAT_ID,
        competitor_id=competitor_id,
        athlete_id=None,
        position=position,
        status=status,
        race_time_ms=time_ms,
        laps_behind=1 if status == ResultStatus.MINUS_LAPS else None,
        points_awarded=0,
        created_by_user_id=1,
        created_at=_NOW,
        updated_at=_NOW,
    )


ATHLETE_COMPETITOR_ID = 1


@pytest.fixture()
def dataset():
    """3 válidas de copa + 1 campeonato; una con DNF; una con cobertura <50%."""
    series_cup = _series(1, kind=RaceSeriesKind.cup, name="Copa Valle")
    series_champ = _series(2, kind=RaceSeriesKind.championship, name="Cto. Departamental")
    series = [series_cup, series_champ]

    ev1 = _event(1, 1, 1, date(2026, 2, 1))
    ev2 = _event(2, 1, 2, date(2026, 3, 1))
    ev3 = _event(3, 1, 3, date(2026, 4, 1))
    ev_champ = _event(4, 2, 1, date(2026, 5, 1), championship=True)
    events = [ev1, ev2, ev3, ev_champ]

    categories = [_category()]

    results: list[RaceResult] = []
    rid = 1

    # Válida 1: campo de 4, atleta 1 termina 2º. Sin historia previa -> sin prior.
    for comp_id, pos, t in [(1, 2, 3_120_000), (2, 1, 3_000_000), (3, 3, 3_200_000), (4, 4, 3_400_000)]:
        results.append(_result(rid, 1, comp_id, pos, t))
        rid += 1

    # Válida 2: campo de 4, atleta 1 termina 1º. Todos tienen historia (válida 1) -> cobertura 100%.
    for comp_id, pos, t in [(1, 1, 2_900_000), (2, 2, 3_000_000), (3, 3, 3_100_000), (4, 4, 3_300_000)]:
        results.append(_result(rid, 2, comp_id, pos, t))
        rid += 1

    # Válida 3: campo de 4, atleta 1 con DNF (sin tiempo/posición). Otros 3 finished.
    results.append(_result(rid, 3, ATHLETE_COMPETITOR_ID, None, None, status=ResultStatus.DNF))
    rid += 1
    for comp_id, pos, t in [(2, 1, 2_950_000), (3, 2, 3_050_000), (4, 3, 3_150_000)]:
        results.append(_result(rid, 3, comp_id, pos, t))
        rid += 1

    # Válida 4 (campeonato): campo de 6, atleta 1 termina 2º. Solo comp_id 1 y 2
    # tienen historia previa a esta fecha (2 de 6 = 33% < 50%) -> cobertura baja.
    champ_rows = [
        (1, 2, 3_050_000),
        (2, 1, 3_000_000),
        (5, 3, 3_100_000),
        (6, 4, 3_200_000),
        (7, 5, 3_300_000),
        (8, 6, 3_400_000),
    ]
    for comp_id, pos, t in champ_rows:
        results.append(_result(rid, 4, comp_id, pos, t))
        rid += 1

    return {
        "results": results,
        "events": events,
        "series": series,
        "categories": categories,
    }


def _call(dataset, competitor_id=ATHLETE_COMPETITOR_ID, season=_SEASON):
    return compute_field_metrics(
        results=dataset["results"],
        events=dataset["events"],
        series=dataset["series"],
        categories=dataset["categories"],
        competitor_id=competitor_id,
        season=season,
    )


class TestBasicShape:
    def test_returns_one_entry_per_event_with_own_result(self, dataset):
        out = _call(dataset)
        assert set(out.keys()) == {1, 2, 3, 4}

    def test_no_third_party_competitor_ids_in_output(self, dataset):
        out = _call(dataset)
        for entry in out.values():
            for key in entry:
                assert key != "competitor_id"

    def test_no_entries_for_unrelated_competitor(self, dataset):
        out = _call(dataset, competitor_id=999)
        assert out == {}

    def test_empty_when_no_season_events(self, dataset):
        out = _call(dataset, season=1999)
        assert out == {}


class TestPercentileAndPosition:
    def test_percentile_field_of_4_second_place(self, dataset):
        # feature 045 (data-model §1): el percentil ahora es por TIEMPO, no
        # por posición, y queda en None por debajo de MIN_FIELD=5 timed
        # finishers. Válida 1 tiene 4 FINISHED -> gate, no formula.
        out = _call(dataset)
        assert out[1]["position"] == 2
        assert out[1]["field_size"] == 4
        assert out[1]["timed_finishers"] == 4
        assert out[1]["percentile"] is None

    def test_percentile_winner_is_100(self, dataset):
        # feature 045: mismo gate MIN_FIELD=5 (válida 2 tiene 4 timed
        # finishers) -> None en vez del antiguo 100.0 basado en posición.
        out = _call(dataset)
        assert out[2]["position"] == 1
        assert out[2]["percentile"] is None

    def test_dnf_has_no_position_or_percentile(self, dataset):
        out = _call(dataset)
        assert out[3]["position"] is None
        assert out[3]["percentile"] is None
        assert out[3]["race_time_ms"] is None
        # field_size cuenta finishers (con tiempo); el propio DNF no computa.
        assert out[3]["field_size"] == 3


class TestGaps:
    def test_gap_to_p1_and_gap_pct(self, dataset):
        out = _call(dataset)
        entry = out[1]
        assert entry["gap_to_p1_ms"] == 120_000
        assert entry["gap_pct"] == pytest.approx(4.0, abs=0.01)

    def test_gap_to_p3(self, dataset):
        out = _call(dataset)
        entry = out[1]
        assert entry["gap_to_p3_ms"] == 3_120_000 - 3_200_000

    def test_gap_to_median(self, dataset):
        # feature 045: gap_to_median_pct comparte la puerta MIN_FIELD=5 con
        # percentile (data-model §1 "same null rules") -> None con 4 timed
        # finishers. category_median_time_ms (el valor crudo en ms, no la
        # métrica porcentual) no lleva puerta y sigue calculándose siempre.
        out = _call(dataset)
        entry = out[1]
        from statistics import median as _median

        times = [3_120_000, 3_000_000, 3_200_000, 3_400_000]
        med = _median(times)
        assert entry["category_median_time_ms"] == med
        assert entry["gap_to_median_pct"] is None


class TestChampionshipLabel:
    def test_is_championship_flag_and_series_kind(self, dataset):
        out = _call(dataset)
        assert out[4]["is_championship"] is True
        assert out[4]["series_kind"] == "championship"
        assert out[1]["is_championship"] is False
        assert out[1]["series_kind"] == "cup"


class TestSeriesFields:
    """``series_id``/``series_name``/``series_short_name`` (hotfix multicopa)."""

    def test_rows_carry_series_id_and_name(self, dataset):
        out = _call(dataset)
        assert out[1]["series_id"] == 1
        assert out[1]["series_name"] == "Copa Valle"
        assert out[4]["series_id"] == 2
        assert out[4]["series_name"] == "Cto. Departamental"

    def test_series_short_name_none_when_column_absent(self, dataset):
        """``RaceSeries.short_name`` puede no existir aún (worker paralelo) —
        ``getattr`` con default no debe romper ni cuando el atributo falta."""
        out = _call(dataset)
        assert out[1]["series_short_name"] is None

    def test_series_short_name_read_via_getattr_when_present(self, dataset):
        """Cuando el atributo SÍ existe (columna ya aterrizada), se expone."""
        for s in dataset["series"]:
            if s.id == 1:
                s.short_name = "Copa Valle CV"
        out = _call(dataset)
        assert out[1]["series_short_name"] == "Copa Valle CV"


class TestPriorIndexAndExpectedPosition:
    def test_first_valida_has_no_prior_and_no_expected_position(self, dataset):
        out = _call(dataset)
        assert out[1]["prior_index"] is None
        assert out[1]["expected_position"] is None
        assert out[1]["coverage_with_prior"] == 0.0

    def test_second_valida_full_coverage_computes_expected_position(self, dataset):
        out = _call(dataset)
        entry = out[2]
        assert entry["coverage_with_prior"] == 1.0
        assert entry["prior_index"] is not None
        assert entry["expected_position"] is not None
        assert entry["field_strength"] is not None
        assert entry["delta_vs_expected"] == entry["expected_position"] - entry["position"]

    def test_low_coverage_valida_has_null_expected_position(self, dataset):
        out = _call(dataset)
        entry = out[4]
        assert entry["coverage_with_prior"] < 0.5
        assert entry["expected_position"] is None
        assert entry["delta_vs_expected"] is None
        assert entry["field_strength"] is None
        # prior_index propio SÍ se calcula (el atleta corrió en válida 1 y 2 antes).
        assert entry["prior_index"] is not None


class TestJsonSerializable:
    def test_all_values_json_native(self, dataset):
        import json

        out = _call(dataset)
        json.dumps(out)  # no debe lanzar (sin numpy types)


@pytest.fixture()
def dataset_minus_laps():
    """1 válida: atleta FINISHED 2º, un tercero MINUS_LAPS y otro FINISHED."""
    series = [_series(1, kind=RaceSeriesKind.cup, name="Copa Valle")]
    events = [_event(1, 1, 1, date(2026, 2, 1))]
    categories = [_category()]

    results = [
        _result(1, 1, ATHLETE_COMPETITOR_ID, 2, 3_120_000, status=ResultStatus.FINISHED),
        _result(2, 1, 2, 1, 3_000_000, status=ResultStatus.FINISHED),
        _result(3, 1, 3, 3, 3_600_000, status=ResultStatus.MINUS_LAPS),
    ]
    return {"results": results, "events": events, "series": series, "categories": categories}


@pytest.fixture()
def dataset_athlete_minus_laps():
    """1 válida: el propio atleta termina con MINUS_LAPS (posición 3 de 3)."""
    series = [_series(1, kind=RaceSeriesKind.cup, name="Copa Valle")]
    events = [_event(1, 1, 1, date(2026, 2, 1))]
    categories = [_category()]

    results = [
        _result(1, 1, 2, 1, 3_000_000, status=ResultStatus.FINISHED),
        _result(2, 1, 3, 2, 3_100_000, status=ResultStatus.FINISHED),
        _result(3, 1, ATHLETE_COMPETITOR_ID, 3, 3_600_000, status=ResultStatus.MINUS_LAPS),
    ]
    return {"results": results, "events": events, "series": series, "categories": categories}


class TestMinusLapsCountsAsFieldMember:
    def test_third_party_minus_laps_counts_in_field_size(self, dataset_minus_laps):
        out = _call(dataset_minus_laps)
        # 3 corredores terminaron (2 FINISHED + 1 MINUS_LAPS) -> pelotón de 3, no 2.
        assert out[1]["field_size"] == 3
        assert out[1]["position"] == 2
        # feature 045: percentile ahora es por tiempo y solo 2 filas son
        # FINISHED con tiempo (timed_finishers=2) -> gate MIN_FIELD=5, None
        # en vez del antiguo 50.0 basado en posición.
        assert out[1]["timed_finishers"] == 2
        assert out[1]["percentile"] is None

    def test_third_party_minus_laps_time_excluded_from_gap_and_median(self, dataset_minus_laps):
        out = _call(dataset_minus_laps)
        entry = out[1]
        # gap/mediana solo entre FINISHED (atleta 3_120_000 vs líder 3_000_000),
        # el tiempo 3_600_000 del MINUS_LAPS nunca entra en la comparación.
        assert entry["gap_to_p1_ms"] == 120_000
        assert entry["gap_pct"] == pytest.approx(4.0, abs=0.01)
        assert entry["category_median_time_ms"] == 3_060_000

    def test_athlete_with_minus_laps_has_position_but_no_time_fields(self, dataset_athlete_minus_laps):
        out = _call(dataset_athlete_minus_laps)
        entry = out[1]
        assert entry["field_size"] == 3
        assert entry["position"] == 3
        # feature 045: percentile es por tiempo -> solo aplica a FINISHED
        # estricto con race_time_ms. Un MINUS_LAPS nunca es elegible (no es
        # comparable en tiempo), así que ahora es None en vez del antiguo
        # valor no-None basado en posición.
        assert entry["percentile"] is None
        # El tiempo propio no es comparable (recorrió menos vueltas) -> None.
        assert entry["race_time_ms"] is None
        assert entry["gap_to_p1_ms"] is None
        assert entry["gap_pct"] is None
        assert entry["gap_to_median_pct"] is None


def _rows(specs: list[tuple], event_id: int = 1) -> list[RaceResult]:
    """Atajo para construir filas de una sola (válida, categoría) a partir
    de tuplas ``(rid, competitor_id, position, time_ms, status)``."""
    return [
        _result(rid, event_id, comp_id, pos, t, status=status)
        for rid, comp_id, pos, t, status in specs
    ]


class TestTimeBasedPercentile:
    """T004 (045, data-model §1 / research R-01): el percentil deja de ser
    por posición y pasa a ser por TIEMPO sobre ``timed_finishers``. Probado
    vía ``compute_category_metrics`` (T008), el motor compartido que
    ``compute_field_metrics`` reutiliza internamente."""

    def test_fastest_is_100_slowest_is_0(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
                (5, 5, 5, 120_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[1]["percentile"] == 100.0  # más rápido
        assert out[5]["percentile"] == 0.0  # más lento
        assert out[3]["percentile"] == 50.0  # punto medio exacto
        assert all(ms["timed_finishers"] == 5 for ms in out.values())

    def test_ties_get_equal_percentile(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 2, 105_000, ResultStatus.FINISHED),  # empate en tiempo con #2
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
                (5, 5, 5, 120_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[2]["percentile"] == out[3]["percentile"] == 75.0

    def test_t_max_equals_t_min_is_none(self):
        # Todo el pelotón cronometrado con el mismo tiempo -> división por
        # cero evitada explícitamente; None para todos, no una excepción.
        rows = _rows(
            [(rid, rid, rid, 100_000, ResultStatus.FINISHED) for rid in range(1, 6)]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert len(out) == 5
        assert all(ms["percentile"] is None for ms in out.values())

    def test_below_min_field_is_none(self):
        assert MIN_FIELD == 5
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert all(ms["timed_finishers"] == 4 for ms in out.values())
        assert all(ms["percentile"] is None for ms in out.values())

    def test_minus_laps_rider_has_no_percentile_but_counts_in_field_size(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
                (5, 5, 5, 120_000, ResultStatus.FINISHED),
                (6, 6, 6, 200_000, ResultStatus.MINUS_LAPS),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[6]["field_size"] == 6
        assert out[6]["timed_finishers"] == 5
        assert out[6]["position"] == 6
        assert out[6]["percentile"] is None
        # el resto del pelotón sí saca percentil (5 timed finishers >= MIN_FIELD).
        assert out[1]["percentile"] == 100.0

    def test_dnf_dns_dsq_have_no_percentile_and_do_not_count_in_field_size(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
                (5, 5, 5, 120_000, ResultStatus.FINISHED),
                (6, 6, None, None, ResultStatus.DNF),
                (7, 7, None, None, ResultStatus.DNS),
                (8, 8, None, None, ResultStatus.DSQ),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        for rid in (6, 7, 8):
            assert out[rid]["position"] is None
            assert out[rid]["percentile"] is None
        # field_size solo cuenta FINISHED + MINUS_LAPS (5); DNF/DNS/DSQ no suman.
        assert out[1]["field_size"] == 5


class TestTimedFinishersAndGaps:
    """T005 (045): ``timed_finishers``, ``gap_to_podium_pct`` (brecha vs. P3
    oficial) y el gate de ``gap_to_median_pct`` por debajo de MIN_FIELD."""

    def test_timed_finishers_excludes_minus_laps_and_dnf(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 200_000, ResultStatus.MINUS_LAPS),
                (4, 4, None, None, ResultStatus.DNF),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[1]["field_size"] == 3
        assert out[1]["timed_finishers"] == 2

    def test_gap_to_podium_pct_against_official_p3(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),  # P3 oficial
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
                (5, 5, 5, 120_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[3]["gap_to_podium_pct"] == 0.0
        assert out[3]["gap_to_podium_ms"] == 0
        # rider 5: 100*(120_000-110_000)/110_000 = 9.1
        assert out[5]["gap_to_podium_pct"] == pytest.approx(9.1, abs=0.05)
        assert out[5]["gap_to_podium_ms"] == 10_000
        # rider 1, más rápido que el podio -> brecha negativa.
        assert out[1]["gap_to_podium_pct"] == pytest.approx(-9.1, abs=0.05)

    def test_gap_to_podium_pct_none_without_official_p3(self):
        # Solo 2 finishers -> nadie ocupa oficialmente la posición 3.
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[1]["gap_to_podium_pct"] is None
        assert out[2]["gap_to_podium_pct"] is None
        assert out[1]["gap_to_podium_ms"] is None
        # gap_to_winner_pct no lleva puerta de tamaño mínimo: sí se calcula.
        assert out[2]["gap_to_winner_pct"] == pytest.approx(5.0, abs=0.05)

    def test_gap_to_winner_ms_against_official_p1(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),  # P1 oficial
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 120_000, ResultStatus.FINISHED),
                (4, 4, 4, 200_000, ResultStatus.MINUS_LAPS),
                (5, 5, None, None, ResultStatus.DNF),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[1]["gap_to_winner_ms"] == 0  # P1 propio -> 0 explícito, no None
        assert out[2]["gap_to_winner_ms"] == 5_000
        assert out[3]["gap_to_winner_ms"] == 20_000
        # Sin tiempo comparable (MINUS_LAPS / DNF) -> None, igual que el % de brecha.
        assert out[4]["gap_to_winner_ms"] is None
        assert out[5]["gap_to_winner_ms"] is None

    def test_gap_to_winner_ms_has_no_min_field_gate(self):
        # 2 finishers (< MIN_FIELD): percentil/mediana en None, pero la brecha
        # oficial vs. P1 sí se calcula (research R-04).
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[2]["percentile"] is None
        assert out[2]["gap_to_winner_ms"] == 5_000

    def test_gap_to_winner_ms_none_without_official_p1(self):
        # Nadie ocupa oficialmente la posición 1 (p. ej. el P1 fue descalificado).
        rows = _rows(
            [
                (1, 1, 2, 105_000, ResultStatus.FINISHED),
                (2, 2, 3, 110_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[1]["gap_to_winner_ms"] is None
        assert out[2]["gap_to_winner_ms"] is None

    def test_gap_to_winner_ms_uses_official_p1_not_fastest_time(self):
        # R-04: con una penalización, el P1 OFICIAL (102_000) no es el más
        # rápido (100_000, P2). La brecha va contra el oficial -> negativa
        # para el más rápido.
        rows = _rows(
            [
                (1, 1, 1, 102_000, ResultStatus.FINISHED),  # P1 oficial (penalizado)
                (2, 2, 2, 100_000, ResultStatus.FINISHED),  # el más rápido
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert out[2]["gap_to_winner_ms"] == -2_000
        assert out[1]["gap_to_winner_ms"] == 0

    def test_gap_to_median_pct_none_below_min_field(self):
        # 4 timed finishers < MIN_FIELD=5 -> gap_to_median_pct en None,
        # misma puerta que percentile (data-model §1, "same null rules").
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert all(ms["timed_finishers"] == 4 for ms in out.values())
        assert all(ms["gap_to_median_pct"] is None for ms in out.values())

    def test_gap_to_median_pct_computed_at_min_field(self):
        rows = _rows(
            [
                (1, 1, 1, 100_000, ResultStatus.FINISHED),
                (2, 2, 2, 105_000, ResultStatus.FINISHED),
                (3, 3, 3, 110_000, ResultStatus.FINISHED),
                (4, 4, 4, 115_000, ResultStatus.FINISHED),
                (5, 5, 5, 120_000, ResultStatus.FINISHED),
            ]
        )
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        # mediana = 110_000 (posición 3) -> brecha 0 para el mediano.
        assert out[3]["gap_to_median_pct"] == 0.0


class TestComputeCategoryMetrics:
    """T008 (045): punto de entrada nuevo, un MetricSet por fila de una
    (válida, categoría). Pura, O(n), sin consultas a la base de datos."""

    def test_returns_one_entry_per_row_including_non_finishers(self):
        rows = [
            _result(1, 1, 1, 1, 100_000, status=ResultStatus.FINISHED),
            _result(2, 1, 2, 2, 105_000, status=ResultStatus.FINISHED),
            _result(3, 1, 3, None, None, status=ResultStatus.DNS),
        ]
        out = compute_category_metrics(rows, event_id=1, category_id=_CAT_ID)
        assert set(out.keys()) == {1, 2, 3}
        assert out[3]["position"] is None

    def test_filters_by_event_and_category_ignoring_other_rows(self):
        row_target = _result(1, 1, 1, 1, 100_000, status=ResultStatus.FINISHED)
        row_other_event = _result(2, 2, 1, 1, 100_000, status=ResultStatus.FINISHED)
        row_other_category = RaceResult(
            id=3,
            event_id=1,
            category_id=99,
            competitor_id=1,
            athlete_id=None,
            position=1,
            status=ResultStatus.FINISHED,
            race_time_ms=100_000,
            laps_behind=None,
            points_awarded=0,
            created_by_user_id=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
        out = compute_category_metrics(
            [row_target, row_other_event, row_other_category], event_id=1, category_id=_CAT_ID
        )
        assert set(out.keys()) == {1}

    def test_excludes_soft_deleted_rows(self):
        row = _result(1, 1, 1, 1, 100_000, status=ResultStatus.FINISHED)
        row.deleted_at = _NOW
        out = compute_category_metrics([row], event_id=1, category_id=_CAT_ID)
        assert out == {}

    def test_shares_math_with_compute_field_metrics(self, dataset):
        # El campeonato (válida 4) tiene 6 FINISHED -> percentile por tiempo
        # elegible (>= MIN_FIELD). compute_field_metrics y
        # compute_category_metrics deben coincidir para el mismo resultado
        # (invariante SC-002 de la 045: un número, un solo significado).
        field_out = _call(dataset)
        champ_result_id = next(
            r.id
            for r in dataset["results"]
            if r.event_id == 4 and r.competitor_id == ATHLETE_COMPETITOR_ID
        )
        cat_out = compute_category_metrics(dataset["results"], event_id=4, category_id=_CAT_ID)

        assert field_out[4]["percentile"] is not None
        assert field_out[4]["percentile"] == cat_out[champ_result_id]["percentile"]
        assert (
            field_out[4]["timed_finishers"]
            == cat_out[champ_result_id]["timed_finishers"]
            == 6
        )
        assert field_out[4]["gap_pct"] == cat_out[champ_result_id]["gap_to_winner_pct"]
        assert field_out[4]["gap_to_p3_ms"] == cat_out[champ_result_id]["gap_to_podium_ms"]
        assert field_out[4]["gap_to_p1_ms"] == cat_out[champ_result_id]["gap_to_winner_ms"]
        assert (
            field_out[4]["gap_to_podium_pct"] == cat_out[champ_result_id]["gap_to_podium_pct"]
        )


@dataclass(frozen=True)
class _LightRow:
    """Fila liviana SIN ORM que cumple ``MetricInput`` (como el dataclass que
    arma ``results_read.py`` desde columnas)."""

    id: int
    event_id: int
    category_id: int
    status: ResultStatus
    position: Optional[int]
    race_time_ms: Optional[int]
    deleted_at: Optional[datetime] = None


class TestMetricInputProtocol:
    """Inversión de dependencias: el motor depende de ``MetricInput`` (un
    Protocol), no de ``RaceResult``. Cualquier objeto con esos atributos sirve
    y ``RaceResult`` la sigue satisfaciendo (los llamadores no cambian)."""

    _SPECS = [
        (1, 1, 1, 100_000, ResultStatus.FINISHED),
        (2, 2, 2, 105_000, ResultStatus.FINISHED),
        (3, 3, 3, 110_000, ResultStatus.FINISHED),
        (4, 4, 4, 115_000, ResultStatus.FINISHED),
        (5, 5, 5, 120_000, ResultStatus.FINISHED),
        (6, 6, 6, 200_000, ResultStatus.MINUS_LAPS),
        (7, 7, None, None, ResultStatus.DNF),
    ]

    def test_protocol_members_are_exactly_what_the_engine_reads(self):
        assert set(get_protocol_members(MetricInput)) == {
            "id",
            "event_id",
            "category_id",
            "status",
            "position",
            "race_time_ms",
            "deleted_at",
        }

    def test_race_result_still_satisfies_the_protocol(self):
        # Ancla el Protocol al modelo: si una columna se renombra, esto falla
        # en vez de romper en runtime dentro del motor.
        assert all(hasattr(RaceResult, name) for name in get_protocol_members(MetricInput))

    def test_light_rows_give_the_same_metrics_as_orm_rows(self):
        orm_rows = _rows(self._SPECS)
        light_rows = [
            _LightRow(
                id=rid, event_id=1, category_id=_CAT_ID, status=status,
                position=pos, race_time_ms=t,
            )
            for rid, _comp, pos, t, status in self._SPECS
        ]
        from_orm = compute_category_metrics(orm_rows, event_id=1, category_id=_CAT_ID)
        from_light = compute_category_metrics(light_rows, event_id=1, category_id=_CAT_ID)
        assert from_light == from_orm
        # Sanity: la comparación no es vacía (percentil calculado, MINUS_LAPS sin tiempo).
        assert from_light[3]["percentile"] == 50.0  # 110_000 entre 100_000 y 120_000
        assert from_light[6]["percentile"] is None

    def test_accepts_any_sequence_not_just_list(self):
        row = _LightRow(id=1, event_id=1, category_id=_CAT_ID, status=ResultStatus.FINISHED,
                        position=1, race_time_ms=100_000)
        assert set(compute_category_metrics((row,), event_id=1, category_id=_CAT_ID)) == {1}

    def test_soft_deleted_light_row_is_excluded(self):
        alive = _LightRow(id=1, event_id=1, category_id=_CAT_ID,
                          status=ResultStatus.FINISHED, position=1, race_time_ms=100_000)
        deleted = _LightRow(id=2, event_id=1, category_id=_CAT_ID,
                            status=ResultStatus.FINISHED, position=2, race_time_ms=105_000,
                            deleted_at=_NOW)
        out = compute_category_metrics([alive, deleted], event_id=1, category_id=_CAT_ID)
        assert set(out) == {1}
        assert out[1]["field_size"] == 1
