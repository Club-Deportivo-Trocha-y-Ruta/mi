from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.club import ClubRole
from app.models.growth import GrowthSource
from app.models.user import User, UserRole
from app.schemas.anthropometry import AnthropometryOut, AnthropometryCreate, GrowthPercentiles
from app.services.category import compute_age_decimal
from app.services.growth import calculate_growth_percentiles, classify_nutritional_status_height
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


def _build_growth_percentiles(
    record: AnthropometricRecord,
    nutritional_status_height: str | None,
) -> GrowthPercentiles | None:
    """
    Construye el objeto GrowthPercentiles a partir de los campos del ORM.
    Retorna None si no hay datos de percentiles en el registro.
    """
    if record.bmi_z_score is None and record.height_z_score is None:
        return None

    # nutritional_status en el ORM almacena la clasificación IMC/E
    nutritional_status_bmi: str | None = None
    if record.nutritional_status is not None:
        # El ORM retorna el objeto enum; .value da el string
        nutritional_status_bmi = (
            record.nutritional_status.value
            if hasattr(record.nutritional_status, "value")
            else str(record.nutritional_status)
        )

    return GrowthPercentiles(
        bmi=record.bmi,
        height_z_score=record.height_z_score,
        height_percentile=record.height_percentile,
        bmi_z_score=record.bmi_z_score,
        bmi_percentile=record.bmi_percentile,
        weight_z_score=record.weight_z_score,
        weight_percentile=record.weight_percentile,
        nutritional_status_height=nutritional_status_height,
        nutritional_status_bmi=nutritional_status_bmi,
    )


def _infer_nutritional_status_height(record: AnthropometricRecord) -> str | None:
    """
    Infiere el estado nutricional T/E a partir del height_z_score almacenado.
    Usado en el GET para registros que tienen percentiles pero no guardaron ns_height.
    """
    if record.height_z_score is None:
        return None
    return classify_nutritional_status_height(float(record.height_z_score)).value


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

    # Calcular percentiles de crecimiento (graceful fallback si tabla LMS vacía)
    age_months = age * 12
    try:
        growth = await calculate_growth_percentiles(
            db=db,
            weight_kg=float(body.weight_kg),
            standing_height_cm=float(body.standing_height_cm),
            sex=athlete.sex.value,
            age_months=age_months,
            source=GrowthSource.CDC,
        )
    except Exception:
        growth = None

    # Si todos los z-scores son None la tabla LMS está vacía — tratar como sin datos
    if growth is not None and growth.height_z_score is None and growth.bmi_z_score is None:
        growth = None

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
        # Campos de percentiles (None si tabla LMS vacía)
        height_z_score=growth.height_z_score if growth else None,
        height_percentile=growth.height_percentile if growth else None,
        bmi=growth.bmi if growth else None,
        bmi_z_score=growth.bmi_z_score if growth else None,
        bmi_percentile=growth.bmi_percentile if growth else None,
        weight_z_score=growth.weight_z_score if growth else None,
        weight_percentile=growth.weight_percentile if growth else None,
        # nutritional_status almacena la clasificación IMC/E (la más clínica)
        nutritional_status=growth.nutritional_status_bmi if growth else None,
    )
    db.add(record)
    await db.flush()

    out = AnthropometryOut.model_validate(record)
    out.growth_percentiles = _build_growth_percentiles(
        record=record,
        nutritional_status_height=growth.nutritional_status_height if growth else None,
    )
    return out


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

    output: list[AnthropometryOut] = []
    for record in records:
        out = AnthropometryOut.model_validate(record)
        # Para registros existentes, nutritional_status_height se infiere del z-score almacenado
        ns_height = _infer_nutritional_status_height(record)
        out.growth_percentiles = _build_growth_percentiles(
            record=record,
            nutritional_status_height=ns_height,
        )
        output.append(out)

    return output
