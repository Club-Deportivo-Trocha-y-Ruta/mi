"""Seed idempotente del catálogo `race_categories` — 26 categorías Copa Valle 2026.

Uso:
    cd backend
    python -m scripts.seed_race_categories

Idempotente: usa UPSERT por `code`. Segunda ejecución imprime `inserted=0, updated=26`.

Fuente: `docs/10-race-results/design.md §3.1` + `edge-cases.md §2`.
26 codes (no 22 — el design tiene un error tipográfico en el conteo).

Heurística de edades (design §3.1):
- Teteros (TET_*):        edad ≤ 5 años.
- Preinfantil (PRE_*):    6–8 años.
- Infantil (INF_*):       9–12 años.
- Prejuvenil (PJUV_*):    13–14 años.
- Junior (JUN_*):         15–16 años.
- Elite (ELITE_*):        17+ años (sin tope superior).
- Promocional (PROMO):    MIXED, sin rango etario.
- Master:
    MAS_A: 30–39, MAS_B1: 40–44, MAS_B2: 45–49,
    MAS_C1: 50–54, MAS_C2: 55–59, MAS_D: 60+,
    MAS_F: femenino mixto (rango amplio 30+).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import CategoryGender, CategoryTier, RaceCategory


# Tupla: (code, label, sex, age_min, age_max, tier, sort_order)
CATEGORIES: list[tuple[str, str, CategoryGender, int | None, int | None, CategoryTier | None, int]] = [
    # Menores
    ("TET_SP",   "Teteros Sin Pedales",       CategoryGender.MIXED, None, 5,    CategoryTier.menores, 10),
    ("TET_CP",   "Teteros Con Pedales",       CategoryGender.MIXED, None, 5,    CategoryTier.menores, 11),
    ("PRE_A",    "Preinfantil A",             CategoryGender.M,     6,    7,    CategoryTier.menores, 20),
    ("PRE_B",    "Preinfantil B",             CategoryGender.M,     7,    8,    CategoryTier.menores, 21),
    ("PRE_A_F",  "Preinfantil A Femenino",    CategoryGender.F,     6,    7,    CategoryTier.menores, 22),
    ("PRE_B_F",  "Preinfantil B Femenino",    CategoryGender.F,     7,    8,    CategoryTier.menores, 23),
    ("INF_A",    "Infantil A",                CategoryGender.M,     9,    10,   CategoryTier.menores, 30),
    ("INF_B",    "Infantil B",                CategoryGender.M,     11,   12,   CategoryTier.menores, 31),
    ("INF_A_F",  "Infantil A Femenino",       CategoryGender.F,     9,    10,   CategoryTier.menores, 32),
    ("INF_B_F",  "Infantil B Femenino",       CategoryGender.F,     11,   12,   CategoryTier.menores, 33),
    ("PJUV_A",   "Prejuvenil A",              CategoryGender.M,     13,   13,   CategoryTier.menores, 40),
    ("PJUV_B",   "Prejuvenil B",              CategoryGender.M,     14,   14,   CategoryTier.menores, 41),
    ("PJUV_A_F", "Prejuvenil A Femenino",     CategoryGender.F,     13,   13,   CategoryTier.menores, 42),
    ("PJUV_B_F", "Prejuvenil B Femenino",     CategoryGender.F,     14,   14,   CategoryTier.menores, 43),
    # Juvenil
    ("JUN_M",    "Junior",                    CategoryGender.M,     15,   16,   CategoryTier.juvenil, 50),
    ("JUN_F",    "Junior Femenino",           CategoryGender.F,     15,   16,   CategoryTier.juvenil, 51),
    # Adulto
    ("ELITE_M",  "Elite",                     CategoryGender.M,     17,   None, CategoryTier.adulto,  60),
    ("ELITE_F",  "Elite Femenino",            CategoryGender.F,     17,   None, CategoryTier.adulto,  61),
    ("PROMO",    "Promocional",               CategoryGender.MIXED, None, None, CategoryTier.adulto,  70),
    # Master
    ("MAS_A",    "Master A",                  CategoryGender.M,     30,   39,   CategoryTier.master,  80),
    ("MAS_B1",   "Master B1",                 CategoryGender.M,     40,   44,   CategoryTier.master,  81),
    ("MAS_B2",   "Master B2",                 CategoryGender.M,     45,   49,   CategoryTier.master,  82),
    ("MAS_C1",   "Master C1",                 CategoryGender.M,     50,   54,   CategoryTier.master,  83),
    ("MAS_C2",   "Master C2",                 CategoryGender.M,     55,   59,   CategoryTier.master,  84),
    ("MAS_D",    "Master D",                  CategoryGender.M,     60,   None, CategoryTier.master,  85),
    ("MAS_F",    "Master Femenino",           CategoryGender.F,     30,   None, CategoryTier.master,  90),
]


async def upsert_categories(session: AsyncSession) -> tuple[int, int]:
    """UPSERT idempotente. Retorna `(inserted, updated)`."""
    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)

    # Cargo existentes en un dict
    existing_q = await session.execute(select(RaceCategory))
    existing: dict[str, RaceCategory] = {c.code: c for c in existing_q.scalars().all()}

    for code, label, sex, age_min, age_max, tier, sort_order in CATEGORIES:
        if code in existing:
            cat = existing[code]
            changed = False
            if cat.label != label:
                cat.label = label
                changed = True
            if cat.sex != sex:
                cat.sex = sex
                changed = True
            if cat.age_min != age_min:
                cat.age_min = age_min
                changed = True
            if cat.age_max != age_max:
                cat.age_max = age_max
                changed = True
            if cat.tier != tier:
                cat.tier = tier
                changed = True
            if cat.sort_order != sort_order:
                cat.sort_order = sort_order
                changed = True
            if not cat.is_active:
                cat.is_active = True
                changed = True
            if changed:
                cat.updated_at = now
                updated += 1
        else:
            session.add(
                RaceCategory(
                    code=code,
                    label=label,
                    sex=sex,
                    age_min=age_min,
                    age_max=age_max,
                    tier=tier,
                    sort_order=sort_order,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1

    await session.commit()
    return inserted, updated


async def main() -> None:
    async with AsyncSessionLocal() as session:
        inserted, updated = await upsert_categories(session)
    print(f"inserted={inserted}, updated={updated}")


if __name__ == "__main__":
    asyncio.run(main())
