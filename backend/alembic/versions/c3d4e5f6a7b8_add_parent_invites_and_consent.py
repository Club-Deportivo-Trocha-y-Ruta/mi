"""add_parent_invites_and_consent

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Crear tabla parent_invites
    # ------------------------------------------------------------------
    op.create_table(
        "parent_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("used_by", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_parent_invites_token"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_parent_invites_token", "parent_invites", ["token"])
    op.create_index("ix_parent_invites_athlete_id", "parent_invites", ["athlete_id"])

    # ------------------------------------------------------------------
    # 2. Agregar columnas de consentimiento parental a athletes
    # ------------------------------------------------------------------
    op.add_column(
        "athletes",
        sa.Column(
            "parental_consent_obtained",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "athletes",
        sa.Column("parental_consent_date", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Eliminar columnas de consentimiento parental de athletes
    # ------------------------------------------------------------------
    op.drop_column("athletes", "parental_consent_date")
    op.drop_column("athletes", "parental_consent_obtained")

    # ------------------------------------------------------------------
    # 2. Eliminar tabla parent_invites
    # ------------------------------------------------------------------
    op.drop_index("ix_parent_invites_athlete_id", table_name="parent_invites")
    op.drop_index("ix_parent_invites_token", table_name="parent_invites")
    op.drop_table("parent_invites")
