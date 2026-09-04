"""
Script de seed para cargar datos LMS del CDC y de la OMS en growth_reference_lms.

Uso:
    cd backend
    python -m app.seed_growth_data

Lee los CSV **vendorizados** en ``app/data/cdc_lms/`` (histórico, feature 003)
y en ``app/data/who_lms/`` (referencia única del feature 040 — ver
``specs/040-growth-module-redesign/contracts/who-lms-seed.md``); no hay
descarga de red en ninguno de los dos casos. El seed es determinista, offline
e idempotente. Requiere que la migración ya esté aplicada (alembic upgrade
head). Reejecutar es un no-op (upsert por la constraint
``uq_lms_source_indicator_sex_age``).
"""
from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Directorio con los CSV del CDC vendorizados (constantes de referencia
# poblacional; NO contienen datos de menores). Ver app/data/cdc_lms/README.md.
DATA_DIR: Path = Path(__file__).parent / "data" / "cdc_lms"

CDC_SOURCES: list[dict[str, str]] = [
    {"filename": "statage.csv", "indicator": "height_for_age"},
    {"filename": "bmiagerev.csv", "indicator": "bmi_for_age"},
    {"filename": "wtage.csv", "indicator": "weight_for_age"},
]

# Rango de edad válido según CDC (meses)
AGE_MIN_MONTHS: float = 24.0
AGE_MAX_MONTHS: float = 240.5

# Directorio con los CSV de la OMS vendorizados — referencia única del
# feature 040 (constantes de referencia poblacional; NO contienen datos de
# menores). Ver app/data/who_lms/README.md.
WHO_DATA_DIR: Path = Path(__file__).parent / "data" / "who_lms"

WHO_SOURCES: list[dict[str, str]] = [
    {"filename": "who_height_for_age.csv", "indicator": "height_for_age"},
    {"filename": "who_bmi_for_age.csv", "indicator": "bmi_for_age"},
    {"filename": "who_weight_for_age.csv", "indicator": "weight_for_age"},
]

BATCH_SIZE: int = 100


async def seed_growth_data() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            total_inserted = 0
            for source_info in CDC_SOURCES:
                csv_path = DATA_DIR / source_info["filename"]
                print(f"Cargando {source_info['indicator']} (CDC) desde {csv_path.name}...")
                rows = parse_csv_file(csv_path, source_info["indicator"])
                inserted = await bulk_insert_lms(session, rows)
                total_inserted += inserted
                print(f"  {source_info['indicator']} (CDC): {inserted} filas procesadas")

            for source_info in WHO_SOURCES:
                csv_path = WHO_DATA_DIR / source_info["filename"]
                print(f"Cargando {source_info['indicator']} (OMS) desde {csv_path.name}...")
                rows = parse_who_csv_file(csv_path, source_info["indicator"])
                inserted = await bulk_insert_lms(session, rows)
                total_inserted += inserted
                print(f"  {source_info['indicator']} (OMS): {inserted} filas procesadas")

            await session.commit()
            print(f"\nTotal: {total_inserted} filas en growth_reference_lms")
    finally:
        await engine.dispose()


def parse_csv_file(csv_path: Path, indicator: str) -> list[dict[str, Any]]:
    """Lee el CSV vendorizado del CDC y retorna filas LMS en el rango válido."""
    raw_bytes = csv_path.read_bytes()

    # Los CSVs del CDC usan encoding latin-1 en algunos casos
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1")

    return _parse_csv_content(content, indicator)


def _parse_csv_content(content: str, indicator: str) -> list[dict[str, Any]]:
    """Parsea el contenido CSV (separado para facilitar pruebas con fixtures)."""
    reader = csv.DictReader(content.splitlines())
    rows: list[dict[str, Any]] = []

    for row in reader:
        # Columnas relevantes: Sex, Agemos, L, M, S
        sex_raw = (row.get("Sex") or "").strip()
        agemos_raw = (row.get("Agemos") or "").strip()
        l_raw = (row.get("L") or "").strip()
        m_raw = (row.get("M") or "").strip()
        s_raw = (row.get("S") or "").strip()

        # Saltar filas con campos vacíos o no numéricos
        if not all([sex_raw, agemos_raw, l_raw, m_raw, s_raw]):
            continue

        try:
            sex_code = int(sex_raw)
            age_months = float(agemos_raw)
            l_val = float(l_raw)
            m_val = float(m_raw)
            s_val = float(s_raw)
        except ValueError:
            continue

        # Filtrar fuera del rango CDC
        if age_months < AGE_MIN_MONTHS or age_months > AGE_MAX_MONTHS:
            continue

        # Mapear código de sexo CDC a M/F
        if sex_code == 1:
            sex = "M"
        elif sex_code == 2:
            sex = "F"
        else:
            continue

        rows.append(
            {
                "source": "CDC",
                "indicator": indicator,
                "sex": sex,
                "age_months": age_months,
                "L": l_val,
                "M": m_val,
                "S": s_val,
            }
        )

    return rows


def parse_who_csv_file(csv_path: Path, indicator: str) -> list[dict[str, Any]]:
    """Lee un CSV vendorizado de la OMS (``app/data/who_lms/``) y retorna filas LMS."""
    content = csv_path.read_text(encoding="utf-8")
    return _parse_who_csv_content(content, indicator)


def _parse_who_csv_content(content: str, indicator: str) -> list[dict[str, Any]]:
    """Parsea el contenido CSV de la OMS (separado para pruebas con fixtures).

    A diferencia del CSV del CDC, el formato de la OMS ya trae ``sex`` como
    ``M``/``F`` y ``age_months`` sin necesidad de filtrar por rango: el
    exportador (``scripts/export_who_lms_csv.py``) ya recorta cada indicador
    al rango publicado por la OMS (61.5–228.5 meses para talla/IMC,
    61.5–120.5 para peso).
    """
    reader = csv.DictReader(content.splitlines())
    rows: list[dict[str, Any]] = []

    for row in reader:
        sex = (row.get("sex") or "").strip()
        age_raw = (row.get("age_months") or "").strip()
        l_raw = (row.get("L") or "").strip()
        m_raw = (row.get("M") or "").strip()
        s_raw = (row.get("S") or "").strip()

        if not all([sex, age_raw, l_raw, m_raw, s_raw]):
            continue
        if sex not in ("M", "F"):
            continue

        try:
            age_months = float(age_raw)
            l_val = float(l_raw)
            m_val = float(m_raw)
            s_val = float(s_raw)
        except ValueError:
            continue

        rows.append(
            {
                "source": "WHO",
                "indicator": indicator,
                "sex": sex,
                "age_months": age_months,
                "L": l_val,
                "M": m_val,
                "S": s_val,
            }
        )

    return rows


async def bulk_insert_lms(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """
    Inserta filas en growth_reference_lms de forma idempotente (upsert por la
    constraint única). El SQL de upsert se adapta al dialecto (MySQL en prod,
    SQLite en pruebas). Procesa en batches de BATCH_SIZE.
    Retorna el número total de filas procesadas.
    """
    if not rows:
        return 0

    dialect_name = session.bind.dialect.name if session.bind is not None else "mysql"

    if dialect_name == "mysql":
        insert_sql = text(
            """
            INSERT INTO growth_reference_lms (source, indicator, sex, age_months, L, M, S)
            VALUES (:source, :indicator, :sex, :age_months, :L, :M, :S)
            ON DUPLICATE KEY UPDATE
                L = VALUES(L),
                M = VALUES(M),
                S = VALUES(S)
            """
        )
    else:
        # SQLite (pruebas) y otros motores con UPSERT estilo ON CONFLICT
        insert_sql = text(
            """
            INSERT INTO growth_reference_lms (source, indicator, sex, age_months, L, M, S)
            VALUES (:source, :indicator, :sex, :age_months, :L, :M, :S)
            ON CONFLICT (source, indicator, sex, age_months) DO UPDATE SET
                L = excluded.L,
                M = excluded.M,
                S = excluded.S
            """
        )

    total = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        await session.execute(insert_sql, batch)
        total += len(batch)

    return total


if __name__ == "__main__":
    asyncio.run(seed_growth_data())
