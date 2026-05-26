"""seed catálogo race_categories — 26 categorías Copa Valle

Revision ID: c4d5e6f7a8b9
Revises: d2e3f4a5b6c7
Create Date: 2026-05-26 00:00:00.000000

Propósito:
  Garantiza que las 26 categorías de la Copa Valle XCO estén presentes en
  producción al arrancar.  Antes de esta migración, entrypoint.sh solo
  ejecutaba el seed en APP_ENV=development, dejando race_categories vacía
  en Render → ValueError en el ingestor → HTTP 500 sin body.

  Idempotente: MySQL usa ON DUPLICATE KEY UPDATE; SQLite (tests) usa
  INSERT OR IGNORE.  Ambas rutas detectan dialect con op.get_bind().dialect.name.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Catálogo: (code, label, sex, age_min, age_max, tier, sort_order)
# sex   → "M" / "F" / "MIXED"  (enum racecategorysex)
# tier  → "menores" / "juvenil" / "adulto" / "master"  (enum racecategorytier)
# ---------------------------------------------------------------------------
_CATEGORIES: list[tuple[str, str, str, int | None, int | None, str, int]] = [
    # Menores
    ("TET_SP",   "Teteros Sin Pedales",    "MIXED", None, 5,    "menores", 10),
    ("TET_CP",   "Teteros Con Pedales",    "MIXED", None, 5,    "menores", 11),
    ("PRE_A",    "Preinfantil A",          "M",     6,    7,    "menores", 20),
    ("PRE_B",    "Preinfantil B",          "M",     7,    8,    "menores", 21),
    ("PRE_A_F",  "Preinfantil A Femenino", "F",     6,    7,    "menores", 22),
    ("PRE_B_F",  "Preinfantil B Femenino", "F",     7,    8,    "menores", 23),
    ("INF_A",    "Infantil A",             "M",     9,    10,   "menores", 30),
    ("INF_B",    "Infantil B",             "M",     11,   12,   "menores", 31),
    ("INF_A_F",  "Infantil A Femenino",    "F",     9,    10,   "menores", 32),
    ("INF_B_F",  "Infantil B Femenino",    "F",     11,   12,   "menores", 33),
    ("PJUV_A",   "Prejuvenil A",           "M",     13,   13,   "menores", 40),
    ("PJUV_B",   "Prejuvenil B",           "M",     14,   14,   "menores", 41),
    ("PJUV_A_F", "Prejuvenil A Femenino",  "F",     13,   13,   "menores", 42),
    ("PJUV_B_F", "Prejuvenil B Femenino",  "F",     14,   14,   "menores", 43),
    # Juvenil
    ("JUN_M",    "Junior",                 "M",     15,   16,   "juvenil", 50),
    ("JUN_F",    "Junior Femenino",        "F",     15,   16,   "juvenil", 51),
    # Adulto
    ("ELITE_M",  "Elite",                  "M",     17,   None, "adulto",  60),
    ("ELITE_F",  "Elite Femenino",         "F",     17,   None, "adulto",  61),
    ("PROMO",    "Promocional",            "MIXED", None, None, "adulto",  70),
    # Master
    ("MAS_A",    "Master A",               "M",     30,   39,   "master",  80),
    ("MAS_B1",   "Master B1",              "M",     40,   44,   "master",  81),
    ("MAS_B2",   "Master B2",              "M",     45,   49,   "master",  82),
    ("MAS_C1",   "Master C1",              "M",     50,   54,   "master",  83),
    ("MAS_C2",   "Master C2",              "M",     55,   59,   "master",  84),
    ("MAS_D",    "Master D",               "M",     60,   None, "master",  85),
    ("MAS_F",    "Master Femenino",        "F",     30,   None, "master",  90),
]

_ALL_CODES = [row[0] for row in _CATEGORIES]


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name  # "mysql" | "mariadb" | "sqlite"

    # Tabla auxiliar para la construcción de la sentencia INSERT
    race_categories = sa.table(
        "race_categories",
        sa.column("code",       sa.String),
        sa.column("label",      sa.String),
        sa.column("sex",        sa.String),
        sa.column("age_min",    sa.SmallInteger),
        sa.column("age_max",    sa.SmallInteger),
        sa.column("tier",       sa.String),
        sa.column("sort_order", sa.SmallInteger),
        sa.column("is_active",  sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    rows = [
        {
            "code":       code,
            "label":      label,
            "sex":        sex,
            "age_min":    age_min,
            "age_max":    age_max,
            "tier":       tier,
            "sort_order": sort_order,
            "is_active":  True,
            "created_at": sa.func.now(),
            "updated_at": sa.func.now(),
        }
        for code, label, sex, age_min, age_max, tier, sort_order in _CATEGORIES
    ]

    if dialect in ("mysql", "mariadb"):
        # ON DUPLICATE KEY UPDATE — idempotente contra la UNIQUE KEY en `code`
        for row in rows:
            op.execute(
                sa.text(
                    "INSERT INTO race_categories "
                    "    (code, label, sex, age_min, age_max, tier, sort_order, is_active, created_at, updated_at) "
                    "VALUES "
                    "    (:code, :label, :sex, :age_min, :age_max, :tier, :sort_order, 1, NOW(), NOW()) "
                    "ON DUPLICATE KEY UPDATE "
                    "    label      = VALUES(label), "
                    "    sex        = VALUES(sex), "
                    "    age_min    = VALUES(age_min), "
                    "    age_max    = VALUES(age_max), "
                    "    tier       = VALUES(tier), "
                    "    sort_order = VALUES(sort_order), "
                    "    is_active  = 1, "
                    "    updated_at = NOW()"
                ).bindparams(
                    code=row["code"],
                    label=row["label"],
                    sex=row["sex"],
                    age_min=row["age_min"],
                    age_max=row["age_max"],
                    tier=row["tier"],
                    sort_order=row["sort_order"],
                )
            )
    else:
        # SQLite (aiosqlite en tests): INSERT OR IGNORE preserva filas existentes
        for row in rows:
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO race_categories "
                    "    (code, label, sex, age_min, age_max, tier, sort_order, is_active, created_at, updated_at) "
                    "VALUES "
                    "    (:code, :label, :sex, :age_min, :age_max, :tier, :sort_order, 1, datetime('now'), datetime('now'))"
                ).bindparams(
                    code=row["code"],
                    label=row["label"],
                    sex=row["sex"],
                    age_min=row["age_min"],
                    age_max=row["age_max"],
                    tier=row["tier"],
                    sort_order=row["sort_order"],
                )
            )


def downgrade() -> None:
    codes_literal = ", ".join(f"'{c}'" for c in _ALL_CODES)
    op.execute(
        sa.text(f"DELETE FROM race_categories WHERE code IN ({codes_literal})")  # noqa: S608
    )
