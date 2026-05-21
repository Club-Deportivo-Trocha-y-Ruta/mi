"""race_imports upload UI delta (F-UP1)

Revision ID: e8f9a0b1c2d3
Revises: 7a8b9c0d1e2f
Create Date: 2026-05-20 18:00:00.000000

Extiende ``race_imports`` con 9 columnas nuevas para soportar el flow upload UI
(docs/10-race-results/upload-design.md §3):

- ``event_id``                — FK a race_events (ON DELETE SET NULL). Permite
                                 enlace directo al evento (evita JOIN indirecto
                                 vía RaceResult.imported_from_id). NULL para
                                 imports F1.7 legacy.
- ``kind``                    — Enum (resultados, general, both). Discrimina
                                 qué PDF(s) trae el import. Default 'resultados'
                                 para imports legacy.
- ``storage_path``            — Path absoluto del PDF RESULTADOS en storage SFTP
                                 (NULL hasta que se guarde el blob).
- ``storage_url``             — URL pública del PDF RESULTADOS.
- ``general_storage_path``    — Path absoluto del PDF GENERAL (si existe).
- ``general_storage_url``     — URL pública del PDF GENERAL.
- ``general_sha256``          — SHA256 del GENERAL para deduplicación.
- ``parse_meta_json``         — Snapshot EventMeta + matches preview entre
                                 parse y commit (NULL post-commit).
- ``original_filename``       — Nombre original del archivo subido. Distinto
                                 a ``filename`` (que puede ser sanitizado).

Todas nullable o con default seguro: los 3 imports F1.7 legacy quedan con
``event_id=NULL``, ``kind='resultados'``, todos los demás NULL.

Índices nuevos:
- ``ix_race_imports_event_id`` — listar imports de un evento puntual.
- ``ix_race_imports_status``    — cleanup de pending viejos (TTL 24h).

Reusa la columna existente ``imported_by_user_id`` (F1.7) — NO se duplica.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Valores del enum kind. Usamos ``resultados`` / ``general`` / ``both`` en
# coherencia con el dominio del workflow upload (vs el enum técnico
# ``raceimportstatus`` que vive en español-inglés mixto).
RACE_IMPORT_KIND_VALUES = ("resultados", "general", "both")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # SQLite no soporta ALTER TABLE con FK directo: usamos batch_alter_table.
    # MySQL acepta ALTER TABLE multi-columna y FK inline.
    with op.batch_alter_table("race_imports") as batch_op:
        # FK al evento (nullable: imports F1.7 legacy quedan NULL).
        batch_op.add_column(
            sa.Column("event_id", sa.Integer(), nullable=True)
        )
        # Discriminador resultados / general / both.
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.Enum(*RACE_IMPORT_KIND_VALUES, name="raceimportkind"),
                nullable=False,
                server_default=sa.text("'resultados'"),
            )
        )
        # Storage RESULTADOS.
        batch_op.add_column(
            sa.Column("storage_path", sa.String(length=500), nullable=True)
        )
        batch_op.add_column(
            sa.Column("storage_url", sa.String(length=500), nullable=True)
        )
        # Storage GENERAL.
        batch_op.add_column(
            sa.Column(
                "general_storage_path", sa.String(length=500), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "general_storage_url", sa.String(length=500), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column("general_sha256", sa.CHAR(length=64), nullable=True)
        )
        # Estado intermedio del wizard (parse → dry-run → commit).
        batch_op.add_column(
            sa.Column("parse_meta_json", sa.JSON(), nullable=True)
        )
        # Filename original (post-sanitización el campo `filename` legacy puede
        # haber sido normalizado por seguridad — preservamos el original para UI).
        batch_op.add_column(
            sa.Column("original_filename", sa.String(length=255), nullable=True)
        )

        batch_op.create_foreign_key(
            "fk_race_imports_event_id",
            "race_events",
            ["event_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Índices nuevos. Creados fuera de batch_alter_table porque CREATE INDEX
    # en MySQL no requiere ALTER TABLE atomic.
    op.create_index(
        "ix_race_imports_event_id",
        "race_imports",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_race_imports_status",
        "race_imports",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_race_imports_status", table_name="race_imports")
    op.drop_index("ix_race_imports_event_id", table_name="race_imports")

    with op.batch_alter_table("race_imports") as batch_op:
        batch_op.drop_constraint(
            "fk_race_imports_event_id", type_="foreignkey"
        )
        batch_op.drop_column("original_filename")
        batch_op.drop_column("parse_meta_json")
        batch_op.drop_column("general_sha256")
        batch_op.drop_column("general_storage_url")
        batch_op.drop_column("general_storage_path")
        batch_op.drop_column("storage_url")
        batch_op.drop_column("storage_path")
        batch_op.drop_column("kind")
        batch_op.drop_column("event_id")

    # Drop del tipo enum (MySQL nativo). SQLite usa VARCHAR + CHECK que se
    # eliminan con la columna.
    if dialect != "sqlite":
        sa.Enum(name="raceimportkind").drop(bind, checkfirst=True)
