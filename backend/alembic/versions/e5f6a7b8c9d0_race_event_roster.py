"""race_event_roster: call-up table for competitions (feature 007-competitions-consolidation)

Revision ID: e5f6a7b8c9d0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-08 10:00:00.000000

Creates `race_event_roster` — the single net-new table for Wave C (US3 FR-022/023):

- ``race_event_roster`` table:
    id PK, race_event_id FK→race_events (CASCADE), athlete_id FK→athletes (RESTRICT),
    status enum `raceeventrosterstatus` (called_up|confirmed|withdrawn, default called_up),
    note String(300) nullable, created_by_user_id FK→users (RESTRICT),
    created_at, updated_at.
- UNIQUE(race_event_id, athlete_id).
- INDEX on race_event_id.

Enum strategy:
- MySQL: native ENUM type (``raceeventrosterstatus``).
- SQLite (tests): Enum rendered as VARCHAR + CHECK constraint by SQLAlchemy
  automatically — no dialect-switch needed for CREATE TABLE.
  DROP TABLE handles downgrade cleanly on both dialects.

No backfill. Fully reversible.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index(
        "ix_race_event_roster_race_event_id",
        table_name="race_event_roster",
    )
    op.drop_table("race_event_roster")

    # Drop the MySQL native enum type if present (no-op on SQLite).
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute("DROP TYPE IF EXISTS raceeventrosterstatus")
