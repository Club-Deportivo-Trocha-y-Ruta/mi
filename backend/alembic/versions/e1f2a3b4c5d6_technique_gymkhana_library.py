"""technique & gymkhana library (feature 018)

Revision ID: e1f2a3b4c5d6
Revises: c2d3e4f5a6b7
Create Date: 2026-06-25 00:00:00.000000

Creates all tables for the Technique & Gymkhana Library module:
  technique_skills, technique_materials, technique_exercises,
  technique_exercise_age_bands, technique_exercise_skills,
  technique_exercise_materials, technique_session_exercises,
  athlete_skill_progress

Then seeds the catalog from app/data/technique_catalog.py (D3, research.md):
  - 8 skills  (A–H taxonomy)
  - 14 materials (including "sin material" sentinel)
  - 24 exercises with age-band / skill / material join rows

Seed is IDEMPOTENT: if any row exists in technique_exercises the data block
is skipped entirely (guard SELECT … LIMIT 1). All seeded rows carry
is_seeded = True.

Downgrade drops all tables in FK-safe order and removes the named ENUM types
on MySQL/MariaDB.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Enum value lists — mirror the Python enum .value strings exactly
# ---------------------------------------------------------------------------
_AGE_BAND_VALUES = ["7-9", "10-12", "13-15"]
_DIFFICULTY_VALUES = ["facil", "media", "avanzada"]
_SEGMENT_VALUES = ["calentamiento", "principal", "vuelta_calma"]
_PROGRESS_VALUES = ["introducido", "en_progreso", "dominado"]


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. technique_skills
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

    # -----------------------------------------------------------------------
    # 2. technique_materials
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # 3. technique_exercises
    # -----------------------------------------------------------------------
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
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], ondelete="RESTRICT"
        ),
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

    # -----------------------------------------------------------------------
    # 4. technique_exercise_age_bands
    # -----------------------------------------------------------------------
    op.create_table(
        "technique_exercise_age_bands",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "age_band",
            sa.Enum(*_AGE_BAND_VALUES, name="ageband"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["technique_exercises.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("exercise_id", "age_band"),
        sa.UniqueConstraint(
            "exercise_id", "age_band", name="uq_technique_exercise_age_band"
        ),
    )

    # -----------------------------------------------------------------------
    # 5. technique_exercise_skills  (M2M secondary)
    # -----------------------------------------------------------------------
    op.create_table(
        "technique_exercise_skills",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["technique_exercises.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["technique_skills.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("exercise_id", "skill_id"),
    )

    # -----------------------------------------------------------------------
    # 6. technique_exercise_materials  (M2M secondary)
    # -----------------------------------------------------------------------
    op.create_table(
        "technique_exercise_materials",
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["technique_exercises.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["technique_materials.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("exercise_id", "material_id"),
    )

    # -----------------------------------------------------------------------
    # 7. technique_session_exercises
    # -----------------------------------------------------------------------
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
            ["training_session_id"],
            ["training_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["technique_exercises.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_tse_session",
        "technique_session_exercises",
        ["training_session_id"],
    )

    # -----------------------------------------------------------------------
    # 8. athlete_skill_progress
    # -----------------------------------------------------------------------
    op.create_table(
        "athlete_skill_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*_PROGRESS_VALUES, name="skillprogressstatus"),
            nullable=False,
        ),
        sa.Column("coach_note", sa.String(length=300), nullable=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="CASCADE"
        ),
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
    # DATA SEED  (D3, research.md) — idempotent: skip if exercises exist
    # -----------------------------------------------------------------------
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT 1 FROM technique_exercises LIMIT 1")
    ).fetchone()
    if row is not None:
        # Catalog already seeded (e.g. a previous migration run or test fixture).
        return

    # Import the pure-data module — no DB imports, no side-effects.
    from app.data.technique_catalog import EXERCISES, MATERIALS, SKILLS  # noqa: PLC0415

    dialect = bind.dialect.name  # "mysql" | "mariadb" | "sqlite"

    # ------------------------------------------------------------------
    # Helper: NOW() expression that works across dialects
    # ------------------------------------------------------------------
    def _now_expr() -> str:
        return "NOW()" if dialect in ("mysql", "mariadb") else "datetime('now')"

    now_sql = _now_expr()

    # ------------------------------------------------------------------
    # 8a. Seed technique_skills
    # ------------------------------------------------------------------
    for skill in SKILLS:
        bind.execute(
            sa.text(
                "INSERT INTO technique_skills (code, name, focus, slug, sort_order) "
                "VALUES (:code, :name, :focus, :slug, :sort_order)"
            ).bindparams(
                code=skill["code"],
                name=skill["name"],
                focus=skill["focus"],
                slug=skill["slug"],
                sort_order=skill["sort_order"],
            )
        )

    # Build slug→id lookup for skills
    skill_rows = bind.execute(
        sa.text("SELECT id, slug FROM technique_skills")
    ).fetchall()
    skill_slug_to_id: dict[str, int] = {r[1]: r[0] for r in skill_rows}
    # Also build code→id for exercises that reference skills by code letter
    skill_code_to_id: dict[str, int] = {}
    for skill in SKILLS:
        sid = skill_slug_to_id[skill["slug"]]
        skill_code_to_id[skill["code"]] = sid

    # ------------------------------------------------------------------
    # 8b. Seed technique_materials
    # ------------------------------------------------------------------
    for mat in MATERIALS:
        bind.execute(
            sa.text(
                "INSERT INTO technique_materials (slug, name, is_none) "
                "VALUES (:slug, :name, :is_none)"
            ).bindparams(
                slug=mat["slug"],
                name=mat["name"],
                is_none=1 if mat["is_none"] else 0,
            )
        )

    # Build slug→id lookup for materials
    mat_rows = bind.execute(
        sa.text("SELECT id, slug FROM technique_materials")
    ).fetchall()
    mat_slug_to_id: dict[str, int] = {r[1]: r[0] for r in mat_rows}

    # ------------------------------------------------------------------
    # 8c. Seed technique_exercises + join rows
    # ------------------------------------------------------------------
    for ex in EXERCISES:
        # Insert the exercise row
        bind.execute(
            sa.text(
                "INSERT INTO technique_exercises "
                "  (slug, name, summary, how_to, difficulty, is_game, is_gymkhana, "
                "   layout_ascii, layout_alt, confidence, is_seeded, is_hidden, "
                "   club_id, created_by_user_id, created_at, updated_at) "
                f"VALUES "
                "  (:slug, :name, :summary, :how_to, :difficulty, :is_game, :is_gymkhana, "
                f"   :layout_ascii, :layout_alt, :confidence, 1, 0, "
                f"   NULL, NULL, {now_sql}, {now_sql})"
            ).bindparams(
                slug=ex["slug"],
                name=ex["name"],
                summary=ex["summary"],
                how_to=ex["how_to"],
                difficulty=ex["difficulty"],
                is_game=1 if ex["is_game"] else 0,
                is_gymkhana=1 if ex["is_gymkhana"] else 0,
                layout_ascii=ex["layout_ascii"],
                layout_alt=ex["layout_alt"],
                confidence=ex["confidence"],
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
                    "INSERT INTO technique_exercise_age_bands (exercise_id, age_band) "
                    "VALUES (:exercise_id, :age_band)"
                ).bindparams(exercise_id=ex_id, age_band=band)
            )

        # Skill join rows (referenced by letter code, e.g. ["A", "D"])
        for code in ex["skill_codes"]:
            bind.execute(
                sa.text(
                    "INSERT INTO technique_exercise_skills (exercise_id, skill_id) "
                    "VALUES (:exercise_id, :skill_id)"
                ).bindparams(
                    exercise_id=ex_id,
                    skill_id=skill_code_to_id[code],
                )
            )

        # Material join rows (referenced by slug, e.g. ["conos", "llantas"])
        for mat_slug in ex["material_slugs"]:
            bind.execute(
                sa.text(
                    "INSERT INTO technique_exercise_materials "
                    "  (exercise_id, material_id) "
                    "VALUES (:exercise_id, :material_id)"
                ).bindparams(
                    exercise_id=ex_id,
                    material_id=mat_slug_to_id[mat_slug],
                )
            )


def downgrade() -> None:
    # Drop in reverse FK-dependency order.
    op.drop_index("idx_asp_athlete_skill_time", table_name="athlete_skill_progress")
    op.drop_table("athlete_skill_progress")

    op.drop_index("idx_tse_session", table_name="technique_session_exercises")
    op.drop_table("technique_session_exercises")

    op.drop_table("technique_exercise_materials")
    op.drop_table("technique_exercise_skills")
    op.drop_table("technique_exercise_age_bands")

    op.drop_index(
        "idx_technique_exercise_visibility", table_name="technique_exercises"
    )
    op.drop_table("technique_exercises")

    op.drop_table("technique_materials")
    op.drop_table("technique_skills")

    # Drop named ENUM types (MySQL/MariaDB only; SQLite has no native ENUM).
    bind = op.get_bind()
    if bind.dialect.name not in ("sqlite",):
        for enum_name in (
            "exercisedifficulty",
            "ageband",
            "sessionsegment",
            "skillprogressstatus",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
