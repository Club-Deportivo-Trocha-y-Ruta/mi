"""Router de lectura del historial de auditoría (feature 041).

Ver ``specs/041-multi-coach-governance/contracts/audit-log-api.md``. Tres
``APIRouter`` en un solo módulo:

- ``clubs_router`` — ``GET /{club_id}/audit-log`` (§2) y
  ``GET /{club_id}/coach-activity``
  (``contracts/coach-activity-report.md`` §1), montado en ``app/main.py``
  con ``prefix="/api/clubs"``.
- ``athletes_router`` — ``GET /{athlete_id}/audit-log`` (§3), montado con
  ``prefix="/api/athletes"``.
- ``catalog_router`` — ``GET /reason-codes`` (§14), ya lleva su propio
  ``prefix="/api/audit"``.

Estos endpoints **solo leen**: nunca escriben una fila de ``audit_log``
(FR-005 excluye las lecturas puras) y nunca mutan nada (FR-004).

Privacidad (Ley 1581, FR-003): ``sentence_es`` solo nombra al actor (un
adulto); el deportista viaja como ``athlete_id``. El bloque ``detail``
reaplica ``VALUE_ALLOWLIST``/``META_ALLOWLIST`` en tiempo de lectura (§8),
como defensa en profundidad frente a una fila escrita por una versión
anterior de ``record_audit``.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_current_user,
    get_db,
    require_role,
    verify_athlete_access_allow_archived,
)
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.user import User, UserRole
from app.schemas.audit import (
    AuditDiffValue,
    AuditEntryDetail,
    AuditEntryOut,
    AuditListOut,
    AuditReasonCodeListOut,
    AuditReasonCodeOut,
)
from app.services.audit import (
    AUDIT_ENTITY_LABELS,
    AUDIT_FIELD_LABELS,
    AUDIT_REASON_GROUPS,
    AUDIT_REASON_LABELS,
    META_ALLOWLIST,
    VALUE_ALLOWLIST,
    AuditEntityType,
    AuditReasonCode,
    AuditReasonGroup,
    render_sentence,
)
from app.schemas.coach_activity import CoachActivityOut
from app.services.coach_activity import (
    ClubNotFoundError,
    CoachNotInClubError,
    InvalidPeriodError,
    compute_coach_activity,
)
from app.services.permissions import can_view_audit

logger = logging.getLogger(__name__)

clubs_router = APIRouter()
athletes_router = APIRouter()
catalog_router = APIRouter(prefix="/api/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Validación y construcción de filtros compartida por ambos endpoints (§2, §3)
# ---------------------------------------------------------------------------


def _validate_date_range(from_date: date | None, to_date: date | None) -> None:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El rango de fechas es inválido: 'from' debe ser anterior o igual a 'to'.",
        )


def _common_filters(
    *,
    actor_user_id: int | None,
    entity_type: AuditEntityType | None,
    action: AuditAction | None,
    from_date: date | None,
    to_date: date | None,
    request_id: str | None,
) -> list[Any]:
    """Filtros compartidos por club y atleta (§2.1/§3): todo excepto la
    predicado base (``club_id`` o ``athlete_id``), que decide cada llamador.
    """
    filters: list[Any] = []
    if actor_user_id is not None:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if entity_type is not None:
        filters.append(AuditLog.entity_type == entity_type.value)
    if action is not None:
        filters.append(AuditLog.action == action)
    if from_date is not None:
        filters.append(AuditLog.occurred_at >= datetime.combine(from_date, time.min))
    if to_date is not None:
        filters.append(
            AuditLog.occurred_at < datetime.combine(to_date + timedelta(days=1), time.min)
        )
    if request_id is not None:
        filters.append(AuditLog.request_id == request_id)
    return filters


async def _paginated_audit_log(
    db: AsyncSession, filters: list[Any], limit: int, offset: int
) -> AuditListOut:
    """Las dos consultas del presupuesto de rendimiento (§11): la página con
    el ``LEFT JOIN`` sobre ``users`` (§6.1) y el conteo total, nunca la
    materialización completa de las filas.
    """
    where_clause = and_(*filters) if filters else True

    rows_stmt = (
        select(AuditLog, User.first_name, User.last_name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(where_clause)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count()).select_from(AuditLog).where(where_clause)

    rows = (await db.execute(rows_stmt)).all()
    total = (await db.execute(count_stmt)).scalar_one()

    items = [
        _build_entry(entry, first_name, last_name) for entry, first_name, last_name in rows
    ]
    return AuditListOut(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# actor_display_name (§6) y construcción de una fila de respuesta (§5, §7, §8)
# ---------------------------------------------------------------------------


_AUTOMATED_ACTOR_LABELS: dict[AuditActorKind, str] = {
    AuditActorKind.system: "Sistema",
    AuditActorKind.webhook: "Servicio externo",
    AuditActorKind.cron: "Tarea programada",
}


def _actor_display_name(
    entry: AuditLog, first_name: str | None, last_name: str | None
) -> str:
    """Resolución de §6: `LEFT JOIN` para actores humanos, etiqueta fija
    para actores automatizados, y el caso defensivo de §6.2 cuando
    ``actor_kind = user`` pero el `JOIN` no trae fila.
    """
    automated_label = _AUTOMATED_ACTOR_LABELS.get(entry.actor_kind)
    if automated_label is not None:
        return automated_label
    if first_name and last_name:
        return f"{first_name} {last_name}".strip()
    return "Usuario no disponible"


def _filter_diff(
    entity_type: str, audit_id: int, diff_json: dict[str, Any] | None
) -> dict[str, AuditDiffValue] | None:
    """Refiltra ``diff_json`` a través de ``VALUE_ALLOWLIST`` en tiempo de
    lectura (§8) — nunca confía en lo ya persistido.
    """
    if not diff_json:
        return None
    allowed = VALUE_ALLOWLIST.get(entity_type, frozenset())
    result: dict[str, AuditDiffValue] = {}
    for field, value in diff_json.items():
        if field not in allowed:
            logger.warning(
                "audit_read_dropped_field | audit_id=%s entity_type=%s field=%s",
                audit_id,
                entity_type,
                field,
            )
            continue
        if isinstance(value, dict):
            result[field] = AuditDiffValue(before=value.get("before"), after=value.get("after"))
    return result or None


def _filter_meta(
    entity_type: str, audit_id: int, meta_json: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Refiltra ``meta_json`` a través de ``META_ALLOWLIST`` en tiempo de
    lectura (§8).
    """
    if not meta_json:
        return None
    result: dict[str, Any] = {}
    for key, value in meta_json.items():
        if key not in META_ALLOWLIST:
            logger.warning(
                "audit_read_dropped_field | audit_id=%s entity_type=%s field=%s",
                audit_id,
                entity_type,
                key,
            )
            continue
        result[key] = value
    return result or None


