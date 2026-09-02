"""ai insights v3 columns (feature 037, T104)

Revision ID: f7a8b9c0d1e3
Revises: 463c1f0ccb38
Create Date: 2026-09-02 10:00:00.000000

Feature 037 (AI Insights v3 — causal, field-relative, prescriptive).
Agrega a ``athlete_ai_insights`` las columnas que soportan la nueva
estructura ``InsightV3`` (ver ``specs/037-ai-insights-v3-causal/data-model.md``)
y el diálogo coach ↔ analista:

- ``structured_json`` (JSON NULL): ``InsightV3.model_dump()`` cuando el
  insight fue generado por el prompt v3. ``NULL`` para filas v1/v2 —
  el router sigue leyendo ``summary_text``/``recommendations_json`` para
  esas filas (compatibilidad hacia atrás, sin backfill).
- ``coach_answer_text`` (VARCHAR(1000) NULL): respuesta del coach a
  ``InsightV3.coach_question``, escrita ya escrubeada (nombres
  prohibidos del club) antes de persistir — ver
  ``routers/athlete_race_analysis.py::answer_insight``.
- ``coach_answer_at`` (DATETIME NULL): timestamp de la respuesta.
- ``coach_rating`` (TINYINT NULL): 1 = útil, -1 = no útil. Sin CHECK
  explícito (rango pequeño, validado en el schema Pydantic
  ``AnswerInsightBody``) para mantener el patrón relajado de esta tabla
  (ver ``ck_insights_coach_edits_count_nonneg`` / ``ck_insights_valida_num_nonneg``
  en el modelo — CHECKs solo para invariantes de negocio duras).

Compatibilidad SQLite (tests): ``ADD COLUMN`` sin FK/CHECK no requiere
``batch_alter_table`` — mismo patrón que ``463c1f0ccb38`` /
``c5d6e7f8a9b0`` / ``c3d4e5f6a7b8``.

Reversible: ``downgrade()`` elimina las 4 columnas. Ningún dato previo
a esta migración existe en ellas (todo NULL) — no hay pérdida de datos
al revertir.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e3"
down_revision: Union[str, None] = "463c1f0ccb38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "athlete_ai_insights",
        sa.Column("structured_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "athlete_ai_insights",
        sa.Column("coach_answer_text", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "athlete_ai_insights",
        sa.Column("coach_answer_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "athlete_ai_insights",
        sa.Column("coach_rating", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("athlete_ai_insights", "coach_rating")
    op.drop_column("athlete_ai_insights", "coach_answer_at")
    op.drop_column("athlete_ai_insights", "coach_answer_text")
    op.drop_column("athlete_ai_insights", "structured_json")
