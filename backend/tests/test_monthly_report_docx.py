"""
Tests — feature 022 (T023): descarga del Informe Técnico Mensual en DOCX.

Cubre:
1. Happy path: coach/admin genera y descarga el DOCX (mismo contexto que PDF).
2. 404 si el reporte no existe.
3. 403 si el usuario no pertenece al club (ni es admin).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.schemas.notification import DocumentFormat, DocumentTemplate


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
    r.narrative_blocks = {}
    r.competition_results = []
    r.coach_observations = None
    r.generated_by_user_id = 1
    r.generated_at = datetime.now(timezone.utc)
    r.club = _make_club(club_id)
    return r


class TestDownloadMonthlyReportDocx:
    @pytest.mark.asyncio
    async def test_genera_y_retorna_docx_con_nombres_reales(self):
        from app.models.user import UserRole
        from app.routers.monthly_reports import download_monthly_report_docx

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
        generated.data = b"PK\x03\x04 fake docx bytes"
        generated.content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        generated.filename = "reporte_2026_03.docx"

        notif_service = MagicMock()
        notif_service.generate_document_only = AsyncMock(return_value=generated)

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=MagicMock()),  # coach pertenece al club
        ):
            response = await download_monthly_report_docx(
                club_id=1,
                year=2026,
                month=3,
                db=db,
                current_user=coach,
                notification_service=notif_service,
            )

        assert response.body == b"PK\x03\x04 fake docx bytes"
        assert response.media_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert response.headers["content-disposition"] == (
            'attachment; filename="informe-tecnico-2026-03.docx"'
        )
        notif_service.generate_document_only.assert_awaited_once()

        # Mismo contexto que el PDF (fuente única de verdad): nombres reales,
        # template/format correctos.
        doc_request = notif_service.generate_document_only.await_args.args[0]
        assert doc_request.context["athlete_names"] == {"42": "Juan Pérez"}
        assert doc_request.template == DocumentTemplate.TRAINING_MONTHLY_TECHNICAL_REPORT_DOCX
        assert doc_request.format == DocumentFormat.DOCX

    @pytest.mark.asyncio
    async def test_404_si_reporte_no_existe(self):
        from fastapi import HTTPException
        from app.models.user import UserRole
        from app.routers.monthly_reports import download_monthly_report_docx

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
                await download_monthly_report_docx(
                    club_id=1,
                    year=2026,
                    month=3,
                    db=db,
                    current_user=coach,
                    notification_service=notif_service,
                )

        assert exc_info.value.status_code == 404
        notif_service.generate_document_only.assert_not_called()

    @pytest.mark.asyncio
    async def test_403_si_coach_no_pertenece_al_club(self):
        from fastapi import HTTPException
        from app.models.user import UserRole
        from app.routers.monthly_reports import download_monthly_report_docx

        db = AsyncMock()

        coach = _make_user(2)
        coach.role = UserRole.coach

        notif_service = MagicMock()
        notif_service.generate_document_only = AsyncMock()

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=None),  # no pertenece al club
        ):
            with pytest.raises(HTTPException) as exc_info:
                await download_monthly_report_docx(
                    club_id=1,
                    year=2026,
                    month=3,
                    db=db,
                    current_user=coach,
                    notification_service=notif_service,
                )

        assert exc_info.value.status_code == 403
        db.execute.assert_not_called()
        notif_service.generate_document_only.assert_not_called()


# ---------------------------------------------------------------------------
# 403 por rol: parent no puede descargar el DOCX (guard `require_role`)
# ---------------------------------------------------------------------------
#
# Los tests anteriores llaman a `download_monthly_report_docx` directamente,
# lo que evita por completo la dependencia `require_role([admin, coach])`
# (current_user se pasa como argumento normal). Para validar el guard de rol
# en sí mismo hay que pasar por la app real y sobrescribir `get_current_user`
# (mismo patrón que `test_ai_router.py`): `require_role` depende de
# `get_current_user`, así que al overridearlo el chequeo de rol corre de
# verdad contra el usuario inyectado.


@pytest.mark.asyncio
async def test_parent_403_al_descargar_docx():
    from app.dependencies import get_current_user, get_db
    from app.main import app
    from app.models.user import UserRole

    parent = _make_user(3, email="padre@example.com", first_name="Padre")
    parent.role = UserRole.parent

    db = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: parent
    app.dependency_overrides[get_db] = lambda: db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/clubs/1/monthly-reports/2026/3/docx"
            )
        assert resp.status_code == 403
        db.execute.assert_not_called()
    finally:
        app.dependency_overrides.clear()
