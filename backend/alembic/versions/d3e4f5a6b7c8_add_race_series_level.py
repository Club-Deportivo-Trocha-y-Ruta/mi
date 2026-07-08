"""add race_series.level

Revision ID: d3e4f5a6b7c8
Revises: a7b8c9d0e1f2
Create Date: 2026-07-08 00:00:00.000000

Spec 023 — national-championship-level.

DDL:
    ALTER TABLE race_series ADD COLUMN level ENUM('departmental','national') NOT NULL
    DEFAULT 'departmental'

Sin backfill de datos: el `server_default` cubre todas las filas existentes (las
válidas de Copa Valle y el "Campeonato Departamental 2026" quedan en
`departmental`, que es su valor correcto). Campo significativo solo cuando
`kind='championship'`; las copas siempre guardan `departmental` y la UI nunca lo
expone para ellas.

Downgrade:
    Elimina la columna `level` (y el tipo enum cuando el dialecto lo requiera).

Portabilidad MySQL/SQLite:
    - El tipo ENUM solo existe en MySQL. SQLite renderiza VARCHAR (comportamiento
      de Alembic cuando el dialecto no soporta ENUM nativo) — mismo patrón que la
      columna `kind` (migración b1c2d3e4f5a6).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Agregar columna `level` a `race_series`
    # -------------------------------------------------------------------------
    op.add_column(
        "race_series",
        sa.Column(
            "level",
            sa.Enum("departmental", "national", name="raceserieslevel"),
            nullable=False,
            server_default="departmental",
        ),
    )


def downgrade() -> None:
    # MySQL requiere existing_type + existing_nullable al alterar columnas ENUM
    op.drop_column("race_series", "level")
