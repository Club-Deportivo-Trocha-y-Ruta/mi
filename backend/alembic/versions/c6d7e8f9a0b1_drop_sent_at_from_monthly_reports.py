"""drop sent_at de monthly_reports

Revision ID: c6d7e8f9a0b1
Revises: a1b2c3d4e5fa
Create Date: 2026-06-02 10:00:00.000000

Elimina la columna sent_at de monthly_reports. El envío del reporte al club
por email fue reemplazado por la descarga directa del PDF, por lo que ya no
existe el concepto de "enviado el". La columna queda sin lectores ni escritores.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "a1b2c3d4e5fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("monthly_reports", "sent_at")


def downgrade() -> None:
    op.add_column(
        "monthly_reports",
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
