"""Tests del MonthlyReportUseCase.

Cubre: privacidad (sin PII en prompt), guardrails, casos feliz y borde.
"""

from __future__ import annotations

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.monthly_report import (
    AnonymizedAthleteStats,
    MonthlyReportContext,
    MonthlyReportUseCase,
)
from app.schemas.training_session import AthleteAttendanceStats, MonthlyMetrics


# ---------------------------------------------------------------------------
# Fixtures de contexto
# ---------------------------------------------------------------------------


def _ctx(
    attendance_stats: list[AnonymizedAthleteStats] | None = None,
    forbidden_names: frozenset[str] = frozenset(),
    coach_observations: str | None = None,
    avg_rpe: float | None = 6.5,
) -> MonthlyReportContext:
    if attendance_stats is None:
        attendance_stats = [
            AnonymizedAthleteStats(pseudonym="A1", count_present=8, count_total=10, percentage=80.0),
            AnonymizedAthleteStats(pseudonym="A2", count_present=6, count_total=10, percentage=60.0),
        ]
    return MonthlyReportContext(
        club_name="Trocha y Ruta",
        period_year=2026,
        period_month=4,
        total_sessions_planned=12,
        total_sessions_executed=10,
        total_sessions_cancelled=2,
        attendance_stats=attendance_stats,
        focos_técnicos=["Frenado progresivo", "Pedaleo en terreno técnico"],
        avg_rpe=avg_rpe,
        avg_rubric_effort=3.8,
        avg_rubric_attitude=4.1,
        avg_rubric_technique=3.5,
        coach_observations=coach_observations,
        forbidden_names=forbidden_names,
    )


def _minimal_canned_response() -> str:
    return (
        "Durante el mes de abril de 2026, el club ejecutó 10 de las 12 sesiones planificadas, "
        "con una tasa de cancelación del 17%. La asistencia grupal fue variable: la mayoría "
        "mantuvo porcentajes superiores al 70%, lo que refleja un compromiso sostenido del grupo. "
        "Los focos técnicos trabajados —frenado progresivo y pedaleo en terreno técnico— "
        "fueron consistentes con el plan mensual aprobado por el comité.\n\n"
        "Los promedios de rúbrica muestran niveles adecuados en esfuerzo y actitud. "
        "Se recomienda continuar reforzando el foco en técnica en las próximas sesiones "
        "del mesociclo en curso."
    )


# ---------------------------------------------------------------------------
# 1. Snapshot del prompt renderizado
# ---------------------------------------------------------------------------


def test_rendered_prompt_contains_pseudonyms_not_names():
    registry = PromptRegistry()
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, registry)
    ctx = _ctx(forbidden_names=frozenset({"Pedro Pérez", "Ana García"}))

    context_dict = ctx.model_dump(exclude={"forbidden_names"})
    context_dict["attendance_stats"] = [s.model_dump() for s in ctx.attendance_stats]
    rendered = registry.render("monthly_report", context_dict)

    assert "A1" in rendered
    assert "A2" in rendered
    assert "Pedro Pérez" not in rendered
    assert "Ana García" not in rendered


def test_rendered_prompt_contains_required_sections():
    registry = PromptRegistry()
    ctx = _ctx()
    context_dict = ctx.model_dump(exclude={"forbidden_names"})
    context_dict["attendance_stats"] = [s.model_dump() for s in ctx.attendance_stats]
    rendered = registry.render("monthly_report", context_dict)

    assert "Agregados de sesión" in rendered
    assert "Asistencia" in rendered
    assert "Focos técnicos" in rendered
    assert "Promedios" in rendered
    assert "2026" in rendered
    assert "Trocha y Ruta" in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered


# ---------------------------------------------------------------------------
# 2. Sin PII en el prompt (build_context_from_metrics)
# ---------------------------------------------------------------------------


def _make_metrics_with_real_names():
    """Simula un MonthlyMetrics con atlas identificables."""
    stats = {
        101: AthleteAttendanceStats(
            athlete_id=101,
            count_present=8,
            count_absent=1,
            count_justified=0,
            count_late=1,
            count_injured=0,
            total_sessions=10,
            attendance_pct=90.0,
        ),
        202: AthleteAttendanceStats(
            athlete_id=202,
            count_present=6,
            count_absent=2,
            count_justified=1,
            count_late=0,
            count_injured=1,
            total_sessions=10,
            attendance_pct=60.0,
        ),
    }
    return MonthlyMetrics(
        club_id=1,
        year=2026,
        month=4,
        total_sessions_planned=12,
        total_sessions_executed=10,
        total_sessions_cancelled=2,
        attendance_by_athlete=stats,
        technical_focus_list=["Frenado técnico"],
        avg_rpe=6.8,
        avg_rubric_effort=3.9,
        avg_rubric_attitude=4.0,
        avg_rubric_technique=3.6,
    )


def test_build_context_no_pii_in_prompt():
    registry = PromptRegistry()
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, registry)

    metrics = _make_metrics_with_real_names()
    ctx = uc.build_context_from_metrics(
        club_name="Trocha y Ruta",
        year=2026,
        month=4,
        metrics=metrics,
        coach_observations=None,
        real_names={"Pedro Pérez", "Ana García"},
    )

    context_dict = ctx.model_dump(exclude={"forbidden_names"})
    context_dict["attendance_stats"] = [s.model_dump() for s in ctx.attendance_stats]
    rendered = registry.render("monthly_report", context_dict)

    assert "Pedro Pérez" not in rendered
    assert "Ana García" not in rendered
    # Los athlete_ids (enteros) no deben aparecer como prefijos de pseudónimos
    # ni como identificadores explícitos — el template solo muestra A1, A2, etc.
    assert "athlete_id" not in rendered.lower()
    assert "A1" in rendered or "A2" in rendered


