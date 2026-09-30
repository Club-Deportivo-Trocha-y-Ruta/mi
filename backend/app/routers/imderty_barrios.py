"""IMDERTY barrio catalog routes (US2, ``contracts/api.md`` §"Barrio catalog").

``GET`` is open to any authenticated admin or coach (the picker needs it);
``POST``/``PATCH`` are admin-only via ``require_admin``. This is a public
geography catalog — no minor's data ever passes through it.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.imderty import ImdertyBarrio
from app.models.user import User, UserRole
from app.schemas.imderty import BarrioCreate, BarrioRead, BarrioUpdate
from app.services.audit import AuditAction, AuditEntityType, record_audit

router = APIRouter(tags=["imderty-barrios"])


async def _require_admin_or_coach(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in (UserRole.admin, UserRole.coach):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta acción",
        )
    return current_user


async def _require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Admin only; 403 for every other role.

    Duplicated from ``app.routers.imderty.require_admin`` on purpose: that
    module imports this one's ``router`` to mount it, so importing back
    from here would be a circular import.
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta acción",
        )
    return current_user


@router.get("/imderty/barrios", response_model=list[BarrioRead])
async def list_barrios(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(_require_admin_or_coach),
) -> list[ImdertyBarrio]:
    stmt = select(ImdertyBarrio).order_by(ImdertyBarrio.name)
    if not include_inactive:
        stmt = stmt.where(ImdertyBarrio.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/imderty/barrios",
    response_model=BarrioRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_barrio(
    body: BarrioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
) -> ImdertyBarrio:
    barrio = ImdertyBarrio(
        name=body.name,
        zone=body.zone,
        is_active=body.is_active,
    )
    db.add(barrio)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un barrio con ese nombre",
        )

    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.imderty_barrio,
        entity_id=barrio.id,
        actor=current_user,
        club_id=None,
        changed_fields=["name", "zone", "is_active"],
    )

    return barrio


@router.patch("/imderty/barrios/{barrio_id}", response_model=BarrioRead)
async def update_barrio(
    barrio_id: int,
    body: BarrioUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
) -> ImdertyBarrio:
    result = await db.execute(
        select(ImdertyBarrio).where(ImdertyBarrio.id == barrio_id)
    )
    barrio = result.scalar_one_or_none()
    if barrio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Barrio no encontrado",
        )

    changed_fields: list[str] = []
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if getattr(barrio, field) != value:
            setattr(barrio, field, value)
            changed_fields.append(field)

    if changed_fields:
        try:
            await db.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un barrio con ese nombre",
            )

        await record_audit(
            db,
            action=AuditAction.update,
            entity_type=AuditEntityType.imderty_barrio,
            entity_id=barrio.id,
            actor=current_user,
            club_id=None,
            changed_fields=changed_fields,
        )

    return barrio
