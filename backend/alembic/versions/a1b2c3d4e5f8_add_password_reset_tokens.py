"""add password_reset_tokens

Revision ID: a1b2c3d4e5f8
Revises: d4e5f6a7b8c9
Create Date: 2026-06-07 10:00:00.000000

Crea la tabla ``password_reset_tokens`` para el flujo de restablecimiento de
contraseña desde la página de login (specs/003-password-reset-login).

- ``token_hash``  — SHA-256 hex (64 chars) del token en claro, UNIQUE para
                    lookup indexado. El token en claro nunca se persiste.
- ``used_at``     — NULL hasta consumir; marca un solo uso e invalidación.
- ``expires_at``  — created_at + TTL (default 60 min).
- índice ``ix_password_reset_tokens_user_id`` — lookup, invalidación de
                    hermanos y ventana de rate-limit por usuario.

Sin backfill. Reversible.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
