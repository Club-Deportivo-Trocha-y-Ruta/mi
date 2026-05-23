"""add_athlete_newsletters_and_badges

Revision ID: a1b2c3d4e5f7
Revises: f9a0b1c2d3e4
Create Date: 2026-05-23 10:00:00.000000

Crea dos tablas para el módulo Boletín mensual individual (Fase 1.8):
  - athlete_badges: insignias idempotentes por periodo (asistencia + competitivas).
  - athlete_monthly_newsletters: boletín con snapshot JSON, narrativa IA y
    estado del workflow (draft → approved → sent / failed).

Enums nuevos:
  - badgetype: attendance_100, attendance_90, attendance_75, first_podium, mtp, top10
  - badgesource: attendance, race
  - newsletterstatus: draft, approved, sent, failed
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers
revision = "a1b2c3d4e5f7"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enums (MySQL ENUM inline en columna — sin CREATE TYPE separado)
    # ------------------------------------------------------------------

    # ----------- athlete_badges -----------
    op.create_table(
        "athlete_badges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column(
            "badge_type",
            mysql.ENUM(
                "attendance_100",
                "attendance_90",
                "attendance_75",
                "first_podium",
                "mtp",
                "top10",
            ),
            nullable=False,
        ),
        sa.Column(
            "badge_source",
            mysql.ENUM("attendance", "race"),
            nullable=False,
        ),
        sa.Column("period_year", sa.SmallInteger(), nullable=False),
        sa.Column("period_month", sa.SmallInteger(), nullable=False),
        sa.Column(
            "earned_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "athlete_id",
            "badge_type",
            "period_year",
            "period_month",
            name="uq_athlete_badge_period",
        ),
    )
    op.create_index(
        "idx_athlete_badges_athlete_period",
        "athlete_badges",
        ["athlete_id", "period_year", "period_month"],
    )

    # ----------- athlete_monthly_newsletters -----------
    op.create_table(
        "athlete_monthly_newsletters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            mysql.ENUM("draft", "approved", "sent", "failed"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=True),
        sa.Column("ai_narrative", sa.JSON(), nullable=True),
        sa.Column("coach_narrative_overrides", sa.JSON(), nullable=True),
        sa.Column("badges_earned", sa.JSON(), nullable=True),
        sa.Column("pdf_storage_url", sa.String(512), nullable=True),
        sa.Column("pdf_generated_at", sa.DateTime(), nullable=True),
        sa.Column("pdf_sha256", sa.CHAR(64), nullable=True),
        sa.Column("generated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("sent_to", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "athlete_id",
            "year",
            "month",
            name="uq_athlete_newsletter_period",
        ),
    )
    op.create_index(
        "idx_newsletter_status_period",
        "athlete_monthly_newsletters",
        ["status", "year", "month"],
    )
    op.create_index(
        "idx_newsletter_athlete_period",
        "athlete_monthly_newsletters",
        ["athlete_id", "year", "month"],
    )


def downgrade() -> None:
    op.drop_index("idx_newsletter_athlete_period", table_name="athlete_monthly_newsletters")
    op.drop_index("idx_newsletter_status_period", table_name="athlete_monthly_newsletters")
    op.drop_table("athlete_monthly_newsletters")
    op.drop_index("idx_athlete_badges_athlete_period", table_name="athlete_badges")
    op.drop_table("athlete_badges")
