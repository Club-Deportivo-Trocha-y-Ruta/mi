from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.club import ClubRole
from app.models.user import User, UserRole
from app.schemas.anthropometry import AnthropometryCreate, AnthropometryOut
from app.services.category import compute_age_decimal
from app.services.phv import calculate_mirwald_offset

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coach_club_ids(user: User) -> set[int]:
    return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}


async def _get_athlete_or_403(
    athlete_id: int,
    db: AsyncSession,
    current_user: User,
) -> Athlete:
    """Obtiene el atleta verificando acceso del coach."""
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

    return athlete


# ---------------------------------------------------------------------------
# POST /api/athletes/{athlete_id}/anthropometry
# ---------------------------------------------------------------------------
@router.post(
    "/{athlete_id}/anthropometry",
    response_model=AnthropometryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_anthropometry(
    athlete_id: int,
    body: AnthropometryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AnthropometryOut:
    athlete = await _get_athlete_or_403(athlete_id, db, current_user)

    # Edad decimal a la fecha de evaluación
    age = compute_age_decimal(athlete.birth_date, body.evaluation_date)

    # Cálculos PHV Mirwald
    phv = calculate_mirwald_offset(
        sex=athlete.sex.value,
        age=age,
        weight=float(body.weight_kg),
        standing_height=float(body.standing_height_cm),
        sitting_height=float(body.sitting_height_cm),
    )

    record = AnthropometricRecord(
        athlete_id=athlete.id,
        evaluation_date=body.evaluation_date,
        mesocycle=body.mesocycle,
        weight_kg=body.weight_kg,
        standing_height_cm=body.standing_height_cm,
        arm_span_cm=body.arm_span_cm,
        sitting_height_cm=body.sitting_height_cm,
        leg_length_cm=phv["leg_length_cm"],
        leg_sitting_ratio=phv["leg_sitting_ratio"],
        maturity_offset=phv["maturity_offset"],
        age_at_phv=phv["age_at_phv"],
        maturation_status=phv["maturation_status"],
        training_implications=phv["training_implications"],
        evaluated_by=current_user.id,
        notes=body.notes,
    )
    db.add(record)
    await db.flush()

    return AnthropometryOut.model_validate(record)


# ---------------------------------------------------------------------------
# GET /api/athletes/{athlete_id}/anthropometry
# ---------------------------------------------------------------------------
@router.get("/{athlete_id}/anthropometry", response_model=list[AnthropometryOut])
async def list_anthropometry(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> list[AnthropometryOut]:
    await _get_athlete_or_403(athlete_id, db, current_user)

    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete_id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    records = result.scalars().all()

    return [AnthropometryOut.model_validate(r) for r in records]
