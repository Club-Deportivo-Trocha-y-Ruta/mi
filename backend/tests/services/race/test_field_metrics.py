"""Tests de ``app.services.race.field_metrics.compute_field_metrics`` (feature 037).

Fixtures 100% ficticias (spec 037: nombres reales nunca en fixtures de test).
Dataset: 1 competidor propio (``competitor_id=1``) + 4 pares TyR/otros por
válida, 3 válidas de copa + 1 campeonato, una válida con DNF, y una válida
donde <50% de los finishers tienen prior_index (cobertura baja).

No usa DB: ``compute_field_metrics`` es pura (recibe listas ORM ya cargadas),
así que los objetos se instancian en memoria sin sesión.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.services.race.field_metrics import compute_field_metrics

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
        # n=4, pos=2 -> 100*(1-(2-1)/(4-1)) = 66.7
        out = _call(dataset)
        assert out[1]["position"] == 2
        assert out[1]["field_size"] == 4
        assert out[1]["percentile"] == pytest.approx(66.7, abs=0.05)

    def test_percentile_winner_is_100(self, dataset):
        out = _call(dataset)
        assert out[2]["position"] == 1
        assert out[2]["percentile"] == 100.0

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
        out = _call(dataset)
        entry = out[1]
        from statistics import median as _median

        times = [3_120_000, 3_000_000, 3_200_000, 3_400_000]
        med = _median(times)
        expected_pct = round(100.0 * (3_120_000 - med) / med, 1)
        assert entry["category_median_time_ms"] == med
        assert entry["gap_to_median_pct"] == expected_pct


class TestChampionshipLabel:
    def test_is_championship_flag_and_series_kind(self, dataset):
        out = _call(dataset)
        assert out[4]["is_championship"] is True
        assert out[4]["series_kind"] == "championship"
        assert out[1]["is_championship"] is False
        assert out[1]["series_kind"] == "cup"


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
