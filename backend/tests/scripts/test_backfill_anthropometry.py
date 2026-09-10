"""Tests del backfill idempotente de derivados antropométricos.

Cubre ``app.scripts.backfill_anthropometry``:

Feature 003 / T011 — ``backfill_anthropometry`` (rellena NULLs con CDC):
  - Un registro con derivados (bmi/percentiles) en NULL pero medidas crudas
    presentes se rellena para coincidir con ``services/growth.py`` y con
    bmi = peso / talla_m**2. Las medidas crudas NO se tocan.
  - Reejecutar el backfill es un no-op (summary.updated == 0 en la 2ª corrida).
  - Privacidad: el resumen impreso por ``run()`` jamás emite nombre ni fecha de
    nacimiento del menor (solo conteos agregados).

Feature 040 / T017 — ``recompute_to_source`` (migra a la referencia OMS,
contrato ``anthropometry-source.md`` §3):
  - Un registro marcado ``growth_source='CDC'`` se recalcula con OMS y queda
    ``growth_source='WHO'``; las medidas crudas NO se tocan.
  - ``weight_z_score``/``weight_percentile`` quedan en NULL para edad > 120.5
    meses (la OMS no publica peso-para-la-edad después de los 10 años).
  - Reejecutar es un no-op (0 registros recalculados en la 2ª corrida).
  - El reporte de cambios de banda tiene la forma
    ``{athlete_id, record_id, indicator, previous, current}`` — solo IDs.
  - El log (``caplog``) nunca contiene nombre ni fecha de nacimiento del menor.

Estrategia: SQLite async in-memory (StaticPool), sin red ni MySQL. La LMS se
siembra con el mismo helper offline del seed real.
"""
from __future__ import annotations

import io
import json
import logging
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus, NutritionalStatus
from app.models.athlete import Athlete, Sex
from app.scripts.backfill_anthropometry import (
    RecomputeSummary,
    backfill_anthropometry,
    recompute_to_source,
    run,
)
from app.seed_growth_data import _parse_csv_content, _parse_who_csv_content, bulk_insert_lms
from app.services.growth import calculate_growth_percentiles
from app.models.growth import GrowthSource
from app.services.category import compute_age_decimal
from tests.helpers.audit_tables import AUDIT_TABLES

# Identificadores ficticios del menor — nunca datos reales de atletas TyR.
_ATHLETE_FIRST = "Juan"
_ATHLETE_LAST = "Pérez Ficticio"
_ATHLETE_DOB = date(2015, 1, 1)
_EVAL_DATE = date(2026, 5, 1)

# CSV LMS mínimo cubriendo edad/sexo del atleta de prueba (varón ~11 años).
_LMS_HEIGHT = "Sex,Agemos,L,M,S\n1,24,1.0,86.0,0.04\n1,240.5,0.9,175.0,0.045\n"
_LMS_BMI = "Sex,Agemos,L,M,S\n1,24,-2.0,16.5,0.08\n1,240.5,-1.5,21.0,0.13\n"
_LMS_WEIGHT = "Sex,Agemos,L,M,S\n1,24,-0.2,12.6,0.10\n1,240.5,-1.0,62.0,0.16\n"

# Fixture OMS mínima (formato real: header "sex,age_months,L,M,S", sexo ya
# M/F) cubriendo 61.5–228.5 meses para talla/IMC. Sin peso: el atleta de
# prueba de este archivo (~136 meses) ya cae por encima del corte OMS de
# 120.5 meses, así que weight_z_score/percentile deben quedar en NULL de
# todas formas tras el recompute — no hace falta sembrar peso OMS aquí.
_LMS_WHO_HEIGHT = "sex,age_months,L,M,S\nM,61.5,1.0,110.0,0.04\nM,228.5,1.0,176.0,0.04\n"
_LMS_WHO_BMI = "sex,age_months,L,M,S\nM,61.5,-1.0,15.0,0.09\nM,228.5,-1.0,22.0,0.13\n"


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in ("athletes", "anthropometric_records", "growth_reference_lms", *AUDIT_TABLES)
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_lms(session: AsyncSession) -> None:
    for content, indicator in (
        (_LMS_HEIGHT, "height_for_age"),
        (_LMS_BMI, "bmi_for_age"),
        (_LMS_WEIGHT, "weight_for_age"),
    ):
        await bulk_insert_lms(session, _parse_csv_content(content, indicator))
    await session.commit()


