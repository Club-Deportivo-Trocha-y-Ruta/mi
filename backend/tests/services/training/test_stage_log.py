"""Tests para stage_log.py (feature 038 — bitácora de etapa).

Cubre:
- BADGE_LABELS / badge_label_for: nunca retorna el código crudo.
- to_parent_dto: key-set exacto (allow-list), remueve block_states /
  grounding_violations / analyst_reading.source_insight_id, aplica
  hidden_blocks.
- Límites de palabras aplicados por los validadores del modelo (regla de
  negocio, no solo tipo).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.services.training.stage_log import (
    BADGE_LABELS,
    AnalystReading,
    BadgeView,
    BlockState,
    EffortWeek,
    FamilyCompass,
    NextRace,
    NextSegment,
    Observation,
    PhotoView,
    StageLog,
    Summit,
    SummitKind,
    Waypoint,
    WaypointKind,
    badge_label_for,
    to_parent_dto,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_stage_log(**overrides) -> StageLog:
    defaults: dict = {
        "stage_number": 3,
        "period_label": "Junio 2026",
        "is_current_month": False,
        "athlete_first_name": "Atleta",
        "athlete_reference": "su hijo",
        "stage_title": "Una etapa de constancia y aprendizaje sobre la bici",
        "trail": [
            Waypoint(
                kind=WaypointKind.RACE,
                date=date(2026, 6, 12),
                label="Válida 3 · P2",
                sublabel="+4,1 % al P1",
                icon="map-pin",
            ),
        ],
        "summit": Summit(
            kind=SummitKind.RACE,
            title="P2 en la Válida 3",
            detail="Copa Valle · Prejuvenil A Femenino",
            caption="Un gran resultado que refleja el trabajo del mes.",
            date=date(2026, 6, 12),
        ),
        "observations": [
            Observation(
                claim="Mantuvo un ritmo de entrenamiento constante.",
                evidence="Asistió a 12 de 14 sesiones (86 %).",
                block_ref="attendance",
            ),
        ],
        "analyst_reading": AnalystReading(
            headline_family="El trabajo en curvas está dando resultado.",
            action_family="Practicar frenado antes de las curvas cerradas.",
            valida_label="Válida 3 · Copa Valle",
            source_insight_id=42,
        ),
        "effort_profile": [
            EffortWeek(week_label="1–7 jun", sessions_planned=3, sessions_attended=3, mean_rpe=6.0),
        ],
        "next_segment": NextSegment(
            focus_groups=["Frenado modulado"],
            next_race=NextRace(label="Válida 4", date=date(2026, 7, 10), venue="Cali", priority_label="Prioridad A"),
            text="Las próximas semanas se enfocan en frenado.",
        ),
        "family_compass": FamilyCompass(
            conversation_question="¿Qué fue lo que más disfrutó en la bici este mes?",
            monthly_challenge="Proponle preparar la bici antes de cada sesión.",
            what_to_watch="Observen cómo mejora el frenado en curvas.",
        ),
        "badges": [BadgeView(code="attendance_100", label="Asistencia 100 %", icon="award", earned_at=date(2026, 6, 30))],
        "photos": [PhotoView(thumbnail_url="https://example.com/thumb.jpg", caption="Entrenamiento de junio")],
        "coach_note": "Muy buen mes, sigue así.",
        "block_states": {"stage_title": BlockState.AI},
        "grounding_violations": [],
    }
    defaults.update(overrides)
    return StageLog(**defaults)


# ---------------------------------------------------------------------------
# BADGE_LABELS / badge_label_for
# ---------------------------------------------------------------------------


class TestBadgeLabels:
    def test_all_current_badge_types_mapped(self):
        # Códigos actuales de app/models/athlete_badge.py::BadgeType.
        for code in ("attendance_100", "attendance_90", "attendance_75", "first_podium", "mtp", "top10"):
            assert code in BADGE_LABELS

    def test_labels_are_not_raw_codes(self):
        for code, label in BADGE_LABELS.items():
            assert label != code
            assert "_" not in label

    def test_badge_label_for_known_code(self):
        assert badge_label_for("attendance_100") == "Asistencia 100 %"

    def test_badge_label_for_unknown_code_never_raw(self):
        label = badge_label_for("some_future_code")
        assert label != "some_future_code"
        assert "_" not in label

    def test_badge_label_for_empty_code(self):
        assert badge_label_for("") == "Insignia"


# ---------------------------------------------------------------------------
# to_parent_dto — allow-list explícito
# ---------------------------------------------------------------------------


class TestToParentDto:
    def test_exact_key_set(self):
        """Enumera explícitamente el set de claves esperado (allow-list)."""
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=[])

        expected_keys = {
            "schema_version",
            "stage_number",
            "period_label",
            "is_current_month",
            "athlete_first_name",
            "athlete_reference",
            "stage_title",
            "trail",
            "summit",
            "observations",
            "analyst_reading",
            "effort_profile",
            "next_segment",
            "family_compass",
            "badges",
            "photos",
            "coach_note",
        }
        assert set(dto.keys()) == expected_keys

    def test_never_contains_block_states_or_grounding_violations(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=[])
        assert "block_states" not in dto
        assert "grounding_violations" not in dto

    def test_analyst_reading_never_leaks_source_insight_id(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=[])
        assert dto["analyst_reading"] is not None
        assert "source_insight_id" not in dto["analyst_reading"]
        assert set(dto["analyst_reading"].keys()) == {
            "headline_family",
            "action_family",
            "valida_label",
        }

    def test_hidden_analyst_reading_becomes_none(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=["analyst_reading"])
        assert dto["analyst_reading"] is None

    def test_hidden_coach_note_becomes_none(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=["coach_note"])
        assert dto["coach_note"] is None

    def test_hidden_photos_becomes_empty_list(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=["photos"])
        assert dto["photos"] == []

    def test_hidden_badges_becomes_empty_list(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=["badges"])
        assert dto["badges"] == []

    def test_no_hidden_blocks_keeps_data(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=None)
        assert dto["photos"] != []
        assert dto["badges"] != []
        assert dto["coach_note"] is not None

    def test_unknown_hidden_block_is_ignored(self):
        stage_log = _minimal_stage_log()
        dto = to_parent_dto(stage_log, hidden_blocks=["not_a_real_block"])
        assert dto["photos"] != []


# ---------------------------------------------------------------------------
# Límites de palabras (regla de negocio)
# ---------------------------------------------------------------------------


class TestWordLimits:
    def test_stage_title_truncated_to_20_words(self):
        long_title = " ".join(["palabra"] * 40)
        stage_log = _minimal_stage_log(stage_title=long_title)
        assert len(stage_log.stage_title.split()) == 20

    def test_coach_note_truncated_to_60_words(self):
        long_note = " ".join(["palabra"] * 100)
        stage_log = _minimal_stage_log(coach_note=long_note)
        assert len(stage_log.coach_note.split()) == 60

    def test_observation_claim_truncated_to_35_words(self):
        obs = Observation(
            claim=" ".join(["palabra"] * 50),
            evidence="Asistió a 10 de 10 sesiones.",
            block_ref="attendance",
        )
        assert len(obs.claim.split()) == 35

    def test_observation_evidence_truncated_to_20_words(self):
        obs = Observation(
            claim="Mantuvo un buen ritmo.",
            evidence=" ".join(["palabra"] * 30),
            block_ref="attendance",
        )
        assert len(obs.evidence.split()) == 20

    def test_family_compass_question_always_ends_with_question_mark(self):
        compass = FamilyCompass(
            conversation_question="Qué fue lo más divertido de este mes",
            monthly_challenge="Reto del mes.",
            what_to_watch="Observen el frenado.",
        )
        assert compass.conversation_question.endswith("?")

    def test_family_compass_question_truncation_keeps_question_mark(self):
        long_question = " ".join(["palabra"] * 40) + "?"
        compass = FamilyCompass(
            conversation_question=long_question,
            monthly_challenge="Reto del mes.",
            what_to_watch="Observen el frenado.",
        )
        assert compass.conversation_question.endswith("?")
        assert len(compass.conversation_question.rstrip("?").split()) <= 30

    def test_trail_max_length_six(self):
        with pytest.raises(ValidationError):
            _minimal_stage_log(
                trail=[
                    Waypoint(kind=WaypointKind.RACE, date=date(2026, 6, i), label=f"W{i}", sublabel=None, icon="map-pin")
                    for i in range(1, 8)
                ]
            )

    def test_trail_allows_single_waypoint(self):
        """Edge case (mes de cero asistencia): trail de un solo waypoint es
        válido — no se exige un mínimo de 3."""
        stage_log = _minimal_stage_log(
            trail=[
                Waypoint(
                    kind=WaypointKind.NEXT_RACE,
                    date=date(2026, 8, 1),
                    label="Próxima: Válida V",
                    sublabel="Palmira",
                    icon="compass",
                    is_future=True,
                ),
            ],
        )
        assert len(stage_log.trail) == 1
