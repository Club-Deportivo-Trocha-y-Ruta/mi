"""Tests de ``app.services.race.audience`` (feature 045, data-model §1/§2).

Política única de audiencia para métricas de carrera: qué campos y qué
métricas nunca llegan a la familia. Pura, sin DB. Datos 100 % ficticios.
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel

from app.models.user import UserRole
from app.schemas.athlete_race_analysis import (
    AthleteRaceHistoryRead,
    EvolutionMetric,
    HistoryPoint,
)
from app.services.race.audience import (
    FAMILY_EXCLUDED_METRIC_FIELDS,
    FAMILY_FORBIDDEN_EVOLUTION_METRICS,
    Audience,
    audience_for_role,
    is_evolution_metric_allowed,
    redact_for_audience,
    serialize_for_audience,
)
from app.services.race.field_metrics import MetricSet

# data-model §1: columnas «Coach» ✓ / «Family» ✓ del MetricSet.
_FAMILY_VISIBLE_METRIC_FIELDS = {
    "field_size",
    "timed_finishers",
    "position",
    "percentile",
    "gap_to_median_pct",
}
_COACH_ONLY_METRIC_FIELDS = {
    "gap_to_winner_pct",
    "gap_to_winner_ms",
    "gap_to_podium_pct",
    "gap_to_podium_ms",
}


class TestAudienceForRole:
    @pytest.mark.parametrize("role", [UserRole.coach, UserRole.admin])
    def test_staff_roles_are_coach_audience(self, role):
        assert audience_for_role(role) is Audience.COACH

    @pytest.mark.parametrize("role", [UserRole.parent, UserRole.athlete])
    def test_every_other_role_is_family_audience(self, role):
        # Fail-closed: un rol no-staff nunca hereda la vista del coach.
        assert audience_for_role(role) is Audience.FAMILY


class TestPolicyDeclaration:
    def test_metric_set_partition_matches_data_model(self):
        """Cada campo de ``MetricSet`` es de familia o solo de coach — nunca
        queda un campo nuevo sin decidir (data-model §1)."""
        all_fields = set(MetricSet.__annotations__)
        excluded = all_fields & FAMILY_EXCLUDED_METRIC_FIELDS
        visible = all_fields - FAMILY_EXCLUDED_METRIC_FIELDS
        assert excluded == _COACH_ONLY_METRIC_FIELDS
        assert visible == _FAMILY_VISIBLE_METRIC_FIELDS

    def test_legacy_names_of_the_winner_and_podium_gaps_are_excluded_too(self):
        # ``compute_field_metrics`` / ``EvolutionPoint`` conservan los nombres
        # heredados de 037/039 — la política los cubre con los canónicos.
        assert {"gap_pct", "gap_to_p1_ms", "gap_to_p3_ms"} <= FAMILY_EXCLUDED_METRIC_FIELDS

    def test_only_the_podium_gap_evolution_metric_is_forbidden_for_family(self):
        assert FAMILY_FORBIDDEN_EVOLUTION_METRICS == {EvolutionMetric.PODIUM_GAP_MS}


class TestEvolutionMetricGate:
    @pytest.mark.parametrize("metric", list(EvolutionMetric))
    def test_coach_may_request_every_metric(self, metric):
        assert is_evolution_metric_allowed(metric, Audience.COACH) is True

    @pytest.mark.parametrize("metric", list(EvolutionMetric))
    def test_family_may_request_all_but_the_forbidden_ones(self, metric):
        allowed = is_evolution_metric_allowed(metric, Audience.FAMILY)
        assert allowed is (metric not in FAMILY_FORBIDDEN_EVOLUTION_METRICS)


class TestRedactForAudience:
    def test_family_loses_excluded_keys_at_any_depth(self):
        payload = {
            "points": [
                {"event_id": 1, "gap_to_winner_pct": 3.2, "gap_to_median_pct": -1.0},
                {"event_id": 2, "nested": {"gap_pct": 0.0, "position": 4}},
            ],
            "gap_to_podium_ms": 1200,
            "caveats": ["small_fields"],
        }
        out = redact_for_audience(payload, Audience.FAMILY)
        assert out == {
            "points": [
                {"event_id": 1, "gap_to_median_pct": -1.0},
                {"event_id": 2, "nested": {"position": 4}},
            ],
            "caveats": ["small_fields"],
        }

    def test_keys_are_removed_not_nulled(self):
        out = redact_for_audience({"gap_to_podium_pct": None, "position": 1}, Audience.FAMILY)
        assert "gap_to_podium_pct" not in out

    def test_coach_payload_is_untouched(self):
        payload = {"gap_to_winner_pct": 3.2, "gap_to_podium_pct": 1.0, "position": 2}
        assert redact_for_audience(payload, Audience.COACH) == payload

    def test_input_is_never_mutated(self):
        payload = {"points": [{"gap_pct": 1.0, "position": 2}]}
        redact_for_audience(payload, Audience.FAMILY)
        assert payload == {"points": [{"gap_pct": 1.0, "position": 2}]}

    def test_scalars_pass_through(self):
        assert redact_for_audience(5, Audience.FAMILY) == 5
        assert redact_for_audience("gap_pct", Audience.FAMILY) == "gap_pct"

    def test_metric_set_family_variant_carries_only_the_family_subset(self):
        metric_set: MetricSet = {
            "field_size": 6,
            "timed_finishers": 5,
            "position": 2,
            "percentile": 75.0,
            "gap_to_median_pct": -2.5,
            "gap_to_winner_pct": 1.5,
            "gap_to_winner_ms": 45_000,
            "gap_to_podium_pct": -0.5,
            "gap_to_podium_ms": -1500,
        }
        assert set(redact_for_audience(metric_set, Audience.FAMILY)) == _FAMILY_VISIBLE_METRIC_FIELDS
        assert set(redact_for_audience(metric_set, Audience.COACH)) == set(metric_set)


def _history_point(**overrides) -> HistoryPoint:
    base = dict(
        event_id=1,
        event_date=date(2024, 2, 1),
        season=2024,
        label="Válida 1 — Pista ficticia",
        series_id=1,
        series_name="Copa Valle",
        series_kind="cup",
        category_code="INF_A",
        category_label="Infantil A",
        category_changed=False,
        status="finished",
        position=2,
        field_size=6,
        timed_finishers=6,
        percentile=80.0,
        gap_to_median_pct=-1.5,
        gap_to_winner_pct=2.0,
        gap_to_podium_pct=0.5,
        points_awarded=18,
    )
    base.update(overrides)
    return HistoryPoint(**base)


class TestSerializeForAudience:
    def test_family_dump_omits_winner_and_podium_gaps(self):
        model = AthleteRaceHistoryRead(points=[_history_point()], seasons=[], caveats=[])
        out = serialize_for_audience(model, Audience.FAMILY)
        point = out["points"][0]
        assert "gap_to_winner_pct" not in point
        assert "gap_to_podium_pct" not in point
        assert point["gap_to_median_pct"] == -1.5
        assert point["percentile"] == 80.0

    def test_coach_dump_keeps_every_field_including_nulls(self):
        model = AthleteRaceHistoryRead(
            points=[_history_point(gap_to_podium_pct=None)], seasons=[], caveats=[]
        )
        point = serialize_for_audience(model, Audience.COACH)["points"][0]
        assert point["gap_to_winner_pct"] == 2.0
        assert point["gap_to_podium_pct"] is None

    def test_dump_is_json_ready(self):
        model = AthleteRaceHistoryRead(points=[_history_point()], seasons=[], caveats=[])
        out = serialize_for_audience(model, Audience.COACH)
        assert out["points"][0]["event_date"] == "2024-02-01"

    def test_works_for_any_pydantic_model(self):
        class Row(BaseModel):
            position: int
            gap_to_podium_ms: int | None = None

        out = serialize_for_audience(Row(position=1, gap_to_podium_ms=900), Audience.FAMILY)
        assert out == {"position": 1}
