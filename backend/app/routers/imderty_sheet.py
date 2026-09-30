"""IMDERTY monthly sheet and readiness routes.

``POST /api/clubs/{club_id}/imderty-sheet`` (US1, T019) generates and
streams the FO-GDD-057 workbook — nothing is written to disk or storage, the
whole request builds the file in memory and returns it.

``GET /api/clubs/{club_id}/imderty-sheet/readiness`` (US3, T042) lists the
readiness gaps of ``services/imderty/readiness.py::build_readiness`` for the
same month range, so a coach can fix them before downloading. It reuses the
``SheetRequest`` schema purely for its month-range validation (format,
``to >= from``, ≤ 12 months) — the same 422 rules ``POST`` enforces — even
though this route takes the range as query params, not a body.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.club import Club
from app.models.imderty import ClubImdertySettings, ImdertyBarrio
from app.models.user import User
from app.schemas.imderty import ImdertySheetHeader, ReadinessRead, SheetRequest
from app.services.audit import (
    AuditAction,
    AuditDocumentKind,
    AuditEntityType,
    record_audit,
)
from app.services.imderty.attendance_grid import (
    active_athletes_in_range,
    build_attendance_grid,
)
from app.services.imderty.readiness import ReadinessTooLarge, build_readiness
from app.services.imderty.rows import build_rows, load_authorized_sensitive_data
from app.services.imderty.workbook import RowValues, SheetTooLarge, build_sheet

router = APIRouter(tags=["imderty-sheet"])

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


async def _require_club_staff(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Club:
    """Thin wrapper around ``app.routers.imderty.require_club_staff``.

    Same lazy-import pattern as ``imderty_settings.py::_require_club_staff``:
    ``imderty.py`` imports this module's ``router`` at the top, before
    defining its own RBAC dependencies further down the file, so a
    module-level import here would be circular.
    """
    from app.routers.imderty import require_club_staff

    return await require_club_staff(club_id, current_user, db)


def _month_range(from_month: str, to_month: str) -> list[date]:
    """First-of-month dates from ``from_month`` to ``to_month`` (inclusive).

    Both are already validated as ``YYYY-MM`` by ``SheetRequest``.
    """
    start = datetime.strptime(from_month, "%Y-%m").date().replace(day=1)
    end = datetime.strptime(to_month, "%Y-%m").date().replace(day=1)
    months: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(date(year, month, 1))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _period_label(months: list[date]) -> str:
    """``2026-11_2027-02`` for a range (first and last month, zero-padded)."""
    return f"{months[0]:%Y-%m}_{months[-1]:%Y-%m}"


def _month_bounds(month: date) -> tuple[date, date]:
    last_day = calendar.monthrange(month.year, month.month)[1]
    return month, month.replace(day=last_day)


def _parse_month_range(from_month: str, to_month: str) -> tuple[str, str]:
    """Validates ``from``/``to`` with ``SheetRequest``'s own rules (format,
    ``to >= from``, ≤ 12 months) and raises a 422 with a Spanish message
    that never echoes the submitted value — only ``SheetRequest``'s own
    validator text, which never names the input either.
    """
    try:
        parsed = SheetRequest.model_validate({"from": from_month, "to": to_month})
    except ValidationError as exc:
        detail = exc.errors()[0].get("msg", "Rango de meses inválido")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        ) from exc
    return parsed.from_month, parsed.to_month


def _settings_to_header(settings: ClubImdertySettings) -> ImdertySheetHeader:
    return ImdertySheetHeader(
        contractor_name=settings.contractor_name,
        venue=settings.venue,
        training_days=settings.training_days,
        schedule=settings.schedule,
        programs=list(settings.programs or []),
    )


@router.post(
    "/clubs/{club_id}/imderty-sheet",
    response_class=Response,
    responses={
        200: {
            "content": {XLSX_MEDIA_TYPE: {}},
            "description": "Archivo XLSX de la planilla de asistencia IMDERTY",
        },
        403: {"description": "Sin acceso al club"},
        404: {"description": "Club no encontrado"},
        422: {
            "description": (
                "Rango de meses inválido o un mes con más de 480 "
                "deportistas activos"
            )
        },
    },
    summary="Generar la planilla mensual de asistencia IMDERTY",
)
async def generate_imderty_sheet(
    body: SheetRequest,
    club: Club = Depends(_require_club_staff),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Builds and streams the FO-GDD-057 workbook for ``body``'s month range.

    The header comes from ``body.header`` when given, otherwise from the
    club's saved ``ClubImdertySettings`` (or blank when neither exists).
    ``body.header`` is always "for this download only" — it is never
    persisted — *unless* ``save_header_as_default`` is also set, in which
    case it get-or-create-upserts ``ClubImdertySettings`` the same way
    ``PUT /imderty-settings`` does (``routers/imderty_settings.py``), audit
    entry included.
    """
    months = _month_range(body.from_month, body.to_month)

    settings_result = await db.execute(
        select(ClubImdertySettings).where(ClubImdertySettings.club_id == club.id)
    )
    settings = settings_result.scalar_one_or_none()

    header = body.header
    if header is None and settings is not None:
        header = _settings_to_header(settings)

    if body.header is not None and body.save_header_as_default:
        data = body.header.model_dump(mode="json")
        is_create = settings is None
        if settings is None:
            settings = ClubImdertySettings(club_id=club.id, **data)
            db.add(settings)
        else:
            for key, value in data.items():
                setattr(settings, key, value)
        await db.flush()
        await record_audit(
            db,
            action=AuditAction.create if is_create else AuditAction.update,
            entity_type=AuditEntityType.club_imderty_settings,
            entity_id=club.id,
            actor=current_user,
            club_id=club.id,
            changed_fields=sorted(data.keys()),
        )

    barrios_result = await db.execute(
        select(ImdertyBarrio)
        .where(ImdertyBarrio.is_active.is_(True))
        .order_by(ImdertyBarrio.name)
    )
    barrios = list(barrios_result.scalars().all())

    rows_by_month: dict[date, list[RowValues]] = {}
    row_count = 0
    for month in months:
        month_start, month_end = _month_bounds(month)
        athletes = await active_athletes_in_range(db, club.id, month_start, month_end)
        grid = await build_attendance_grid(
            db, club.id, month_start, month_end, athletes=athletes
        )
        # Columns L/N/O (disability, victim, ethnicity) are filled only for
        # athletes with an *active* sensitive-data authorization (FR-006/7).
        # Loaded per month, in one batch query, never through an ``Athlete``
        # relationship and never logged.
        sensitive = await load_authorized_sensitive_data(
            db, [athlete.id for athlete in athletes]
        )
        month_rows = build_rows(athletes, grid, month, sensitive=sensitive)
        rows_by_month[month] = month_rows
        row_count += len(month_rows)

    try:
        content = build_sheet(months, rows_by_month, header, barrios)
    except SheetTooLarge:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Ese mes supera el máximo de 480 deportistas que admite la "
                "planilla"
            ),
        )

    # Canonical ``YYYY-MM`` from the parsed range (never the raw input), so
    # the file name and the audit meta hold only months (US4, T049).
    period = _period_label(months)
    filename = f"FO-GDD-057_asistencia_{period}.xlsx"

    # Readiness gap count for the audit row (T043). The sheet above already
    # passed the 480-athlete limit, so ``ReadinessTooLarge`` cannot fire here.
    readiness = await build_readiness(db, club.id, months)

    # Export row (contracts/api.md §"POST .../imderty-sheet", data-model.md
    # §audit): exactly these five keys, all in ``META_ALLOWLIST``. Months and
    # counts only — never a name, a document number or a value of the new
    # IMDERTY fields. ``row_count`` is the number of athlete rows written
    # across every month sheet; ``gap_count`` the number of athletes the
    # readiness report lists with at least one gap.
    await record_audit(
        db,
        action=AuditAction.export,
        entity_type=AuditEntityType.imderty_attendance_sheet,
        entity_id=club.id,
        actor=current_user,
        club_id=club.id,
        meta={
            "document_kind": AuditDocumentKind.imderty_attendance_xlsx.value,
            "from_month": f"{months[0]:%Y-%m}",
            "to_month": f"{months[-1]:%Y-%m}",
            "row_count": row_count,
            "gap_count": len(readiness.gaps),
        },
    )

    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


