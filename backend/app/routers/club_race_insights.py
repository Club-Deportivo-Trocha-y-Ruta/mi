"""Router ``GET /api/races/{race_event_id}/club-insights`` (Sprint 3).

Vista agregada de insights de todos los atletas del club en una válida
específica. Solo insights activos + aprobados (``is_active=1``,
``coach_approved=True``).

RBAC
====
- coach / admin: ven todos los atletas del club con nombre completo,
  ``summary_excerpt`` y ``confidence``.
- parent: ven todos los atletas listados, pero:
    - Para sus hijos: nombre completo + ``summary_excerpt``.
    - Para otros atletas: ``athlete_display_name="[Atleta del club]"``,
      ``summary_excerpt=None``, ``confidence=None`` (siempre).
- Roles no autorizados (ej. usuario sin membresía de club): 403.

Privacidad Ley 1581 (Colombia)
================================
- ``confidence`` NUNCA se expone a parent.
- ``summary_excerpt`` para atletas ajenos al parent: ``None``.
- ``athlete_id`` se incluye en el item SOLO para coach/admin — el
  frontend parent no debería navegar al detalle de atletas ajenos.
  Para parent, ``athlete_id`` se devuelve como ``0`` en los items
  enmascarados (el frontend lo reconoce como "no navegable").
  DECISIÓN: por simplicidad del contrato se mantiene ``athlete_id``
  en el schema pero el router lo setea a ``0`` para atletas ajenos
  cuando el caller es parent.

URL
===
``GET /api/races/{race_event_id}/club-insights``

Query params:
- ``club_id`` (int, opcional): si no se pasa, usa el club del usuario
  autenticado (primer club con rol coach/parent). Admin debe especificar
  explícitamente.
- ``latest_only`` (bool, default True): solo el insight más reciente
  por atleta. Flag reservado para futura extensión.
- ``limit`` (int, 1..50, default 50): límite de atletas en el response.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.athlete_ai_insight import InsightConfidence
from app.models.club import ClubMember, ClubRole
from app.models.user import User, UserRole
from app.schemas.athlete_race_analysis import (
    ClubInsightByRaceItem,
    ClubInsightsByRaceResponse,
)
from app.services.permissions import parent_athlete_ids, user_club_role
from app.services.race.club_insights import (
    build_race_event_label,
    fetch_club_insights_by_race,
    get_race_event_or_none,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_MASKED_NAME = "[Atleta del club]"
_EXCERPT_LEN = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_club_id(
    db: AsyncSession,
    current_user: User,
    club_id_param: Optional[int],
) -> int:
    """Resuelve el club_id a usar para la consulta.

    Reglas:
    - Si ``club_id_param`` se pasa explícitamente: verificar que el caller
      sea miembro (o admin). Si no, 403.
    - Si no se pasa y el caller es admin: 422 (debe especificar club_id).
    - Si no se pasa y el caller es coach/parent: usa su primer club.
    """
    if club_id_param is not None:
        # Verificar membresía (admin siempre pasa).
        if current_user.role == UserRole.admin:
            return club_id_param

        role = await user_club_role(db, current_user.id, club_id_param)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No eres miembro del club indicado",
            )
        return club_id_param

    # Sin club_id explícito.
    if current_user.role == UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los administradores deben especificar club_id explícitamente",
        )

    # Coach o parent: buscar primer club del usuario.
    stmt = (
        select(ClubMember.club_id)
        .where(ClubMember.user_id == current_user.id)
        .order_by(ClubMember.club_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    first_club_id = result.scalar_one_or_none()

    if first_club_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No perteneces a ningún club. Especifica club_id.",
        )
    return int(first_club_id)


def _build_item_coach(
    athlete_id: int,
    display_name: str,
    valida_num: Optional[int],
    insight_id: Optional[int],
    summary_text: Optional[str],
    generated_at,
    confidence: Optional[InsightConfidence],
) -> ClubInsightByRaceItem:
    """Construye item sin enmascaramiento (coach/admin)."""
    excerpt: Optional[str] = None
    if summary_text:
        excerpt = summary_text[:_EXCERPT_LEN]

    return ClubInsightByRaceItem(
        athlete_id=athlete_id,
        athlete_display_name=display_name,
        valida_num=valida_num,
        insight_id=insight_id,
        summary_excerpt=excerpt,
        generated_at=generated_at,
        confidence=confidence,
    )


def _build_item_parent_own_child(
    athlete_id: int,
    display_name: str,
    valida_num: Optional[int],
    insight_id: Optional[int],
    summary_text: Optional[str],
    generated_at,
) -> ClubInsightByRaceItem:
    """Construye item para el hijo propio del parent (sin confidence)."""
    excerpt: Optional[str] = None
    if summary_text:
        excerpt = summary_text[:_EXCERPT_LEN]

    return ClubInsightByRaceItem(
        athlete_id=athlete_id,
        athlete_display_name=display_name,
        valida_num=valida_num,
        insight_id=insight_id,
        summary_excerpt=excerpt,
        generated_at=generated_at,
        confidence=None,  # NUNCA para parent
    )


def _build_item_parent_other(
    athlete_id: int,
    valida_num: Optional[int],
) -> ClubInsightByRaceItem:
    """Construye item enmascarado para atleta ajeno al parent."""
    return ClubInsightByRaceItem(
        athlete_id=0,  # no navegable — atleta ajeno
        athlete_display_name=_MASKED_NAME,
        valida_num=valida_num,
        insight_id=None,
        summary_excerpt=None,
        generated_at=None,
        confidence=None,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{race_event_id}/club-insights",
    response_model=ClubInsightsByRaceResponse,
    summary="Insights del club en una válida",
    description=(
        "Lista los atletas del club que corrieron una válida específica "
        "junto con su insight activo aprobado más reciente. "
        "RBAC: coach/admin ven todo; parent solo ve datos de sus hijos. "
        "Atletas corridos sin insight aparecen con campos None."
    ),
)
async def list_club_insights_by_race(
    race_event_id: int,
    club_id: Optional[int] = Query(
        default=None,
        ge=1,
        description=(
            "ID del club cuyos atletas listar. Si se omite, "
            "usa el club del usuario autenticado. "
            "Admin DEBE especificarlo."
        ),
    ),
    latest_only: bool = Query(
        default=True,
        description="Solo el insight más reciente por atleta (default True).",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=50,
        description="Máximo de atletas en el response (máx 50).",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClubInsightsByRaceResponse:
    """``GET /api/races/{race_event_id}/club-insights``."""

    # 1. Verificar que el race_event existe.
    event = await get_race_event_or_none(db, race_event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Válida no encontrada",
        )

    # 2. Resolver club_id (con verificación de membresía incluida).
    resolved_club_id = await _resolve_club_id(db, current_user, club_id)

    # 3. Obtener filas de atletas + insights.
    rows = await fetch_club_insights_by_race(
        db,
        race_event_id=race_event_id,
        club_id=resolved_club_id,
        latest_only=latest_only,
        limit=limit,
    )

    # 4. Serializar según RBAC.
    items: list[ClubInsightByRaceItem] = []

    if current_user.role in (UserRole.coach, UserRole.admin):
        # Coach/admin: nombre completo + confidence + excerpt.
        for row in rows:
            athlete = row.athlete
            ins = row.insight
            display_name = f"{athlete.first_name} {athlete.last_name}"

            items.append(
                _build_item_coach(
                    athlete_id=athlete.id,
                    display_name=display_name,
                    valida_num=event.sequence_number,
                    insight_id=ins.id if ins else None,
                    summary_text=ins.summary_text if ins else None,
                    generated_at=ins.generated_at if ins else None,
                    confidence=ins.confidence if ins else None,
                )
            )

    elif current_user.role == UserRole.parent:
        # Parent: necesitamos saber qué atletas son sus hijos.
        child_ids: set[int] = set(
            await parent_athlete_ids(db, current_user.id)
        )

        for row in rows:
            athlete = row.athlete
            ins = row.insight

            if athlete.id in child_ids:
                # Hijo propio: datos completos (sin confidence).
                display_name = f"{athlete.first_name} {athlete.last_name}"
                items.append(
                    _build_item_parent_own_child(
                        athlete_id=athlete.id,
                        display_name=display_name,
                        valida_num=event.sequence_number,
                        insight_id=ins.id if ins else None,
                        summary_text=ins.summary_text if ins else None,
                        generated_at=ins.generated_at if ins else None,
                    )
                )
            else:
                # Atleta ajeno: enmascarado.
                items.append(
                    _build_item_parent_other(
                        athlete_id=athlete.id,
                        valida_num=event.sequence_number,
                    )
                )

    else:
        # Rol no reconocido → 403.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta acción",
        )

    return ClubInsightsByRaceResponse(
        race_event_id=race_event_id,
        race_event_label=build_race_event_label(event),
        total_athletes=len(items),
        items=items,
    )


__all__ = ["router"]
