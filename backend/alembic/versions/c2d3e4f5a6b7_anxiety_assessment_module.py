"""anxiety assessment module (feature 017)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-23 00:00:00.000000

Spec 017 — competitive-anxiety-assessment.

Creates the four ``anxiety_*`` tables (instruments, assessments, response
tokens, baselines) and adds the ``psychological_assessment`` consent scope to
``parental_consents`` (FR-023). All enums use named ENUM types in MySQL;
SQLite renders them as VARCHAR (no native ENUM), which is fine for tests.

Downgrade drops the four tables and the consent column.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Consent scope: parental_consents.psychological_assessment
    # -----------------------------------------------------------------------
    op.add_column(
        "parental_consents",
        sa.Column(
            "psychological_assessment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # -----------------------------------------------------------------------
    # 2. anxiety_instruments
    # -----------------------------------------------------------------------
    op.create_table(
        "anxiety_instruments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            sa.Enum("csai2", "csai2r", "sas2", name="anxietyinstrumenttype"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column(
            "age_band",
            sa.Enum("10-12", "13-15", "import", name="anxietyinstrumentageband"),
            nullable=False,
        ),
        sa.Column("item_count", sa.SmallInteger(), nullable=False),
        sa.Column("scoring_key_json", sa.JSON(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anxiety_instruments_type_active",
        "anxiety_instruments",
        ["type", "is_active"],
    )
    op.create_index(
        "ix_anxiety_instruments_age_band", "anxiety_instruments", ["age_band"]
    )

    # -----------------------------------------------------------------------
    # 3. anxiety_assessments
    # -----------------------------------------------------------------------
    op.create_table(
        "anxiety_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column(
            "priority",
            sa.Enum("A", "B", "C", name="anxietyeventpriority"),
            nullable=True,
        ),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "partial", "completed", name="anxietyassessmentstatus"
            ),
            nullable=False,
        ),
        sa.Column("answers_json", sa.JSON(), nullable=True),
        sa.Column("score_cognitive", sa.Float(), nullable=True),
        sa.Column("score_somatic", sa.Float(), nullable=True),
        sa.Column("score_selfconfidence", sa.Float(), nullable=True),
        sa.Column(
            "is_partial", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "instrument_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("override_ack_at", sa.DateTime(), nullable=True),
        sa.Column("interpretation_json", sa.JSON(), nullable=True),
        sa.Column(
            "interpretation_source",
            sa.Enum("llm", "rule", name="anxietyinterpretationsource"),
            nullable=True,
        ),
        sa.Column("interpretation_model", sa.String(length=128), nullable=True),
        sa.Column("interpreted_at", sa.DateTime(), nullable=True),
        sa.Column("flags_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["anxiety_instruments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["race_events.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anxiety_assessments_athlete_scheduled",
        "anxiety_assessments",
        ["athlete_id", "scheduled_at"],
    )
    op.create_index(
        "ix_anxiety_assessments_event", "anxiety_assessments", ["event_id"]
    )
    op.create_index(
        "ix_anxiety_assessments_status", "anxiety_assessments", ["status"]
    )

    # -----------------------------------------------------------------------
    # 4. anxiety_response_tokens
    # -----------------------------------------------------------------------
    op.create_table(
        "anxiety_response_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["anxiety_assessments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_anxiety_response_tokens_hash"),
    )
    op.create_index(
        "ix_anxiety_response_tokens_assessment",
        "anxiety_response_tokens",
        ["assessment_id"],
    )

    # -----------------------------------------------------------------------
    # 5. anxiety_baselines
    # -----------------------------------------------------------------------
    op.create_table(
        "anxiety_baselines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column(
            "subscale",
            sa.Enum(
                "cognitive",
                "somatic",
                "selfconfidence",
                name="anxietybaselinesubscale",
            ),
            nullable=False,
        ),
        sa.Column(
            "instrument_type",
            sa.Enum(
                "csai2", "csai2r", "sas2", name="anxietybaselineinstrumenttype"
            ),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("source_assessment_id", sa.Integer(), nullable=False),
        sa.Column("established_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_assessment_id"],
            ["anxiety_assessments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "athlete_id",
            "subscale",
            "instrument_type",
            name="uq_anxiety_baseline_athlete_subscale_instrument",
        ),
    )


def downgrade() -> None:
    op.drop_table("anxiety_baselines")
    op.drop_index(
        "ix_anxiety_response_tokens_assessment",
        table_name="anxiety_response_tokens",
    )
    op.drop_table("anxiety_response_tokens")
    op.drop_index(
        "ix_anxiety_assessments_status", table_name="anxiety_assessments"
    )
    op.drop_index(
        "ix_anxiety_assessments_event", table_name="anxiety_assessments"
    )
    op.drop_index(
        "ix_anxiety_assessments_athlete_scheduled",
        table_name="anxiety_assessments",
    )
    op.drop_table("anxiety_assessments")
    op.drop_index(
        "ix_anxiety_instruments_age_band", table_name="anxiety_instruments"
    )
    op.drop_index(
        "ix_anxiety_instruments_type_active", table_name="anxiety_instruments"
    )
    op.drop_table("anxiety_instruments")
    op.drop_column("parental_consents", "psychological_assessment")

    # Drop named ENUM types (MySQL/PostgreSQL no-op-safe on SQLite).
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for enum_name in (
            "anxietyinstrumenttype",
            "anxietyinstrumentageband",
            "anxietyeventpriority",
            "anxietyassessmentstatus",
            "anxietyinterpretationsource",
            "anxietybaselinesubscale",
            "anxietybaselineinstrumenttype",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
