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
            club_id=1,
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
            club_id=1,
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
        )
        assert report.coach_observations is None


# ---------------------------------------------------------------------------
# Invariante 5: guardrails rechazan nombres reales en output IA
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Feature 022 (T028) — invariantes de privacidad de las NUEVAS superficies:
# session_detail (metrics_snapshot), /pdf + /docx 403 para padres, y el
# contexto IA del bloque "competencia".
# ---------------------------------------------------------------------------


def _make_user_022(uid: int, email: str = "test@example.com") -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.email = email
    u.first_name = "Test"
    u.last_name = "User"
    u.is_active = True
    return u


def _make_report_022(rid: int = 1, club_id: int = 1, year: int = 2026, month: int = 6) -> MagicMock:
    """Reporte con TODAS las superficies nuevas pobladas (session_detail incl.)."""
    r = MagicMock()
    r.id = rid
    r.club_id = club_id
    r.year = year
    r.month = month
    r.ai_summary = "Resumen de prueba."
    r.metrics_snapshot = {
        "total_sessions_planned": 8,
        "total_sessions_executed": 7,
        "attendance_by_athlete": {
            "42": {
                "athlete_id": 42,
                "count_present": 6,
                "count_absent": 1,
                "count_justified": 0,
                "count_late": 0,
                "count_injured": 0,
                "total_sessions": 7,
                "attendance_pct": 85.7,
            }
        },
        # SPEC 2 (feature 022) — detalle por sesión: fecha/hora/lugar exactos
        # + conteos de asistencia de TODO el club. No debe llegar a padres.
        "session_detail": [
            {
                "session_date": "2026-06-03",
                "start_time": "16:00:00",
                "technical_focus": "Frenado progresivo",
                "location": "Pista Ginebra",
                "status": "executed",
                "present_count": 6,
                "attendee_total": 7,
            }
        ],
    }
    r.narrative_blocks = {
        "objetivo": {"final_text": "Texto interno del coach.", "ai_draft": "..."}
    }
    r.competition_results = [
        {"athlete_id": 42, "athlete_name": "Juan Pérez", "event_id": 1}
    ]
    r.coach_observations = "Observación interna del coach sobre Juan Pérez."
    r.generated_by_user_id = 1
    r.generated_at = datetime.now(timezone.utc)
    r.status = "draft"
    r.athlete_names = {"42": "Juan Pérez"}
    return r


class TestParentNeverReceivesSessionDetail:
    """`_build_report_read` debe despojar `session_detail` (y no solo
    `attendance_by_athlete`) del `metrics_snapshot` cuando el consumidor es
    un padre — expone lugar/hora exactos y asistencia agregada de TODO el
    club, fuera del alcance de la vista padre (feature 022, SPEC 2)."""

    def test_build_report_read_despoja_session_detail_para_padres(self):
        from app.routers.monthly_reports import _build_report_read

        report = _make_report_022()
        out = _build_report_read(report, is_parent=True)

        assert out.narrative_blocks is None
        assert out.competition_results is None
        assert out.athlete_names == {}
        assert out.coach_observations is None
        assert isinstance(out.metrics_snapshot, dict)
        assert "session_detail" not in out.metrics_snapshot
        assert "attendance_by_athlete" not in out.metrics_snapshot
        # Métricas agregadas SÍ se conservan (no PII):
        assert out.metrics_snapshot["total_sessions_executed"] == 7

    def test_build_report_read_coach_conserva_session_detail(self):
        """Control: coach/admin sí reciben `session_detail` sin filtrar."""
        from app.routers.monthly_reports import _build_report_read

        report = _make_report_022()
        out = _build_report_read(report, is_parent=False)

        assert out.narrative_blocks is not None
        assert out.competition_results is not None
        assert "session_detail" in out.metrics_snapshot
        assert "attendance_by_athlete" in out.metrics_snapshot

    @pytest.mark.asyncio
    async def test_get_monthly_report_endpoint_padre_no_recibe_session_detail(self):
        """Prueba de integración del helper contra el endpoint de detalle."""
        from app.models.user import UserRole
        from app.routers.monthly_reports import get_monthly_report

        report = _make_report_022()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = report

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        parent = _make_user_022(3, email="padre@example.com")
        parent.role = UserRole.parent

        with patch(
            "app.routers.monthly_reports.can_view_monthly_report",
            AsyncMock(return_value=True),
        ):
            out = await get_monthly_report(
                club_id=1, year=2026, month=6, db=db, current_user=parent,
            )

        assert out.narrative_blocks is None
        assert out.competition_results is None
        assert out.athlete_names == {}
        assert isinstance(out.metrics_snapshot, dict)
        assert "session_detail" not in out.metrics_snapshot
        # Nunca debe aparecer el nombre real del atleta en ningún campo expuesto.
        dumped = out.model_dump()
        assert "Juan Pérez" not in str(dumped)


class TestParentForbiddenFromPdfAndDocx:
    """Un padre nunca puede descargar el Informe Técnico (PDF ni DOCX) —
    ambos endpoints están detrás de ``require_role([admin, coach])``."""

    @pytest.mark.asyncio
    async def test_parent_403_al_descargar_pdf(self):
        from app.dependencies import get_current_user, get_db
        from app.main import app

        parent = _make_user_022(3, email="padre@example.com")
        from app.models.user import UserRole
        parent.role = UserRole.parent

        db = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: parent
        app.dependency_overrides[get_db] = lambda: db

        try:
            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/clubs/1/monthly-reports/2026/6/pdf")
            assert resp.status_code == 403
            db.execute.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_parent_403_al_descargar_docx(self):
        from app.dependencies import get_current_user, get_db
        from app.main import app

        parent = _make_user_022(3, email="padre@example.com")
        from app.models.user import UserRole
        parent.role = UserRole.parent

        db = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: parent
        app.dependency_overrides[get_db] = lambda: db

        try:
            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/clubs/1/monthly-reports/2026/6/docx")
            assert resp.status_code == 403
            db.execute.assert_not_called()
        finally:
            app.dependency_overrides.clear()


