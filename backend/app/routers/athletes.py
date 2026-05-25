from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
    verify_athlete_access,
)
from app.models.athlete import Athlete
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.club import Club, ClubMember, ClubRole
from app.models.parent_invite import ParentInvite
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole
from app.models.athlete import ParentAthlete
from app.schemas.athlete import (
    AthleteCreate,
    AthleteDetailOut,
    AthleteListOut,
    AthleteOut,
    AthleteUpdate,
    AthleteParentView,
    AnthropometryParentView,
)
from app.schemas.anthropometry import AnthropometryOut
from app.schemas.notification import NotificationRecipient, NotificationRequest, NotificationTemplate
from app.schemas.training_session import AttendanceRead
from app.services import training as training_svc
from app.services.category import compute_age_decimal, compute_years_in_club, get_category
from app.services.notification.service import NotificationService
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.permissions import can_view_athlete_feedback, parent_athlete_ids

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coach_club_ids(user: User) -> set[int]:
    return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}


def _enrich_athlete(athlete: Athlete) -> AthleteOut:
    """Agrega campos calculados (age_decimal, category, years_in_club) al response."""
    out = AthleteOut.model_validate(athlete)
    out.age_decimal = compute_age_decimal(athlete.birth_date)
    out.category = get_category(athlete.birth_date.year, athlete.sex.value)
    if athlete.club_join_date is not None:
        out.years_in_club = compute_years_in_club(athlete.club_join_date)
    return out


