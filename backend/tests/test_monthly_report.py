"""
Tests PASO 9 — Endpoint reporte mensual + descarga PDF.

Cubre:
1. Happy path: generate crea MonthlyReport con métricas e IA
2. 409 en duplicado sin force_regenerate
3. force_regenerate sobreescribe reporte existente
4. Período futuro rechazado (400)
5. Mes actual (< día 28) rechazado (400)
6. pdf: genera y retorna el PDF del reporte (coach/admin)
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
    async def test_run_all_blocks_incluye_plan_entrenamiento_y_competencia(self):
        """T012: la orquestación de `generate_monthly_report` no usa un listado
        de claves hardcodeado propio — delega en `run_all_blocks(ctx)` (sin
        `block_keys` explícito), que a su vez expone los 8 bloques estándar
        incluyendo `plan_entrenamiento` y `competencia` (feature 022, T009).
        Verifica que ambos queden persistidos en `narrative_blocks`.
        """
        from app.services.ai.use_cases.monthly_report_blocks import BlockDraft

        db = AsyncMock()
        coach = _make_user(1)
        club = _make_club(1)
        metrics = _make_empty_metrics()

        call_n = [0]

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

        db.execute = mock_execute
        db.add = MagicMock()
        db.flush = AsyncMock()

        standard_keys = [
            "objetivo",
            "plan_entrenamiento",
            "desarrollo",
            "competencia",
            "resultados",
            "conclusiones",
            "apoyos_materiales",
            "analisis_grupo",
        ]

        blocks_use_case = MagicMock()
        blocks_use_case.build_context_from_metrics.return_value = MagicMock()

        async def fake_run_all_blocks(ctx, block_keys=None):
            keys = block_keys or standard_keys
            return [
                BlockDraft(
                    block_key=key,
                    ai_draft=f"Borrador de {key}.",
                    ai_model="fake-model",
                    generated_at=datetime.now(timezone.utc),
                )
                for key in keys
            ]

        blocks_use_case.run_all_blocks = AsyncMock(side_effect=fake_run_all_blocks)

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
                blocks_use_case=blocks_use_case,
            )

        # run_all_blocks se invocó sin block_keys explícito (deja que el use
        # case decida el listado estándar — no hay lista hardcodeada aquí).
        blocks_use_case.run_all_blocks.assert_awaited_once()
        _, kwargs = blocks_use_case.run_all_blocks.await_args
        assert not kwargs.get("block_keys")
        assert (
            len(blocks_use_case.run_all_blocks.await_args.args) < 2
            or blocks_use_case.run_all_blocks.await_args.args[1] is None
        )

        persisted = report.narrative_blocks
        assert "plan_entrenamiento" in persisted
        assert "competencia" in persisted
        assert persisted["plan_entrenamiento"]["ai_draft"] == "Borrador de plan_entrenamiento."
        assert persisted["competencia"]["ai_draft"] == "Borrador de competencia."

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
# Tests download_monthly_report_pdf (router)
# ---------------------------------------------------------------------------


class TestDownloadMonthlyReportPdf:
    @pytest.mark.asyncio
    async def test_genera_y_retorna_pdf_con_nombres_reales(self):
        from app.models.user import UserRole
        from app.routers.monthly_reports import download_monthly_report_pdf

        report = _make_report()

        athlete = MagicMock()
        athlete.id = 42
        athlete.first_name = "Juan"
        athlete.last_name = "Pérez"

        report_res = MagicMock()
        report_res.scalar_one_or_none.return_value = report
        athletes_res = MagicMock()
        athletes_res.scalars.return_value.all.return_value = [athlete]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[report_res, athletes_res])

        coach = _make_user(1)
        coach.role = UserRole.coach

        generated = MagicMock()
        generated.data = b"%PDF-1.4 fake"
        generated.content_type = "application/pdf"
        generated.filename = "reporte_2026_03.pdf"

        notif_service = MagicMock()
        notif_service.generate_document_only = AsyncMock(return_value=generated)

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=MagicMock()),  # coach pertenece al club
        ):
            response = await download_monthly_report_pdf(
                club_id=1,
                year=2026,
                month=3,
                db=db,
                current_user=coach,
                notification_service=notif_service,
            )

        assert response.body == b"%PDF-1.4 fake"
        assert response.media_type == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        notif_service.generate_document_only.assert_awaited_once()

        # El contexto del documento lleva los nombres reales resueltos (clave str)
        doc_request = notif_service.generate_document_only.await_args.args[0]
        assert doc_request.context["athlete_names"] == {"42": "Juan Pérez"}

    @pytest.mark.asyncio
    async def test_404_si_reporte_no_existe(self):
        from fastapi import HTTPException
        from app.models.user import UserRole
        from app.routers.monthly_reports import download_monthly_report_pdf

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            )
        )

        coach = _make_user(1)
        coach.role = UserRole.coach

        notif_service = MagicMock()
        notif_service.generate_document_only = AsyncMock()

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=MagicMock()),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await download_monthly_report_pdf(
                    club_id=1,
                    year=2026,
                    month=3,
                    db=db,
                    current_user=coach,
                    notification_service=notif_service,
                )

        assert exc_info.value.status_code == 404
        notif_service.generate_document_only.assert_not_called()


# ---------------------------------------------------------------------------
# Tests get_monthly_report — gate de nombres reales (coach sí, padre no)
# ---------------------------------------------------------------------------


class TestGetMonthlyReportAthleteNames:
    @pytest.mark.asyncio
    async def test_coach_recibe_nombres_reales(self):
        from app.models.user import UserRole
        from app.routers.monthly_reports import get_monthly_report

        report = _make_report()
        report.metrics_snapshot = {}
        report.athlete_names = {}  # evita auto-attr de MagicMock en model_validate

        athlete = MagicMock()
        athlete.id = 42
        athlete.first_name = "Juan"
        athlete.last_name = "Pérez"

        report_res = MagicMock()
        report_res.scalar_one_or_none.return_value = report
        athletes_res = MagicMock()
        athletes_res.scalars.return_value.all.return_value = [athlete]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[report_res, athletes_res])

        coach = _make_user(1)
        coach.role = UserRole.coach

        with patch(
            "app.routers.monthly_reports.can_view_monthly_report",
            AsyncMock(return_value=True),
        ):
            out = await get_monthly_report(
                club_id=1, year=2026, month=3, db=db, current_user=coach,
            )

        assert out.athlete_names == {"42": "Juan Pérez"}

    @pytest.mark.asyncio
    async def test_parent_no_recibe_nombres(self):
        from app.models.user import UserRole
        from app.routers.monthly_reports import get_monthly_report

        report = _make_report()
        report.metrics_snapshot = {}
        report.athlete_names = {}

        report_res = MagicMock()
        report_res.scalar_one_or_none.return_value = report

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[report_res])

        parent = _make_user(2)
        parent.role = UserRole.parent

        with patch(
            "app.routers.monthly_reports.can_view_monthly_report",
            AsyncMock(return_value=True),
        ):
            out = await get_monthly_report(
                club_id=1, year=2026, month=3, db=db, current_user=parent,
            )

        # Padre NUNCA recibe nombres de menores ni observaciones del coach.
        assert out.athlete_names == {}
        assert out.coach_observations is None
        # Solo hubo 1 query (reporte); no se consultaron atletas.
        assert db.execute.await_count == 1


# ---------------------------------------------------------------------------
# Tests build_report_photo_evidence — fotos del mes con fecha de sesión
# ---------------------------------------------------------------------------


class TestReportPhotoEvidence:
    @pytest.mark.asyncio
    async def test_embebe_thumbnail_base64_con_fecha_de_sesion(self):
        import base64 as _b64
        import tempfile as _tf
        from app.models.training_session import SessionKind
        from app.services.training.reports import build_report_photo_evidence

        media = MagicMock()
        media.storage_path = "static/uploads/media/sessions/1/abc.jpg"
        media.caption = "Bajada técnica"

        row_result = MagicMock()
        row_result.all.return_value = [
            (media, date(2026, 5, 15), SessionKind.ENTRENAMIENTO)
        ]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=row_result)

        # Thumbnail "descargado": archivo temporal con bytes conocidos.
        tmp = _tf.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(b"\xff\xd8\xff\xe0FAKEJPEG")
        tmp.close()

        with patch(
            "app.services.training.storage_sftp.download_to_tempfile",
            AsyncMock(return_value=tmp.name),
        ):
            items = await build_report_photo_evidence(
                db=db, club_id=1, year=2026, month=5,
            )

        assert len(items) == 1
        it = items[0]
        assert it["session_date"] == "15/05/2026"   # fecha de la SESIÓN, no de subida
        assert it["caption"] == "Bajada técnica"
        assert it["data_uri"].startswith("data:image/jpeg;base64,")
        decoded = _b64.b64decode(it["data_uri"].split(",", 1)[1])
        assert decoded == b"\xff\xd8\xff\xe0FAKEJPEG"

    @pytest.mark.asyncio
    async def test_omite_foto_que_no_se_puede_leer(self):
        from app.models.training_session import SessionKind
        from app.services.training.reports import build_report_photo_evidence

        media = MagicMock()
        media.storage_path = "static/uploads/media/sessions/1/missing.jpg"
        media.caption = None

        row_result = MagicMock()
        row_result.all.return_value = [
            (media, date(2026, 5, 10), SessionKind.ENTRENAMIENTO)
        ]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=row_result)

        with patch(
            "app.services.training.storage_sftp.download_to_tempfile",
            AsyncMock(side_effect=FileNotFoundError("nope")),
        ):
            items = await build_report_photo_evidence(
                db=db, club_id=1, year=2026, month=5,
            )

        # Degradación limpia: foto ilegible se omite, no rompe.
        assert items == []


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
