"""Tests — Feature 022, T008 (US1: Informe que coincide con el formato aprobado).

Cubre, vía ``build_report_document_context`` (fuente única de verdad
compartida por los renderers PDF/DOCX):

1. El orden de ``sections`` coincide exactamente con el orden aprobado:
   Objetivo -> Plan de entrenamiento -> Desarrollo de actividades ->
   Participación en competencia -> Resultados obtenidos -> Conclusiones.
2. Con un ``ClubProjectProfile`` completo, los campos del encabezado se
   pueblan y ninguno cae al placeholder ``"—"``.
3. Con un perfil incompleto (algunos campos ausentes), solo esos campos
   del encabezado muestran ``"—"``; los presentes se pueblan normalmente.
4. El banner de borrador (``missing_sections``) enumera exactamente las
   secciones sin contenido (``final_text`` ni ``ai_draft``).

No hace consultas a BD: instancia ``MonthlyReport``/``ClubProjectProfile``
en memoria, mismo patrón que ``backend/tests/test_monthly_report_context.py``.
"""

from __future__ import annotations

from app.models.club_project_profile import ClubProjectProfile
from app.models.training_session import MonthlyReport, MonthlyReportStatus
from app.services.training.reports import build_report_document_context

# Orden aprobado del formato institucional (feature 022 / spec).
APPROVED_SECTION_ORDER: list[tuple[str, str]] = [
    ("objetivo", "Objetivo"),
    ("plan_entrenamiento", "Plan de entrenamiento"),
    ("desarrollo", "Desarrollo de actividades"),
    ("competencia", "Participación en competencia"),
    ("resultados", "Resultados obtenidos"),
    ("conclusiones", "Conclusiones"),
]


def _make_report(
    narrative_blocks: dict | None = None,
    status: MonthlyReportStatus = MonthlyReportStatus.DRAFT,
) -> MonthlyReport:
    return MonthlyReport(
        club_id=1,
        year=2026,
        month=6,
        generated_by_user_id=1,
        status=status,
        metrics_snapshot={},
        narrative_blocks=narrative_blocks if narrative_blocks is not None else {},
        competition_results=[],
    )


def _all_sections_filled() -> dict:
    return {
        "objetivo": {"final_text": "Consolidar técnica de curvas.", "ai_draft": "x"},
        "plan_entrenamiento": {"final_text": "Bloques de fuerza y técnica.", "ai_draft": "x"},
        "desarrollo": {"final_text": "Se ejecutaron 7 de 8 sesiones planeadas.", "ai_draft": "x"},
        "competencia": {"final_text": "Participación en Copa Valle III.", "ai_draft": "x"},
        "resultados": {"final_text": "2do lugar en Copa Valle III.", "ai_draft": "x"},
        "conclusiones": {"final_text": "Buen cierre de mes.", "ai_draft": "x"},
    }


class TestApprovedSectionOrder:
    """Happy path: el orden de las secciones coincide con el formato aprobado."""

    def test_sections_list_matches_approved_order_exactly(self):
        report = _make_report(narrative_blocks=_all_sections_filled())
        ctx = build_report_document_context(report, profile=None)

        actual_order = [(s["key"], s["title"]) for s in ctx["sections"]]
        assert actual_order == APPROVED_SECTION_ORDER

    def test_sections_order_is_stable_even_with_pre_feature_snapshot(self):
        """Snapshot sin plan_entrenamiento/competencia: el orden sigue siendo
        el aprobado (las secciones nuevas aparecen en su posición, marcadas
        como pendientes, no se omiten ni se reordenan)."""
        legacy_blocks = {
            "objetivo": {"final_text": "Objetivo del mes."},
            "desarrollo": {"final_text": "Desarrollo del mes."},
            "resultados": {"final_text": "Resultados del mes."},
            "conclusiones": {"final_text": "Conclusiones del mes."},
        }
        report = _make_report(narrative_blocks=legacy_blocks)
        ctx = build_report_document_context(report, profile=None)

        actual_order = [(s["key"], s["title"]) for s in ctx["sections"]]
        assert actual_order == APPROVED_SECTION_ORDER


