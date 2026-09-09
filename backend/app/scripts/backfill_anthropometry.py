"""
Backfill idempotente de valores derivados en anthropometric_records.

Uso:
    cd backend
    python -m app.scripts.backfill_anthropometry

Corre dos pasadas, ambas idempotentes y sin tocar jamás las columnas de
medidas crudas (weight_kg, standing_height_cm, sitting_height_cm,
arm_span_cm, evaluation_date, notes, maturity_offset, age_at_phv,
maturation_status, training_implications):

1. ``backfill_anthropometry`` (feature 003): para cada registro con BMI y/o
   percentiles en NULL pero con medidas crudas presentes, recalcula y
   persiste los derivados usando la misma matemática de
   ``app/services/growth.py`` y la fórmula de BMI.
2. ``recompute_to_source`` (feature 040, T023): migra todo registro cuyo
   ``growth_source`` no sea ya la referencia objetivo (OMS 2007 por
   defecto) — incluye filas ya calculadas con CDC — y emite un reporte de
   cambios de banda. Ver
   ``specs/040-growth-module-redesign/contracts/anthropometry-source.md`` §3.

Privacidad: solo se registran conteos agregados y IDs (atleta/registro).
Nunca se emite nombre, fecha de nacimiento ni ningún otro identificador de
menor en los logs ni en el reporte de cambios de banda.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.growth import GrowthSource
from app.services.audit import AuditAction, AuditEntityType, record_audit
from app.services.category import compute_age_decimal
from app.services.growth import calculate_growth_percentiles, classify_nutritional_status_height
from app.services.request_context import system_context

logger = logging.getLogger(__name__)

# La OMS no publica peso-para-la-edad más allá de los 10 años (120.5 meses);
# por encima de este umbral, weight_z_score/weight_percentile quedan en NULL.
WHO_WEIGHT_AGE_CUTOFF_MONTHS: float = 120.5

# Directorio de salida del reporte de cambios de banda — relativo al cwd del
# backend (mismo patrón que el checkpoint sqlite de LangGraph en ./data/),
# ignorado por git (``backend/data/`` en .gitignore).
DEFAULT_REPORT_DIR: Path = Path("data")


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
    ctx = system_context(job="anthropometry_backfill")

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

        changed_fields: list[str] = []

        if record.bmi != new_bmi:
            record.bmi = new_bmi
            changed_fields.append("bmi")

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
                    changed_fields.append(attr)
            if (
                growth.nutritional_status_bmi is not None
                and record.nutritional_status != growth.nutritional_status_bmi
            ):
                record.nutritional_status = growth.nutritional_status_bmi
                changed_fields.append("nutritional_status")

        if changed_fields:
            summary.updated += 1
            await record_audit(
                session,
                action=AuditAction.update,
                entity_type=AuditEntityType.anthropometric_record,
                entity_id=record.id,
                actor=ctx.actor,
                actor_kind=ctx.actor_kind,
                club_id=athlete.club_id,
                athlete_id=record.athlete_id,
                changed_fields=changed_fields,
                meta={"job": "anthropometry_backfill"},
                request_id=ctx.request_id,
            )
        else:
            summary.skipped += 1

    await session.commit()
    return summary


@dataclass
class RecomputeSummary:
    scanned: int = 0
    recomputed: int = 0
    unchanged_status: int = 0
    band_changes: list[dict[str, object]] = field(default_factory=list)


def _needs_recompute(record: AnthropometricRecord, target: GrowthSource) -> bool:
    """Candidato si tiene medidas crudas y su growth_source no es ``target``."""
    if record.weight_kg is None or record.standing_height_cm is None:
        return False
    return record.growth_source is None or record.growth_source != target


def _write_band_change_report(
    band_changes: list[dict[str, object]], report_dir: Path
) -> Path:
    """Escribe el reporte de cambios de banda (solo IDs) como JSON.

    Nombre determinista por fecha de corrida: ``growth_band_changes_<YYYYMMDD>.json``.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = f"growth_band_changes_{date.today().strftime('%Y%m%d')}.json"
    path = report_dir / filename
    path.write_text(json.dumps(band_changes, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def recompute_to_source(
    session: AsyncSession,
    target: GrowthSource = GrowthSource.WHO,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> RecomputeSummary:
    """Migra los derivados antropométricos a la referencia ``target``.

    Selecciona registros con medidas crudas presentes cuyo ``growth_source``
    no sea ya ``target`` (incluye filas nunca calculadas y filas calculadas
    con una referencia distinta, p. ej. CDC). Recalcula BMI (misma fórmula),
    height/BMI Z-score + percentil + ``nutritional_status``, y
    weight_z_score/weight_percentile (NULL por encima de
    ``WHO_WEIGHT_AGE_CUTOFF_MONTHS`` cuando ``target`` es OMS). NUNCA toca
    medidas crudas. Segunda corrida: cero candidatos (no-op).

    Escribe ``report_dir / growth_band_changes_<YYYYMMDD>.json`` con la lista
    de cambios de clasificación (banda) detectados — solo
    ``athlete_id``/``record_id``, sin ningún dato identificable del menor.
    """
    summary = RecomputeSummary()

    result = await session.execute(
        select(AnthropometricRecord).where(
            AnthropometricRecord.weight_kg.is_not(None),
            AnthropometricRecord.standing_height_cm.is_not(None),
            or_(
                AnthropometricRecord.growth_source.is_(None),
                AnthropometricRecord.growth_source != target,
            ),
        )
    )
    records = result.scalars().all()

    athlete_cache: dict[int, Athlete] = {}
    ctx = system_context(job="anthropometry_backfill")

    for record in records:
        if not _needs_recompute(record, target):
            continue
        summary.scanned += 1

        athlete = athlete_cache.get(record.athlete_id)
        if athlete is None:
            athlete = await session.get(Athlete, record.athlete_id)
            if athlete is None:
                continue
            athlete_cache[record.athlete_id] = athlete

        age = compute_age_decimal(athlete.birth_date, record.evaluation_date)
        age_months = age * 12

        # BMI desacoplado: misma fórmula, independiente de la referencia.
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
                source=target,
            )
        except Exception:
            continue

        weight_z = growth.weight_z_score
        weight_pct = growth.weight_percentile
        if age_months > WHO_WEIGHT_AGE_CUTOFF_MONTHS:
            weight_z = None
            weight_pct = None

        # Clasificaciones ANTES de sobrescribir, para detectar cambio de banda.
        previous_height_status = (
            classify_nutritional_status_height(float(record.height_z_score)).value
            if record.height_z_score is not None
            else None
        )
        previous_bmi_status = (
            record.nutritional_status.value
            if record.nutritional_status is not None
            else None
        )

        record.bmi = new_bmi
        record.height_z_score = growth.height_z_score
        record.height_percentile = growth.height_percentile
        record.bmi_z_score = growth.bmi_z_score
        record.bmi_percentile = growth.bmi_percentile
        record.weight_z_score = weight_z
        record.weight_percentile = weight_pct
        if growth.nutritional_status_bmi is not None:
            record.nutritional_status = growth.nutritional_status_bmi
        record.growth_source = target

        summary.recomputed += 1

        await record_audit(
            session,
            action=AuditAction.update,
            entity_type=AuditEntityType.anthropometric_record,
            entity_id=record.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=athlete.club_id,
            athlete_id=record.athlete_id,
            changed_fields=[
                "bmi",
                "height_z_score",
                "height_percentile",
                "bmi_z_score",
                "bmi_percentile",
                "weight_z_score",
                "weight_percentile",
                "nutritional_status",
                "growth_source",
            ],
            meta={"job": "anthropometry_backfill"},
            request_id=ctx.request_id,
        )

        band_changed = False
        if (
            previous_height_status is not None
            and growth.nutritional_status_height is not None
            and previous_height_status != growth.nutritional_status_height
        ):
            summary.band_changes.append(
                {
                    "athlete_id": record.athlete_id,
                    "record_id": record.id,
                    "indicator": "height_for_age",
                    "previous": previous_height_status,
                    "current": growth.nutritional_status_height,
                }
            )
            band_changed = True

        if (
            previous_bmi_status is not None
            and growth.nutritional_status_bmi is not None
            and previous_bmi_status != growth.nutritional_status_bmi
        ):
            summary.band_changes.append(
                {
                    "athlete_id": record.athlete_id,
                    "record_id": record.id,
                    "indicator": "bmi_for_age",
                    "previous": previous_bmi_status,
                    "current": growth.nutritional_status_bmi,
                }
            )
            band_changed = True

        if not band_changed:
            summary.unchanged_status += 1

    await session.commit()

    _write_band_change_report(summary.band_changes, report_dir)

    # Solo conteos agregados e IDs — jamás nombre ni fecha de nacimiento.
    logger.info(
        "growth_recompute_summary scanned=%d recomputed=%d unchanged_status=%d band_changes=%d",
        summary.scanned,
        summary.recomputed,
        summary.unchanged_status,
        len(summary.band_changes),
    )

    return summary


async def run() -> tuple[BackfillSummary, RecomputeSummary]:
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

            recompute_summary = await recompute_to_source(session, target=GrowthSource.WHO)
            print(
                f"Recompute a referencia OMS: {recompute_summary.scanned} escaneados, "
                f"{recompute_summary.recomputed} recalculados, "
                f"{recompute_summary.unchanged_status} sin cambio de banda, "
                f"{len(recompute_summary.band_changes)} cambios de banda "
                "(ver ./data/growth_band_changes_<fecha>.json)."
            )

            return summary, recompute_summary
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
