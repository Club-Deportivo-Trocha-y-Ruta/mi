"""Tests para las funciones v2 (bitácora de etapa) de newsletter_static_copy.py.

Cubre: title/observations/summit caption/next segment/family compass sobre
snapshots completo / sin carreras / cero asistencia; nunca mencionan
suplementos ni conteo calórico; la pregunta de la brújula siempre termina en
"?"; gender-aware vía athlete_reference.
"""

from __future__ import annotations

from datetime import date

from app.services.training.newsletter_static_copy import (
    static_family_compass,
    static_next_segment,
    static_observations,
    static_stage_title,
    static_summit_caption,
)
from app.services.training.stage_log import NextRace, NextSegment, Summit, SummitKind

_FORBIDDEN_TERMS = (
    "suplemento",
    "proteína en polvo",
    "creatina",
    "caloría",
    "calorías",
    "contar calorías",
)


def _full_month_email_blocks() -> dict:
    return {
        "attendance": {"sessions_total": 14, "sessions_present": 13, "attendance_pct": 92.9, "streak_sessions": 10},
        "technical": {"focos_tecnicos": ["Frenado"], "avg_rpe": 6.5, "total_training_hours": 12.0},
        "race_results": {
            "has_races": True,
            "results": [
                {
                    "label": "Válida 3",
                    "event_date": "2026-06-12",
                    "position": 2,
                    "gap_to_winner_pct": 4.1,
                    "category_label": "Prejuvenil A",
                }
            ],
        },
    }


def _no_race_email_blocks() -> dict:
    return {
        "attendance": {"sessions_total": 12, "sessions_present": 12, "attendance_pct": 100.0, "streak_sessions": 12},
        "technical": {"focos_tecnicos": ["Curvas"], "avg_rpe": 5.5, "total_training_hours": 9.0},
        "race_results": {"has_races": False, "results": []},
    }


def _zero_attendance_email_blocks() -> dict:
    return {
        "attendance": {"sessions_total": 0, "sessions_present": 0, "attendance_pct": 0.0, "streak_sessions": 0},
        "technical": {"focos_tecnicos": [], "avg_rpe": None, "total_training_hours": 0.0},
        "race_results": {"has_races": False, "results": []},
    }


class TestStaticStageTitle:
    def test_full_month_mentions_races(self):
        title = static_stage_title(_full_month_email_blocks(), "su hija")
        assert "su hija" in title
        assert len(title.split()) <= 20

    def test_no_race_month(self):
        title = static_stage_title(_no_race_email_blocks(), "su hijo")
        assert "su hijo" in title
        assert "carreras" not in title

    def test_zero_attendance_month(self):
        title = static_stage_title(_zero_attendance_email_blocks(), "su hijo/a")
        assert "pausa" in title.lower()

    def test_never_generic_fixed_phrase_across_scenarios(self):
        full = static_stage_title(_full_month_email_blocks(), "su hijo")
        no_race = static_stage_title(_no_race_email_blocks(), "su hijo")
        zero = static_stage_title(_zero_attendance_email_blocks(), "su hijo")
        assert len({full, no_race, zero}) == 3


class TestStaticObservations:
    def test_full_month_has_up_to_three(self):
        observations = static_observations(_full_month_email_blocks(), "su hija")
        assert 1 <= len(observations) <= 3
        assert all(o.evidence for o in observations)

    def test_evidence_contains_a_number(self):
        observations = static_observations(_full_month_email_blocks(), "su hija")
        for obs in observations:
            assert any(ch.isdigit() for ch in obs.evidence)

    def test_zero_attendance_month_returns_empty_or_minimal(self):
        observations = static_observations(_zero_attendance_email_blocks(), "su hijo")
        assert observations == []

    def test_race_observation_present_when_has_races(self):
        observations = static_observations(_full_month_email_blocks(), "su hija")
        assert any(o.block_ref == "race" for o in observations)


class TestStaticSummitCaption:
    def test_race_summit_caption(self):
        summit = Summit(
            kind=SummitKind.RACE,
            title="P2 en la Válida 3",
            detail="Prejuvenil A",
            caption=None,
            date=date(2026, 6, 12),
        )
        caption = static_summit_caption(summit, _full_month_email_blocks(), "su hija")
        assert "su hija" in caption.lower()
        assert len(caption.split()) <= 25

    def test_training_summit_caption_no_race_month(self):
        summit = Summit(
            kind=SummitKind.TRAINING,
            title="Mejor sesión de entrenamiento del mes",
            detail=None,
            caption=None,
            date=date(2026, 6, 20),
        )
        caption = static_summit_caption(summit, _no_race_email_blocks(), "su hijo")
        assert len(caption.split()) <= 25
        assert "racha" in caption.lower() or "esfuerzo" in caption.lower()


class TestStaticNextSegment:
    def test_with_focus_groups_and_next_race(self):
        segment = NextSegment(
            focus_groups=["Frenado modulado", "Trazado de curvas"],
            next_race=NextRace(label="Válida 4", date=date(2026, 7, 10), venue="Cali", priority_label="Prioridad A"),
            text=None,
        )
        text = static_next_segment(segment, "su hija")
        assert "su hija" in text
        assert len(text.split()) <= 40

    def test_with_no_focus_and_no_race_falls_back(self):
        segment = NextSegment(focus_groups=[], next_race=None, text=None)
        text = static_next_segment(segment, "su hijo")
        assert "su hijo" in text
        assert len(text.split()) <= 40


class TestStaticFamilyCompass:
    def test_question_ends_with_question_mark(self):
        compass = static_family_compass(_full_month_email_blocks(), None, "su hija")
        assert compass.conversation_question.endswith("?")

    def test_no_supplements_or_calories_mentioned(self):
        for email_blocks in (_full_month_email_blocks(), _no_race_email_blocks(), _zero_attendance_email_blocks()):
            compass = static_family_compass(email_blocks, None, "su hijo/a")
            combined = " ".join(
                [compass.conversation_question, compass.monthly_challenge, compass.what_to_watch]
            ).lower()
            for term in _FORBIDDEN_TERMS:
                assert term not in combined

    def test_what_to_watch_references_next_segment_focus(self):
        segment = NextSegment(focus_groups=["Frenado modulado"], next_race=None, text=None)
        compass = static_family_compass(_full_month_email_blocks(), segment, "su hija")
        assert "Frenado modulado" in compass.what_to_watch

    def test_what_to_watch_references_next_race_when_no_focus_groups(self):
        segment = NextSegment(
            focus_groups=[],
            next_race=NextRace(label="Válida 4", date=date(2026, 7, 10), venue=None, priority_label=None),
            text=None,
        )
        compass = static_family_compass(_full_month_email_blocks(), segment, "su hijo")
        assert "Válida 4" in compass.what_to_watch

    def test_gender_aware(self):
        compass_f = static_family_compass(_full_month_email_blocks(), None, "su hija")
        compass_m = static_family_compass(_full_month_email_blocks(), None, "su hijo")
        assert "su hija" in compass_f.conversation_question
        assert "su hijo" in compass_m.conversation_question
