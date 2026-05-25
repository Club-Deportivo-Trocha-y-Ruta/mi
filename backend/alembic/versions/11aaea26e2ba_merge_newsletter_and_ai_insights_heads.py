"""merge newsletter and ai-insights heads

Revision ID: 11aaea26e2ba
Revises: 8c1d2e3f4a5b, a1b2c3d4e5f7
Create Date: 2026-05-25 14:42:30.655506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11aaea26e2ba'
down_revision: Union[str, None] = ('8c1d2e3f4a5b', 'a1b2c3d4e5f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
