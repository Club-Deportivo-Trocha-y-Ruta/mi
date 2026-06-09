"""email_change_requests + merge de cabezas

Revision ID: b4c5d6e7f8a9
Revises: 8c1d2e3f4a5b, a1b2c3d4e5f7, a1b2c3d4e5f8
Create Date: 2026-06-07 12:00:00.000000

Doble propósito (specs/004-user-profile):

1. **Merge** de las tres cabezas Alembic existentes en esta rama
   (``8c1d2e3f4a5b``, ``a1b2c3d4e5f7``, ``a1b2c3d4e5f8``) en una sola, para que
   ``alembic upgrade head`` del entrypoint vuelva a funcionar en el deploy.

2. Crea ``email_change_requests`` para el flujo de cambio de correo con
   verificación previa de la nueva dirección (verify-new-email-before-apply):

   - ``new_email``    — dirección propuesta (no la activa hasta confirmar).
   - ``token_hash``   — SHA-256 hex (64 chars) del token en claro, UNIQUE.
                        El token en claro nunca se persiste.
   - ``used_at``      — NULL hasta consumir; marca un solo uso e invalidación.
   - ``expires_at``   — created_at + TTL (default 60 min).
   - índice ``ix_email_change_requests_user_id`` — lookup, invalidación de
                        hermanos y ventana de rate-limit por usuario.

Sin backfill. Reversible.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = (
    "8c1d2e3f4a5b",
    "a1b2c3d4e5f7",
    "a1b2c3d4e5f8",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_change_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("new_email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash", name="uq_email_change_requests_token_hash"
        ),
    )
    op.create_index(
        "ix_email_change_requests_user_id",
        "email_change_requests",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_change_requests_user_id",
        table_name="email_change_requests",
    )
    op.drop_table("email_change_requests")
