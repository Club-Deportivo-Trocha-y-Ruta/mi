"""Roster de la jornada de medición (feature 048, US3, research R9).

``GET /api/anthropometry/roster?date=YYYY-MM-DD`` — coach/admin. Devuelve los
deportistas NO archivados a los que el llamador tiene acceso, con lo que el
selector de la jornada necesita sin N+1:

- ``last_evaluation_date`` y ``has_record_on_date`` (una consulta agrupada),
- ``skinfolds_eligible``: edad ≥ ``BODY_COMP_MIN_AGE_YEARS`` a la fecha y
  intervalo de ``BODY_COMP_MIN_INTERVAL_DAYS`` abierto respecto al último set
  de pliegues que cuenta (misma regla que ``check_min_age`` /
  ``check_interval`` de ``services/body_composition.py``).

Presupuesto: ≤ 3 consultas en el handler (atletas, agregados de mediciones,
sets de pliegues), por debajo del ≤ 4 del contrato. Solo lectura, sin
auditoría (FR-005: las lecturas no se registran) y sin logging: la respuesta
lleva nombres y fechas de nacimiento de menores.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_role
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.models.user import User, UserRole
from app.schemas.anthropometry import RosterRowOut
from app.services.body_composition import SITES
from app.services.category import compute_age_decimal, get_category
from app.services.permissions import coach_club_ids

router = APIRouter()

#: Código estable del 422 por fecha futura.
ROSTER_DATE_IN_FUTURE = "roster_date_in_future"


@router.get("/roster", response_model=list[RosterRowOut])
async def get_anthropometry_roster(
    on_date: date | None = Query(default=None, alias="date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> list[RosterRowOut]:
    today = date.today()
    target = on_date or today
    if target > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ROSTER_DATE_IN_FUTURE,
        )

    # 1) Atletas en alcance — misma regla que `verify_athlete_access`:
    #    admin todos; coach solo los de clubes donde es `ClubRole.coach`.
    athletes_stmt = select(Athlete).where(Athlete.deleted_at.is_(None))
    if current_user.role != UserRole.admin:
        club_ids = coach_club_ids(current_user)
        if not club_ids:
            return []
        athletes_stmt = athletes_stmt.where(Athlete.club_id.in_(club_ids))
    athletes_stmt = athletes_stmt.order_by(
        Athlete.last_name, Athlete.first_name, Athlete.id
    )
    athletes = list((await db.execute(athletes_stmt)).scalars().all())
    if not athletes:
        return []
    athlete_ids = [a.id for a in athletes]

    # 2) Última evaluación + ¿ya tiene medición en la fecha? (una agrupada).
    agg_stmt = (
        select(
            AnthropometricRecord.athlete_id,
            func.max(AnthropometricRecord.evaluation_date),
            func.max(
                case((AnthropometricRecord.evaluation_date == target, 1), else_=0)
            ),
        )
        .where(AnthropometricRecord.athlete_id.in_(athlete_ids))
        .group_by(AnthropometricRecord.athlete_id)
    )
    last_by_id: dict[int, date] = {}
    on_date_ids: set[int] = set()
    for athlete_id, last_date, has_on_date in (await db.execute(agg_stmt)).all():
        last_by_id[athlete_id] = last_date
        if has_on_date:
            on_date_ids.add(athlete_id)

    # 3) Último set de pliegues que CUENTA (algún sitio con valor) en o antes
    #    de la fecha, por atleta. Solo las columnas `<site>_mm`: nunca se
    #    cargan lecturas ni estimaciones.
    site_columns = [getattr(SkinfoldMeasurement, f"{site}_mm") for site in SITES]
    sets_stmt = (
        select(
            AnthropometricRecord.athlete_id,
            AnthropometricRecord.evaluation_date,
            *site_columns,
        )
        .join(
            SkinfoldMeasurement,
            SkinfoldMeasurement.anthropometric_record_id == AnthropometricRecord.id,
        )
        .where(
            AnthropometricRecord.athlete_id.in_(athlete_ids),
            AnthropometricRecord.evaluation_date <= target,
        )
        .order_by(
            AnthropometricRecord.athlete_id,
            AnthropometricRecord.evaluation_date.desc(),
        )
    )
    last_set_by_id: dict[int, date] = {}
    for row in (await db.execute(sets_stmt)).all():
        athlete_id, set_date, *site_values = row
        if athlete_id in last_set_by_id:
            continue
        if any(value is not None for value in site_values):
            last_set_by_id[athlete_id] = set_date

    min_age = settings.body_comp_min_age_years
    min_interval = timedelta(days=settings.body_comp_min_interval_days)

    rows: list[RosterRowOut] = []
    for athlete in athletes:
        sex = athlete.sex.value if hasattr(athlete.sex, "value") else str(athlete.sex)
        old_enough = compute_age_decimal(athlete.birth_date, target) >= min_age
        last_set = last_set_by_id.get(athlete.id)
        interval_open = last_set is None or (target - last_set) >= min_interval
        rows.append(
            RosterRowOut(
                athlete_id=athlete.id,
                full_name=f"{athlete.first_name} {athlete.last_name}",
                category=get_category(athlete.birth_date.year, sex),
                sex=sex,
                birth_date=athlete.birth_date,
                last_evaluation_date=last_by_id.get(athlete.id),
                has_record_on_date=athlete.id in on_date_ids,
                skinfolds_eligible=old_enough and interval_open,
            )
        )
    return rows
