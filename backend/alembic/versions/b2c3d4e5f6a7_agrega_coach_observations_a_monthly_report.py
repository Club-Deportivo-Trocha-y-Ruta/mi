"""agrega coach_observations a monthly_report

Revision ID: b2c3d4e5f6a7
Revises: 6e189a7e1e51
Create Date: 2026-05-06 15:00:00.000000

Agrega columna coach_observations (TEXT, nullable) a la tabla monthly_reports.
Permite al entrenador incluir observaciones de texto libre en el reporte mensual.
Estas observaciones se redactan de nombres reales antes de pasar al prompt de IA.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "6e189a7e1e51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monthly_reports",
        sa.Column("coach_observations", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monthly_reports", "coach_observations")
