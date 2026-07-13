from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, require_role
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.alerts import (
    AlertsSummary,
    AthleteAlert,
    GrowthAlert,
    MeasurementStatus,
)
from app.services.category import compute_age_decimal, get_category
from app.services.measurement_alerts import (
    DEFAULT_INTERVAL,
    GROWTH_VELOCITY_THRESHOLD,
    WARNING_DAYS,
    calculate_growth_velocity,
    calculate_next_due,
    detect_approaching_circa,
    get_measurement_interval,
)
from app.services.permissions import coach_club_ids as _coach_club_ids

router = APIRouter()


@router.get("/alerts", response_model=AlertsSummary)
async def get_measurement_alerts(
    club_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AlertsSummary:
    """Retorna alertas de medición antropométrica para los atletas del coach/admin."""

    # 1. Filtro de acceso
    filters = []
    if current_user.role == UserRole.admin:
        if club_id is not None:
            filters.append(Athlete.club_id == club_id)
    else:
        coach_clubs = _coach_club_ids(current_user)
        if not coach_clubs:
            return AlertsSummary(
                overdue=0, due_soon=0, ok=0, never_measured=0,
                rapid_growth_count=0, athletes=[],
            )
        if club_id is not None:
            if club_id not in coach_clubs:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No perteneces al club indicado como coach",
                )
            filters.append(Athlete.club_id == club_id)
        else:
            filters.append(Athlete.club_id.in_(coach_clubs))

    # 2. Query: atletas con sus mediciones precargadas
    query = (
        select(Athlete)
        .options(selectinload(Athlete.anthropometric_records))
        .where(*filters)
        .order_by(Athlete.last_name, Athlete.first_name)
    )
    result = await db.execute(query)
    athletes = result.scalars().all()

    # 3. Construir alertas
    today = date.today()
    alerts: list[AthleteAlert] = []
    counters = {"overdue": 0, "due_soon": 0, "ok": 0, "never": 0, "rapid_growth": 0}

    for athlete in athletes:
        # Ordenar registros por fecha DESC, tomar los 2 más recientes
        records = sorted(
            athlete.anthropometric_records,
            key=lambda r: r.evaluation_date,
            reverse=True,
        )
        latest = records[0] if records else None
        previous = records[1] if len(records) > 1 else None

        age = compute_age_decimal(athlete.birth_date)
        category = get_category(athlete.birth_date.year, athlete.sex.value)
        name = f"{athlete.first_name} {athlete.last_name}"

        if latest is None:
            # Nunca medido
            alert = AthleteAlert(
                athlete_id=athlete.id,
                athlete_name=name,
                sex=athlete.sex.value,
                age_decimal=age,
                category=category,
                measurement_status=MeasurementStatus.never,
                measurement_interval_days=DEFAULT_INTERVAL,
                growth_alerts=[],
            )
            counters["never"] += 1
        else:
            phv_status = latest.maturation_status.value
            interval = get_measurement_interval(phv_status)
            next_due = calculate_next_due(latest.evaluation_date, phv_status)
            days_diff = (today - next_due).days  # positivo = atrasado

            if days_diff > 0:
                m_status = MeasurementStatus.overdue
                counters["overdue"] += 1
            elif days_diff >= -WARNING_DAYS:
                m_status = MeasurementStatus.due_soon
                counters["due_soon"] += 1
            else:
                m_status = MeasurementStatus.ok
                counters["ok"] += 1

            # Alertas de crecimiento
            growth_alerts: list[GrowthAlert] = []
            velocity = calculate_growth_velocity(latest, previous)

            if velocity is not None and velocity >= GROWTH_VELOCITY_THRESHOLD:
                growth_alerts.append(GrowthAlert.rapid_growth)
                counters["rapid_growth"] += 1

            if detect_approaching_circa(float(latest.maturity_offset)):
                growth_alerts.append(GrowthAlert.approaching_circa)

            if previous is not None and latest.maturation_status != previous.maturation_status:
                growth_alerts.append(GrowthAlert.phase_changed)

            alert = AthleteAlert(
                athlete_id=athlete.id,
                athlete_name=name,
                sex=athlete.sex.value,
                age_decimal=age,
                category=category,
                measurement_status=m_status,
                last_measurement_date=latest.evaluation_date,
                next_due_date=next_due,
                days_overdue=days_diff,
                current_phv_status=phv_status,
                measurement_interval_days=interval,
                growth_velocity_cm_month=velocity,
                growth_alerts=growth_alerts,
                training_implications=latest.training_implications,
            )

        alerts.append(alert)

    # 4. Ordenar por prioridad: overdue > never > due_soon > ok
    priority = {
        MeasurementStatus.overdue: 0,
        MeasurementStatus.never: 1,
        MeasurementStatus.due_soon: 2,
        MeasurementStatus.ok: 3,
    }
    alerts.sort(key=lambda a: (priority[a.measurement_status], -(a.days_overdue or 0)))

    return AlertsSummary(
        overdue=counters["overdue"],
        due_soon=counters["due_soon"],
        ok=counters["ok"],
        never_measured=counters["never"],
        rapid_growth_count=counters["rapid_growth"],
        athletes=alerts,
    )
