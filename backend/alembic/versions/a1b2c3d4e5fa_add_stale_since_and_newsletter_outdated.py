"""add stale_since to agent_runs + 'outdated' a newsletter status (PR5)

Revision ID: a1b2c3d4e5fa
Revises: c4d5e6f7a8b9
Create Date: 2026-06-01 12:00:00.000000

PR5 (unificación /competitions) — re-trigger IA + flag stale:

1. ``agent_runs.stale_since`` (DATETIME NULL):
   - NULL = análisis vigente.
   - NOT NULL = el run quedó desactualizado (una re-ingesta sobre el mismo
     race_event detectó SHA256 distinto). Se puebla vía
     ``POST /runs/{run_id}/invalidate`` (auto desde el ingestor) o al
     confirmar un diff.
   - Nullable, sin default → migración NO bloqueante. Filas existentes
     quedan NULL (vigentes). No requiere backfill.

2. ``athlete_monthly_newsletters.status`` gana el valor ``'outdated'`` (D3):
   - Un boletín ya enviado que quedó desactualizado por una corrección se
     marca ``outdated`` — NO se reenvía. En MySQL es ENUM nativo: requiere
     MODIFY COLUMN. En SQLite (tests) la columna es VARCHAR + CHECK creado
     al definir la tabla desde el modelo (que ya incluye 'outdated'), así
     que no se requiere acción en SQLite.

Compatibilidad SQLite: ADD COLUMN sin FK es nativo. El MODIFY del enum se
ejecuta solo en MySQL (guard por dialecto).

Reversibilidad: downgrade dropea la columna y revierte el enum a sus 4
valores previos (solo MySQL). NO destruye datos funcionales.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5fa"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEWSLETTER_TABLE = "athlete_monthly_newsletters"
_ENUM_WITH_OUTDATED = "('draft','approved','sent','failed','outdated')"
_ENUM_WITHOUT_OUTDATED = "('draft','approved','sent','failed')"


def upgrade() -> None:
    # 1. agent_runs.stale_since
    op.add_column(
        "agent_runs",
        sa.Column("stale_since", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_agent_runs_stale_since",
        "agent_runs",
        ["stale_since"],
        unique=False,
    )

    # 2. newsletter status enum → añadir 'outdated' (solo MySQL).
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            f"ALTER TABLE {_NEWSLETTER_TABLE} "
            f"MODIFY COLUMN status ENUM{_ENUM_WITH_OUTDATED} NOT NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            f"ALTER TABLE {_NEWSLETTER_TABLE} "
            f"MODIFY COLUMN status ENUM{_ENUM_WITHOUT_OUTDATED} NOT NULL"
        )

    op.drop_index("ix_agent_runs_stale_since", table_name="agent_runs")
    op.drop_column("agent_runs", "stale_since")
