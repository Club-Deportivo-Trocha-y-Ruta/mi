"""agrega tablas race_categories y race_competitors

Revision ID: 0c28a22dc064
Revises: a2b3c4d5e6f7
Create Date: 2026-05-15 13:07:55.255460

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c28a22dc064"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column(
            "sex",
            sa.Enum("M", "F", "MIXED", name="racecategorysex"),
            nullable=False,
        ),
        sa.Column("age_min", sa.SmallInteger(), nullable=True),
        sa.Column("age_max", sa.SmallInteger(), nullable=True),
        sa.Column("birth_year_min", sa.SmallInteger(), nullable=True),
        sa.Column("birth_year_max", sa.SmallInteger(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_race_categories_code"),
    )
    op.create_table(
        "race_competitors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("club_text", sa.String(length=150), nullable=True),
        sa.Column(
            "sex",
            sa.Enum("M", "F", name="racecompetitorsex"),
            nullable=True,
        ),
        sa.Column("athlete_id", sa.Integer(), nullable=True),
        sa.Column("linked_at", sa.DateTime(), nullable=True),
        sa.Column("linked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_race_competitors_athlete_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by_user_id"],
            ["users.id"],
            name="fk_race_competitors_linked_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", name="uq_race_competitors_normalized_name"),
    )
    op.create_index(
        "ix_race_competitors_athlete_id",
        "race_competitors",
        ["athlete_id"],
        unique=False,
    )
    op.create_index(
        "ix_race_competitors_club_text",
        "race_competitors",
        ["club_text"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("race_competitors")
    op.drop_table("race_categories")
