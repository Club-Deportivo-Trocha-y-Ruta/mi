"""add is_fallback to athlete_ai_insights (feature 036, US4)

Revision ID: 463c1f0ccb38
Revises: c7d8e9f0a1b2
Create Date: 2026-08-31 10:00:00.000000

Feature 036 (AI Insights tab review, US4, T020-T023). El coach no podía
distinguir un insight con contenido real de un placeholder de falla del
analyst LLM (fallback determinista, ``services/race/ai/fallback.py``):
ambos podían llegar con ``confidence`` bajo, pero confianza baja también
ocurre por razones legítimas (datos incompletos, regla N=1) — de ahí un
discriminador explícito en vez de inferirlo de la confianza o del texto.

Cambios:

- ``athlete_ai_insights.is_fallback`` (BOOLEAN NOT NULL, server_default
  FALSE): ``True`` ⇔ la fila la escribió el *failure path* de
  ``deterministic_fallback`` (NO ``deterministic_fallback_n1``, que es un
  análisis legítimo bajo la regla N=1 y nunca marca esta columna). La
  escriben ``persist_insight`` hacia delante vía el discriminador
  expuesto en ``services/race/ai/fallback.is_fallback_output`` (chequeo
  de tipo, no de contenido).
- Backfill único (T023): filas existentes cuyo ``summary_text`` coincide
  EXACTO con el texto del fallback de falla se reclasifican a
  ``is_fallback=1``. Es seguro matchear por texto sólo en este backfill
  porque es una constante de compilación (no input de usuario) y porque
  el fallback N=1 usa un texto completamente distinto (multi-sección) que
  nunca coincide. El código en marcha (``is_fallback_output``) NUNCA
  vuelve a inspeccionar texto — sólo este backfill histórico lo hace.
  El texto se duplica literal en esta migración (no se importa desde
  ``app.services.race.ai.fallback``) para que la migración siga siendo
  reproducible incluso si el wording cambia más adelante.

Compatibilidad SQLite (tests): ``ADD COLUMN`` sin FK/CHECK no requiere
``batch_alter_table``; SQLite lo soporta nativamente (mismo patrón que
``c5d6e7f8a9b0`` y ``c3d4e5f6a7b8``).

Nota de heads: al momento de escribir esta migración, ``alembic heads``
reporta un único head (``c7d8e9f0a1b2``) — el segundo head histórico
``e5f6a7b8c9d0`` (feature 007, documentado en
``docs/implementation-status.md``) ya fue encadenado por
``a3b4c5d6e7f8_add_coach_note_to_race_results.py``, así que esta revisión
no crea un branch point nuevo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "463c1f0ccb38"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Texto EXACTO de `_FALLBACK_MARKDOWN` en `app/services/race/ai/fallback.py`
# al momento de esta migración. Duplicado a propósito (no importado desde
# app code) — ver docstring del módulo arriba.
_FALLBACK_TEXT = (
    "Análisis IA no disponible en este momento. Revisa los datos crudos "
    "en la sección de resultados."
)


def upgrade() -> None:
    op.add_column(
        "athlete_ai_insights",
        sa.Column(
            "is_fallback",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )

    # Backfill (T023): reclasifica filas históricas del failure path.
    # Match EXACTO (no LIKE): el fallback N=1 es multi-sección y jamás
    # coincide con esta constante de una sola oración.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE athlete_ai_insights SET is_fallback = 1 "
            "WHERE summary_text = :fallback_text"
        ).bindparams(fallback_text=_FALLBACK_TEXT)
    )


def downgrade() -> None:
    op.drop_column("athlete_ai_insights", "is_fallback")
