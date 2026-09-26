"""race_import_staged_documents (amendment 2026-09-26 — carga por skill)

Revision ID: c9d0e1f2a3b4
Revises: be4595de1ad2
Create Date: 2026-09-26 00:00:00.000000

Crea ``race_import_staged_documents`` (data-model.md §11.1): la tabla que
guarda las filas que ``race-results-load`` extrajo de un acta, mientras la
ingesta está en revisión (``pending`` o ``committed`` con
``pending_categories``). Relación 1:1 con ``race_imports``: ``import_id``
es a la vez PK y FK, ``ON DELETE CASCADE``.

Sin índice más allá de la PK (data-model.md §11.1: "no index beyond the
primary key" — el único acceso es por ``import_id``, ya cubierto). Sin
valor de enum nuevo en ninguna columna existente.

Reversible: el downgrade solo hace ``DROP TABLE``, sin pérdida de datos
fuera de esta tabla nueva (las filas migran de vuelta al archivo original
si algún día hiciera falta releerlo — no se pierde nada del acta).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "be4595de1ad2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_import_staged_documents",
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("profile_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=16), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["race_imports.id"],
            name="fk_race_import_staged_documents_import_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("import_id"),
    )


def downgrade() -> None:
    op.drop_table("race_import_staged_documents")