async def _seed_lms_who(session: AsyncSession) -> None:
    for content, indicator in (
        (_LMS_WHO_HEIGHT, "height_for_age"),
        (_LMS_WHO_BMI, "bmi_for_age"),
    ):
        await bulk_insert_lms(session, _parse_who_csv_content(content, indicator))
    await session.commit()


# Medidas crudas del registro a rellenar (derivados inicialmente en NULL).
_RAW_WEIGHT = Decimal("38.00")
_RAW_HEIGHT = Decimal("145.0")
_RAW_SITTING = Decimal("74.0")


async def _seed_athlete_and_record(session: AsyncSession) -> tuple[int, int]:
    """Crea un atleta ficticio + un registro antropométrico sin derivados."""
    athlete = Athlete(
        user_id=1,
        first_name=_ATHLETE_FIRST,
        last_name=_ATHLETE_LAST,
        birth_date=_ATHLETE_DOB,
        sex=Sex.M,
        club_id=1,
        created_by=1,
    )
    session.add(athlete)
    await session.flush()

    record = AnthropometricRecord(
        athlete_id=athlete.id,
        evaluation_date=_EVAL_DATE,
        weight_kg=_RAW_WEIGHT,
        standing_height_cm=_RAW_HEIGHT,
        sitting_height_cm=_RAW_SITTING,
        leg_length_cm=Decimal("71.0"),
        leg_sitting_ratio=Decimal("0.9595"),
        maturity_offset=Decimal("-1.50"),
        age_at_phv=Decimal("13.50"),
        maturation_status=MaturationStatus.pre_phv,
        evaluated_by=1,
        # Derivados deliberadamente en NULL → candidatos a backfill
        bmi=None,
        bmi_percentile=None,
        height_percentile=None,
        weight_percentile=None,
    )
    session.add(record)
    await session.commit()
    return athlete.id, record.id


@pytest.mark.asyncio
async def test_backfill_fills_derived_and_preserves_raw(session_factory) -> None:
    async with session_factory() as session:
        await _seed_lms(session)
        athlete_id, record_id = await _seed_athlete_and_record(session)

    async with session_factory() as session:
        summary = await backfill_anthropometry(session)

    assert summary.scanned == 1
    assert summary.updated == 1

    # Valor esperado de growth (misma matemática que el servicio).
    async with session_factory() as session:
        athlete = await session.get(Athlete, athlete_id)
        age_months = (
            compute_age_decimal(athlete.birth_date, _EVAL_DATE) * 12
        )
        expected = await calculate_growth_percentiles(
            db=session,
            weight_kg=float(_RAW_WEIGHT),
            standing_height_cm=float(_RAW_HEIGHT),
            sex="M",
            age_months=age_months,
            source=GrowthSource.CDC,
        )

    async with session_factory() as session:
        record = await session.get(AnthropometricRecord, record_id)

        # BMI = peso / talla_m**2
        expected_bmi = float(_RAW_WEIGHT) / (float(_RAW_HEIGHT) / 100) ** 2
        assert record.bmi is not None
        assert float(record.bmi) == pytest.approx(round(expected_bmi, 2), abs=0.01)

        # Percentiles/z-scores coinciden con services/growth.py
        assert record.bmi_percentile == expected.bmi_percentile
        assert record.height_percentile == expected.height_percentile
        assert record.weight_percentile == expected.weight_percentile
        assert record.bmi_z_score == expected.bmi_z_score
        assert record.height_z_score == expected.height_z_score
        assert record.weight_z_score == expected.weight_z_score

        # Medidas crudas INTACTAS
        assert record.weight_kg == _RAW_WEIGHT
        assert record.standing_height_cm == _RAW_HEIGHT
        assert record.sitting_height_cm == _RAW_SITTING


