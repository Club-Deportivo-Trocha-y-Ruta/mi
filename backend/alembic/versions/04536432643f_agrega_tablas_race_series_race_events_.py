"""agrega tablas race_series, race_events, race_points_schemes, race_results

Revision ID: 04536432643f
Revises: 0c28a22dc064
Create Date: 2026-05-15 13:19:11.116206

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "04536432643f"
down_revision: Union[str, None] = "0c28a22dc064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_points_schemes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("position_points", sa.JSON(), nullable=False),
        sa.Column("attendance_points", sa.SmallInteger(), nullable=False),
        sa.Column("dnf_points", sa.SmallInteger(), nullable=False),
        sa.Column("dsq_points", sa.SmallInteger(), nullable=False),
        sa.Column("dns_points", sa.SmallInteger(), nullable=False),
        sa.Column("is_official", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "attendance_points >= 0", name="ck_race_points_attendance_nonneg"
        ),
        sa.CheckConstraint("dnf_points >= 0", name="ck_race_points_dnf_nonneg"),
        sa.CheckConstraint("dns_points >= 0", name="ck_race_points_dns_nonneg"),
        sa.CheckConstraint("dsq_points >= 0", name="ck_race_points_dsq_nonneg"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_race_points_schemes_code"),
    )
    op.create_table(
        "race_series",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("organizer", sa.String(length=150), nullable=True),
        sa.Column("points_scheme_code", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "season_year", name="uq_race_series_name_year"),
    )
    op.create_index(
        "ix_race_series_season_year", "race_series", ["season_year"], unique=False
    )
    op.create_table(
        "race_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("location", sa.String(length=150), nullable=True),
        sa.Column("is_championship", sa.Boolean(), nullable=False),
        sa.Column("calendar_event_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled", "completed", "cancelled", name="raceeventstatus"
            ),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["calendar_event_id"],
            ["calendar_events.id"],
            name="fk_race_events_calendar_event_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_race_events_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["race_series.id"],
            name="fk_race_events_series_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_id", "sequence_number", name="uq_race_events_series_sequence"
        ),
    )
    op.create_index(
        "ix_race_events_event_date", "race_events", ["event_date"], unique=False
    )
    op.create_table(
        "race_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("competitor_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=True),
        sa.Column("bib_number", sa.SmallInteger(), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("finished", "dnf", "dns", "dsq", name="raceresultstatus"),
            nullable=False,
        ),
        sa.Column("race_time_ms", sa.Integer(), nullable=True),
        sa.Column("laps_behind", sa.SmallInteger(), nullable=True),
        sa.Column("points_awarded", sa.SmallInteger(), nullable=False),
        sa.Column("imported_from_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=300), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(status = 'finished' AND race_time_ms IS NOT NULL) "
            "OR (status != 'finished' AND race_time_ms IS NULL) "
            "OR (status = 'finished' AND laps_behind IS NOT NULL)",
            name="ck_race_results_time_consistent_with_status",
        ),
        sa.CheckConstraint(
            "laps_behind IS NULL OR laps_behind >= 1",
            name="ck_race_results_laps_behind_positive",
        ),
        sa.CheckConstraint(
            "points_awarded >= 0", name="ck_race_results_points_nonneg"
        ),
        sa.CheckConstraint(
            "position IS NULL OR position >= 1",
            name="ck_race_results_position_positive",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_race_results_athlete_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["race_categories.id"],
            name="fk_race_results_category_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["race_competitors.id"],
            name="fk_race_results_competitor_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_race_results_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["race_events.id"],
            name="fk_race_results_event_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "category_id",
            "competitor_id",
            name="uq_race_results_event_category_competitor",
        ),
    )
    op.create_index(
        "ix_race_results_athlete_event",
        "race_results",
        ["athlete_id", "event_id"],
        unique=False,
    )
    op.create_index(
        "ix_race_results_category_event",
        "race_results",
        ["category_id", "event_id"],
        unique=False,
    )
    op.create_index(
        "ix_race_results_deleted_at",
        "race_results",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_race_results_event_category_position",
        "race_results",
        ["event_id", "category_id", "position"],
        unique=False,
    )


def downgrade() -> None:
    # Orden inverso a la creación; drop_table dropea índices y FKs en cascada.
    op.drop_table("race_results")
    op.drop_table("race_events")
    op.drop_table("race_series")
    op.drop_table("race_points_schemes")
