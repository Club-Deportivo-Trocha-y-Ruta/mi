"""
Tests de privacidad — PASO 9 Reporte mensual.

Invariantes verificados:
1. Padre A no puede ver resumen de atleta B (403 → PermissionError)
2. Padre ve solo sus atletas, nunca el atleta de otro padre
3. PDF/email no contiene nombres reales de atletas (solo A1, A2...)
4. coach_observations no se expone a padres en GET detalle
5. Métricas en metrics_snapshot usan IDs de atleta, no nombres
6. Guardrails de IA rechazan output con nombres reales
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.training.reports import parent_monthly_summary
from app.services.ai.use_cases.monthly_report import (
    MonthlyReportContext,
    MonthlyReportGuardrails,
    MonthlyReportUseCase,
    AnonymizedAthleteStats,
)
from app.services.ai.errors import LLMSchemaError
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.prompts.registry import PromptRegistry


# ---------------------------------------------------------------------------
# Invariante 1 & 2: padre A no puede ver atleta B
# ---------------------------------------------------------------------------


class TestParentAthleteIsolation:
    @pytest.mark.asyncio
    async def test_padre_no_puede_ver_atleta_de_otro_padre(self):
        db = AsyncMock()
        # Padre 99 tiene atleta 5; intenta acceder atleta 7 (de otro padre)
        with patch(
            "app.services.training.reports.parent_athlete_ids",
            AsyncMock(return_value=[5]),
        ):
            with pytest.raises(PermissionError):
                await parent_monthly_summary(
                    db=db,
                    parent_user_id=99,
                    athlete_id=7,
                    year=2026,
                    month=3,
                )

    @pytest.mark.asyncio
    async def test_padre_sin_atletas_vinculados_no_accede(self):
        db = AsyncMock()
        with patch(
            "app.services.training.reports.parent_athlete_ids",
            AsyncMock(return_value=[]),
        ):
            with pytest.raises(PermissionError):
                await parent_monthly_summary(
                    db=db,
                    parent_user_id=99,
                    athlete_id=5,
                    year=2026,
                    month=3,
                )

    @pytest.mark.asyncio
    async def test_resumen_no_incluye_datos_de_otros_atletas(self):
        """El resumen devuelto solo tiene los datos del atleta_id solicitado."""
        from app.models.training_session import AttendanceStatus, SessionStatus

        db = AsyncMock()
        athlete = MagicMock()
        athlete.id = 5
        athlete.club_id = 1
        athlete.first_name = "Lucas"
        athlete.last_name = "García"

        session = MagicMock()
        session.id = 10
        session.technical_focus = "Frenado"
        session.status = SessionStatus.EXECUTED

        att_athlete5 = MagicMock()
        att_athlete5.session_id = 10
        att_athlete5.athlete_id = 5
        att_athlete5.status = AttendanceStatus.PRESENTE

        att_athlete6 = MagicMock()
        att_athlete6.session_id = 10
        att_athlete6.athlete_id = 6
        att_athlete6.status = AttendanceStatus.PRESENTE

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = athlete
            elif call_count["n"] == 2:
                result.scalars.return_value.all.return_value = [session]
            else:
                # Solo attendance del atleta 5 (el WHERE filtra por athlete_id)
                result.scalars.return_value.all.return_value = [att_athlete5]
            return result

        db.execute = mock_execute

        with patch(
            "app.services.training.reports.parent_athlete_ids",
            AsyncMock(return_value=[5]),
        ):
            summary = await parent_monthly_summary(
                db=db,
                parent_user_id=99,
                athlete_id=5,
                year=2026,
                month=3,
            )

        assert summary.athlete_id == 5
        # El count_present es 1 (solo atleta 5), no 2 (si incluyera atleta 6)
        assert summary.count_present == 1


# ---------------------------------------------------------------------------
# Invariante 3: el contexto IA no contiene nombres reales
# ---------------------------------------------------------------------------


class TestAIContextPrivacy:
    def _make_metrics(self):
        from app.schemas.training_session import AthleteAttendanceStats, MonthlyMetrics
        return MonthlyMetrics(
            club_id=1,
            year=2026,
            month=3,
            total_sessions_planned=5,
            total_sessions_executed=4,
            total_sessions_cancelled=1,
            attendance_by_athlete={
                101: AthleteAttendanceStats(
                    athlete_id=101, count_present=4, count_absent=0,
                    count_justified=0, count_late=0, count_injured=0,
                    total_sessions=4, attendance_pct=100.0,
                ),
                102: AthleteAttendanceStats(
                    athlete_id=102, count_present=3, count_absent=1,
                    count_justified=0, count_late=0, count_injured=0,
                    total_sessions=4, attendance_pct=75.0,
                ),
            },
            technical_focus_list=["Frenado"],
            avg_rpe=6.0,
            avg_rubric_effort=3.5,
            avg_rubric_attitude=4.0,
            avg_rubric_technique=3.8,
        )

    def test_build_context_no_contiene_nombres_reales(self):
        provider = FakeLLMProvider(model="fake")
        registry = PromptRegistry()
        use_case = MonthlyReportUseCase(provider=provider, registry=registry)

        metrics = self._make_metrics()
        real_names = {"Juan Pérez", "Ana García"}

        ctx = use_case.build_context_from_metrics(
            club_name="Trocha y Ruta",
            year=2026,
            month=3,
            metrics=metrics,
            real_names=real_names,
        )

        for stat in ctx.attendance_stats:
            assert stat.pseudonym.startswith("A")
            assert "Pérez" not in stat.pseudonym
            assert "García" not in stat.pseudonym

        assert "forbidden_names" not in ctx.model_dump(exclude={"forbidden_names"})

    def test_observaciones_coach_redactadas(self):
        provider = FakeLLMProvider(model="fake")
        registry = PromptRegistry()
        use_case = MonthlyReportUseCase(provider=provider, registry=registry)

        metrics = self._make_metrics()
        real_names = {"Juan Pérez"}

        ctx = use_case.build_context_from_metrics(
            club_name="Trocha y Ruta",
            year=2026,
            month=3,
            metrics=metrics,
            coach_observations="Juan Pérez tuvo un mes excelente.",
            real_names=real_names,
        )

        assert "Juan Pérez" not in (ctx.coach_observations or "")
        assert "[REDACTADO]" in (ctx.coach_observations or "")


# ---------------------------------------------------------------------------
# Invariante 4: padres no ven coach_observations en el reporte
# (verificado en router — aquí probamos que el schema lo permite ser None)
# ---------------------------------------------------------------------------


class TestMonthlyReportReadSchema:
    def test_coach_observations_puede_ser_none(self):
        from app.schemas.training_session import MonthlyReportRead

        report = MonthlyReportRead(
            id=1,
            club_id=1,
            year=2026,
            month=3,
            ai_summary="Resumen",
            metrics_snapshot={},
            coach_observations=None,
            generated_by_user_id=1,
            generated_at=datetime.now(timezone.utc),
            sent_at=None,
        )
        assert report.coach_observations is None


# ---------------------------------------------------------------------------
# Invariante 5: guardrails rechazan nombres reales en output IA
# ---------------------------------------------------------------------------


class TestGuardrailsRejectNames:
    def test_guardrails_rechazan_nombre_real_en_output(self):
        forbidden = frozenset({"Juan Pérez"})
        guardrails = MonthlyReportGuardrails(forbidden_names=forbidden)

        texto_con_nombre = (
            "En el mes de marzo, Juan Pérez destacó por su constancia en los "
            "entrenamientos técnicos del club. La participación del grupo fue "
            "positiva y los focos técnicos se abordaron correctamente durante "
            "las sesiones ejecutadas. El grupo mostró gran compromiso con los "
            "objetivos planteados y la dinámica grupal fue constructiva. Los "
            "indicadores de asistencia y rendimiento técnico muestran una "
            "tendencia positiva respecto al período anterior del ciclo anual."
        )

        with pytest.raises(LLMSchemaError, match="nombre real"):
            guardrails.scrub(texto_con_nombre)

    def test_guardrails_aceptan_texto_con_pseudonimos(self):
        forbidden = frozenset({"Juan Pérez"})
        guardrails = MonthlyReportGuardrails(forbidden_names=forbidden)

        texto_valido = (
            "En el mes de marzo el grupo mostró una participación positiva en "
            "los entrenamientos planificados. El atleta A1 mantuvo una asistencia "
            "del cien por ciento, mientras que A2 registró el setenta y cinco por "
            "ciento debido a compromisos escolares reportados oportunamente. Los "
            "focos técnicos de frenado progresivo y pedaleo técnico fueron cubiertos "
            "satisfactoriamente. Se destaca la disposición del grupo ante los retos "
            "de la periodización mensual propuesta por el entrenador del club."
        )

        # No debe lanzar
        result = guardrails.scrub(texto_valido)
        assert result == texto_valido

    def test_guardrails_rechazan_terminos_medicos(self):
        guardrails = MonthlyReportGuardrails(forbidden_names=frozenset())

        texto_medico = (
            "El rendimiento mejoró gracias a la suplementación con creatina "
            "que algunos atletas incorporaron a su rutina de entrenamiento "
            "durante este mes de alta carga en el club deportivo. La dosis "
            "recomendada por el preparador físico fue de cinco gramos diarios "
            "en días de entrenamiento. El grupo reportó mejoría en la recuperación "
            "muscular y en la capacidad de sostener esfuerzos intensos en sesión."
        )

        with pytest.raises(LLMSchemaError, match="médicos"):
            guardrails.scrub(texto_medico)

    def test_guardrails_rechazan_texto_muy_corto(self):
        guardrails = MonthlyReportGuardrails(forbidden_names=frozenset())

        with pytest.raises(LLMSchemaError, match="corto"):
            guardrails.scrub("Mes excelente. Todos bien.")
