"""add pii_scrubbed_at to athlete_ai_insights (retention 180d post-deprecation)

Revision ID: c5d6e7f8a9b0
Revises: 11aaea26e2ba
Create Date: 2026-05-25 10:00:00.000000

Soporte para el job de retención de PII: 180 días después de
``deprecated_at`` un proceso fuera de banda redactará campos PII del
insight (resumen, snapshot, recomendaciones) y marcará la fila con
``pii_scrubbed_at = now()``.

Decisión cerrada (Task #7): NO se cifra columnarmente. La política es
borrado/redacción diferida; ``pii_scrubbed_at`` actúa como bandera
idempotente para que el job no reprocese filas ya scrubeadas.

Cambios:

- ``athlete_ai_insights.pii_scrubbed_at`` (DATETIME NULL):
  - ``NULL`` = aún no scrubeado (fila vigente o aún dentro de la ventana
    de retención).
  - ``NOT NULL`` = el job ya redactó PII en esta fila; valor = timestamp
    de la corrida del job.
  - Las filas existentes quedan NULL (no requiere backfill).

- Índice ``ix_ai_insights_pii_scrubbed_at`` sobre ``(pii_scrubbed_at)``:
  - El job de retención escanea
    ``WHERE deprecated_at < now() - INTERVAL 180 DAY AND pii_scrubbed_at IS NULL``.
    El índice acelera el filtro por ``pii_scrubbed_at IS NULL`` cuando el
    histórico crezca; complementa el índice existente
    ``ix_insights_deprecated_at``.

Compatibilidad SQLite (tests): ADD COLUMN sin FK no requiere
``batch_alter_table``; SQLite lo soporta nativamente. El índice se crea
igual en ambos motores.

Reversibilidad: downgrade dropea índice + columna. NO destruye datos
funcionales (la columna es metadata; los datos PII reales viven en otras
columnas y no se tocan aquí).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "11aaea26e2ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "athlete_ai_insights",
        sa.Column("pii_scrubbed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_ai_insights_pii_scrubbed_at",
        "athlete_ai_insights",
        ["pii_scrubbed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_insights_pii_scrubbed_at",
        table_name="athlete_ai_insights",
    )
    op.drop_column("athlete_ai_insights", "pii_scrubbed_at")
