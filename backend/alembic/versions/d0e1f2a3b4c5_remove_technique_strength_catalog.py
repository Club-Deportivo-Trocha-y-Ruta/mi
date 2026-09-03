"""remove technique & strength catalog (retired feature)

Revision ID: d0e1f2a3b4c5
Revises: 6b998c214e5a
Create Date: 2026-09-03 00:00:00.000000

Retires the Technique & Gymkhana Library (feature 018/019) and the Strength
Training Exercise Library (feature 021): the whole coach-facing catalog —
skills, materials, exercises, session builder attach links and per-athlete
progress tracking — was cut from the product. Race AI v3 no longer cites
these resources (only interval templates remain in ``catalog_ref``).

Drops, in FK-safe order:
  Technique: athlete_skill_progress, technique_session_exercises,
    technique_exercise_materials, technique_exercise_skills,
    technique_exercise_age_bands, technique_exercises, technique_materials,
    technique_skills
  Strength: strength_progress_notes, strength_session_blocks,
    strength_block_entries, strength_blocks, strength_exercise_age_bands,
    strength_exercises

Also drops the named ENUM types owned exclusively by these tables
(``exercisedifficulty``, ``sessionsegment``, ``skillprogressstatus``,
``equipmentkind``, ``movementcategory``, ``strengthprogressstatus``) on
MySQL/MariaDB. ``ageband`` is NOT dropped — ``interval_structures`` /
``interval_templates`` (feature 026) still use it for
``target_age_band``.

Downgrade recreates the empty schema (tables, indexes, enums) — seed data is
NOT restored (the catalog content lived in ``app/data/technique_catalog.py``
/ ``app/data/strength_catalog.py``, both removed alongside this migration).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "6b998c214e5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Enum value lists — mirror the Python enum .value strings exactly
# (kept here only so downgrade() can recreate the columns faithfully)
# ---------------------------------------------------------------------------
_AGE_BAND_VALUES = ["7-9", "10-12", "13-15"]
_DIFFICULTY_VALUES = ["facil", "media", "avanzada"]
_SEGMENT_VALUES = ["calentamiento", "principal", "vuelta_calma"]
_SKILL_PROGRESS_VALUES = ["introducido", "en_progreso", "dominado"]
_EQUIPMENT_KIND_VALUES = ["sin_equipo", "equipo_gym"]
_MOVEMENT_CATEGORY_VALUES = [
    "empuje_superior",
    "traccion_superior",
    "inferior_bilateral",
    "inferior_unilateral",
    "core_estabilidad",
]
_STRENGTH_PROGRESS_VALUES = ["introducido", "en_progreso", "dominado"]


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Technique & Gymkhana Library (feature 018/019) — children first.
    # -----------------------------------------------------------------------
    op.drop_table("athlete_skill_progress")
    op.drop_table("technique_session_exercises")
    op.drop_table("technique_exercise_materials")
    op.drop_table("technique_exercise_skills")
    op.drop_table("technique_exercise_age_bands")
    op.drop_table("technique_exercises")
    op.drop_table("technique_materials")
    op.drop_table("technique_skills")

    # -----------------------------------------------------------------------
    # Strength Training Exercise Library (feature 021) — children first.
    # -----------------------------------------------------------------------
    op.drop_table("strength_progress_notes")
    op.drop_table("strength_session_blocks")
    op.drop_table("strength_block_entries")
    op.drop_table("strength_blocks")
    op.drop_table("strength_exercise_age_bands")
    op.drop_table("strength_exercises")

    # -----------------------------------------------------------------------
    # Drop named ENUM types owned exclusively by the retired tables
    # (MySQL/MariaDB only; SQLite has no native ENUM). ``ageband`` is
    # intentionally excluded — feature 026 (interval_structures /
    # interval_templates) still owns it.
    # -----------------------------------------------------------------------
    bind = op.get_bind()
    if bind.dialect.name not in ("sqlite",):
        for enum_name in (
            "exercisedifficulty",
            "sessionsegment",
            "skillprogressstatus",
            "equipmentkind",
            "movementcategory",
            "strengthprogressstatus",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)


def downgrade() -> None:
    # -----------------------------------------------------------------------
    # Technique & Gymkhana Library (feature 018/019)
    # -----------------------------------------------------------------------
    op.create_table(
        "technique_skills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=1), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("focus", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_technique_skills_code"),
        sa.UniqueConstraint("slug", name="uq_technique_skills_slug"),
    )

    op.create_table(
        "technique_materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "is_none", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_technique_materials_slug"),
    )

    op.create_table(
        "technique_exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("how_to", sa.Text(), nullable=False),
        sa.Column(
            "difficulty",
            sa.Enum(*_DIFFICULTY_VALUES, name="exercisedifficulty"),
            nullable=False,
        ),
        sa.Column(
            "is_game", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_gymkhana", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("layout_ascii", sa.Text(), nullable=True),
        sa.Column("layout_alt", sa.Text(), nullable=True),
        sa.Column("layout_json", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.String(length=40), nullable=True),
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
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_technique_exercises_slug"),
    )
    op.create_index(
        "idx_technique_exercise_visibility",
        "technique_exercises",
        ["is_hidden", "difficulty"],
    )

    op.create_table(
        "technique_exercise_age_bands",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["technique_exercises.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("exercise_id", "age_band"),
        sa.UniqueConstraint(
            "exercise_id", "age_band", name="uq_technique_exercise_age_band"
        ),
    )

    op.create_table(
        "technique_exercise_skills",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["technique_exercises.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["technique_skills.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("exercise_id", "skill_id"),
    )

    op.create_table(
        "technique_exercise_materials",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["technique_exercises.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["technique_materials.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("exercise_id", "material_id"),
    )

    op.create_table(
        "technique_session_exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("training_session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum(*_SEGMENT_VALUES, name="sessionsegment"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["training_session_id"], ["training_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["technique_exercises.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_tse_session", "technique_session_exercises", ["training_session_id"]
    )

    op.create_table(
        "athlete_skill_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*_SKILL_PROGRESS_VALUES, name="skillprogressstatus"),
            nullable=False,
        ),
        sa.Column("coach_note", sa.String(length=300), nullable=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["technique_skills.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_asp_athlete_skill_time",
        "athlete_skill_progress",
        ["athlete_id", "skill_id", "recorded_at"],
    )

    # -----------------------------------------------------------------------
    # Strength Training Exercise Library (feature 021)
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
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="RESTRICT"),
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
        "ix_strength_exercises_equipment", "strength_exercises", ["equipment"]
    )

    op.create_table(
        "strength_exercise_age_bands",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["strength_exercises.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("exercise_id", "age_band"),
        sa.UniqueConstraint(
            "exercise_id", "age_band", name="uq_strength_exercise_age_band"
        ),
    )

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
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

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
    op.create_index("idx_sbe_block", "strength_block_entries", ["block_id"])

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
            ["training_session_id"], ["training_sessions.id"], ondelete="CASCADE"
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

    op.create_table(
        "strength_progress_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*_STRENGTH_PROGRESS_VALUES, name="strengthprogressstatus"),
            nullable=False,
        ),
        sa.Column("coach_note", sa.String(length=500), nullable=True),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
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
