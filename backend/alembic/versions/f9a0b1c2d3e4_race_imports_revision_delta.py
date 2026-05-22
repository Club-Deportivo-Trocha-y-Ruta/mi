"""race_imports revision delta (F-UP-REV1)

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-05-21 09:00:00.000000

Extiende ``race_imports`` con 2 columnas + 1 índice para soportar el flow de
revisión integral de resultados Copa Valle (docs/10-race-results/revision-design.md §2):

- ``parent_import_id``  — FK self-ref a ``race_imports.id`` (ON DELETE SET NULL).
                            Apunta al import committed inmediato anterior cuando
                            esta ingesta es revisión. NULL para primer import.
                            Encadenamiento lineal: revisión-de-revisión apunta
                            al último committed.
- ``revision_reason``   — VARCHAR(300) NULL. Texto libre del coach explicando
                            la revisión (ej. "Federación corrigió posiciones
                            tras reclamo Andrés Mejía 2026-05-19"). Obligatorio
                            cuando el diff incluye deletes (validación app-level,
                            NO SQL — preserva flexibilidad). Loggeo solo
                            ``len(reason)`` nunca el texto (privacidad menores).

Índice nuevo:
- ``ix_race_imports_parent_id`` — listar revisiones descendientes (audit query).

``is_revision`` NO se persiste: se deriva via ``parent_import_id IS NOT NULL``
(evita drift entre dos campos que deben siempre coincidir).

Reversible: ambas columnas nullable, índice + FK con names únicos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("race_imports") as batch_op:
        # FK self-ref al import committed previo (encadenamiento revisión).
        batch_op.add_column(
            sa.Column("parent_import_id", sa.Integer(), nullable=True)
        )
        # Texto del motivo (obligatorio si hay deletes — validación en app).
        batch_op.add_column(
            sa.Column(
                "revision_reason", sa.String(length=300), nullable=True
            )
        )

        batch_op.create_foreign_key(
            "fk_race_imports_parent_id",
            "race_imports",
            ["parent_import_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Índice fuera de batch_alter_table (CREATE INDEX no requiere ALTER atomic).
    op.create_index(
        "ix_race_imports_parent_id",
        "race_imports",
        ["parent_import_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_race_imports_parent_id", table_name="race_imports")

    with op.batch_alter_table("race_imports") as batch_op:
        batch_op.drop_constraint(
            "fk_race_imports_parent_id", type_="foreignkey"
        )
        batch_op.drop_column("revision_reason")
        batch_op.drop_column("parent_import_id")
