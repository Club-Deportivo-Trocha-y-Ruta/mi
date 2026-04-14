"""athletes: reemplaza years_in_club por club_join_date

Revision ID: 3a1f8c9d4e72
Revises: 072add69b927
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a1f8c9d4e72'
down_revision: Union[str, None] = '072add69b927'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("athletes", "years_in_club")
    op.add_column(
        "athletes",
        sa.Column("club_join_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("athletes", "club_join_date")
    op.add_column(
        "athletes",
        sa.Column("years_in_club", sa.SmallInteger(), nullable=True),
    )
