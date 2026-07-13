"""Router del mission control ("resumen del coach") en el home del entrenador.

Agrega, en una sola llamada, los indicadores que el coach necesita revisar al
iniciar sesión: consentimientos pendientes, insights de IA desactualizados y
carga semanal planificada por banda de edad. El endpoint se agrega en la fase
Foundational (ver `specs/031-coach-home-mission-control/tasks.md`).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.user import User, UserRole
from app.schemas.dashboard import CoachSummaryOut
from app.services.dashboard_summary import (
    compute_consents_pending,
    compute_insights_stale,
    compute_weekly_load,
)
from app.services.permissions import coach_club_ids as _coach_club_ids

router = APIRouter()


@router.get("/coach-summary", response_model=CoachSummaryOut)
async def get_coach_summary(
    club_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> CoachSummaryOut:
    """Resumen agregado del mission control del coach (home).

    Mismo patrón de scoping por club que ``GET /api/athletes/alerts``
    (``routers/alerts.py:37-65``): admin sin ``club_id`` ve todos los clubes
    sin filtrar; admin con ``club_id`` se acota a ese club; coach siempre se
    acota a sus propios clubes, y un ``club_id`` ajeno es 403.
    """

    club_ids: set[int] | None
    if current_user.role == UserRole.admin:
        club_ids = {club_id} if club_id is not None else None
    else:
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            return CoachSummaryOut(
                generated_at=datetime.now(timezone.utc),
                consents_pending=0,
                insights_stale=0,
                weekly_load=[],
            )
        if club_id is not None:
            if club_id not in coach_clubs:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No perteneces al club indicado como coach",
                )
            club_ids = {club_id}
        else:
            club_ids = coach_clubs

    consents_pending = await compute_consents_pending(db, club_ids)
    insights_stale = await compute_insights_stale(db, club_ids)
    weekly_load = await compute_weekly_load(db, club_ids)

    return CoachSummaryOut(
        generated_at=datetime.now(timezone.utc),
        consents_pending=consents_pending,
        insights_stale=insights_stale,
        weekly_load=weekly_load,
    )