# ---------------------------------------------------------------------------
# POST /api/athletes
# ---------------------------------------------------------------------------
@router.post("", response_model=AthleteOut, status_code=status.HTTP_201_CREATED)
async def create_athlete(
    body: AthleteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service: NotificationService = Depends(get_notification_service),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> AthleteOut:
    # Coach solo puede crear en sus clubes
    if current_user.role == UserRole.coach:
        if body.club_id not in _coach_club_ids(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club indicado como coach",
            )

    # Crear user stub (role=athlete, can_login=false, sin email/password)
    user = User(
        first_name=body.first_name,
        last_name=body.last_name,
        role=UserRole.athlete,
        can_login=False,
        created_by=current_user.id,
    )
    db.add(user)
    await db.flush()

    # Crear perfil de atleta
    athlete = Athlete(
        user_id=user.id,
        first_name=body.first_name,
        last_name=body.last_name,
        birth_date=body.birth_date,
        sex=body.sex,
        club_join_date=body.club_join_date,
        club_id=body.club_id,
        created_by=current_user.id,
    )
    db.add(athlete)
    await db.flush()

    # Crear membresía al club
    member = ClubMember(
        club_id=body.club_id,
        user_id=user.id,
        role_in_club=ClubRole.athlete,
    )
    db.add(member)
    await db.flush()

    # -----------------------------------------------------------------------
    # Email de bienvenida (Paso 11)
    # Busca si hay un padre vinculado (ej: si se crearon a la vez o se hizo attach auto)
    # -----------------------------------------------------------------------
    p_result = await db.execute(
        select(ParentAthlete).where(ParentAthlete.athlete_id == athlete.id)
    )
    parents = p_result.scalars().all()
    
    parent_user = None
    for link in parents:
        u_res = await db.execute(select(User).where(User.id == link.parent_id))
        u = u_res.scalar_one_or_none()
        if u and u.email:
            parent_user = u
            break
            
    if parent_user:
        club_res = await db.execute(select(Club).where(Club.id == body.club_id))
        club = club_res.scalar_one()
        from datetime import date
        
        notification_req = NotificationRequest(
            recipient=NotificationRecipient(
                email=parent_user.email,
                name=f"{parent_user.first_name} {parent_user.last_name}",
            ),
            template=NotificationTemplate.WELCOME_ATHLETE,
            send_async=True,
            context={
                "athlete_first_name": body.first_name,
                "club_name": club.name,
                "parent_name": f"{parent_user.first_name} {parent_user.last_name}",
                "season_year": date.today().year,
            },
        )
        await notification_service.send(notification_req, dispatcher=dispatcher)

    return _enrich_athlete(athlete)


# ---------------------------------------------------------------------------
# GET /api/athletes
# ---------------------------------------------------------------------------
@router.get("", response_model=AthleteListOut)
async def list_athletes(
    club_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AthleteListOut:
    if current_user.role == UserRole.admin:
        scope_clubs = {club_id} if club_id else None
    else:
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            return AthleteListOut(items=[], total=0)
        if club_id is not None:
            if club_id not in coach_clubs:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No perteneces al club indicado como coach",
                )
            scope_clubs = {club_id}
        else:
            scope_clubs = coach_clubs

    # Excluir soft-deleted: filtra atletas con deleted_at NULL.
    filters = [Athlete.deleted_at.is_(None)]
    if scope_clubs is not None:
        filters.append(Athlete.club_id.in_(scope_clubs))

    query = select(Athlete).where(*filters).order_by(Athlete.last_name, Athlete.first_name)
    count_query = select(func.count()).select_from(Athlete).where(*filters)

    result = await db.execute(query)
    athletes = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return AthleteListOut(
        items=[_enrich_athlete(a) for a in athletes],
        total=total,
    )


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}
# ---------------------------------------------------------------------------
@router.get("/{athlete_id}", response_model=None)
async def get_athlete(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> AthleteDetailOut | AthleteParentView:
    # Parent: vista reducida sin campos internos del coach
    if current_user.role == UserRole.parent:
        # Cargar registros para obtener el más reciente
        result = await db.execute(
            select(AnthropometricRecord)
            .where(AnthropometricRecord.athlete_id == athlete.id)
            .order_by(AnthropometricRecord.evaluation_date.desc())
        )
        records = result.scalars().all()

        latest_record: AnthropometryParentView | None = None
        if records:
            latest_record = AnthropometryParentView.model_validate(records[0])

        out_parent = AthleteParentView.model_validate(athlete)
        out_parent.age_decimal = compute_age_decimal(athlete.birth_date)
        out_parent.category = get_category(athlete.birth_date.year, athlete.sex.value)
        out_parent.latest_anthropometry = latest_record
        return out_parent

    # Coach / Admin: vista completa con selectinload para eager loading
    result = await db.execute(
        select(Athlete)
        .options(selectinload(Athlete.anthropometric_records))
        .where(Athlete.id == athlete.id)
    )
    athlete_full = result.scalar_one()

    latest: AnthropometryOut | None = None
    if athlete_full.anthropometric_records:
        latest_orm = max(
            athlete_full.anthropometric_records, key=lambda r: r.evaluation_date
        )
        latest = AnthropometryOut.model_validate(latest_orm)

    out = AthleteDetailOut.model_validate(athlete_full)
    out.age_decimal = compute_age_decimal(athlete_full.birth_date)
    out.category = get_category(athlete_full.birth_date.year, athlete_full.sex.value)
    if athlete_full.club_join_date is not None:
        out.years_in_club = compute_years_in_club(athlete_full.club_join_date)
    out.latest_anthropometry = latest
    return out


# ---------------------------------------------------------------------------
# PATCH /api/athletes/{athlete_id}
# ---------------------------------------------------------------------------
@router.patch("/{athlete_id}", response_model=AthleteOut)
async def update_athlete(
    athlete_id: int,
    body: AthleteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AthleteOut:
    result = await db.execute(
        select(Athlete).where(
            Athlete.id == athlete_id, Athlete.deleted_at.is_(None)
        )
    )
    athlete = result.scalar_one_or_none()

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    if current_user.role == UserRole.coach:
        if athlete.club_id not in _coach_club_ids(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(athlete, field, value)

    # Sincronizar nombres con el user vinculado si cambiaron
    if "first_name" in update_data or "last_name" in update_data:
        user_result = await db.execute(select(User).where(User.id == athlete.user_id))
        user = user_result.scalar_one()
        if "first_name" in update_data:
            user.first_name = update_data["first_name"]
        if "last_name" in update_data:
            user.last_name = update_data["last_name"]

    await db.flush()

    return _enrich_athlete(athlete)


# ---------------------------------------------------------------------------
# DELETE /api/athletes/{athlete_id}
# ---------------------------------------------------------------------------
@router.delete("/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_athlete(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> None:
    """Marca un atleta como eliminado (soft-delete).

    El atleta queda con `deleted_at != NULL`; los lectores deben filtrar
    `WHERE deleted_at IS NULL`. El user stub asociado (role=athlete) también
    se marca soft-deleted y se desactiva (is_active=False).

    Las filas relacionadas (consents, parent_athlete, anthropometry, etc.)
    se conservan: la integridad referencial está garantizada por las FKs
    con ondelete=RESTRICT.
    """
    result = await db.execute(
        select(Athlete).where(
            Athlete.id == athlete_id, Athlete.deleted_at.is_(None)
        )
    )
    athlete = result.scalar_one_or_none()

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    if current_user.role == UserRole.coach:
        if athlete.club_id not in _coach_club_ids(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )

    now = datetime.now(timezone.utc)
    athlete.deleted_at = now

    # Soft-delete del user stub vinculado (role=athlete) si existe.
    if athlete.user_id:
        user_res = await db.execute(
            select(User).where(
                User.id == athlete.user_id,
                User.role == UserRole.athlete,
                User.deleted_at.is_(None),
            )
        )
        user_stub = user_res.scalar_one_or_none()
        if user_stub is not None:
            user_stub.deleted_at = now
            user_stub.is_active = False

    await db.flush()


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/attendance — Historial de asistencia
# ---------------------------------------------------------------------------


@router.get("/{athlete_id}/attendance", response_model=list[AttendanceRead])
async def get_athlete_attendance(
    athlete_id: int,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AttendanceRead]:
    """
    Historial de asistencia de un atleta.

    - Admin/coach: cualquier atleta de su club.
    - Padre: solo sus propios atletas.
    """
    # Verificar permiso de feedback sobre el atleta (usa misma lógica RBAC)
    allowed = await can_view_athlete_feedback(db, current_user, athlete_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver la asistencia de este atleta",
        )

    # Coach: verificar que el atleta pertenece a su club (excluye soft-deleted)
    if current_user.role == UserRole.coach:
        result = await db.execute(
            select(Athlete).where(
                Athlete.id == athlete_id, Athlete.deleted_at.is_(None)
            )
        )
        athlete = result.scalar_one_or_none()
        if athlete is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Atleta no encontrado",
            )
        coach_clubs = {m.club_id for m in current_user.club_memberships}
        if athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este atleta no pertenece a ninguno de tus clubes",
            )

    records = await training_svc.attendance.athlete_attendance_history(
        db=db,
        athlete_id=athlete_id,
        date_from=from_date,
        date_to=to_date,
    )

    # Aplicar limit/offset manualmente (el service no lo recibe aún)
    records = records[offset : offset + limit]

    return [AttendanceRead.model_validate(r) for r in records]
