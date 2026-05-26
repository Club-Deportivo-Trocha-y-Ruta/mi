"""add selected_race_insight_ids to athlete_monthly_newsletter

Agrega columna JSON ``selected_race_insight_ids`` a la tabla
``athlete_monthly_newsletters``.

Propósito:
  Permite al coach adjuntar insights aprobados de race-analysis (AthleteAiInsight)
  a un boletín mensual. La lista almacena IDs ordenados; la posición define el
  orden de renderizado en el boletín.

Decisión de diseño:
  - JSON en lugar de tabla M:N: use-case actual es una lista simple de IDs
    seleccionados por el coach. El overhead de una tabla de unión no aporta
    valor en este contexto (no hay atributos adicionales en la relación).
  - nullable=True + default NULL: boletines existentes no se ven afectados.
  - RBAC garantizado en capa de aplicación: solo coach/admin del club accede
    a este campo. Parent nunca puede leer ni escribir.

Privacidad Ley 1581:
  La columna solo almacena IDs enteros (sin PII). El contenido de los insights
  referenciados se filtra por rol en capa de presentación (ticket separado).

Revision ID: d2e3f4a5b6c7
Revises: c5d6e7f8a9b0
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "athlete_monthly_newsletters",
        sa.Column(
            "selected_race_insight_ids",
            sa.JSON(),
            nullable=True,
            comment="IDs ordenados de AthleteAIInsight seleccionados manualmente por el coach",
        ),
    )


def downgrade() -> None:
    op.drop_column("athlete_monthly_newsletters", "selected_race_insight_ids")
