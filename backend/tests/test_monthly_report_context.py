"""Tests — Feature 022 (Alinear el Informe Técnico Mensual al formato institucional).

Cubre ``build_report_document_context`` (fuente única de verdad compartida por
los renderers PDF/DOCX):

(a) Snapshot con forma pre-feature (``metrics_snapshot`` sin ``session_detail``,
    ``competition_results`` como dicts planos sin ``event_id``/``series_kind``/
    ``awards_points``, ``narrative_blocks`` sin ``plan_entrenamiento`` ni
    ``competencia``): no debe lanzar excepción y debe marcar esas secciones/
    tablas como pendientes (FR-012, degradación limpia).
(b) Snapshot moderno completamente poblado: todas las secciones/tablas deben
    aparecer presentes, sin marcas de "pendiente".

``build_report_document_context`` es una función pura (no hace consultas a
BD): se testea instanciando ``MonthlyReport``/``ClubProjectProfile`` en
memoria, sin sesión — mismo patrón usado en
``backend/tests/models/test_monthly_report_refactor_columns.py`` para probar
instanciación de modelos ORM sin persistir.
"""

from __future__ import annotations

from app.models.club_project_profile import ClubProjectProfile
from app.models.training_session import MonthlyReport, MonthlyReportStatus
from app.services.training.reports import build_report_document_context


def _section_map(ctx: dict) -> dict[str, dict]:
    return {s["key"]: s for s in ctx["sections"]}


# ---------------------------------------------------------------------------
# (a) Snapshot pre-feature — degradación limpia (FR-012)
# ---------------------------------------------------------------------------


class TestPreFeatureSnapshotBackwardCompatibility:
    def _make_report(self) -> MonthlyReport:
        # metrics_snapshot con forma antigua: SIN clave "session_detail".
        metrics_snapshot = {
            "total_sessions_planned": 5,
            "total_sessions_executed": 4,
            "attendance_by_athlete": {
                "5": {
                    "count_present": 3,
                    "count_absent": 1,
                    "count_justified": 0,
                    "count_late": 0,
                    "count_injured": 0,
                    "total_sessions": 4,
                    "attendance_pct": 75.0,
                    "avg_rubric_effort": 7.5,
                    "avg_rubric_attitude": 8.0,
                    "avg_rubric_technique": 6.5,
                }
            },
        }

        # competition_results con forma antigua: items planos, SIN event_id,
        # series_kind ni awards_points.
        competition_results = [
            {
                "athlete_id": "5",
                "event_name": "Copa Valle I",
                "event_date": "2026-01-31",
                "position": 3,
            }
        ]

        # narrative_blocks SIN "plan_entrenamiento" ni "competencia" (agregadas
        # en esta feature); las 4 claves preexistentes sí tienen contenido.
        narrative_blocks = {
            "objetivo": {"final_text": "Objetivo del mes.", "ai_draft": "borrador"},
            "desarrollo": {"final_text": "Desarrollo de actividades del mes."},
            "resultados": {"final_text": "Resultados obtenidos en el mes."},
            "conclusiones": {"final_text": "Conclusiones del mes."},
        }

        return MonthlyReport(
            club_id=1,
            year=2026,
            month=2,
            generated_by_user_id=1,
            status=MonthlyReportStatus.DRAFT,
            metrics_snapshot=metrics_snapshot,
            narrative_blocks=narrative_blocks,
            competition_results=competition_results,
        )

    def test_no_raises_and_marks_missing_sections_pending(self):
        report = self._make_report()

        # No debe lanzar excepción (FR-012).
        ctx = build_report_document_context(report, profile=None)

        sections = _section_map(ctx)

        # Las secciones nuevas (agregadas en esta feature) faltan en el
        # snapshot antiguo → deben marcarse como pendientes.
        assert sections["plan_entrenamiento"]["is_missing"] is True
        assert sections["plan_entrenamiento"]["text"] == "Pendiente de completar"
        assert sections["competencia"]["is_missing"] is True
        assert sections["competencia"]["text"] == "Pendiente de completar"

        assert "Plan de entrenamiento" in ctx["missing_sections"]
        assert "Participación en competencia" in ctx["missing_sections"]
        assert len(ctx["missing_sections"]) == 2

        # Las secciones preexistentes SÍ tienen contenido y no están pendientes.
        assert sections["objetivo"]["is_missing"] is False
        assert sections["objetivo"]["text"] == "Objetivo del mes."
        assert sections["desarrollo"]["is_missing"] is False
        assert sections["resultados"]["is_missing"] is False
        assert sections["conclusiones"]["is_missing"] is False

    def test_session_detail_missing_marks_table_pending(self):
        report = self._make_report()
        ctx = build_report_document_context(report, profile=None)

        assert ctx["session_detail"]["is_empty"] is True
        assert ctx["session_detail"]["rows"] == []
        assert ctx["session_detail"]["placeholder"] == "Pendiente — regenerar informe"

    def test_attendance_table_still_builds_from_old_snapshot(self):
        """attendance_by_athlete ya existía antes de esta feature: sigue funcionando."""
        report = self._make_report()
        ctx = build_report_document_context(report, profile=None)

        assert ctx["attendance_table"]["is_empty"] is False
        assert len(ctx["attendance_table"]["rows"]) == 1
        assert ctx["attendance_table"]["rows"][0]["athlete_id"] == "5"

    def test_flat_competition_results_grouped_with_safe_defaults(self):
        """Items sin event_id/series_kind/awards_points no rompen el agrupador."""
        report = self._make_report()
        ctx = build_report_document_context(report, profile=None)

        assert ctx["has_competition_results"] is True
        assert len(ctx["competition_groups"]) == 1
        group = ctx["competition_groups"][0]
        assert group["event_id"] == 0
        assert group["series_kind"] is None
        assert group["awards_points"] is True
        assert group["event_name"] == "Copa Valle I"
        assert len(group["results"]) == 1

    def test_header_falls_back_to_placeholder_without_profile(self):
        report = self._make_report()
        ctx = build_report_document_context(report, profile=None)

        assert ctx["header"]["project_name"] == "—"
        assert ctx["header"]["executing_entity"] == "—"
        assert ctx["header"]["report_responsible"] == "—"
        assert ctx["header"]["period_label"] == "Febrero 2026"

    def test_status_and_is_draft(self):
        report = self._make_report()
        ctx = build_report_document_context(report, profile=None)

        assert ctx["status"] == "draft"
        assert ctx["is_draft"] is True


