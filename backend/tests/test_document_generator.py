import pytest
from app.schemas.notification import DocumentRequest, DocumentTemplate, DocumentFormat
from app.services.notification.template_registry import TemplateRegistry
from app.services.notification.document_generator import (
    DocumentGenerator,
    _render_markdown,
)


def test_render_markdown_bold_italic_lists():
    out = str(_render_markdown("**Resumen** del *mes*\n\n* uno\n* dos"))
    assert "<strong>Resumen</strong>" in out
    assert "<em>mes</em>" in out
    assert "<li>uno</li>" in out
    assert "**Resumen**" not in out


def test_render_markdown_empty():
    assert str(_render_markdown(None)) == ""
    assert str(_render_markdown("")) == ""


def test_monthly_report_template_renders_markdown_summary():
    """El resumen IA en Markdown se renderiza a HTML en el PDF (no texto crudo)."""
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    spec = registry.get_document_spec(DocumentTemplate.TRAINING_MONTHLY_REPORT.value)
    template = generator._jinja.get_template(spec.template_path)
    html = template.render(
        club_name="Trocha y Ruta",
        month_label="Mayo",
        season_year="2026",
        ai_summary="**Resumen mensual** con *énfasis*.",
        metrics_snapshot={},
        coach_observations="",
        generated_at="2026-06-01",
    )
    assert "<strong>Resumen mensual</strong>" in html
    assert "<em>énfasis</em>" in html
    assert "**Resumen mensual**" not in html


def _render_monthly_report(**overrides):
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    spec = registry.get_document_spec(DocumentTemplate.TRAINING_MONTHLY_REPORT.value)
    template = generator._jinja.get_template(spec.template_path)
    ctx = {
        "club_name": "Trocha y Ruta",
        "month_label": "Mayo",
        "season_year": "2026",
        "ai_summary": "Resumen.",
        "metrics_snapshot": {
            "total_sessions_planned": 8,
            "total_sessions_executed": 7,
            "total_sessions_cancelled": 1,
            "avg_rpe": 4.6,
            "avg_rubric_effort": 3.5,
            "total_minutes_planned": 720,
            "total_minutes_executed": 630,
            "avg_hours_per_week": 2.4,
            "technical_focus_counts": {"Frenada": 3, "Curvas": 2},
            "attendance_status_totals": {
                "presente": 30, "tarde": 4, "justificado": 2, "ausente": 5, "lesionado": 1,
            },
            "attendance_by_athlete": {
                "42": {
                    "count_present": 6, "count_late": 1, "count_justified": 0,
                    "count_absent": 0, "count_injured": 1,
                    "total_sessions": 7, "attendance_pct": 85.7,
                },
            },
        },
        "coach_observations": "",
        "athlete_names": {"42": "Juan Pérez"},
        "generated_at": "2026-06-01",
    }
    ctx.update(overrides)
    return template.render(**ctx)


def test_monthly_report_template_shows_real_names_no_pseudonyms():
    html = _render_monthly_report()
    assert "Juan Pérez" in html          # nombre real
    assert "pseudónimos" not in html      # nota de pseudónimos eliminada


def test_monthly_report_template_omits_rpe():
    html = _render_monthly_report()
    # RPE oculto aunque venga en el snapshot
    assert "RPE" not in html
    # Otras rúbricas siguen presentes
    assert "Esfuerzo" in html


def test_monthly_report_template_name_fallback_when_unknown_athlete():
    html = _render_monthly_report(athlete_names={})
    assert "Atleta 1" in html


def test_monthly_report_template_photo_evidence():
    html = _render_monthly_report(photos=[
        {
            "data_uri": "data:image/jpeg;base64,AAAABBBB",
            "session_date": "15/05/2026",
            "caption": "Bajada técnica",
        },
    ])
    assert "Evidencia fotográfica del mes" in html
    assert 'src="data:image/jpeg;base64,AAAABBBB"' in html
    assert "15/05/2026" in html
    assert "Bajada técnica" in html


def test_monthly_report_template_no_photo_section_when_empty():
    html = _render_monthly_report()  # sin photos
    assert "Evidencia fotográfica del mes" not in html


def test_format_hms():
    from app.services.notification.document_generator import _format_hms

    assert _format_hms(720) == "12:00:00"
    assert _format_hms(90) == "01:30:00"
    assert _format_hms(144) == "02:24:00"
    assert _format_hms(0) == "00:00:00"
    assert _format_hms(None) == ""


def test_monthly_report_template_spec1_volume_focus_attendance():
    html = _render_monthly_report()
    # Volumen ejecutado en hh:mm:ss (el planificado fue removido del reporte)
    assert "Volumen planificado" not in html
    assert "Volumen ejecutado" in html
    assert "10:30:00" in html          # 630 min ejecutados
    assert "02:24:00" in html          # 2.4 h/sem
    # Frecuencia de focos técnicos
    assert "Frenada — 3 sesiones" in html
    assert "Curvas — 2 sesiones" in html
    # Desglose de asistencia por estado + lesionados visibles
    assert "Lesion." in html            # columna
    assert "Lesionados: 1" in html       # totales del club

@pytest.mark.asyncio
async def test_generate_pdf(mocker):
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    
    # Evitar problemas nativos de WeasyPrint en macOS
    mocker.patch.object(
        generator, 
        "_generate_pdf", 
        return_value=__import__("app.schemas.notification", fromlist=["GeneratedDocument", "DocumentFormat"]).GeneratedDocument(
            filename="fake.pdf", format=DocumentFormat.PDF, data=b"%PDF_FAKE", content_type="application/pdf"
        )
    )
    
    req = DocumentRequest(
        template=DocumentTemplate.ANTHROPOMETRY_REPORT,
        format=DocumentFormat.PDF,
        context={
            "athlete_first_name": "F", "athlete_last_name": "L",
            "birth_date": "2010-01-01", "sex": "M", "club_name": "C",
            "age_years": 13,
            "evaluation_date": "2024-01-01", "weight_kg": 50,
            "standing_height_cm": 150, "sitting_height_cm": 75,
            "maturation_status": "Pre-PHV", "maturity_offset": -2.0,
            "age_at_phv": 14.0
        }
    )
    doc = await generator.generate(req)
    assert doc.data.startswith(b'%PDF')

@pytest.mark.asyncio
async def test_generate_docx():
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    req = DocumentRequest(
        template=DocumentTemplate.MEDICAL_CLEARANCE,
        format=DocumentFormat.DOCX,
        context={
            "athlete_first_name": "F", "athlete_last_name": "L",
            "birth_date": "2010-01-01", "club_name": "C",
            "season_year": 2024, "medical_conditions": ["A"]
        }
    )
    doc = await generator.generate(req)
    assert doc.data.startswith(b'PK')
