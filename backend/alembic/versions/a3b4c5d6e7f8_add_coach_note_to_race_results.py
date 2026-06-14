"""add coach note to race results

Revision ID: a3b4c5d6e7f8
Revises: e5f6a7b8c9d0
Create Date: 2026-06-14 00:00:00.000000

Agrega tres columnas a ``race_results`` para el flujo de notas cualitativas
del entrenador por atleta por válida (feature 013-race-result-athlete-notes):

- ``coach_note``           — VARCHAR(500) NULL. Observación cualitativa del
                             entrenador/admin. Separada de la columna ``notes``
                             del importador para no ser sobreescrita en
                             re-importaciones.
- ``coach_note_author_id`` — FK → ``users.id`` (ON DELETE SET NULL). Usuario
                             que escribió la nota por última vez.
- ``coach_note_updated_at`` — DATETIME NULL. Timestamp de la última escritura;
                              se limpia junto con la nota en DELETE.

Constraint FK nombrado explícitamente para facilitar downgrade sin ambigüedad:
``fk_race_results_coach_note_author``.

La columna legada ``notes`` (String 300, importador PDF/CSV) no se toca.

Reversible: las tres columnas son nullable y no tienen backfill; el downgrade
elimina el FK antes de las columnas (orden requerido por MySQL).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("race_results") as batch_op:
        batch_op.add_column(
            sa.Column("coach_note", sa.String(length=500), nullable=True)
        )
        batch_op.add_column(
            sa.Column("coach_note_author_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("coach_note_updated_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_race_results_coach_note_author",
            "users",
            ["coach_note_author_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("race_results") as batch_op:
        batch_op.drop_constraint(
            "fk_race_results_coach_note_author", type_="foreignkey"
        )
        batch_op.drop_column("coach_note_updated_at")
        batch_op.drop_column("coach_note_author_id")
        batch_op.drop_column("coach_note")
