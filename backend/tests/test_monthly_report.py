"""
Tests PASO 9 — Endpoint reporte mensual + envío email.

Cubre:
1. Happy path: generate crea MonthlyReport con métricas e IA
2. 409 en duplicado sin force_regenerate
3. force_regenerate sobreescribe reporte existente
4. Período futuro rechazado (400)
5. Mes actual (< día 28) rechazado (400)
6. send: actualiza sent_at, llama send() por cada admin
7. Listado devuelve reportes del club
8. Variante padre: resumen mensual solo de sus atletas
H8. LLM timeout → propagación de MonthlyReportLLMTimeout al router → 503
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.training_session import MonthlyMetrics, ParentMonthlySummary
from app.services.training.reports import (
    _validate_period,
    generate_monthly_report,
    parent_monthly_summary,
    send_monthly_report_email,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(uid: int, email: str = "test@example.com", first_name: str = "Admin") -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.email = email
    u.first_name = first_name
    u.last_name = "Test"
    u.is_active = True
    return u


def _make_club(cid: int = 1, name: str = "Trocha y Ruta") -> MagicMock:
    c = MagicMock()
    c.id = cid
    c.name = name
    return c


def _make_report(rid: int = 1, club_id: int = 1, year: int = 2026, month: int = 3) -> MagicMock:
    r = MagicMock()
    r.id = rid
    r.club_id = club_id
    r.year = year
    r.month = month
    r.ai_summary = "Resumen de prueba del mes de marzo."
    r.metrics_snapshot = {"total_sessions_planned": 5, "total_sessions_executed": 4}
    r.coach_observations = None
    r.generated_by_user_id = 1
    r.generated_at = datetime.now(timezone.utc)
    r.sent_at = None
    r.club = _make_club(club_id)
    return r


def _make_empty_metrics(club_id: int = 1, year: int = 2026, month: int = 3) -> MonthlyMetrics:
    return MonthlyMetrics(
        club_id=club_id,
        year=year,
        month=month,
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


# ---------------------------------------------------------------------------
# Tests _validate_period
# ---------------------------------------------------------------------------


class TestValidatePeriod:
    def test_acepta_mes_cerrado_anterior(self):
        today = date.today()
        if today.month == 1:
            year, month = today.year - 1, 12
        else:
            year, month = today.year, today.month - 1
        # No debe lanzar si el mes anterior está cerrado o hoy es >= día 28
        if today.day >= 28 or month < today.month - 1 or year < today.year:
            _validate_period(year, month)

    def test_rechaza_mes_futuro(self):
        today = date.today()
        with pytest.raises(ValueError, match="cerrado"):
            _validate_period(today.year, today.month + 1 if today.month < 12 else 1)

    def test_rechaza_mes_actual(self):
        today = date.today()
        with pytest.raises(ValueError, match="cerrado"):
            _validate_period(today.year, today.month)

    def test_acepta_mes_dos_atras(self):
        today = date.today()
        if today.month <= 2:
            year = today.year - 1
            month = today.month + 10
        else:
            year = today.year
            month = today.month - 2
        _validate_period(year, month)


# ---------------------------------------------------------------------------
# Tests generate_monthly_report
# ---------------------------------------------------------------------------


class TestGenerateMonthlyReport:
    @pytest.mark.asyncio
    async def test_happy_path_crea_reporte(self):
        db = AsyncMock()
        coach = _make_user(1)
        club = _make_club(1)

        # DB queries: existing=None, club=club, athletes
        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute
        db.add = MagicMock()
        db.flush = AsyncMock()

        metrics = _make_empty_metrics()

        ai_use_case = MagicMock()
        ai_use_case.build_context_from_metrics.return_value = MagicMock()
        ai_result = MagicMock()
        ai_result.text = "Resumen IA del mes."
        ai_use_case.run = AsyncMock(return_value=ai_result)

        with patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=metrics),
        ), patch(
            "app.services.training.reports._validate_period",
        ):
            with patch(
                "app.services.training.reports.select",
            ) as mock_select:
                # Simular Club lookup separado
                club_result = MagicMock()
                club_result.scalar_one_or_none.return_value = club

                call_count = {"n": 0}

                async def mock_execute2(stmt):
                    call_count["n"] += 1
                    result = MagicMock()
                    if call_count["n"] == 1:
                        result.scalar_one_or_none.return_value = None
                    elif call_count["n"] == 2:
                        result.scalar_one_or_none.return_value = club
                    else:
                        result.scalars.return_value.all.return_value = []
                    return result

                db.execute = mock_execute2

                report = await generate_monthly_report(
                    db=db,
                    club_id=1,
                    year=2026,
                    month=3,
                    generator_user=coach,
                    ai_use_case=ai_use_case,
                )

        assert report is not None
        db.add.assert_called_once()
        db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_409_si_existe_sin_force_regenerate(self):
        db = AsyncMock()
        coach = _make_user(1)
        existing = _make_report()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = existing
            return result

        db.execute = mock_execute

        with patch("app.services.training.reports._validate_period"):
            with pytest.raises(ValueError, match="Ya existe"):
                await generate_monthly_report(
                    db=db,
                    club_id=1,
                    year=2026,
                    month=3,
                    generator_user=coach,
                    force_regenerate=False,
                )

    @pytest.mark.asyncio
    async def test_force_regenerate_sobreescribe(self):
        db = AsyncMock()
        coach = _make_user(1)
        existing = _make_report()
        club = _make_club(1)

        metrics = _make_empty_metrics()

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = existing
            elif call_count["n"] == 2:
                result.scalar_one_or_none.return_value = club
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute
        db.flush = AsyncMock()

        ai_use_case = MagicMock()
        ai_use_case.build_context_from_metrics.return_value = MagicMock()
        ai_result = MagicMock()
        ai_result.text = "Narrativa regenerada."
        ai_use_case.run = AsyncMock(return_value=ai_result)

        with patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=metrics),
        ), patch("app.services.training.reports._validate_period"):
            report = await generate_monthly_report(
                db=db,
                club_id=1,
                year=2026,
                month=3,
                generator_user=coach,
                force_regenerate=True,
                ai_use_case=ai_use_case,
            )

        # Debe retornar el existente modificado (no un objeto nuevo)
        assert report is existing
        assert existing.ai_summary == "Narrativa regenerada."
        db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_periodo_futuro_rechazado(self):
        db = AsyncMock()
        coach = _make_user(1)
        today = date.today()

        with pytest.raises(ValueError, match="cerrado"):
            await generate_monthly_report(
                db=db,
                club_id=1,
                year=today.year,
                month=today.month,
                generator_user=coach,
            )


# ---------------------------------------------------------------------------
# Tests send_monthly_report_email
# ---------------------------------------------------------------------------


class TestSendMonthlyReportEmail:
    @pytest.mark.asyncio
    async def test_envia_a_admins_y_actualiza_sent_at(self):
        db = AsyncMock()
        report = _make_report()
        admin1 = _make_user(10, "admin1@club.com", "Carlos")
        admin2 = _make_user(11, "admin2@club.com", "María")

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = report
            else:
                result.scalars.return_value.all.return_value = [admin1, admin2]
            return result

        db.execute = mock_execute
        db.flush = AsyncMock()

        notif_service = MagicMock()
        ok_result = MagicMock()
        ok_result.success = True
        notif_service.send = AsyncMock(return_value=ok_result)

        dispatcher = MagicMock()

        results = await send_monthly_report_email(
            db=db,
            report_id=1,
            notification_service=notif_service,
            dispatcher=dispatcher,
        )

        assert len(results) == 2
        assert all(r.success for r in results)
        assert notif_service.send.call_count == 2
        assert report.sent_at is not None
        db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_reporte_no_encontrado_lanza_error(self):
        db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        notif_service = MagicMock()
        dispatcher = MagicMock()

        with pytest.raises(ValueError, match="no encontrado"):
            await send_monthly_report_email(
                db=db,
                report_id=999,
                notification_service=notif_service,
                dispatcher=dispatcher,
            )

    @pytest.mark.asyncio
    async def test_sin_admins_no_envia(self):
        db = AsyncMock()
        report = _make_report()

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = report
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute
        db.flush = AsyncMock()

        notif_service = MagicMock()
        notif_service.send = AsyncMock()
        dispatcher = MagicMock()

        results = await send_monthly_report_email(
            db=db,
            report_id=1,
            notification_service=notif_service,
            dispatcher=dispatcher,
        )

        assert results == []
        notif_service.send.assert_not_called()


# ---------------------------------------------------------------------------
# Tests parent_monthly_summary
# ---------------------------------------------------------------------------


class TestParentMonthlySummary:
    @pytest.mark.asyncio
    async def test_lanza_permission_error_si_atleta_no_pertenece(self):
        db = AsyncMock()

        with patch(
            "app.services.training.reports.parent_athlete_ids",
            AsyncMock(return_value=[5, 6]),
        ):
            with pytest.raises(PermissionError, match="permiso"):
                await parent_monthly_summary(
                    db=db,
                    parent_user_id=99,
                    athlete_id=7,
                    year=2026,
                    month=3,
                )

    @pytest.mark.asyncio
    async def test_calcula_resumen_correcto(self):
        from app.models.training_session import AttendanceStatus, SessionStatus

        db = AsyncMock()
        athlete = MagicMock()
        athlete.id = 5
        athlete.club_id = 1
        athlete.first_name = "Lucas"
        athlete.last_name = "García"

        session1 = MagicMock()
        session1.id = 10
        session1.technical_focus = "Frenado"
        session1.status = SessionStatus.EXECUTED
        session2 = MagicMock()
        session2.id = 11
        session2.technical_focus = "Pedaleo"
        session2.status = SessionStatus.EXECUTED

        att1 = MagicMock()
        att1.session_id = 10
        att1.athlete_id = 5
        att1.status = AttendanceStatus.PRESENTE

        att2 = MagicMock()
        att2.session_id = 11
        att2.athlete_id = 5
        att2.status = AttendanceStatus.AUSENTE

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = athlete
            elif call_count["n"] == 2:
                result.scalars.return_value.all.return_value = [session1, session2]
            else:
                result.scalars.return_value.all.return_value = [att1, att2]
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
        assert summary.athlete_name == "Lucas García"
        assert summary.count_present == 1
        assert summary.count_total == 2
        assert summary.percentage == 50.0
        assert set(summary.focos_técnicos) == {"Frenado", "Pedaleo"}


# ---------------------------------------------------------------------------
# H8 — LLM timeout se propaga desde generate_monthly_report → 503 en router
# ---------------------------------------------------------------------------


class TestLLMTimeoutPropagation:
    """Verifica que MonthlyReportLLMTimeout escala hasta el router como 503.

    Usa dos niveles de cobertura:
    1. Servicio: generate_monthly_report re-lanza MonthlyReportLLMTimeout cuando
       el use case lo lanza.
    2. Router: create_monthly_report captura MonthlyReportLLMTimeout y responde 503.
    """

    @pytest.mark.asyncio
    async def test_generate_monthly_report_propagates_llm_timeout(self):
        """generate_monthly_report no captura MonthlyReportLLMTimeout — lo deja burbujear."""
        from app.services.ai.use_cases.monthly_report import MonthlyReportLLMTimeout

        db = AsyncMock()
        coach = _make_user(1)
        club = _make_club(1)
        metrics = _make_empty_metrics()

        async def mock_execute(stmt):
            call_n[0] += 1
            result = MagicMock()
            if call_n[0] == 1:
                result.scalar_one_or_none.return_value = None  # no existing report
            elif call_n[0] == 2:
                result.scalar_one_or_none.return_value = club
            else:
                result.scalars.return_value.all.return_value = []
            return result

        call_n = [0]
        db.execute = mock_execute
        db.add = MagicMock()
        db.flush = AsyncMock()

        ai_use_case = MagicMock()
        ai_use_case.build_context_from_metrics.return_value = MagicMock()
        ai_use_case.run = AsyncMock(side_effect=MonthlyReportLLMTimeout("timeout simulado"))

        with patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=metrics),
        ), patch("app.services.training.reports._validate_period"):
            with pytest.raises(MonthlyReportLLMTimeout):
                await generate_monthly_report(
                    db=db,
                    club_id=1,
                    year=2026,
                    month=3,
                    generator_user=coach,
                    ai_use_case=ai_use_case,
                )

    @pytest.mark.asyncio
    async def test_router_returns_503_on_llm_timeout(self):
        """El router convierte MonthlyReportLLMTimeout en HTTPException 503."""
        from fastapi import HTTPException
        from app.models.user import UserRole
        from app.routers.monthly_reports import create_monthly_report
        from app.schemas.training_session import MonthlyReportCreate
        from app.services.ai.use_cases.monthly_report import MonthlyReportLLMTimeout

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        coach = _make_user(1)
        coach.role = UserRole.coach

        ai_use_case = MagicMock()

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=MagicMock()),  # coach pertenece al club
        ), patch(
            "app.routers.monthly_reports.generate_monthly_report",
            AsyncMock(side_effect=MonthlyReportLLMTimeout("timeout simulado")),
        ):
            body = MonthlyReportCreate(year=2025, month=3)
            with pytest.raises(HTTPException) as exc_info:
                await create_monthly_report(
                    club_id=1,
                    body=body,
                    db=db,
                    current_user=coach,
                    ai_use_case=ai_use_case,
                )

        assert exc_info.value.status_code == 503
        detail = exc_info.value.detail.lower()
        assert "ia" in detail or "disponible" in detail or "intenta" in detail
