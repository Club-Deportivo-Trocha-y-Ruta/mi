"""Router de parent-athletes: vinculación padre/acudiente ↔ atleta e invitaciones."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
)
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import ClubMember, ClubRole
from app.models.parent_invite import ParentInvite
from app.models.user import User, UserRole
from app.config import settings
from app.schemas.notification import (
    NotificationRecipient,
    NotificationRequest,
    NotificationTemplate,
)
from app.schemas.parent_athlete import (
    MyAthleteOut,
    ParentAthleteCreate,
    ParentAthleteListOut,
    ParentAthleteOut,
)
from app.schemas.parent_invite import ParentInviteCreate, ParentInviteCreatedOut, ParentInviteOut
from app.services.category import compute_age_decimal, get_category
from app.services.invitations import create_invite

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coach_club_ids(user: User) -> set[int]:
    """IDs de clubes donde el usuario tiene rol de coach."""
    return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}


def _measurement_status(latest_date: date | None) -> str:
    """Clasifica el estado de la última medición antropométrica.

    never     — nunca ha tenido medición
    overdue   — último registro > 90 días
    due_soon  — último registro entre 61 y 90 días
    ok        — último registro ≤ 60 días
    """
    if latest_date is None:
        return "never"
    days_ago = (date.today() - latest_date).days
    if days_ago > 90:
        return "overdue"
    if days_ago > 60:
        return "due_soon"
    return "ok"


# ---------------------------------------------------------------------------
# POST /api/parent-athletes — vincular padre con atleta
# ---------------------------------------------------------------------------
@router.post("", response_model=ParentAthleteOut, status_code=status.HTTP_201_CREATED)
async def link_parent_athlete(
    body: ParentAthleteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ParentAthleteOut:
    # 1. Verificar que parent_id sea un usuario con rol parent
    parent_result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.id == body.parent_id)
    )
    parent = parent_result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario padre no encontrado",
        )
    if parent.role != UserRole.parent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El usuario indicado no tiene rol de padre/acudiente",
        )

    # 2. Verificar que athlete_id existe
    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == body.athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    # 3. Coach: padre y atleta deben pertenecer a sus clubes
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No eres coach de ningún club",
            )
        # Atleta en el club del coach
        if athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El atleta no pertenece a ninguno de tus clubes",
            )
        # Padre también debe pertenecer al mismo club
        parent_club_ids = {m.club_id for m in parent.club_memberships}
        if not coach_clubs.intersection(parent_club_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El padre/acudiente no pertenece a ninguno de tus clubes",
            )

    # 4. Máx 3 padres por atleta
    count_result = await db.execute(
        select(ParentAthlete).where(ParentAthlete.athlete_id == body.athlete_id)
    )
    existing_parents = count_result.scalars().all()
    if len(existing_parents) >= 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El atleta ya tiene el máximo de 3 padres/acudientes vinculados",
        )

    # 5. Crear la relación
    relation = ParentAthlete(
        parent_id=body.parent_id,
        athlete_id=body.athlete_id,
        relationship_type=body.relationship,
    )
    db.add(relation)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe esta vinculación",
        )

    # 6. Recargar con relaciones para serializar
    result = await db.execute(
        select(ParentAthlete)
        .options(selectinload(ParentAthlete.parent), selectinload(ParentAthlete.athlete))
        .where(ParentAthlete.id == relation.id)
    )
    loaded = result.scalar_one()
    return ParentAthleteOut.model_validate(loaded)


# ---------------------------------------------------------------------------
# GET /api/parent-athletes/my-athletes — portal del padre (debe ir antes de /{id})
# ---------------------------------------------------------------------------
@router.get("/my-athletes", response_model=list[MyAthleteOut])
async def my_athletes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.parent])),
) -> list[MyAthleteOut]:
    # Cargar todas las relaciones del padre con sus atletas
    stmt = (
        select(ParentAthlete)
        .options(selectinload(ParentAthlete.athlete))
        .where(ParentAthlete.parent_id == current_user.id)
    )
    relations_result = await db.execute(stmt)
    relations = relations_result.scalars().all()

    output: list[MyAthleteOut] = []

    for rel in relations:
        ath = rel.athlete

        # Último registro antropométrico (más reciente por fecha de evaluación)
        antro_stmt = (
            select(AnthropometricRecord)
            .where(AnthropometricRecord.athlete_id == ath.id)
            .order_by(AnthropometricRecord.evaluation_date.desc())
            .limit(1)
        )
        antro_result = await db.execute(antro_stmt)
        latest = antro_result.scalar_one_or_none()

        age_dec = compute_age_decimal(ath.birth_date)
        category = get_category(ath.birth_date.year, ath.sex.value)

        output.append(
            MyAthleteOut(
                athlete_id=ath.id,
                athlete_first_name=ath.first_name,
                athlete_last_name=ath.last_name,
                birth_date=ath.birth_date,
                sex=ath.sex,
                age_decimal=age_dec,
                category=category,
                relationship=rel.relationship_type,
                latest_anthropometry_date=latest.evaluation_date if latest else None,
                maturation_status=latest.maturation_status if latest else None,
                standing_height_cm=latest.standing_height_cm if latest else None,
                weight_kg=latest.weight_kg if latest else None,
                measurement_status=_measurement_status(
                    latest.evaluation_date if latest else None
                ),
            )
        )

    return output


# ---------------------------------------------------------------------------
# POST /api/parent-athletes/invite — generar invitación (antes de /{id})
# ---------------------------------------------------------------------------
@router.post("/invite", response_model=ParentInviteCreatedOut, status_code=status.HTTP_201_CREATED)
async def generate_invite(
    body: ParentInviteCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> ParentInviteCreatedOut:
    # Verificar que el atleta existe
    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == body.athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    # Coach: el atleta debe pertenecer a su club
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        if athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El atleta no pertenece a ninguno de tus clubes",
            )

    invite = await create_invite(
        athlete_id=body.athlete_id,
        email=body.email,
        created_by_user_id=current_user.id,
        db=db,
    )

    # Enviar email de invitación en background
    invite_url = f"{settings.frontend_base_url}/onboarding?token={invite.token}"
    dispatcher = get_task_dispatcher(background_tasks)
    await notification_service.send(
        NotificationRequest(
            recipient=NotificationRecipient(email=body.email, name="Padre/Acudiente"),
            template=NotificationTemplate.PARENT_INVITE,
            context={
                "athlete_first_name": athlete.first_name,
                "club_name": settings.club_name,
                "invite_url": invite_url,
            },
            send_async=True,
        ),
        dispatcher=dispatcher,
    )

    return ParentInviteCreatedOut.model_validate(invite)


# ---------------------------------------------------------------------------
# GET /api/parent-athletes/invites — listar invitaciones de un atleta (antes de /{id})
# ---------------------------------------------------------------------------
@router.get("/invites", response_model=list[ParentInviteOut])
async def list_invites(
    athlete_id: int = Query(..., description="ID del atleta"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> list[ParentInviteOut]:
    # Verificar que el atleta existe
    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    # Coach: el atleta debe pertenecer a su club
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        if athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El atleta no pertenece a ninguno de tus clubes",
            )

    stmt = (
        select(ParentInvite)
        .where(ParentInvite.athlete_id == athlete_id)
        .order_by(ParentInvite.created_at.desc())
    )
    result = await db.execute(stmt)
    invites = result.scalars().all()
    return [ParentInviteOut.model_validate(i) for i in invites]


# ---------------------------------------------------------------------------
# GET /api/parent-athletes — listar relaciones
# ---------------------------------------------------------------------------
@router.get("", response_model=ParentAthleteListOut)
async def list_parent_athletes(
    athlete_id: int | None = Query(default=None),
    parent_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ParentAthleteListOut:
    stmt = (
        select(ParentAthlete)
        .options(selectinload(ParentAthlete.parent), selectinload(ParentAthlete.athlete))
    )

    if athlete_id is not None:
        stmt = stmt.where(ParentAthlete.athlete_id == athlete_id)
    if parent_id is not None:
        stmt = stmt.where(ParentAthlete.parent_id == parent_id)

    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            return ParentAthleteListOut(items=[], total=0)
        # Solo relaciones donde el atleta pertenece a un club del coach
        stmt = stmt.join(Athlete, Athlete.id == ParentAthlete.athlete_id).where(
            Athlete.club_id.in_(coach_clubs)
        )

    result = await db.execute(stmt)
    relations = result.scalars().all()

    items = [ParentAthleteOut.model_validate(r) for r in relations]
    return ParentAthleteListOut(items=items, total=len(items))


# ---------------------------------------------------------------------------
# DELETE /api/parent-athletes/{relation_id} — desvincular
# ---------------------------------------------------------------------------
@router.delete("/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_parent_athlete(
    relation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> None:
    result = await db.execute(
        select(ParentAthlete)
        .options(selectinload(ParentAthlete.athlete))
        .where(ParentAthlete.id == relation_id)
    )
    relation = result.scalar_one_or_none()

    if relation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vinculación no encontrada",
        )

    # Coach: solo puede eliminar relaciones de sus clubes
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        if relation.athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para eliminar esta vinculación",
            )

    await db.delete(relation)
