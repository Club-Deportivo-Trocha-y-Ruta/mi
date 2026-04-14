from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.anthropometry import AnthropometricRecord
from app.models.club import ClubMember, ClubRole
from app.models.user import User, UserRole
from app.schemas.athlete import (
    AthleteCreate,
    AthleteDetailOut,
    AthleteListOut,
    AthleteOut,
    AthleteUpdate,
)
from app.schemas.anthropometry import AnthropometryOut
from app.services.category import compute_age_decimal, compute_years_in_club, get_category

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

    filters = []
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
@router.get("/{athlete_id}", response_model=AthleteDetailOut)
async def get_athlete(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AthleteDetailOut:
    result = await db.execute(
        select(Athlete)
        .options(selectinload(Athlete.anthropometric_records))
        .where(Athlete.id == athlete_id)
    )
    athlete = result.scalar_one_or_none()

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    # Coach solo ve atletas de sus clubes
    if current_user.role == UserRole.coach:
        if athlete.club_id not in _coach_club_ids(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )

    # Último registro antropométrico (más reciente por fecha)
    latest = None
    if athlete.anthropometric_records:
        latest_record = max(
            athlete.anthropometric_records, key=lambda r: r.evaluation_date
        )
        latest = AnthropometryOut.model_validate(latest_record)

    out = AthleteDetailOut.model_validate(athlete)
    out.age_decimal = compute_age_decimal(athlete.birth_date)
    out.category = get_category(athlete.birth_date.year, athlete.sex.value)
    if athlete.club_join_date is not None:
        out.years_in_club = compute_years_in_club(athlete.club_join_date)
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
    result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
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