class TestCompetenciaBlockAIContextHasNoRealNames:
    """El contexto/prompt enviado al LLM para el bloque `competencia` (feature
    022) nunca contiene nombres reales de atletas — solo agregados/pseudónimos,
    igual que el resto de bloques (misma invariante que
    `TestAIContextPrivacy.test_build_context_no_contiene_nombres_reales`)."""

    def _metrics(self):
        from app.schemas.training_session import AthleteAttendanceStats, MonthlyMetrics
        return MonthlyMetrics(
            club_id=1,
            year=2026,
            month=6,
            total_sessions_planned=8,
            total_sessions_executed=7,
            total_sessions_cancelled=1,
            attendance_by_athlete={
                101: AthleteAttendanceStats(
                    athlete_id=101, count_present=6, count_absent=1,
                    count_justified=0, count_late=0, count_injured=0,
                    total_sessions=7, attendance_pct=85.7,
                ),
                102: AthleteAttendanceStats(
                    athlete_id=102, count_present=7, count_absent=0,
                    count_justified=0, count_late=0, count_injured=0,
                    total_sessions=7, attendance_pct=100.0,
                ),
            },
            technical_focus_list=["Frenado progresivo"],
            avg_rpe=6.2,
            avg_rubric_effort=3.8,
            avg_rubric_attitude=4.1,
            avg_rubric_technique=3.7,
        )

    @staticmethod
    def _canned_competencia_text() -> str:
        """Texto ≥50 palabras (mínimo del guardrail) para que `run_block` no
        rechace el borrador por longitud antes de llegar a las aserciones de
        privacidad que interesan a este test."""
        return (
            "El grupo de alto rendimiento mantuvo una participación activa en "
            "las jornadas de competencia del período, con buena disposición "
            "hacia el calendario Copa Valle y aprendizajes claros sobre la "
            "relación entre el entrenamiento planificado y el desempeño "
            "competitivo del conjunto. Se observó una alineación adecuada "
            "entre la carga de trabajo semanal y las exigencias propias de "
            "cada válida, consolidando hábitos de preparación previa y "
            "recuperación posterior a cada jornada dentro del ciclo mensual."
        )

    @pytest.mark.asyncio
    async def test_contexto_competencia_no_contiene_nombres_reales(self):
        from app.services.ai.use_cases.monthly_report_blocks import (
            MonthlyReportBlocksUseCase,
        )

        real_names = {"Juan Pérez", "Ana García"}
        fake = FakeLLMProvider(canned=self._canned_competencia_text())
        uc = MonthlyReportBlocksUseCase(fake, PromptRegistry())

        ctx = uc.build_context_from_metrics(
            club_id=1,
            club_name="Trocha y Ruta",
            year=2026,
            month=6,
            metrics=self._metrics(),
            real_names=real_names,
        )

        draft = await uc.run_block(ctx, "competencia")

        # El contexto anonimizado (lo que build_context_from_metrics produce)
        # nunca lleva nombres reales — solo pseudónimos A1/A2.
        for stat in ctx.attendance_stats:
            assert stat.pseudonym.startswith("A")
        assert "forbidden_names" not in ctx.model_dump(exclude={"forbidden_names"})

        # El payload REAL enviado al proveedor LLM (prompt renderizado) —
        # misma verificación que test_monthly_report_blocks.py.
        assert fake.last_request is not None
        rendered = fake.last_request.messages[-1].content
        for name in real_names:
            assert name not in rendered

        # El draft final tampoco debe contener nombres reales.
        assert draft.error is None
        for name in real_names:
            assert name not in (draft.ai_draft or "")

    @pytest.mark.asyncio
    async def test_competencia_no_recibe_competition_results_estructurados(self):
        """El flujo de generación de bloques nunca mezcla los resultados
        estructurados de competencia (nombres reales, curados por el coach en
        `MonthlyReport.competition_results`) dentro del contexto/prompt IA —
        se construyen por separado (`build_competition_results`), fuera de
        este pipeline (ver docstring de `monthly_report_blocks.py`). El
        template solo *menciona* la clave `competition_results` en una
        instrucción de restricción (texto estático, sin datos); lo que NUNCA
        debe aparecer es un dato real de un resultado individual."""
        from app.services.ai.use_cases.monthly_report_blocks import (
            MonthlyReportBlocksUseCase,
        )

        fake = FakeLLMProvider(canned=self._canned_competencia_text())
        uc = MonthlyReportBlocksUseCase(fake, PromptRegistry())

        ctx = uc.build_context_from_metrics(
            club_id=1,
            club_name="Trocha y Ruta",
            year=2026,
            month=6,
            metrics=self._metrics(),
            real_names=set(),
        )

        await uc.run_block(ctx, "competencia")

        assert fake.last_request is not None
        rendered = fake.last_request.messages[-1].content
        # Ningún dato estructurado de resultado individual (posición, atleta,
        # evento) llega al prompt — solo agregados de asistencia/rúbrica.
        assert "athlete_name" not in rendered
        assert "event_id" not in rendered
        assert "position" not in rendered


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
