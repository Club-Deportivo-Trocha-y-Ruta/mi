"""drop_anthropometry_mesocycle

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-05-06 13:00:00.000000

Elimina la columna `mesocycle` de `anthropometric_records`. El campo nunca llegó
a usarse en práctica; su rol descriptivo lo cubre la envergadura (`arm_span_cm`),
que ya existe y aporta valor morfológico real.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("anthropometric_records", "mesocycle")


def downgrade() -> None:
    op.add_column(
        "anthropometric_records",
        sa.Column("mesocycle", sa.SmallInteger(), nullable=True),
    )