@router.get(
    "/clubs/{club_id}/imderty-sheet/readiness",
    responses={
        403: {"description": "Sin acceso al club"},
        404: {"description": "Club no encontrado"},
        422: {
            "description": (
                "Rango de meses inválido o un mes con más de 480 "
                "deportistas activos"
            )
        },
    },
    summary="Reporte de disponibilidad previo a la planilla IMDERTY",
)
async def get_imderty_sheet_readiness(
    club: Club = Depends(_require_club_staff),
    db: AsyncSession = Depends(get_db),
    from_month: str = Query(alias="from"),
    to_month: str = Query(alias="to"),
) -> ReadinessRead:
    """Readiness gaps for ``from``..``to`` (contracts/api.md §"GET
    .../readiness"). Same validation as the ``POST`` route (month format,
    ``to >= from``, ≤ 12 months, and ≤ 480 active athletes per month).

    ``display_name`` in the response is built from platform fields already
    visible to admin/coach elsewhere in the app; nothing here logs it.
    """
    validated_from, validated_to = _parse_month_range(from_month, to_month)
    months = _month_range(validated_from, validated_to)

    try:
        return await build_readiness(db, club.id, months)
    except ReadinessTooLarge:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Ese mes supera el máximo de 480 deportistas que admite la "
                "planilla"
            ),
        )