class TestHeaderPopulation:
    """Encabezado: perfil completo -> sin '—'; perfil incompleto -> '—' solo
    en los campos ausentes."""

    def test_complete_profile_populates_all_header_fields_no_placeholder(self):
        report = _make_report(narrative_blocks=_all_sections_filled())
        profile = ClubProjectProfile(
            club_id=1,
            project_name="Escuela de ciclismo juvenil",
            executing_entity="Club Deportivo Trocha y Ruta",
            report_responsible="Coordinación técnica",
        )

        ctx = build_report_document_context(report, profile)

        header = ctx["header"]
        assert header["project_name"] == "Escuela de ciclismo juvenil"
        assert header["executing_entity"] == "Club Deportivo Trocha y Ruta"
        assert header["report_responsible"] == "Coordinación técnica"
        assert header["period_label"] == "Junio 2026"
        for value in header.values():
            assert value != "—"

    def test_incomplete_profile_shows_placeholder_only_for_missing_fields(self):
        report = _make_report(narrative_blocks=_all_sections_filled())
        # Perfil parcial: solo project_name está definido.
        profile = ClubProjectProfile(
            club_id=1,
            project_name="Escuela de ciclismo juvenil",
            executing_entity=None,
            report_responsible=None,
        )

        ctx = build_report_document_context(report, profile)

        header = ctx["header"]
        assert header["project_name"] == "Escuela de ciclismo juvenil"
        assert header["executing_entity"] == "—"
        assert header["report_responsible"] == "—"

    def test_no_profile_at_all_shows_placeholder_for_every_field(self):
        report = _make_report(narrative_blocks=_all_sections_filled())

        ctx = build_report_document_context(report, profile=None)

        header = ctx["header"]
        assert header["project_name"] == "—"
        assert header["executing_entity"] == "—"
        assert header["report_responsible"] == "—"
        # El período siempre se calcula del reporte, nunca depende del perfil.
        assert header["period_label"] == "Junio 2026"


class TestDraftMissingSectionsBanner:
    """El banner de borrador enumera exactamente las secciones sin contenido."""

    def test_missing_sections_lists_only_empty_ones_in_approved_order(self):
        partial_blocks = {
            "objetivo": {"final_text": "Objetivo del mes."},
            # plan_entrenamiento ausente por completo.
            "desarrollo": {"final_text": "Desarrollo del mes."},
            "competencia": {},  # presente pero sin final_text ni ai_draft.
            "resultados": {"final_text": "Resultados del mes."},
            "conclusiones": {"ai_draft": None, "final_text": None},
        }
        report = _make_report(narrative_blocks=partial_blocks)

        ctx = build_report_document_context(report, profile=None)

        assert ctx["missing_sections"] == [
            "Plan de entrenamiento",
            "Participación en competencia",
            "Conclusiones",
        ]
        assert ctx["is_draft"] is True

        sections = {s["key"]: s for s in ctx["sections"]}
        for key in ("plan_entrenamiento", "competencia", "conclusiones"):
            assert sections[key]["is_missing"] is True
            assert sections[key]["text"] == "Pendiente de completar"
        for key in ("objetivo", "desarrollo", "resultados"):
            assert sections[key]["is_missing"] is False

    def test_ai_draft_alone_counts_as_not_missing(self):
        """Un bloque con ai_draft pero sin final_text NO se marca 'pendiente'
        (el borrador de IA existe, solo falta que el coach lo apruebe/edite)."""
        blocks = _all_sections_filled()
        blocks["resultados"] = {"final_text": None, "ai_draft": "Borrador generado por IA."}
        report = _make_report(narrative_blocks=blocks)

        ctx = build_report_document_context(report, profile=None)

        assert "Resultados obtenidos" not in ctx["missing_sections"]
        sections = {s["key"]: s for s in ctx["sections"]}
        assert sections["resultados"]["is_missing"] is False
        # El texto final expuesto sigue siendo el placeholder porque el
        # documento nunca expone el ai_draft crudo (solo final_text aprobado).
        assert sections["resultados"]["text"] == "Pendiente de completar"

    def test_no_missing_sections_when_fully_approved(self):
        report = _make_report(
            narrative_blocks=_all_sections_filled(), status=MonthlyReportStatus.APPROVED
        )

        ctx = build_report_document_context(report, profile=None)

        assert ctx["missing_sections"] == []
        assert ctx["is_draft"] is False
