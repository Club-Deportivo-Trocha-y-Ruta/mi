"""strength training exercise library (feature 021)

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-02 00:00:00.000000

Creates all tables for the Strength Training Exercise Library module:
  strength_exercises, strength_exercise_age_bands, strength_blocks,
  strength_block_entries, strength_session_blocks, strength_progress_notes

`AgeBand` is reused from technique_exercises (enum name "ageband", already
created by migration e1f2a3b4c5d6) — no new age-band enum type is created
here.

Seeds the catalog from app/data/strength_catalog.py (~22 exercises) at the
end of upgrade(). Seed is IDEMPOTENT: if any row exists in
strength_exercises the data block is skipped entirely (guard SELECT …
LIMIT 1). All seeded rows carry is_seeded = True.

Downgrade drops all tables in FK-safe reverse order and removes the new
named ENUM types on MySQL/MariaDB.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Enum value lists — mirror the Python enum .value strings exactly
# ---------------------------------------------------------------------------
_AGE_BAND_VALUES = ["7-9", "10-12", "13-15"]
_EQUIPMENT_KIND_VALUES = ["sin_equipo", "equipo_gym"]
_MOVEMENT_CATEGORY_VALUES = [
    "empuje_superior",
    "traccion_superior",
    "inferior_bilateral",
    "inferior_unilateral",
    "core_estabilidad",
]
_PROGRESS_VALUES = ["introducido", "en_progreso", "dominado"]


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. strength_exercises
    # -----------------------------------------------------------------------
    op.create_table(
        "strength_exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("how_to", sa.Text(), nullable=False),
        sa.Column("common_errors", sa.Text(), nullable=False),
        sa.Column("illustration_ascii", sa.Text(), nullable=False),
        sa.Column("illustration_alt", sa.String(length=500), nullable=False),
        sa.Column(
            "equipment",
            sa.Enum(*_EQUIPMENT_KIND_VALUES, name="equipmentkind"),
            nullable=False,
        ),
        sa.Column("equipment_detail", sa.String(length=200), nullable=True),
        sa.Column(
            "movement_category",
            sa.Enum(*_MOVEMENT_CATEGORY_VALUES, name="movementcategory"),
            nullable=False,
        ),
        sa.Column("suggested_duration_min", sa.SmallInteger(), nullable=False),
        sa.Column("suggested_reps", sa.String(length=60), nullable=False),
        sa.Column(
            "is_seeded", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_strength_exercises_slug"),
    )
    op.create_index(
        "idx_strength_exercise_visibility",
        "strength_exercises",
        ["is_hidden", "equipment"],
    )
    op.create_index(
        "ix_strength_exercises_equipment",
        "strength_exercises",
        ["equipment"],
    )

    # -----------------------------------------------------------------------
    # 2. strength_exercise_age_bands
    # -----------------------------------------------------------------------
    op.create_table(
        "strength_exercise_age_bands",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["strength_exercises.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("exercise_id", "age_band"),
        sa.UniqueConstraint(
            "exercise_id", "age_band", name="uq_strength_exercise_age_band"
        ),
    )

    # -----------------------------------------------------------------------
    # 3. strength_blocks
    # -----------------------------------------------------------------------
    op.create_table(
        "strength_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "target_age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.Column(
            "duration_target_min",
            sa.SmallInteger(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -----------------------------------------------------------------------
    # 4. strength_block_entries
    # -----------------------------------------------------------------------
    op.create_table(
        "strength_block_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("duration_min", sa.SmallInteger(), nullable=False),
        sa.Column("reps", sa.String(length=60), nullable=True),
        sa.Column(
            "is_age_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("override_note", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(
            ["block_id"], ["strength_blocks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["strength_exercises.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "block_id", "position", name="uq_strength_block_entry_position"
        ),
    )
    op.create_index(
        "idx_sbe_block", "strength_block_entries", ["block_id"]
    )

    # -----------------------------------------------------------------------
    # 5. strength_session_blocks
    # -----------------------------------------------------------------------
    op.create_table(
        "strength_session_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("training_session_id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.Column(
            "position", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column("attached_by_user_id", sa.Integer(), nullable=False),
        sa.Column("attached_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["training_session_id"],
            ["training_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["block_id"], ["strength_blocks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["attached_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "training_session_id", "block_id", name="uq_strength_session_block"
        ),
    )
    op.create_index(
        "idx_ssb_session", "strength_session_blocks", ["training_session_id"]
    )

    # -----------------------------------------------------------------------
    # 6. strength_progress_notes
    # -----------------------------------------------------------------------
    op.create_table(
        "strength_progress_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*_PROGRESS_VALUES, name="strengthprogressstatus"),
            nullable=False,
        ),
        sa.Column("coach_note", sa.String(length=500), nullable=True),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["strength_exercises.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_spn_athlete_exercise_time",
        "strength_progress_notes",
        ["athlete_id", "exercise_id", "recorded_at"],
    )

    # -----------------------------------------------------------------------
    # DATA SEED (research.md D1/D7) — idempotent: skip if exercises exist
    # -----------------------------------------------------------------------
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT 1 FROM strength_exercises LIMIT 1")
    ).fetchone()
    if row is not None:
        # Catalog already seeded (e.g. a previous migration run or test fixture).
        return

    # Import the pure-data module — no DB imports, no side-effects.
    from app.data.strength_catalog import EXERCISES  # noqa: PLC0415

    dialect = bind.dialect.name  # "mysql" | "mariadb" | "sqlite"

    # ------------------------------------------------------------------
    # Helper: NOW() expression that works across dialects
    # ------------------------------------------------------------------
    def _now_expr() -> str:
        return "NOW()" if dialect in ("mysql", "mariadb") else "datetime('now')"

    now_sql = _now_expr()

    # ------------------------------------------------------------------
    # Seed strength_exercises + age-band join rows
    # ------------------------------------------------------------------
    for ex in EXERCISES:
        # Insert the exercise row
        bind.execute(
            sa.text(
                "INSERT INTO strength_exercises "
                "  (slug, name, summary, how_to, common_errors, illustration_ascii, "
                "   illustration_alt, equipment, equipment_detail, movement_category, "
                "   suggested_duration_min, suggested_reps, is_seeded, is_hidden, "
                "   club_id, created_by_user_id, created_at, updated_at) "
                "VALUES "
                "  (:slug, :name, :summary, :how_to, :common_errors, :illustration_ascii, "
                "   :illustration_alt, :equipment, :equipment_detail, :movement_category, "
                "   :suggested_duration_min, :suggested_reps, 1, 0, "
                f"   NULL, NULL, {now_sql}, {now_sql})"
            ).bindparams(
                slug=ex["slug"],
                name=ex["name"],
                summary=ex["summary"],
                how_to=ex["how_to"],
                common_errors=ex["common_errors"],
                illustration_ascii=ex["illustration_ascii"],
                illustration_alt=ex["illustration_alt"],
                equipment=ex["equipment"],
                equipment_detail=ex["equipment_detail"],
                movement_category=ex["movement_category"],
                suggested_duration_min=ex["suggested_duration_min"],
                suggested_reps=ex["suggested_reps"],
            )
        )

        # Retrieve the new exercise id
        if dialect in ("mysql", "mariadb"):
            ex_id: int = bind.execute(
                sa.text("SELECT LAST_INSERT_ID()")
            ).scalar()
        else:
            ex_id = bind.execute(
                sa.text("SELECT last_insert_rowid()")
            ).scalar()

        # Age-band join rows
        for band in ex["age_bands"]:
            bind.execute(
                sa.text(
                    "INSERT INTO strength_exercise_age_bands (exercise_id, age_band) "
                    "VALUES (:exercise_id, :age_band)"
                ).bindparams(exercise_id=ex_id, age_band=band)
            )


def downgrade() -> None:
    # Drop in reverse FK-dependency order. Note: indexes that back an FK
    # constraint (e.g. idx_spn_athlete_exercise_time, idx_ssb_session,
    # idx_sbe_block) are NOT dropped explicitly here — MySQL/MariaDB refuse
    # to drop such an index while the FK still references it ("needed in a
    # foreign key constraint"), and DROP TABLE removes the index for free.
    op.drop_table("strength_progress_notes")

    op.drop_table("strength_session_blocks")

    op.drop_table("strength_block_entries")

    op.drop_table("strength_blocks")

    op.drop_table("strength_exercise_age_bands")

    op.drop_index(
        "ix_strength_exercises_equipment", table_name="strength_exercises"
    )
    op.drop_index(
        "idx_strength_exercise_visibility", table_name="strength_exercises"
    )
    op.drop_table("strength_exercises")

    # Drop named ENUM types added by this migration (MySQL/MariaDB only;
    # SQLite has no native ENUM). Note: "ageband" is reused from migration
    # e1f2a3b4c5d6 and must NOT be dropped here — it is owned by that
    # migration's downgrade.
    bind = op.get_bind()
    if bind.dialect.name not in ("sqlite",):
        for enum_name in (
            "equipmentkind",
            "movementcategory",
            "strengthprogressstatus",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
