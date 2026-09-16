"""race course profile: variants, category setups, race_events terrain fields (feature 043)

Revision ID: 5ba077132b3b
Revises: d5b125474e2b
Create Date: 2026-09-15 00:00:00.000000

Creates the two net-new tables backing the optional per-válida course
profile (feature 043 — `specs/043-race-course-profile/`), and extends
`race_events` with the terrain/difficulty/sector/notes columns used by the
reconnaissance card and the race analyst's `course_block`.

1. ``race_course_variants`` — one row per GPX-derived route variant of a
   válida. Geometry is a single lap (position + elevation only); the raw
   upload and any recording timestamp are never persisted (FR-003). Mirrors
   ``app/models/race_course_variant.py`` (``RaceCourseVariant``).

   - FKs: race_event_id → race_events.id (CASCADE), created_by_user_id →
     users.id (RESTRICT), updated_by_user_id → users.id (SET NULL, from
     ``ActorTimestampMixin``).
   - UNIQUE(race_event_id, label); INDEX on race_event_id.

2. ``race_course_category_setups`` — one row per (válida, categoría): laps
   run and which variant they run on. Mirrors
   ``app/models/race_course_category_setup.py`` (``RaceCourseCategorySetup``).

   - FKs: race_event_id → race_events.id (CASCADE), category_id →
     race_categories.id (RESTRICT), variant_id → race_course_variants.id
     (RESTRICT), updated_by_user_id → users.id (SET NULL).
   - UNIQUE(race_event_id, category_id); CHECK laps BETWEEN 1 AND 20.

3. ``race_events``: adds ``terrain_type`` (new enum ``terraintype``),
   ``technical_difficulty``, ``key_sectors`` (JSON), ``course_notes``
   (Text) — all nullable, backward compatible — plus the
   ``ck_race_events_difficulty_range`` check constraint. Mirrors the
   "Perfil de circuito" block added to ``app/models/race_event.py``.

Enum strategy (same as `64c263edd07f`): MySQL gets a native ENUM
(``terraintype``); SQLite (tests) renders it as VARCHAR — no dialect
switch needed for CREATE TABLE / ADD COLUMN. Downgrade explicitly drops the
MySQL enum type after the batch block, guarded to skip SQLite.

No backfill. Fully reversible.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5ba077132b3b"
down_revision: Union[str, None] = "d5b125474e2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- 1. race_course_variants ------------------------------------------
    op.create_table(
        "race_course_variants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("race_event_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("lap_distance_m", sa.Integer(), nullable=False),
        sa.Column("elevation_gain_m", sa.SmallInteger(), nullable=True),
        sa.Column(
            "has_elevation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("point_count", sa.SmallInteger(), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("detection_method", sa.String(length=16), nullable=False),
        sa.Column(
            "recorded_laps",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["race_event_id"],
            ["race_events.id"],
            name="fk_race_course_variants_race_event_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_race_course_variants_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_race_course_variants_updated_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "race_event_id",
            "label",
            name="uq_race_course_variants_event_label",
        ),
    )
    op.create_index(
        "ix_race_course_variants_event",
        "race_course_variants",
        ["race_event_id"],
        unique=False,
    )

    # ---- 2. race_course_category_setups ------------------------------------
    op.create_table(
        "race_course_category_setups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("race_event_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("laps", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["race_event_id"],
            ["race_events.id"],
            name="fk_race_course_category_setups_race_event_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["race_categories.id"],
            name="fk_race_course_category_setups_category_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["race_course_variants.id"],
            name="fk_race_course_category_setups_variant_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_race_course_category_setups_updated_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "race_event_id",
            "category_id",
            name="uq_race_course_setups_event_category",
        ),
        sa.CheckConstraint(
            "laps BETWEEN 1 AND 20", name="ck_race_course_setups_laps_range"
        ),
    )

    # ---- 3. race_events: perfil de circuito --------------------------------
    with op.batch_alter_table("race_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "terrain_type",
                sa.Enum(
                    "sendero",
                    "trocha",
                    "mixto",
                    "pista",
                    "pavimento",
                    name="terraintype",
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("technical_difficulty", sa.SmallInteger(), nullable=True)
        )
        batch_op.add_column(sa.Column("key_sectors", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("course_notes", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "ck_race_events_difficulty_range",
            "technical_difficulty IS NULL OR technical_difficulty BETWEEN 1 AND 5",
        )


def downgrade() -> None:
    # ---- 3'. race_events: revierte perfil de circuito ----------------------
    with op.batch_alter_table("race_events") as batch_op:
        batch_op.drop_constraint("ck_race_events_difficulty_range", type_="check")
        batch_op.drop_column("course_notes")
        batch_op.drop_column("key_sectors")
        batch_op.drop_column("technical_difficulty")
        batch_op.drop_column("terrain_type")
    if op.get_bind().dialect.name != "sqlite":
        sa.Enum(name="terraintype").drop(op.get_bind(), checkfirst=True)

    # ---- 2'. drop race_course_category_setups ------------------------------
    op.drop_table("race_course_category_setups")

    # ---- 1'. drop race_course_variants --------------------------------------
    op.drop_index("ix_race_course_variants_event", table_name="race_course_variants")
    op.drop_table("race_course_variants")
