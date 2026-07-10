"""structured interval training with strava correlation (feature 026)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-10 00:00:00.000000

Creates all six tables for the Structured Interval Training module:
  interval_structures, interval_structure_blocks,
  interval_templates, interval_template_blocks,
  strava_activity_laps, interval_match_results

Enum `ageband` is REUSED from technique_exercises (enum name "ageband",
already created by migration e1f2a3b4c5d6) — no new age-band enum type is
created here, and it must NOT be dropped in downgrade() (owned by that
migration). Same rule feature 021 (a7b8c9d0e1f2) followed.

New named ENUM types created by this migration: `intervalblocktype`,
`hrzone`, `matchtrigger`. Their value lists mirror the Python enum `.value`
strings exactly (the models use `values_callable`), so the DB stores the
value strings.

PRIVACY / non-negotiables (Ley 1581, minors): the laps table intentionally
has NO geo/map columns, no free lap `name`, no `average_cadence`, and NO
power column anywhere in the module (FR-005, D2). Do not add them.

Downgrade drops all tables in FK-safe reverse order and removes the three
new named ENUM types on MySQL/MariaDB (never `ageband`).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------
revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Enum value lists — mirror the Python enum .value strings exactly
# ---------------------------------------------------------------------------
_AGE_BAND_VALUES = ["7-9", "10-12", "13-15"]  # reused enum "ageband"
_INTERVAL_BLOCK_TYPE_VALUES = ["warmup", "work", "recovery", "cooldown"]
_HR_ZONE_VALUES = ["Z1", "Z2", "Z3", "Z4", "Z5"]
_MATCH_TRIGGER_VALUES = ["link", "structure_change", "manual"]


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. interval_structures — coach-authored plan, 1:1 with a session
    # -----------------------------------------------------------------------
    op.create_table(
        "interval_structures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("training_session_id", sa.Integer(), nullable=False),
        sa.Column(
            "target_age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.Column(
            "age_gate_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("age_gate_confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("age_gate_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["training_session_id"],
            ["training_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["age_gate_confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "training_session_id", name="uq_interval_structure_session"
        ),
    )

    # -----------------------------------------------------------------------
    # 2. interval_structure_blocks — ordered steps of a structure
    # -----------------------------------------------------------------------
    op.create_table(
        "interval_structure_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("structure_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "block_type",
            sa.Enum(*_INTERVAL_BLOCK_TYPE_VALUES, name="intervalblocktype"),
            nullable=False,
        ),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column(
            "target_zone",
            sa.Enum(*_HR_ZONE_VALUES, name="hrzone"),
            nullable=False,
        ),
        sa.Column("target_cadence_rpm", sa.Integer(), nullable=False),
        sa.Column("repeat_group", sa.Integer(), nullable=True),
        sa.Column("repeat_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["structure_id"], ["interval_structures.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "structure_id",
            "position",
            name="uq_interval_structure_block_position",
        ),
    )

    # -----------------------------------------------------------------------
    # 3. interval_templates — reusable, session-independent structure
    # -----------------------------------------------------------------------
    op.create_table(
        "interval_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "target_age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.Column("mesocycle_phase", sa.String(length=50), nullable=False),
        sa.Column("competition_proximity", sa.String(length=50), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -----------------------------------------------------------------------
    # 4. interval_template_blocks — steps of a template (same set as §2)
    # -----------------------------------------------------------------------
    op.create_table(
        "interval_template_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "block_type",
            sa.Enum(*_INTERVAL_BLOCK_TYPE_VALUES, name="intervalblocktype"),
            nullable=False,
        ),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column(
            "target_zone",
            sa.Enum(*_HR_ZONE_VALUES, name="hrzone"),
            nullable=False,
        ),
        sa.Column("target_cadence_rpm", sa.Integer(), nullable=False),
        sa.Column("repeat_group", sa.Integer(), nullable=True),
        sa.Column("repeat_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["template_id"], ["interval_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "position",
            name="uq_interval_template_block_position",
        ),
    )

    # -----------------------------------------------------------------------
    # 5. strava_activity_laps — persisted laps of a synced activity
    #    NO geo/map/name/cadence/power columns (Ley 1581 + scope, D4).
    # -----------------------------------------------------------------------
    op.create_table(
        "strava_activity_laps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strava_activity_id", sa.Integer(), nullable=False),
        sa.Column("lap_index", sa.Integer(), nullable=False),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=False),
        sa.Column("moving_time_s", sa.Integer(), nullable=True),
        sa.Column("average_heartrate", sa.Float(), nullable=True),
        sa.Column("average_speed_m_s", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["strava_activity_id"],
            ["strava_activities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "strava_activity_id",
            "lap_index",
            name="uq_strava_activity_laps_activity_index",
        ),
    )

    # -----------------------------------------------------------------------
    # 6. interval_match_results — plan-vs-actual comparison (derived artifact)
    # -----------------------------------------------------------------------
    op.create_table(
        "interval_match_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("structure_id", sa.Integer(), nullable=False),
        sa.Column("strava_activity_id", sa.Integer(), nullable=False),
        sa.Column(
            "engine_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column(
            "triggered_by",
            sa.Enum(*_MATCH_TRIGGER_VALUES, name="matchtrigger"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["structure_id"], ["interval_structures.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["strava_activity_id"],
            ["strava_activities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "structure_id",
            "strava_activity_id",
            name="uq_interval_match_results_structure_activity",
        ),
    )


def downgrade() -> None:
    # Drop in reverse FK-dependency order. DROP TABLE removes any backing
    # index for free (MySQL/MariaDB refuse to drop an FK-backing index while
    # the FK still references it).
    op.drop_table("interval_match_results")
    op.drop_table("strava_activity_laps")
    op.drop_table("interval_template_blocks")
    op.drop_table("interval_templates")
    op.drop_table("interval_structure_blocks")
    op.drop_table("interval_structures")

    # Drop named ENUM types added by this migration (MySQL/MariaDB only;
    # SQLite has no native ENUM). "ageband" is REUSED from migration
    # e1f2a3b4c5d6 and must NOT be dropped here — it is owned by that
    # migration's downgrade.
    bind = op.get_bind()
    if bind.dialect.name not in ("sqlite",):
        for enum_name in (
            "intervalblocktype",
            "hrzone",
            "matchtrigger",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