def _build_entry(entry: AuditLog, first_name: str | None, last_name: str | None) -> AuditEntryOut:
    actor_display_name = _actor_display_name(entry, first_name, last_name)
    sentence_es = render_sentence(entry, actor_display_name)

    try:
        entity_type_enum = AuditEntityType(entry.entity_type)
    except ValueError:
        entity_type_enum = None
    entity_label = (
        AUDIT_ENTITY_LABELS.get(entity_type_enum, entry.entity_type)
        if entity_type_enum is not None
        else entry.entity_type
    )

    reason_label: str | None = None
    if entry.reason_code:
        try:
            reason_label = AUDIT_REASON_LABELS.get(AuditReasonCode(entry.reason_code))
        except ValueError:
            reason_label = None

    changed_fields = list(entry.changed_fields or [])
    changed_field_labels = [AUDIT_FIELD_LABELS.get(field, field) for field in changed_fields]

    detail = AuditEntryDetail(
        changed_fields=changed_fields,
        changed_field_labels=changed_field_labels,
        diff=_filter_diff(entry.entity_type, entry.id, entry.diff_json),
        meta=_filter_meta(entry.entity_type, entry.id, entry.meta_json),
    )

    return AuditEntryOut(
        id=entry.id,
        occurred_at=entry.occurred_at,
        actor_user_id=entry.actor_user_id,
        actor_kind=entry.actor_kind,
        actor_role=entry.actor_role,
        actor_display_name=actor_display_name,
        action=entry.action,
        entity_type=entity_type_enum or AuditEntityType(entry.entity_type),
        entity_id=entry.entity_id,
        entity_label=entity_label,
        club_id=entry.club_id,
        athlete_id=entry.athlete_id,
        reason_code=entry.reason_code,
        reason_label=reason_label,
        sentence_es=sentence_es,
        request_id=entry.request_id,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id}/audit-log (§2)
# ---------------------------------------------------------------------------


@clubs_router.get(
    "/{club_id}/audit-log",
    response_model=AuditListOut,
    tags=["audit"],
)
async def list_club_audit_log(
    club_id: int,
    actor_user_id: int | None = Query(default=None, ge=1),
    athlete_id: int | None = Query(default=None, ge=1),
    entity_type: AuditEntityType | None = Query(default=None),
    action: AuditAction | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    request_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AuditListOut:
    """FR-006/US1 AS8: historial del club, admin y coaches del club."""
    if not can_view_audit(current_user, club_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver el historial de este club.",
        )

    _validate_date_range(from_date, to_date)

    filters = [AuditLog.club_id == club_id]
    if athlete_id is not None:
        filters.append(AuditLog.athlete_id == athlete_id)
    filters.extend(
        _common_filters(
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            action=action,
            from_date=from_date,
            to_date=to_date,
            request_id=request_id,
        )
    )

    return await _paginated_audit_log(db, filters, limit, offset)


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id}/coach-activity
# (contracts/coach-activity-report.md §1; T081)
# ---------------------------------------------------------------------------


