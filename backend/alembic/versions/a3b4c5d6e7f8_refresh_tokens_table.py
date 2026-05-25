"""refresh_tokens table (A3 — JWT jti + revocation)

Revision ID: a3b4c5d6e7f8
Revises: 7b85747392d2
Create Date: 2026-05-25 00:00:00.000000

Crea la tabla ``refresh_tokens`` para soportar revocación explícita de
refresh tokens JWT (rotación, logout).

Schema
======
- ``jti``               CHAR(32) PK              — uuid4.hex del refresh token.
- ``user_id``           BIGINT NOT NULL FK→users CASCADE.
- ``issued_at``         DATETIME NOT NULL       — momento de emisión (utc).
- ``expires_at``        DATETIME NOT NULL       — exp del JWT.
- ``revoked_at``        DATETIME NULL           — NULL si vivo, != NULL si revocado.
- ``replaced_by_jti``   CHAR(32) NULL           — jti que reemplazó a éste (rotación).

Índices
=======
- ``ix_refresh_tokens_user_id`` (user_id) — ya creado por la FK.
- ``ix_refresh_tokens_user_revoked`` (user_id, revoked_at) — listar tokens vivos.
- ``ix_refresh_tokens_expires_at`` (expires_at) — limpieza/expiración batch.

Reversible
==========
``downgrade()`` borra la tabla con drop_index + drop_table. Sin dependencias
cíclicas porque la FK ``user_id → users.id`` es one-way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "7b85747392d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.CHAR(length=32), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by_jti", sa.CHAR(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name="pk_refresh_tokens"),
    )
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_user_revoked",
        "refresh_tokens",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    # En MySQL ``drop_table`` borra automáticamente FKs e índices de la
    # tabla — drop_index explícitos previos disparan error 1553 porque
    # ``ix_refresh_tokens_user_id`` está siendo usado por la FK
    # ``fk_refresh_tokens_user_id``. Confiamos en drop_table cascade
    # interno de InnoDB.
    op.drop_table("refresh_tokens")
