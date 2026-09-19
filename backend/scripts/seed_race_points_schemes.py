"""Seed idempotente del catálogo `race_points_schemes` — esquemas descriptivos
de temporadas históricas (feature 044).

Uso:
    cd backend
    python -m scripts.seed_race_points_schemes

Idempotente: usa UPSERT por `code`. Segunda ejecución imprime `inserted=0, updated=2`.

Por qué un script dedicado y no otro lugar existente
------------------------------------------------------
`race_points_schemes` no tenía, antes de esta feature, ningún script ni
endpoint que insertara filas: el código de ingesta (`app/services/race/
ingestor.py`) solo referencia `points_scheme_code="copa_valle_2026"` como FK
lógica (no forzada por `ForeignKey` — ver docstring de
`app/models/race_points_scheme.py`), y no existe ninguna migración ni
seed que cree esa fila ni ninguna otra. Se sigue el mismo patrón idempotente
de `scripts/seed_race_categories.py` (UPSERT por `code`, mismo estilo de
sesión async) en vez de meter estas dos filas en `scripts/seed.py` (que siembra
datos de desarrollo no relacionados con carreras) o en la migración Alembic de
la feature 044 (que según `data-model.md` no crea columnas nuevas en esta
tabla, solo filas — y los datos de fila no van en DDL de esquema).

Filas sembradas (feature 044 — histórico Copa Valle)
------------------------------------------------------
`copa_valle_2024` y `copa_valle_2025`: para las temporadas históricas los
puntos se toman literalmente de cada fila del PDF oficial; no se recalculan
contra ninguna tabla de puntos por posición. `position_points={}` y
`is_official=False` documentan esa decisión en la base de datos — existen
solo para que las series 2024/2025 tengan un `points_scheme_code` válido al
que apuntar.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import RacePointsScheme

DESCRIPTION = "Puntos tal como fueron impresos por el organizador; no se recalculan"

# Tupla: (code, description, is_official)
POINTS_SCHEMES: list[tuple[str, str, bool]] = [
    ("copa_valle_2024", DESCRIPTION, False),
    ("copa_valle_2025", DESCRIPTION, False),
]


async def upsert_points_schemes(session: AsyncSession) -> tuple[int, int]:
    """UPSERT idempotente. Retorna `(inserted, updated)`."""
    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)

    existing_q = await session.execute(select(RacePointsScheme))
    existing: dict[str, RacePointsScheme] = {s.code: s for s in existing_q.scalars().all()}

    for code, description, is_official in POINTS_SCHEMES:
        if code in existing:
            scheme = existing[code]
            changed = False
            if scheme.description != description:
                scheme.description = description
                changed = True
            if scheme.position_points != {}:
                scheme.position_points = {}
                changed = True
            if scheme.is_official != is_official:
                scheme.is_official = is_official
                changed = True
            if changed:
                scheme.updated_at = now
                updated += 1
        else:
            session.add(
                RacePointsScheme(
                    code=code,
                    description=description,
                    position_points={},
                    attendance_points=0,
                    dnf_points=0,
                    dsq_points=0,
                    dns_points=0,
                    is_official=is_official,
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1

    await session.commit()
    return inserted, updated


async def main() -> None:
    async with AsyncSessionLocal() as session:
        inserted, updated = await upsert_points_schemes(session)
    print(f"inserted={inserted}, updated={updated}")


if __name__ == "__main__":
    asyncio.run(main())