@pytest.mark.asyncio
async def test_backfill_is_idempotent(session_factory) -> None:
    async with session_factory() as session:
        await _seed_lms(session)
        await _seed_athlete_and_record(session)

    async with session_factory() as session:
        first = await backfill_anthropometry(session)
    assert first.updated == 1

    # Segunda corrida: nada cambia (no-op)
    async with session_factory() as session:
        second = await backfill_anthropometry(session)
    assert second.updated == 0
    assert second.scanned == 0  # ya no quedan registros con derivados NULL


@pytest.mark.asyncio
async def test_run_summary_emits_no_pii(session_factory, tmp_path, monkeypatch) -> None:
    async with session_factory() as session:
        await _seed_lms(session)
        await _seed_lms_who(session)
        await _seed_athlete_and_record(session)

    # El reporte de cambios de banda se escribe en ./data/ relativo al cwd;
    # se aísla en tmp_path para no dejar artefactos de prueba en el repo.
    monkeypatch.chdir(tmp_path)

    # run() construye su propio engine; lo apuntamos al engine in-memory de test.
    buffer = io.StringIO()
    with patch(
        "app.scripts.backfill_anthropometry.create_async_engine",
        return_value=session_factory.kw["bind"],
    ):
        with redirect_stdout(buffer):
            summary, recompute_summary = await run()

    assert summary.updated == 1
    # Segunda pasada (recompute a OMS): el registro llenado por CDC en la
    # primera pasada queda con growth_source=NULL, así que también migra.
    assert recompute_summary.recomputed == 1
    output = buffer.getvalue()
    assert output  # se imprimió el resumen agregado

    # Privacidad: ni nombre ni fecha de nacimiento del menor en el log.
    assert _ATHLETE_FIRST not in output
    assert _ATHLETE_LAST not in output
    assert "Ficticio" not in output
    assert "2015" not in output
    assert _ATHLETE_DOB.isoformat() not in output


# ---------------------------------------------------------------------------
# Feature 040 / T017 — recompute_to_source (migración a la referencia OMS)
# ---------------------------------------------------------------------------

# Atleta ficticio distinto del usado arriba (~12.3 años → 147.96 meses, por
# encima del corte OMS de 120.5 meses de peso-para-la-edad).
_RECOMPUTE_ATHLETE_FIRST = "Andrés"
_RECOMPUTE_ATHLETE_LAST = "Gómez Ficticio"
_RECOMPUTE_ATHLETE_DOB = date(2014, 1, 1)
_RECOMPUTE_EVAL_DATE = date(2026, 5, 1)

_RECOMPUTE_RAW_WEIGHT = Decimal("45.00")
_RECOMPUTE_RAW_HEIGHT = Decimal("155.0")
_RECOMPUTE_RAW_SITTING = Decimal("80.0")

# Fixture OMS: talla y BMI a los dos extremos del rango 61.5–228.5 meses.
# Con estos L/M/S, a los ~148 meses la talla cruzada con 155 cm da un
# z-score ≈ 1.5 (banda talla_adecuada) y el IMC cruzado con peso/talla da un
# z-score ≈ 0.05 (banda adecuado) — ambos distintos de las bandas "antiguas"
# (talla_alta / sobrepeso) fijadas a mano abajo, para forzar un cambio de
# banda real y verificable.
_RECOMPUTE_LMS_WHO_HEIGHT = (
    "sex,age_months,L,M,S\nM,61.5,1.0,110.0,0.05\nM,228.5,1.0,176.0,0.05\n"
)
_RECOMPUTE_LMS_WHO_BMI = (
    "sex,age_months,L,M,S\nM,61.5,-1.0,15.0,0.09\nM,228.5,-1.0,22.0,0.13\n"
)


