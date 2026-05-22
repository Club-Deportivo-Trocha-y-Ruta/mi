"""add race_competitor_link_audit

Revision ID: 6e01932b21fb
Revises: f9a0b1c2d3e4
Create Date: 2026-05-22 12:00:00.000000

R3-M1: persistir audit trail completo de link/unlink de competitors.

Antes de esta migración el audit de quién enlazó un competitor vivía sólo en
las columnas ``race_competitors.linked_by_user_id`` + ``linked_at`` y se
perdía cuando el coach hacía ``unlink`` (ambos campos vuelven a NULL). Esta
tabla persiste cada transición link/unlink con su actor + IDs + timestamp.

Append-only por diseño: el servicio NUNCA hace UPDATE ni DELETE sobre filas
de esta tabla (sólo INSERT). FKs configuradas para que el audit sobreviva
hard-deletes de athletes (SET NULL) y bloquee borrado accidental de
competitors/usuarios (RESTRICT).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6e01932b21fb"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_competitor_link_audit",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("competitor_id", sa.Integer(), nullable=False),
        sa.Column(
            "action",
            sa.Enum("link", "unlink", "relink", name="link_audit_action"),
            nullable=False,
        ),
        sa.Column("previous_athlete_id", sa.Integer(), nullable=True),
        sa.Column("new_athlete_id", sa.Integer(), nullable=True),
        sa.Column(
            "results_propagated",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["competitor_id"], ["race_competitors.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["previous_athlete_id"], ["athletes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["new_athlete_id"], ["athletes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_link_audit_competitor_id",
        "race_competitor_link_audit",
        ["competitor_id"],
        unique=False,
    )
    op.create_index(
        "ix_link_audit_user_id",
        "race_competitor_link_audit",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_link_audit_created_at",
        "race_competitor_link_audit",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_link_audit_created_at", table_name="race_competitor_link_audit"
    )
    op.drop_index(
        "ix_link_audit_user_id", table_name="race_competitor_link_audit"
    )
    op.drop_index(
        "ix_link_audit_competitor_id", table_name="race_competitor_link_audit"
    )
    op.drop_table("race_competitor_link_audit")
    sa.Enum(name="link_audit_action").drop(op.get_bind(), checkfirst=True)
