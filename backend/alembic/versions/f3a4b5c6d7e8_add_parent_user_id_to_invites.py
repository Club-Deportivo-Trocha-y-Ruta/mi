"""add_parent_user_id_to_invites

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-05-06 14:30:00.000000

Agrega columna parent_user_id a parent_invites para enlazar la invitación con
un usuario padre pre-creado por el coach. Cuando está presente, consume_invite
hace UPDATE del usuario existente en lugar de INSERT, evitando duplicados.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parent_invites",
        sa.Column("parent_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_parent_invites_parent_user_id_users",
        "parent_invites",
        "users",
        ["parent_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_parent_invites_parent_user_id",
        "parent_invites",
        ["parent_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_parent_invites_parent_user_id", table_name="parent_invites")
    op.drop_constraint(
        "fk_parent_invites_parent_user_id_users",
        "parent_invites",
        type_="foreignkey",
    )
    op.drop_column("parent_invites", "parent_user_id")
