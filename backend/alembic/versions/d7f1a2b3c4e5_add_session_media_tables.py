"""add session_media and session_media_athlete tables

Revision ID: d7f1a2b3c4e5
Revises: a2b3c4d5e6f7
Create Date: 2026-05-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7f1a2b3c4e5"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_media",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("photo", "video", name="mediatype"),
            nullable=False,
        ),
        sa.Column("storage_url", sa.String(length=500), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("filename_original", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("caption", sa.String(length=280), nullable=True),
        sa.Column("consent_ack", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["training_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_session_media_session",
        "session_media",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "idx_session_media_uploaded_at",
        "session_media",
        ["uploaded_at"],
        unique=False,
    )

    op.create_table(
        "session_media_athlete",
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("tagged_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["session_media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("media_id", "athlete_id"),
    )


def downgrade() -> None:
    op.drop_table("session_media_athlete")
    op.drop_index("idx_session_media_uploaded_at", table_name="session_media")
    op.drop_index("idx_session_media_session", table_name="session_media")
    op.drop_table("session_media")
    sa.Enum(name="mediatype").drop(op.get_bind(), checkfirst=True)
