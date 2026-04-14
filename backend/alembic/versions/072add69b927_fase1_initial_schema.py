"""fase1_initial_schema

Revision ID: 072add69b927
Revises:
Create Date: 2026-04-14 10:40:23.463024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '072add69b927'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column(
            "role",
            sa.Enum("admin", "coach", "parent", "athlete", name="userrole"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("can_login", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_users_role", "users", ["role"])

    # --- clubs ---
    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # --- club_members ---
    op.create_table(
        "club_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role_in_club",
            sa.Enum("admin", "coach", "parent", "athlete", name="clubrole"),
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", "user_id"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_club_members_user_id", "club_members", ["user_id"])

    # --- athletes ---
    op.create_table(
        "athletes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("sex", sa.Enum("M", "F", name="sex"), nullable=False),
        sa.Column("years_in_club", sa.SmallInteger(), nullable=True),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_athletes_club_id", "athletes", ["club_id"])
    op.create_index("ix_athletes_created_by", "athletes", ["created_by"])

    # --- parent_athlete ---
    op.create_table(
        "parent_athlete",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column(
            "relationship",
            sa.Enum("padre", "madre", "acudiente", name="familyrelationship"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "athlete_id", name="uq_parent_athlete"),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
    )
    op.create_index("ix_parent_athlete_athlete_id", "parent_athlete", ["athlete_id"])

    # --- anthropometric_records ---
    op.create_table(
        "anthropometric_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_date", sa.Date(), nullable=False),
        sa.Column("mesocycle", sa.SmallInteger(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=False),
        sa.Column("standing_height_cm", sa.Numeric(5, 1), nullable=False),
        sa.Column("arm_span_cm", sa.Numeric(5, 1), nullable=True),
        sa.Column("sitting_height_cm", sa.Numeric(5, 1), nullable=False),
        sa.Column("leg_length_cm", sa.Numeric(5, 1), nullable=False),
        sa.Column("leg_sitting_ratio", sa.Numeric(6, 4), nullable=False),
        sa.Column("maturity_offset", sa.Numeric(5, 2), nullable=False),
        sa.Column("age_at_phv", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "maturation_status",
            sa.Enum("Pre-PHV", "Circa-PHV", "Post-PHV", name="maturationstatus"),
            nullable=False,
        ),
        sa.Column("training_implications", sa.Text(), nullable=True),
        sa.Column("evaluated_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"]),
        sa.ForeignKeyConstraint(["evaluated_by"], ["users.id"]),
    )
    op.create_index(
        "ix_anthro_athlete_date",
        "anthropometric_records",
        ["athlete_id", "evaluation_date"],
    )


def downgrade() -> None:
    op.drop_table("anthropometric_records")
    op.drop_table("parent_athlete")
    op.drop_table("athletes")
    op.drop_table("club_members")
    op.drop_table("clubs")
    op.drop_table("users")