@clubs_router.get(
    "/{club_id}/coach-activity",
    response_model=CoachActivityOut,
    tags=["audit"],
)
async def get_coach_activity(
    club_id: int,
    period_from: date = Query(alias="from"),
    period_to: date = Query(alias="to"),
    coach_user_id: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoachActivityOut:
    """FR-013/FR-032/US7: actividad por entrenador de un club y período.

    Superficie interna de gestión: solo admin y entrenadores del propio club
    (§4). Un padre o un deportista recibe `403`, igual que un entrenador de
    otro club; nunca se renderiza bajo ``routes/parents/`` ni viaja en un
    correo, PDF o boletín de familia.

    ``from``/``to`` son obligatorios a propósito (§1.1): un "mes actual"
    implícito ataría la reconciliación de SC-008 al reloj del servidor.
    ``coach_user_id`` recorta ``coaches``; ``club_totals`` jamás se recorta.

    Se reutiliza ``can_view_audit`` en lugar del ``can_view_coach_activity``
    que nombra el contrato: la tabla de RBAC del §4 es idéntica a la del
    historial (admin siempre, coach solo su club, el resto `403`) y
    ``app/services/permissions.py`` pertenece a otra tarea de esta oleada.

    Privacidad (Ley 1581): el payload son nombres de personal adulto y
    enteros. El log de error solo lleva ``club_id`` y la ventana.
    """
    if not can_view_audit(current_user, club_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver la actividad de este club.",
        )

    try:
        return await compute_coach_activity(
            db,
            club_id=club_id,
            period_from=period_from,
            period_to=period_to,
            coach_user_id=coach_user_id,
        )
    except InvalidPeriodError:
        logger.info(
            "coach_activity: periodo inválido club_id=%s from=%s to=%s",
            club_id,
            period_from,
            period_to,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "El periodo debe empezar antes de terminar y no superar 366 días."
            ),
        ) from None
    except ClubNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club no encontrado",
        ) from None
    except CoachNotInClubError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrenador no encontrado en este club",
        ) from None


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/audit-log (§3, trampa de orden de §4.3)
# ---------------------------------------------------------------------------


@athletes_router.get(
    "/{athlete_id}/audit-log",
    response_model=AuditListOut,
    tags=["audit"],
    dependencies=[Depends(require_role([UserRole.admin, UserRole.coach]))],
)
async def list_athlete_audit_log(
    actor_user_id: int | None = Query(default=None, ge=1),
    entity_type: AuditEntityType | None = Query(default=None),
    action: AuditAction | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    request_id: str | None = Query(default=None),
    limit: int = Query(default=15, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    athlete: Athlete = Depends(verify_athlete_access_allow_archived),
    db: AsyncSession = Depends(get_db),
) -> AuditListOut:
    """FR-007/US7 AS6: panel de historial del deportista.

    ``require_role`` corre primero (vía ``dependencies=``, resuelto antes
    que los parámetros de la función) para que un padre que intenta adivinar
    un ``athlete_id`` reciba `403` y no el `404` de ``verify_athlete_access``
    — el orden es lo que evita confirmar si el id existe (§4.3).
    """
    _validate_date_range(from_date, to_date)

    filters = [AuditLog.athlete_id == athlete.id]
    filters.extend(
        _common_filters(
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            action=action,
            from_date=from_date,
            to_date=to_date,
            request_id=request_id,
        )
    )

    return await _paginated_audit_log(db, filters, limit, offset)


# ---------------------------------------------------------------------------
# GET /api/audit/reason-codes (§14)
# ---------------------------------------------------------------------------


@catalog_router.get(
    "/reason-codes",
    response_model=AuditReasonCodeListOut,
    dependencies=[Depends(require_role([UserRole.admin, UserRole.coach]))],
)
async def list_audit_reason_codes(
    group: AuditReasonGroup | None = Query(default=None),
) -> AuditReasonCodeListOut:
    """Catálogo cerrado de motivos (§14) — sin club, sin SQL, sin paginar."""
    groups = [group] if group is not None else list(AuditReasonGroup)
    items = [
        AuditReasonCodeOut(
            code=member.value,
            label=AUDIT_REASON_LABELS[AuditReasonCode(member.value)],
            group=g,
        )
        for g in groups
        for member in AUDIT_REASON_GROUPS[g]
    ]
    return AuditReasonCodeListOut(items=items)
