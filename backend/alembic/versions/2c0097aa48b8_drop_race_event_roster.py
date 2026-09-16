"""drop_race_event_roster: retire the call-up roster feature

Revision ID: 2c0097aa48b8
Revises: 5ba077132b3b
Create Date: 2026-09-16 00:00:00.000000

Removes `race_event_roster` (created by `e5f6a7b8c9d0`). The roster's only
downstream consumer — the parent visibility gate on the course-profile
endpoint (feature 043) — is simplified to depend solely on `RaceResult` in
the same change; the reconciliation banner was purely informational with no
other consumer. Historical `audit_log` rows with entity_type
`race_event_roster` are untouched (that column is a plain VARCHAR, not an
enum type) and simply stop matching a live Python enum member.

Not reversible with data: downgrade recreates the empty table shape but any
call-up rows that existed are gone.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2c0097aa48b8"
down_revision: Union[str, Sequence[str], None] = "5ba077132b3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_race_event_roster_race_event_id",
        table_name="race_event_roster",
    )
    op.drop_table("race_event_roster")

    # MySQL enums are inline column types — dropping the table removes it.
    # Only PostgreSQL keeps a standalone enum type to clean up.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS raceeventrosterstatus")


def downgrade() -> None:
    op.create_table(
        "race_event_roster",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("race_event_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "called_up",
                "confirmed",
                "withdrawn",
                name="raceeventrosterstatus",
            ),
            nullable=False,
            server_default="called_up",
        ),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["race_event_id"],
            ["race_events.id"],
            name="fk_race_event_roster_race_event_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_race_event_roster_athlete_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_race_event_roster_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "race_event_id",
            "athlete_id",
            name="uq_race_event_roster_event_athlete",
        ),
    )
    op.create_index(
        "ix_race_event_roster_race_event_id",
        "race_event_roster",
        ["race_event_id"],
        unique=False,
    )
