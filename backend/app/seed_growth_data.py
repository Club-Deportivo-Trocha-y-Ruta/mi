"""
Script de seed para cargar datos LMS del CDC en growth_reference_lms.

Uso:
    cd backend
    python -m app.seed_growth_data

Requiere que la migración ya esté aplicada (alembic upgrade head).
"""
from __future__ import annotations

import asyncio
import csv
import io
import urllib.request
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


CDC_SOURCES: list[dict[str, str]] = [
    {
        "url": "https://www.cdc.gov/growthcharts/data/zscore/statage.csv",
        "indicator": "height_for_age",
    },
    {
        "url": "https://www.cdc.gov/growthcharts/data/zscore/bmiagerev.csv",
        "indicator": "bmi_for_age",
    },
    {
        "url": "https://www.cdc.gov/growthcharts/data/zscore/wtage.csv",
        "indicator": "weight_for_age",
    },
]

# Rango de edad válido según CDC (meses)
AGE_MIN_MONTHS: float = 24.0
AGE_MAX_MONTHS: float = 240.5

BATCH_SIZE: int = 100


async def seed_growth_data() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        total_inserted = 0
        for source_info in CDC_SOURCES:
            print(f"Descargando {source_info['indicator']}...")
            rows = download_and_parse_csv(source_info["url"], source_info["indicator"])
            inserted = await bulk_insert_lms(session, rows)
            total_inserted += inserted
            print(f"  {source_info['indicator']}: {inserted} filas procesadas")

        await session.commit()
        print(f"\nTotal: {total_inserted} filas en growth_reference_lms")

    await engine.dispose()


def download_and_parse_csv(url: str, indicator: str) -> list[dict[str, Any]]:
    """Descarga el CSV del CDC y retorna filas LMS en el rango de edad válido."""
    with urllib.request.urlopen(url, timeout=30) as response:
        raw_bytes = response.read()

    # Los CSVs del CDC usan encoding latin-1 en algunos casos
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(content))
    rows: list[dict[str, Any]] = []

    for row in reader:
        # Columnas relevantes: Sex, Agemos, L, M, S
        sex_raw = row.get("Sex", "").strip()
        agemos_raw = row.get("Agemos", "").strip()
        l_raw = row.get("L", "").strip()
        m_raw = row.get("M", "").strip()
        s_raw = row.get("S", "").strip()

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


async def bulk_insert_lms(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    """
    Inserta filas en growth_reference_lms usando ON DUPLICATE KEY UPDATE.
    Procesa en batches de BATCH_SIZE para no saturar la conexión.
    Retorna el número total de filas procesadas.
    """
    if not rows:
        return 0

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

    total = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        await session.execute(insert_sql, batch)
        total += len(batch)

    return total


if __name__ == "__main__":
    asyncio.run(seed_growth_data())
