"""Seed idempotente del catálogo `race_categories` — 26 categorías Copa Valle 2026
más 3 categorías propias de temporadas históricas (feature 044).

Uso:
    cd backend
    python -m scripts.seed_race_categories

Idempotente: usa UPSERT por `code`. Segunda ejecución imprime `inserted=0, updated=29`.

Fuente: catálogo oficial Federación Colombiana de Ciclismo — Copa Valle
XCO 2026. 26 codes activos.

Heurística de edades:
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

Categorías propias de temporada (feature 044, `is_active=False`)
------------------------------------------------------------------
En 2025 la Copa corrió máster masculino en dos grupos (B, C) donde 2024 y 2026
usan cuatro (B1, B2, C1, C2); y en 2024 y 2025 las niñas de preinfantil
corrieron en un solo grupo donde 2026 las divide en A y B. Se cargan como
categorías propias de su temporada — nunca se funden con una subdivisión
posterior ni con una anterior, porque eso inventaría un rango de edad que ese
año no existía:

- `MAS_B_2025` / `MAS_C_2025`: `age_min`/`age_max` en `NULL` a propósito. No
  hay fuente confiable para saber si el corte de edad de 2025 replicó la
  frontera combinada de sus equivalentes activas (B1+B2 → 40–49,
  C1+C2 → 50–59) o usó otra distinta ese año puntual; el contrato
  (`contracts/category-mapping.md`) permite dejarlos en `NULL` cuando no hay
  certeza en vez de adivinar.
- `PRE_F_U`: `age_min=6`, `age_max=8` — unión exacta de los rangos ya
  confirmados de `PRE_A_F` (6–7) y `PRE_B_F` (7–8), que sí son ciertos porque
  son las categorías activas que ese grupo único reemplaza en 2026.

`sort_order`: se insertaron en huecos existentes del catálogo (sin renumerar
ninguna de las 26 filas activas). `PRE_F_U` va en 24, entre `PRE_B_F` (23) y
`INF_A` (30) — justo después de sus dos equivalentes activas. `MAS_B_2025` y
`MAS_C_2025` van en 86 y 87, después de `MAS_D` (85, cierre del bloque
masculino de máster) y antes de `MAS_F` (90); no hay hueco entero disponible
entre `MAS_B2` (82) y `MAS_C1` (83) para insertarlas justo tras cada
equivalente sin renumerar, así que se agrupan al final del bloque masculino.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import CategoryGender, CategoryTier, RaceCategory


# Tupla: (code, label, sex, age_min, age_max, tier, sort_order, is_active)
CATEGORIES: list[
    tuple[str, str, CategoryGender, int | None, int | None, CategoryTier | None, int, bool]
] = [
    # Menores
    ("TET_SP",   "Teteros Sin Pedales",       CategoryGender.MIXED, None, 5,    CategoryTier.menores, 10, True),
    ("TET_CP",   "Teteros Con Pedales",       CategoryGender.MIXED, None, 5,    CategoryTier.menores, 11, True),
    ("PRE_A",    "Preinfantil A",             CategoryGender.M,     6,    7,    CategoryTier.menores, 20, True),
    ("PRE_B",    "Preinfantil B",             CategoryGender.M,     7,    8,    CategoryTier.menores, 21, True),
    ("PRE_A_F",  "Preinfantil A Femenino",    CategoryGender.F,     6,    7,    CategoryTier.menores, 22, True),
    ("PRE_B_F",  "Preinfantil B Femenino",    CategoryGender.F,     7,    8,    CategoryTier.menores, 23, True),
    # Propia de temporada 2024/2025 — grupo único, ver docstring del módulo.
    ("PRE_F_U",  "Preinfantil femenino (grupo único)", CategoryGender.F, 6, 8,  CategoryTier.menores, 24, False),
    ("INF_A",    "Infantil A",                CategoryGender.M,     9,    10,   CategoryTier.menores, 30, True),
    ("INF_B",    "Infantil B",                CategoryGender.M,     11,   12,   CategoryTier.menores, 31, True),
    ("INF_A_F",  "Infantil A Femenino",       CategoryGender.F,     9,    10,   CategoryTier.menores, 32, True),
    ("INF_B_F",  "Infantil B Femenino",       CategoryGender.F,     11,   12,   CategoryTier.menores, 33, True),
    ("PJUV_A",   "Prejuvenil A",              CategoryGender.M,     13,   13,   CategoryTier.menores, 40, True),
    ("PJUV_B",   "Prejuvenil B",              CategoryGender.M,     14,   14,   CategoryTier.menores, 41, True),
    ("PJUV_A_F", "Prejuvenil A Femenino",     CategoryGender.F,     13,   13,   CategoryTier.menores, 42, True),
    ("PJUV_B_F", "Prejuvenil B Femenino",     CategoryGender.F,     14,   14,   CategoryTier.menores, 43, True),
    # Juvenil
    ("JUN_M",    "Junior",                    CategoryGender.M,     15,   16,   CategoryTier.juvenil, 50, True),
    ("JUN_F",    "Junior Femenino",           CategoryGender.F,     15,   16,   CategoryTier.juvenil, 51, True),
    # Adulto
    ("ELITE_M",  "Elite",                     CategoryGender.M,     17,   None, CategoryTier.adulto,  60, True),
    ("ELITE_F",  "Elite Femenino",            CategoryGender.F,     17,   None, CategoryTier.adulto,  61, True),
    ("PROMO",    "Promocional",               CategoryGender.MIXED, None, None, CategoryTier.adulto,  70, True),
    # Master
    ("MAS_A",    "Master A",                  CategoryGender.M,     30,   39,   CategoryTier.master,  80, True),
    ("MAS_B1",   "Master B1",                 CategoryGender.M,     40,   44,   CategoryTier.master,  81, True),
    ("MAS_B2",   "Master B2",                 CategoryGender.M,     45,   49,   CategoryTier.master,  82, True),
    ("MAS_C1",   "Master C1",                 CategoryGender.M,     50,   54,   CategoryTier.master,  83, True),
    ("MAS_C2",   "Master C2",                 CategoryGender.M,     55,   59,   CategoryTier.master,  84, True),
    ("MAS_D",    "Master D",                  CategoryGender.M,     60,   None, CategoryTier.master,  85, True),
    # Propias de temporada 2025 — grupos B/C únicos, ver docstring del módulo.
    ("MAS_B_2025", "Máster B (2025)",         CategoryGender.M,     None, None, CategoryTier.master,  86, False),
    ("MAS_C_2025", "Máster C (2025)",         CategoryGender.M,     None, None, CategoryTier.master,  87, False),
    ("MAS_F",    "Master Femenino",           CategoryGender.F,     30,   None, CategoryTier.master,  90, True),
]


async def upsert_categories(session: AsyncSession) -> tuple[int, int]:
    """UPSERT idempotente. Retorna `(inserted, updated)`."""
    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)

    # Cargo existentes en un dict
    existing_q = await session.execute(select(RaceCategory))
    existing: dict[str, RaceCategory] = {c.code: c for c in existing_q.scalars().all()}

    for code, label, sex, age_min, age_max, tier, sort_order, is_active in CATEGORIES:
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
            if cat.is_active != is_active:
                cat.is_active = is_active
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
                    is_active=is_active,
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
