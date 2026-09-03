"""Tests para stage_log_builder.py (feature 038 — bitácora de etapa).

Cubre (según alcance de la tarea):
- trail_waypoints: prioridad (race > badge > streak > best_session >
  first_session), tope de 6, next_race siempre al final.
- summit: mes sin carrera -> cima de entrenamiento; mes de cero asistencia
  -> None.
- effort_profile: agrupación por semana ISO, cruzando límites de mes.
- stage_number: meses desde la primera sesión.
- build_stage_log: integración completa (overrides > narrativa > estático),
  mes de cero asistencia end-to-end.
"""

from __future__ import annotations

from datetime import date

from app.services.training.stage_log import BlockState, FamilyCompass, SummitKind
from app.services.training.stage_log_builder import (
    build_stage_log,
    effort_profile,
    stage_number,
    summit,
    trail_waypoints,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _base_snapshot(**overrides) -> dict:
    """Snapshot mínimo con la forma real de build_newsletter_metrics."""
    email_blocks = {
        "period": {"year": 2026, "month": 6, "label": "Junio 2026"},
        "attendance": {
            "sessions_total": 12,
            "sessions_present": 11,
            "attendance_pct": 91.7,
            "attendance_pct_prev_month": 80.0,
            "streak_sessions": 0,
        },
        "technical": {"focos_tecnicos": [], "focus_groups": [], "avg_rpe": 6.0, "total_training_hours": 10.0},
        "race_results": {"has_races": False, "competitor_id": None, "results": []},
        "calendar": {"next_training_sessions": [], "next_race_events": []},
        "photos": {"count": 0, "items": []},
        "badges": {"count": 0, "items": []},
        "athlete_first_session_date": None,
    }
    pdf_only_blocks = {
        "weekly": [],
        "next_focus_groups": [],
    }
    snapshot = {"email_blocks": email_blocks, "pdf_only_blocks": pdf_only_blocks}
    for key, value in overrides.items():
        if key in ("email_blocks", "pdf_only_blocks"):
            snapshot[key].update(value)
        else:
            snapshot[key] = value
    return snapshot


def _weekly_entry(day: int, *, attended: bool = True, rpe: int | None = 6, rubric_avg: float | None = 4.0) -> dict:
    return {"date": date(2026, 6, day).isoformat(), "attended": attended, "rpe": rpe, "rubric_avg": rubric_avg}


NEXT_RACE_EVENT = {"valida": "VI", "date": "2026-09-12", "location": "Roldanillo", "priority": "A"}


# ---------------------------------------------------------------------------
# trail_waypoints — prioridad y tope
# ---------------------------------------------------------------------------


class TestTrailWaypoints:
    def test_next_race_always_last(self):
        snapshot = _base_snapshot(
            email_blocks={
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
                "calendar": {"next_race_events": [NEXT_RACE_EVENT]},
            },
        )
        trail = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        assert trail[-1].kind.value == "next_race"
        assert trail[-1].is_future is True

    def test_race_beats_badge_when_trimming(self):
        """Con 5 carreras + próxima carrera (6 candidatos "compitiendo" por 6
        espacios), first_session (menor prioridad) queda fuera del recorte."""
        race_results = [
            {
                "label": f"Válida {i}",
                "event_date": f"2026-06-{i:02d}",
                "position": i,
                "gap_to_winner_pct": 1.0 * i,
                "category_label": "Prejuvenil A",
            }
            for i in range(1, 6)
        ]
        snapshot = _base_snapshot(
            email_blocks={
                "race_results": {"has_races": True, "results": race_results},
                "attendance": {"sessions_total": 12, "sessions_present": 12, "attendance_pct": 100.0, "streak_sessions": 0},
                "calendar": {"next_race_events": [NEXT_RACE_EVENT]},
            },
        )
        trail = trail_waypoints(
            snapshot,
            month_start=date(2026, 6, 1),
            month_end=date(2026, 6, 30),
            first_session_date=date(2026, 6, 15),
        )
        kinds = [w.kind.value for w in trail]
        assert kinds.count("race") == 5
        assert "first_session" not in kinds
        assert kinds[-1] == "next_race"
        assert len(trail) == 6  # tope

    def test_max_six_including_next_race(self):
        race_results = [
            {"label": f"Válida {i}", "event_date": f"2026-06-{i:02d}", "position": i, "gap_to_winner_pct": None, "category_label": None}
            for i in range(1, 8)
        ]
        snapshot = _base_snapshot(
            email_blocks={
                "race_results": {"has_races": True, "results": race_results},
                "calendar": {"next_race_events": [NEXT_RACE_EVENT]},
            },
        )
        trail = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        assert len(trail) == 6
        assert trail[-1].kind.value == "next_race"
        # 5 slots para el resto, priorizando race
        assert [w.kind.value for w in trail[:-1]].count("race") == 5

    def test_badge_present_via_badge_labels(self):
        snapshot = _base_snapshot(
            email_blocks={
                "badges": {
                    "count": 1,
                    "items": [{"badge_type": "attendance_100", "earned_at": "2026-06-30T00:00:00"}],
                },
            },
        )
        trail = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        badge_waypoints = [w for w in trail if w.kind.value == "badge"]
        assert len(badge_waypoints) == 1
        assert badge_waypoints[0].label == "Asistencia 100 %"
        assert "attendance_100" not in badge_waypoints[0].label

    def test_streak_milestone_threshold(self):
        snapshot_below = _base_snapshot(email_blocks={"attendance": {"streak_sessions": 4}})
        trail_below = trail_waypoints(
            snapshot_below, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        assert not any(w.kind.value == "streak" for w in trail_below)

        snapshot_above = _base_snapshot(email_blocks={"attendance": {"streak_sessions": 10}})
        trail_above = trail_waypoints(
            snapshot_above, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        streak_waypoints = [w for w in trail_above if w.kind.value == "streak"]
        assert len(streak_waypoints) == 1
        assert "10" in streak_waypoints[0].label

    def test_best_session_waypoint_from_weekly(self):
        snapshot = _base_snapshot(
            pdf_only_blocks={"weekly": [_weekly_entry(5, rubric_avg=4.5), _weekly_entry(12, rubric_avg=3.0)]},
        )
        trail = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        best = [w for w in trail if w.kind.value == "best_session"]
        assert len(best) == 1
        assert best[0].date == date(2026, 6, 5)

    def test_first_session_only_when_in_month(self):
        snapshot = _base_snapshot()
        trail_in_month = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=date(2026, 6, 3)
        )
        assert any(w.kind.value == "first_session" for w in trail_in_month)

        trail_outside_month = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=date(2026, 3, 3)
        )
        assert not any(w.kind.value == "first_session" for w in trail_outside_month)

    def test_zero_attendance_month_only_next_race(self):
        """Edge case: mes de cero asistencia -> el trail muestra solo la
        próxima carrera."""
        snapshot = _base_snapshot(
            email_blocks={
                "attendance": {"sessions_total": 0, "sessions_present": 0, "attendance_pct": 0.0, "streak_sessions": 0},
                "calendar": {"next_race_events": [NEXT_RACE_EVENT]},
            },
        )
        trail = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        assert len(trail) == 1
        assert trail[0].kind.value == "next_race"

    def test_no_data_at_all_returns_empty_trail(self):
        snapshot = _base_snapshot()
        trail = trail_waypoints(
            snapshot, month_start=date(2026, 6, 1), month_end=date(2026, 6, 30), first_session_date=None
        )
        assert trail == []


# ---------------------------------------------------------------------------
# summit
# ---------------------------------------------------------------------------


class TestSummit:
    def test_race_month_summit_is_race_kind(self):
        snapshot = _base_snapshot(
            email_blocks={
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
            },
        )
        result = summit(snapshot)
        assert result is not None
        assert result.kind == SummitKind.RACE
        assert "P2" in result.title

    def test_no_race_month_falls_back_to_training_summit(self):
        snapshot = _base_snapshot(
            pdf_only_blocks={"weekly": [_weekly_entry(10, rubric_avg=4.5)]},
        )
        result = summit(snapshot)
        assert result is not None
        assert result.kind == SummitKind.TRAINING

    def test_zero_attendance_month_has_no_summit(self):
        snapshot = _base_snapshot(pdf_only_blocks={"weekly": []})
        assert summit(snapshot) is None

    def test_no_attended_sessions_has_no_summit(self):
        snapshot = _base_snapshot(pdf_only_blocks={"weekly": [_weekly_entry(3, attended=False, rpe=None, rubric_avg=None)]})
        assert summit(snapshot) is None


# ---------------------------------------------------------------------------
# effort_profile — semanas ISO, límites de mes
# ---------------------------------------------------------------------------


class TestEffortProfile:
    def test_groups_by_iso_week(self):
        # Junio 2026: lunes 1 es semana ISO 23; 8 jun es semana ISO 24.
        snapshot = _base_snapshot(
            pdf_only_blocks={"weekly": [_weekly_entry(1), _weekly_entry(3), _weekly_entry(8)]},
        )
        weeks = effort_profile(snapshot)
        assert len(weeks) == 2
        assert weeks[0].sessions_planned == 2
        assert weeks[1].sessions_planned == 1

    def test_week_crossing_month_boundary(self):
        # 29-30 junio 2026 caen en la misma semana ISO que 1-5 julio 2026
        # (lunes 29/jun a domingo 5/jul).
        snapshot = _base_snapshot(
            email_blocks={"period": {"year": 2026, "month": 6, "label": "Junio 2026"}},
            pdf_only_blocks={
                "weekly": [
                    {"date": "2026-06-29", "attended": True, "rpe": 5, "rubric_avg": 4.0},
                    {"date": "2026-06-30", "attended": True, "rpe": 6, "rubric_avg": 4.0},
                ]
            },
        )
        weeks = effort_profile(snapshot)
        assert len(weeks) == 1
        assert "jun" in weeks[0].week_label
        assert "jul" in weeks[0].week_label

    def test_mean_rpe_ignores_missing_values(self):
        snapshot = _base_snapshot(
            pdf_only_blocks={
                "weekly": [
                    _weekly_entry(1, rpe=8),
                    _weekly_entry(2, attended=False, rpe=None, rubric_avg=None),
                ]
            },
        )
        weeks = effort_profile(snapshot)
        assert weeks[0].mean_rpe == 8.0
        assert weeks[0].sessions_attended == 1
        assert weeks[0].sessions_planned == 2

    def test_empty_weekly_returns_empty_list(self):
        snapshot = _base_snapshot(pdf_only_blocks={"weekly": []})
        assert effort_profile(snapshot) == []


# ---------------------------------------------------------------------------
# stage_number
# ---------------------------------------------------------------------------


class TestStageNumber:
    def test_same_month_is_stage_one(self):
        assert stage_number(date(2026, 6, 5), 2026, 6) == 1

    def test_months_later(self):
        assert stage_number(date(2026, 3, 1), 2026, 6) == 4

    def test_crosses_year_boundary(self):
        assert stage_number(date(2025, 11, 1), 2026, 2) == 4

    def test_none_first_session_defaults_to_one(self):
        assert stage_number(None, 2026, 6) == 1


# ---------------------------------------------------------------------------
# build_stage_log — integración
# ---------------------------------------------------------------------------


class _FakeAnalystReadingText:
    def __init__(self, headline_family: str, action_family: str) -> None:
        self.headline_family = headline_family
        self.action_family = action_family


class _FakeNarrative:
    def __init__(self, **kwargs) -> None:
        self.stage_title = kwargs.get("stage_title", "")
        self.summit_caption = kwargs.get("summit_caption")
        self.observations = kwargs.get("observations", [])
        self.next_segment_text = kwargs.get("next_segment_text")
        self.family_compass = kwargs.get(
            "family_compass",
            FamilyCompass(
                conversation_question="¿Qué disfrutó más este mes?",
                monthly_challenge="Reto del mes.",
                what_to_watch="Observen el frenado.",
            ),
        )
        self.analyst_reading = kwargs.get("analyst_reading")


class TestBuildStageLog:
    def test_static_fallback_when_no_narrative(self):
        snapshot = _base_snapshot()
        stage_log = build_stage_log(
            snapshot,
            narrative=None,
            family_input=None,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="F",
            athlete_first_name="Atleta",
        )
        assert stage_log.athlete_reference == "su hija"
        assert stage_log.block_states["stage_title"] == BlockState.STATIC
        assert stage_log.analyst_reading is None

    def test_overrides_win_over_narrative(self):
        snapshot = _base_snapshot()
        narrative = _FakeNarrative(stage_title="Título generado por IA")
        stage_log = build_stage_log(
            snapshot,
            narrative=narrative,
            family_input=None,
            overrides={"stage_title": "Título editado por el entrenador"},
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.stage_title == "Título editado por el entrenador"
        assert stage_log.block_states["stage_title"] == BlockState.EDITED

    def test_narrative_wins_over_static(self):
        snapshot = _base_snapshot()
        narrative = _FakeNarrative(stage_title="Un mes de curvas y aprendizaje sobre la bici")
        stage_log = build_stage_log(
            snapshot,
            narrative=narrative,
            family_input=None,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.stage_title == "Un mes de curvas y aprendizaje sobre la bici"
        assert stage_log.block_states["stage_title"] == BlockState.AI

    def test_analyst_reading_requires_both_narrative_and_family_input(self):
        snapshot = _base_snapshot()
        narrative = _FakeNarrative(
            analyst_reading=_FakeAnalystReadingText("Titular familiar", "Acción familiar")
        )
        # Sin family_input -> no hay analyst_reading, aunque narrative lo traiga.
        stage_log_missing_input = build_stage_log(
            snapshot,
            narrative=narrative,
            family_input=None,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log_missing_input.analyst_reading is None

        stage_log = build_stage_log(
            snapshot,
            narrative=narrative,
            family_input={"valida_label": "Válida 3 · Copa Valle", "source_insight_id": 7},
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.analyst_reading is not None
        assert stage_log.analyst_reading.source_insight_id == 7
        assert stage_log.analyst_reading.valida_label == "Válida 3 · Copa Valle"

    def test_hidden_blocks_sets_block_state_but_keeps_data(self):
        snapshot = _base_snapshot(
            email_blocks={"badges": {"count": 1, "items": [{"badge_type": "top10", "earned_at": "2026-06-30"}]}},
        )
        stage_log = build_stage_log(
            snapshot,
            narrative=None,
            family_input=None,
            overrides=None,
            coach_note="Buen mes.",
            hidden_blocks=["badges", "coach_note"],
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.block_states["badges"] == BlockState.HIDDEN
        assert stage_log.block_states["coach_note"] == BlockState.HIDDEN
        # El dato sigue presente en el StageLog (coach DTO) — solo el
        # to_parent_dto lo oculta de verdad.
        assert len(stage_log.badges) == 1
        assert stage_log.coach_note == "Buen mes."

    def test_zero_attendance_month_end_to_end(self):
        snapshot = _base_snapshot(
            email_blocks={
                "attendance": {"sessions_total": 0, "sessions_present": 0, "attendance_pct": 0.0, "streak_sessions": 0},
                "calendar": {"next_race_events": [NEXT_RACE_EVENT]},
            },
            pdf_only_blocks={"weekly": []},
        )
        stage_log = build_stage_log(
            snapshot,
            narrative=None,
            family_input=None,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex=None,
            athlete_first_name="Atleta",
        )
        assert stage_log.summit is None
        assert len(stage_log.trail) == 1
        assert "pausa" in stage_log.stage_title.lower()
        assert stage_log.athlete_reference == "su hijo/a"

    def test_narrative_as_plain_dict_from_db_json_column(self):
        """``AthleteMonthlyNewsletter.ai_narrative`` viaja como dict plano al
        leerlo de la columna JSON (no como objeto ``StageNarrative``) — el
        router real (``routers/athlete_monthly_newsletters.py::_rederive_stage_log``)
        pasa ``nl.ai_narrative`` tal cual. build_stage_log debe soportar esta
        forma sin lanzar excepción."""
        snapshot = _base_snapshot()
        narrative_dict = {
            "version": 2,
            "stage_title": "Un mes de curvas y aprendizaje sobre la bici",
            "summit_caption": None,
            "observations": [
                {"claim": "Buen ritmo.", "evidence": "12 de 14 sesiones.", "block_ref": "attendance"},
            ],
            "next_segment_text": None,
            "family_compass": {
                "conversation_question": "¿Qué disfrutó más este mes?",
                "monthly_challenge": "Reto del mes.",
                "what_to_watch": "Observen el frenado.",
            },
            "analyst_reading": None,
            "model": "gemini-3.1-flash-lite",
            "prompt_version": "athlete_monthly_newsletter_v2",
            "confidence": "high",
        }
        stage_log = build_stage_log(
            snapshot,
            narrative=narrative_dict,
            family_input=None,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="F",
            athlete_first_name="Atleta",
        )
        assert stage_log.stage_title == "Un mes de curvas y aprendizaje sobre la bici"
        assert stage_log.block_states["stage_title"] == BlockState.AI
        assert len(stage_log.observations) == 1
        assert stage_log.observations[0].block_ref == "attendance"

    def test_analyst_reading_as_plain_dicts_from_db_json(self):
        """``narrative["analyst_reading"]`` y ``family_input`` como dicts
        planos (forma real persistida / compuesta por el router)."""
        snapshot = _base_snapshot()
        narrative_dict = {
            "stage_title": "Etapa de curvas",
            "analyst_reading": {
                "headline_family": "El trabajo en curvas está dando resultado.",
                "action_family": "Practicar frenado antes de curvas cerradas.",
            },
        }
        family_input_dict = {"valida_label": "Válida 3 · Copa Valle", "source_insight_id": 99}
        stage_log = build_stage_log(
            snapshot,
            narrative=narrative_dict,
            family_input=family_input_dict,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.analyst_reading is not None
        assert stage_log.analyst_reading.source_insight_id == 99
        assert stage_log.analyst_reading.valida_label == "Válida 3 · Copa Valle"
        assert stage_log.block_states["analyst_reading"] == BlockState.AI

    def test_malformed_family_input_does_not_crash(self):
        """Un ``family_input`` sin las claves esperadas (p. ej. la tupla
        ``(insight_id, InsightV3)`` que hoy compone el router de forma
        provisional) no debe lanzar excepción: el bloque simplemente queda
        vacío en vez de romper la re-derivación completa."""
        snapshot = _base_snapshot()
        narrative_dict = {
            "stage_title": "Etapa de curvas",
            "analyst_reading": {
                "headline_family": "Titular familiar",
                "action_family": "Acción familiar",
            },
        }
        stage_log = build_stage_log(
            snapshot,
            narrative=narrative_dict,
            family_input=(7, object()),  # forma inesperada, sin .get/valida_label
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.analyst_reading is None
        assert stage_log.block_states["analyst_reading"] == BlockState.EMPTY

    def test_stage_number_uses_first_session_date(self):
        snapshot = _base_snapshot(email_blocks={"athlete_first_session_date": "2026-03-10"})
        stage_log = build_stage_log(
            snapshot,
            narrative=None,
            family_input=None,
            overrides=None,
            coach_note=None,
            hidden_blocks=None,
            athlete_sex="M",
            athlete_first_name="Atleta",
        )
        assert stage_log.stage_number == 4  # marzo=1, abril=2, mayo=3, junio=4
