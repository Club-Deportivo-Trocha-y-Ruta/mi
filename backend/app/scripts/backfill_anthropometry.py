"""
Backfill idempotente de valores derivados en anthropometric_records.

Uso:
    cd backend
    python -m app.scripts.backfill_anthropometry

Para cada registro con BMI y/o percentiles en NULL pero con medidas crudas
presentes (peso + talla), recalcula y persiste los valores derivados usando la
misma matemática de ``app/services/growth.py`` y la fórmula de BMI. NUNCA toca
las columnas de medidas crudas. Reejecutar es un no-op: si los valores ya están
calculados (o no cambian) no se emite UPDATE.

Privacidad: solo se registran conteos agregados. Nunca se emite nombre, fecha
de nacimiento ni ningún identificador de menor en los logs.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.growth import GrowthSource
from app.services.category import compute_age_decimal
from app.services.growth import calculate_growth_percentiles


@dataclass
class BackfillSummary:
    scanned: int = 0
    updated: int = 0
    skipped: int = 0


def _needs_backfill(record: AnthropometricRecord) -> bool:
    """Un registro es candidato si tiene medidas crudas y algún derivado en NULL."""
    if record.weight_kg is None or record.standing_height_cm is None:
        return False
    return (
        record.bmi is None
        or record.bmi_percentile is None
        or record.height_percentile is None
        or record.weight_percentile is None
    )


async def backfill_anthropometry(session: AsyncSession) -> BackfillSummary:
    """Recalcula derivados faltantes. Idempotente; no toca medidas crudas."""
    summary = BackfillSummary()

    result = await session.execute(
        select(AnthropometricRecord).where(
            AnthropometricRecord.weight_kg.is_not(None),
            AnthropometricRecord.standing_height_cm.is_not(None),
            or_(
                AnthropometricRecord.bmi.is_(None),
                AnthropometricRecord.bmi_percentile.is_(None),
                AnthropometricRecord.height_percentile.is_(None),
                AnthropometricRecord.weight_percentile.is_(None),
            ),
        )
    )
    records = result.scalars().all()

    # Cache de (birth_date, sex) por atleta para evitar N consultas repetidas
    athlete_cache: dict[int, Athlete] = {}

    for record in records:
        summary.scanned += 1

        if not _needs_backfill(record):
            summary.skipped += 1
            continue

        athlete = athlete_cache.get(record.athlete_id)
        if athlete is None:
            athlete = await session.get(Athlete, record.athlete_id)
            if athlete is None:
                summary.skipped += 1
                continue
            athlete_cache[record.athlete_id] = athlete

        age = compute_age_decimal(athlete.birth_date, record.evaluation_date)
        age_months = age * 12

        # BMI desacoplado: siempre que haya peso + talla (FR-001a)
        weight = float(record.weight_kg)
        height_cm = float(record.standing_height_cm)
        bmi_value = weight / (height_cm / 100) ** 2
        new_bmi = Decimal(str(round(bmi_value, 2)))

        try:
            growth = await calculate_growth_percentiles(
                db=session,
                weight_kg=weight,
                standing_height_cm=height_cm,
                sex=athlete.sex.value,
                age_months=age_months,
                source=GrowthSource.CDC,
            )
        except Exception:
            growth = None

        changed = False

        if record.bmi != new_bmi:
            record.bmi = new_bmi
            changed = True

        if growth is not None:
            for attr, value in (
                ("height_z_score", growth.height_z_score),
                ("height_percentile", growth.height_percentile),
                ("bmi_z_score", growth.bmi_z_score),
                ("bmi_percentile", growth.bmi_percentile),
                ("weight_z_score", growth.weight_z_score),
                ("weight_percentile", growth.weight_percentile),
            ):
                if value is not None and getattr(record, attr) != value:
                    setattr(record, attr, value)
                    changed = True
            if (
                growth.nutritional_status_bmi is not None
                and record.nutritional_status != growth.nutritional_status_bmi
            ):
                record.nutritional_status = growth.nutritional_status_bmi
                changed = True

        if changed:
            summary.updated += 1
        else:
            summary.skipped += 1

    await session.commit()
    return summary


async def run() -> BackfillSummary:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session() as session:
            summary = await backfill_anthropometry(session)
            # Solo conteos agregados — sin identificadores de menores.
            print(
                f"Backfill antropometría: {summary.scanned} escaneados, "
                f"{summary.updated} actualizados, {summary.skipped} sin cambios."
            )
            return summary
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
