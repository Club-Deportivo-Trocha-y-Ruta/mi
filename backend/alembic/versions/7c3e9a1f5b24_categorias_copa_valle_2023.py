"""categorías propias de la temporada 2023 (Copa Valle)

Revision ID: 7c3e9a1f5b24
Revises: 448f7dfbca14
Create Date: 2026-10-20

Carga histórica Copa Valle 2023. Solo datos: inserta 10 filas inactivas en
``race_categories`` (``is_active = 0``), nunca ofrecidas para datos 2026+. Mismo
criterio que ``MAS_B_2025`` / ``*_2022`` (feature 044): lo que cambió de forma
entre temporadas es un código propio de temporada, no una fusión.

Idempotente: MySQL ``ON DUPLICATE KEY UPDATE`` (no reactiva una fila existente);
SQLite ``INSERT OR IGNORE``. ``scripts/seed_race_categories.py`` lleva las mismas
filas y converge al mismo estado.

``downgrade`` borra por ``code``. Falla (FK) si ya hay resultados cargados en
alguna de ellas — correcto: no se debe perder historia en silencio.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7c3e9a1f5b24"
down_revision: Union[str, None] = "448f7dfbca14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (code, label, sex, age_min, age_max, tier, sort_order)
_CATEGORIES: list[tuple[str, str, str, int | None, int | None, str, int]] = [
    ("PRE_A_MIX_2023", "Preinfantil A mixto (2023)", "MIXED", 6, 7, "menores", 25),
    ("PRE_B_MIX_2023", "Preinfantil B mixto (2023)", "MIXED", 7, 8, "menores", 26),
    ("NOV_2023", "Novatos (2023)", "M", None, None, "adulto", 73),
    ("NOV_F_2023", "Novatas (2023)", "F", None, None, "adulto", 74),
    ("NOV_A_2023", "Novatos A (2023)", "MIXED", None, None, "adulto", 75),
    ("NOV_B_2023", "Novatos B (2023)", "MIXED", None, None, "adulto", 76),
    ("SPORT_A_2023", "Sport A (2023)", "MIXED", None, None, "adulto", 77),
    ("SPORT_B_2023", "Sport B (2023)", "MIXED", None, None, "adulto", 78),
    ("MAS_A1_2023", "Máster A1 (2023)", "M", None, None, "master", 91),
    ("MAS_A2_2023", "Máster A2 (2023)", "M", None, None, "master", 92),
]


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect in ("mysql", "mariadb"):
        verb, now, tail = "INSERT", "NOW()", " ON DUPLICATE KEY UPDATE code = code"
    else:
        verb, now, tail = "INSERT OR IGNORE", "datetime('now')", ""
    stmt = (
        f"{verb} INTO race_categories "  # noqa: S608
        "(code, label, sex, age_min, age_max, tier, sort_order, is_active, created_at, updated_at) "
        f"VALUES (:code, :label, :sex, :age_min, :age_max, :tier, :sort_order, 0, {now}, {now})"
        f"{tail}"
    )
    for code, label, sex, age_min, age_max, tier, sort_order in _CATEGORIES:
        op.execute(
            sa.text(stmt).bindparams(
                code=code, label=label, sex=sex, age_min=age_min, age_max=age_max,
                tier=tier, sort_order=sort_order,
            )
        )


def downgrade() -> None:
    codes = ", ".join(f"'{row[0]}'" for row in _CATEGORIES)
    op.execute(sa.text(f"DELETE FROM race_categories WHERE code IN ({codes})"))  # noqa: S608