async def _seed_recompute_who_lms(session: AsyncSession) -> None:
    for content, indicator in (
        (_RECOMPUTE_LMS_WHO_HEIGHT, "height_for_age"),
        (_RECOMPUTE_LMS_WHO_BMI, "bmi_for_age"),
    ):
        await bulk_insert_lms(session, _parse_who_csv_content(content, indicator))
    await session.commit()


async def _seed_cdc_tagged_record(session: AsyncSession) -> tuple[int, int]:
    """Atleta + registro ya clasificado con CDC (bandas "antiguas" fijadas
    a mano), listo para ser migrado por ``recompute_to_source``."""
    athlete = Athlete(
        user_id=2,
        first_name=_RECOMPUTE_ATHLETE_FIRST,
        last_name=_RECOMPUTE_ATHLETE_LAST,
        birth_date=_RECOMPUTE_ATHLETE_DOB,
        sex=Sex.M,
        club_id=1,
        created_by=1,
    )
    session.add(athlete)
    await session.flush()

    record = AnthropometricRecord(
        athlete_id=athlete.id,
        evaluation_date=_RECOMPUTE_EVAL_DATE,
        weight_kg=_RECOMPUTE_RAW_WEIGHT,
        standing_height_cm=_RECOMPUTE_RAW_HEIGHT,
        sitting_height_cm=_RECOMPUTE_RAW_SITTING,
        leg_length_cm=Decimal("75.0"),
        leg_sitting_ratio=Decimal("0.9375"),
        maturity_offset=Decimal("0.20"),
        age_at_phv=Decimal("12.10"),
        maturation_status=MaturationStatus.circa_phv,
        evaluated_by=1,
        notes=None,
        growth_source=GrowthSource.CDC,
        bmi=Decimal("18.73"),
        height_z_score=Decimal("2.50"),  # CDC → talla_alta (z > 2)
        height_percentile=Decimal("98.0"),
        bmi_z_score=Decimal("1.50"),
        bmi_percentile=Decimal("93.0"),
        nutritional_status=NutritionalStatus.sobrepeso,  # CDC → sobrepeso
        weight_z_score=Decimal("1.00"),
        weight_percentile=Decimal("84.0"),
    )
    session.add(record)
    await session.commit()
    return athlete.id, record.id


@pytest.mark.asyncio
async def test_recompute_switches_cdc_row_to_who(session_factory, tmp_path) -> None:
    async with session_factory() as session:
        await _seed_recompute_who_lms(session)
        athlete_id, record_id = await _seed_cdc_tagged_record(session)

    async with session_factory() as session:
        summary = await recompute_to_source(
            session, target=GrowthSource.WHO, report_dir=tmp_path
        )

    assert isinstance(summary, RecomputeSummary)
    assert summary.scanned == 1
    assert summary.recomputed == 1

    async with session_factory() as session:
        record = await session.get(AnthropometricRecord, record_id)

        assert record.growth_source == GrowthSource.WHO

        # Medidas crudas INTACTAS.
        assert record.weight_kg == _RECOMPUTE_RAW_WEIGHT
        assert record.standing_height_cm == _RECOMPUTE_RAW_HEIGHT
        assert record.sitting_height_cm == _RECOMPUTE_RAW_SITTING
        assert record.evaluation_date == _RECOMPUTE_EVAL_DATE
        assert record.maturity_offset == Decimal("0.20")
        assert record.age_at_phv == Decimal("12.10")
        assert record.maturation_status == MaturationStatus.circa_phv

        # Talla/IMC recalculados con OMS — bandas cambiaron respecto a CDC.
        assert 1.0 < float(record.height_z_score) < 2.0
        assert record.nutritional_status == NutritionalStatus.adecuado

        # Peso: por encima del corte OMS de 120.5 meses → NULL.
        assert record.weight_z_score is None
        assert record.weight_percentile is None