def test_build_context_redacts_names_in_coach_observations():
    registry = PromptRegistry()
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, registry)

    metrics = _make_metrics_with_real_names()
    ctx = uc.build_context_from_metrics(
        club_name="Trocha y Ruta",
        year=2026,
        month=4,
        metrics=metrics,
        coach_observations="Pedro Pérez tuvo buena actitud esta semana.",
        real_names={"Pedro Pérez"},
    )

    assert ctx.coach_observations is not None
    assert "Pedro Pérez" not in ctx.coach_observations
    assert "[REDACTADO]" in ctx.coach_observations


# ---------------------------------------------------------------------------
# 3. Mock provider — camino feliz
# ---------------------------------------------------------------------------


async def test_run_returns_summary_with_fake_provider():
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, PromptRegistry())
    result = await uc.run(_ctx())

    assert result.text
    assert result.provider == "fake"
    assert result.period_year == 2026
    assert result.period_month == 4


async def test_run_sends_request_to_provider():
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, PromptRegistry())
    await uc.run(_ctx())

    assert fake.last_request is not None
    assert fake.call_count == 1
    user_msg = fake.last_request.messages[0].content
    assert "Trocha y Ruta" in user_msg


# ---------------------------------------------------------------------------
# 4. Guardrails rechazan nombre real en output
# ---------------------------------------------------------------------------


async def test_guardrails_reject_real_name_in_output():
    fake = FakeLLMProvider(
        canned=_minimal_canned_response() + " Pedro Pérez destacó esta semana."
    )
    uc = MonthlyReportUseCase(fake, PromptRegistry())
    ctx = _ctx(forbidden_names=frozenset({"Pedro Pérez"}))

    with pytest.raises(LLMSchemaError, match="nombre real"):
        await uc.run(ctx)


# ---------------------------------------------------------------------------
# 5. Guardrails rechazan consejo médico/suplementación
# ---------------------------------------------------------------------------


async def test_guardrails_reject_supplement_advice():
    fake = FakeLLMProvider(
        canned=_minimal_canned_response() + " Se recomienda tomar suplemento de hierro."
    )
    uc = MonthlyReportUseCase(fake, PromptRegistry())

    with pytest.raises(LLMSchemaError, match="médicos"):
        await uc.run(_ctx())


async def test_guardrails_reject_creatina():
    fake = FakeLLMProvider(
        canned=_minimal_canned_response() + " Algunos atletas podrían beneficiarse de creatina."
    )
    uc = MonthlyReportUseCase(fake, PromptRegistry())

    with pytest.raises(LLMSchemaError, match="médicos"):
        await uc.run(_ctx())


# ---------------------------------------------------------------------------
# 6. Guardrails rechazan output demasiado largo
# ---------------------------------------------------------------------------


async def test_guardrails_reject_too_long_output():
    long_output = " ".join(["palabra"] * 800)
    fake = FakeLLMProvider(canned=long_output)
    uc = MonthlyReportUseCase(fake, PromptRegistry())

    with pytest.raises(LLMSchemaError, match="largo"):
        await uc.run(_ctx())


async def test_guardrails_reject_too_short_output():
    short_output = "Resumen breve."
    fake = FakeLLMProvider(canned=short_output)
    uc = MonthlyReportUseCase(fake, PromptRegistry())

    with pytest.raises(LLMSchemaError, match="corto"):
        await uc.run(_ctx())


# ---------------------------------------------------------------------------
# 7. Periodo vacío — sin sesiones
# ---------------------------------------------------------------------------


async def test_empty_period_produces_valid_prompt():
    registry = PromptRegistry()
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, registry)

    empty_ctx = MonthlyReportContext(
        club_name="Trocha y Ruta",
        period_year=2026,
        period_month=3,
        total_sessions_planned=0,
        total_sessions_executed=0,
        total_sessions_cancelled=0,
        attendance_stats=[],
        focos_técnicos=[],
        avg_rpe=None,
        avg_rubric_effort=None,
        avg_rubric_attitude=None,
        avg_rubric_technique=None,
        coach_observations=None,
    )

    result = await uc.run(empty_ctx)
    assert result.text
    assert fake.call_count == 1
    user_msg = fake.last_request.messages[0].content
    assert "Sin registros de asistencia" in user_msg or "0" in user_msg


async def test_empty_period_build_context_from_empty_metrics():
    registry = PromptRegistry()
    fake = FakeLLMProvider(canned=_minimal_canned_response())
    uc = MonthlyReportUseCase(fake, registry)

    empty_metrics = MonthlyMetrics(
        club_id=1,
        year=2026,
        month=3,
        total_sessions_planned=0,
        total_sessions_executed=0,
        total_sessions_cancelled=0,
        attendance_by_athlete={},
        technical_focus_list=[],
        avg_rpe=None,
        avg_rubric_effort=None,
        avg_rubric_attitude=None,
        avg_rubric_technique=None,
    )
    ctx = uc.build_context_from_metrics(
        club_name="Trocha y Ruta",
        year=2026,
        month=3,
        metrics=empty_metrics,
    )
    result = await uc.run(ctx)
    assert result.text


# ---------------------------------------------------------------------------
# 8. Registry tiene la spec registrada
# ---------------------------------------------------------------------------


def test_monthly_report_registered_in_registry():
    registry = PromptRegistry()
    spec = registry.get_spec("monthly_report")
    assert spec.template_id == "monthly_report"
    assert "club_name" in spec.required_keys
    assert "attendance_stats" in spec.required_keys
    assert "focos_técnicos" in spec.required_keys