# ---------------------------------------------------------------------------
# (b) Snapshot moderno completamente poblado
# ---------------------------------------------------------------------------


class TestFullyPopulatedModernSnapshot:
    def _make_report_and_profile(self) -> tuple[MonthlyReport, ClubProjectProfile]:
        metrics_snapshot = {
            "total_sessions_planned": 8,
            "total_sessions_executed": 7,
            "session_detail": [
                {
                    "date": "2026-06-02",
                    "session_kind": "entrenamiento",
                    "technical_focus": "Curvas",
                    "attendance_count": 10,
                },
                {
                    "date": "2026-06-09",
                    "session_kind": "salida",
                    "technical_focus": "Resistencia",
                    "attendance_count": 9,
                },
            ],
            "attendance_by_athlete": {
                "5": {
                    "count_present": 6,
                    "count_absent": 1,
                    "count_justified": 0,
                    "count_late": 0,
                    "count_injured": 0,
                    "total_sessions": 7,
                    "attendance_pct": 85.7,
                    "avg_rubric_effort": 8.0,
                    "avg_rubric_attitude": 8.5,
                    "avg_rubric_technique": 7.0,
                },
                "6": {
                    "count_present": 7,
                    "count_absent": 0,
                    "count_justified": 0,
                    "count_late": 0,
                    "count_injured": 0,
                    "total_sessions": 7,
                    "attendance_pct": 100.0,
                    "avg_rubric_effort": 9.0,
                    "avg_rubric_attitude": 9.0,
                    "avg_rubric_technique": 8.0,
                },
            },
        }

        competition_results = [
            {
                "athlete_id": "5",
                "event_id": 12,
                "event_name": "Copa Valle III",
                "event_date": "2026-06-19",
                "series_kind": "cup",
                "awards_points": True,
                "position": 2,
            },
            {
                "athlete_id": "6",
                "event_id": 12,
                "event_name": "Copa Valle III",
                "event_date": "2026-06-19",
                "series_kind": "cup",
                "awards_points": True,
                "position": 5,
            },
            {
                "athlete_id": "5",
                "event_id": 13,
                "event_name": "Campeonato Departamental",
                "event_date": "2026-06-12",
                "series_kind": "championship",
                "awards_points": False,
                "position": 1,
            },
        ]

        narrative_blocks = {
            "objetivo": {"final_text": "Consolidar técnica de curvas.", "ai_draft": "x"},
            "plan_entrenamiento": {"final_text": "Bloques de fuerza y técnica.", "ai_draft": "x"},
            "desarrollo": {"final_text": "Se ejecutaron 7 de 8 sesiones planeadas.", "ai_draft": "x"},
            "competencia": {"final_text": "Participación en Copa Valle III y Dptal.", "ai_draft": "x"},
            "resultados": {"final_text": "2do y 5to lugar en Copa Valle III.", "ai_draft": "x"},
            "conclusiones": {"final_text": "Buen cierre de mes, mantener carga.", "ai_draft": "x"},
        }

        report = MonthlyReport(
            club_id=1,
            year=2026,
            month=6,
            generated_by_user_id=1,
            status=MonthlyReportStatus.APPROVED,
            metrics_snapshot=metrics_snapshot,
            narrative_blocks=narrative_blocks,
            competition_results=competition_results,
        )

        profile = ClubProjectProfile(
            club_id=1,
            project_name="Escuela de ciclismo juvenil",
            executing_entity="Club Deportivo Trocha y Ruta",
            report_responsible="Coordinación técnica",
        )

        return report, profile

    def test_no_missing_sections(self):
        report, profile = self._make_report_and_profile()
        ctx = build_report_document_context(report, profile)

        assert ctx["missing_sections"] == []
        for section in ctx["sections"]:
            assert section["is_missing"] is False
            assert section["text"] != "Pendiente de completar"

    def test_all_approved_section_keys_present_with_final_text(self):
        report, profile = self._make_report_and_profile()
        ctx = build_report_document_context(report, profile)

        sections = _section_map(ctx)
        expected_keys = {
            "objetivo",
            "plan_entrenamiento",
            "desarrollo",
            "competencia",
            "resultados",
            "conclusiones",
        }
        assert set(sections.keys()) == expected_keys
        assert sections["plan_entrenamiento"]["text"] == "Bloques de fuerza y técnica."
        assert sections["competencia"]["text"] == "Participación en Copa Valle III y Dptal."

    def test_session_detail_and_attendance_tables_populated(self):
        report, profile = self._make_report_and_profile()
        ctx = build_report_document_context(report, profile)

        assert ctx["session_detail"]["is_empty"] is False
        assert len(ctx["session_detail"]["rows"]) == 2

        assert ctx["attendance_table"]["is_empty"] is False
        assert len(ctx["attendance_table"]["rows"]) == 2

    def test_competition_groups_grouped_by_event_and_ordered_by_date(self):
        report, profile = self._make_report_and_profile()
        ctx = build_report_document_context(report, profile)

        assert ctx["has_competition_results"] is True
        assert len(ctx["competition_groups"]) == 2

        # Ordenado por event_date ascendente: Dptal. (12-jun) antes de Copa III (19-jun).
        first, second = ctx["competition_groups"]
        assert first["event_id"] == 13
        assert first["event_date"] == "2026-06-12"
        assert first["series_kind"] == "championship"
        assert first["awards_points"] is False
        assert len(first["results"]) == 1

        assert second["event_id"] == 12
        assert second["event_date"] == "2026-06-19"
        assert second["series_kind"] == "cup"
        assert second["awards_points"] is True
        assert len(second["results"]) == 2

    def test_header_uses_profile_values(self):
        report, profile = self._make_report_and_profile()
        ctx = build_report_document_context(report, profile)

        assert ctx["header"]["project_name"] == "Escuela de ciclismo juvenil"
        assert ctx["header"]["executing_entity"] == "Club Deportivo Trocha y Ruta"
        assert ctx["header"]["report_responsible"] == "Coordinación técnica"
        assert ctx["header"]["period_label"] == "Junio 2026"

    def test_status_approved_is_not_draft(self):
        report, profile = self._make_report_and_profile()
        ctx = build_report_document_context(report, profile)

        assert ctx["status"] == "approved"
        assert ctx["is_draft"] is False