@pytest.mark.asyncio
async def test_recompute_band_change_report_shape(session_factory, tmp_path) -> None:
    async with session_factory() as session:
        await _seed_recompute_who_lms(session)
        athlete_id, record_id = await _seed_cdc_tagged_record(session)

    async with session_factory() as session:
        summary = await recompute_to_source(
            session, target=GrowthSource.WHO, report_dir=tmp_path
        )

    # Dos bandas cambiaron: talla_alta→talla_adecuada, sobrepeso→adecuado.
    assert len(summary.band_changes) == 2
    indicators = {entry["indicator"] for entry in summary.band_changes}
    assert indicators == {"height_for_age", "bmi_for_age"}

    for entry in summary.band_changes:
        assert set(entry.keys()) == {
            "athlete_id",
            "record_id",
            "indicator",
            "previous",
            "current",
        }
        assert entry["athlete_id"] == athlete_id
        assert entry["record_id"] == record_id
        assert isinstance(entry["athlete_id"], int)
        assert isinstance(entry["record_id"], int)
        # Ids solamente: nada de nombre ni fecha de nacimiento en el reporte.
        assert _RECOMPUTE_ATHLETE_FIRST not in json.dumps(entry)
        assert _RECOMPUTE_ATHLETE_LAST not in json.dumps(entry)
        assert _RECOMPUTE_ATHLETE_DOB.isoformat() not in json.dumps(entry)

    height_entry = next(
        e for e in summary.band_changes if e["indicator"] == "height_for_age"
    )
    assert height_entry["previous"] == "talla_alta"
    assert height_entry["current"] == "talla_adecuada"

    bmi_entry = next(
        e for e in summary.band_changes if e["indicator"] == "bmi_for_age"
    )
    assert bmi_entry["previous"] == "sobrepeso"
    assert bmi_entry["current"] == "adecuado"

    # El archivo se escribió en report_dir con el mismo contenido.
    report_files = list(tmp_path.glob("growth_band_changes_*.json"))
    assert len(report_files) == 1
    on_disk = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert on_disk == summary.band_changes
    report_text = report_files[0].read_text(encoding="utf-8")
    assert _RECOMPUTE_ATHLETE_FIRST not in report_text
    assert _RECOMPUTE_ATHLETE_LAST not in report_text
    assert _RECOMPUTE_ATHLETE_DOB.isoformat() not in report_text


@pytest.mark.asyncio
async def test_recompute_is_idempotent(session_factory, tmp_path) -> None:
    async with session_factory() as session:
        await _seed_recompute_who_lms(session)
        await _seed_cdc_tagged_record(session)

    async with session_factory() as session:
        first = await recompute_to_source(
            session, target=GrowthSource.WHO, report_dir=tmp_path
        )
    assert first.recomputed == 1

    # Segunda corrida: ya no hay candidatos (growth_source ya es WHO).
    async with session_factory() as session:
        second = await recompute_to_source(
            session, target=GrowthSource.WHO, report_dir=tmp_path
        )
    assert second.scanned == 0
    assert second.recomputed == 0
    assert second.band_changes == []


@pytest.mark.asyncio
async def test_recompute_caplog_emits_no_pii(session_factory, tmp_path, caplog) -> None:
    async with session_factory() as session:
        await _seed_recompute_who_lms(session)
        await _seed_cdc_tagged_record(session)

    with caplog.at_level(logging.INFO, logger="app.scripts.backfill_anthropometry"):
        async with session_factory() as session:
            await recompute_to_source(session, target=GrowthSource.WHO, report_dir=tmp_path)

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert log_text  # se emitió el resumen agregado
    assert _RECOMPUTE_ATHLETE_FIRST not in log_text
    assert _RECOMPUTE_ATHLETE_LAST not in log_text
    assert "Ficticio" not in log_text
    assert _RECOMPUTE_ATHLETE_DOB.isoformat() not in log_text
    assert "2014" not in log_text
