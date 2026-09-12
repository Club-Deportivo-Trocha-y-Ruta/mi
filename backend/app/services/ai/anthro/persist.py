"""Paso 5 del pipeline antropométrico (feature 042, T038): persistencia + auditoría.

Implementa ``specs/042-traceable-growth-ai/tasks.md`` T038 y
``specs/042-traceable-growth-ai/data-model.md`` §1 (las nueve columnas nuevas) y §6
(invariantes 1, 3 y 5). Firma compatible con un nodo LangGraph (``async def
step(state, config) -> dict``, ``research.md`` R-03) por el mismo motivo que
``context.py``/``analyst.py``/``guardrails_step.py``: este pipeline es un orquestador
plano sin grafo, checkpointer ni HITL, pero mantener la firma idéntica hace que una
futura promoción a ``StateGraph`` sea un envoltorio mecánico, no una reescritura. Este
paso en particular no llama a ningún LLM ni abre su propio span de traza — ``config``
se acepta solo por uniformidad de firma.

Contrato de entrada de ``state`` (lo puebla ``pipeline.py``, T039, no este módulo —
este paso corre DESPUÉS de ``guardrails_step.guardrails_step``, que ya resolvió el
texto final saneado y la pertenencia a la puerta familiar; ver la máquina de estados
completa en ``data-model.md`` §3):

- ``db``: sesión async de SQLAlchemy — comparte la transacción del caller (mismo
  criterio que ``app/routers/ai.py::_record_explanation_audit``: este módulo nunca
  comitea por su cuenta, el router/caller lo hace al terminar el request).
- ``athlete``: instancia de ``Athlete`` ya cargada (aporta ``club_id`` para la
  auditoría).
- ``target_record``: ``AnthropometricRecord`` que se está analizando (aporta su
  ``id`` para la clave de caché).
- ``use_case``: string de caché YA resuelto por audiencia por el caller
  (``phv_explainer`` / ``phv_explanation_coach`` / el par por-medición —
  ``measurement-analysis-api.md`` §0.1). Este módulo nunca decide el ``use_case``,
  solo lo usa como clave.
- ``actor``: ``User`` autenticado que pidió la generación — puebla
  ``generated_by_user_id`` y el ``actor`` de la fila de auditoría.
- ``insight``: ``AnthropometryInsightV1`` FINAL ya resuelto (el mismo que vio
  ``guardrails_step``, T036) — se serializa tal cual a ``structured_json``.
- ``critic_verdict``: el veredicto persistido de CINCO valores (``approved |
  revised | flagged | fallback | skipped``, ``data-model.md`` §3) — **no** el
  vocabulario crudo de tres valores del crítico (ver la nota de colisión de
  nombres de ``schemas.py``).
- ``guardrail_rendered_text``: el texto plano YA renderizado y saneado por
  ``guardrails_step`` (``report.text``) — esto y SOLO esto va a la columna
  ``NOT NULL`` ``text`` (insight-schema.md §4: nunca una segunda renderización
  independiente, para que la defensa final de guardrails cubra exactamente lo que
  se persiste/muestra).
- ``prompt_version``: la versión de ``AI_ANTHRO_PROMPT_VERSION`` vigente en la
  generación que produjo el insight final (si hubo reanálisis, la del intento que
  ganó) — nunca releída de ``settings`` aquí, para que un rollback posterior de la
  variable no reetiquete filas viejas (``data-model.md`` §1).
- ``model`` / ``provider``: strings ya resueltos por ``pipeline.py`` vía
  ``app.services.llm.factory.resolve_configured_model``/``settings.ai_provider`` —
  este módulo no vuelve a resolverlos, solo los persiste tal cual (mismo criterio
  que el use case legado, que los recibe ya resueltos de ``LLMResponse``).
- ``age_group`` / ``maturation_status``: strings ya derivados por ``pipeline.py``
  de ``analysis_context.identity``/``target_record`` — columnas ``NOT NULL``
  heredadas de la feature 033, sin cambio de significado.
- ``generated_at``: ``datetime`` (UTC) del momento de generación, fijado por
  ``pipeline.py`` antes de este paso — nunca ``datetime.now()`` propio de este
  módulo, para que coincida exactamente con lo que ``pipeline.py`` reporta en el
  resto de la corrida.
- ``tokens_in`` / ``tokens_out``: enteros YA sumados por ``pipeline.py`` entre la
  llamada del analista y, cuando corrió, la del crítico (incluidas ambas si hubo
  reanálisis) — este módulo no suma nada, solo persiste.
- ``cost_usd``: float YA sumado y redondeado a 6 decimales por ``pipeline.py``
  (mismo criterio de redondeo que ``compute_cost_usd``).
- ``latency_ms``: entero — tiempo de reloj del pipeline completo (contexto →
  este paso), medido por ``pipeline.py``, NUNCA solo las llamadas al LLM
  (``data-model.md`` §1).
- ``langfuse_trace_id``: ``str | None`` — ``None`` siempre que
  ``LANGFUSE_ENABLED=false`` (el caso siempre-verdadero en producción), por
  construcción, no un bug (``data-model.md`` §1).

Privacidad (CLAUDE.md / Ley 1581): ``structured_json``/``text`` son el output YA
saneado por guardrails (última defensa, paso 4) — este módulo no aplica ninguna
sanitización propia, solo persiste. La fila de auditoría nunca incluye el texto
generado ni ningún dato del menor — solo identificadores y el hecho
(``create``/``update``), mismo criterio que ``app/routers/ai.py::
_record_explanation_audit`` (§4.3 del proyecto).

Invariante (data-model.md §6, invariante 5): las nueve columnas nuevas son
de solo escritura DESDE este módulo — ningún otro módulo del feature 042 debe
escribirlas directamente.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_explanation import AthleteAIExplanation
from app.services.audit import AuditAction, AuditEntityType, record_audit

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User
    from app.services.ai.anthro.schemas import AnthropometryInsightV1

__all__ = ["persist"]


# Campos que este upsert efectivamente reescribe en cada corrida — usado SOLO
# para poblar `changed_fields` de la fila de auditoría cuando la acción es
# `update` (mismo propósito y mismo criterio que
# `app/routers/ai.py::_EXPLANATION_REWRITTEN_FIELDS`, que este módulo no
# importa por no acoplarse a un símbolo privado de la capa de routers —
# duplicado deliberado, ampliado con las nueve columnas de trazabilidad de
# esta feature). Un `update` cuyo texto no cambia igual escribe fila (R7 de
# `record_audit` compara solo si HUBO escritura de negocio, que aquí siempre
# ocurre por el propio upsert) — perder este rastro perdería la evidencia de
# que el entrenador pidió una regeneración.
_EXPLANATION_REWRITTEN_FIELDS: tuple[str, ...] = (
    "age_group",
    "generated_at",
    "generated_by_user_id",
    "maturation_status",
    "model",
    "provider",
    "text",
    "schema_version",
    "structured_json",
    "critic_verdict",
    "prompt_version",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "langfuse_trace_id",
)

# Discriminador de formato de fila para TODA fila escrita por este módulo
# (data-model.md §0/§1: nunca "v1" en esta columna — un insight estructurado
# siempre es "v2", incluidas las filas `critic_verdict="fallback"`).
_ROW_SCHEMA_VERSION = "v2"


async def _cached_explanation_id(
    db: AsyncSession,
    *,
    athlete_id: int,
    anthropometric_record_id: int,
    use_case: str,
) -> Optional[int]:
    """Id de la fila de caché `(athlete_id, record_id, use_case)`, o ``None``.

    Duplicado deliberado de `app/routers/ai.py::_cached_explanation_id` (mismo
    propósito exacto: pre-SELECT del upsert, decide `create` vs `update` para
    la auditoría) — este módulo de servicios no importa un símbolo privado de
    la capa de routers.
    """
    result = await db.execute(
        select(AthleteAIExplanation.id).where(
            AthleteAIExplanation.athlete_id == athlete_id,
            AthleteAIExplanation.anthropometric_record_id == anthropometric_record_id,
            AthleteAIExplanation.use_case == use_case,
        )
    )
    return result.scalar_one_or_none()


async def persist(state: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Paso 5: upsert de la fila de caché + fila de auditoría.

    Ver el docstring del módulo para el contrato completo de ``state``. Devuelve
    ``{"persisted_explanation_id": int, "persisted_action": "create" | "update"}``
    para que ``pipeline.py`` pueda, si lo necesita, correlacionar la respuesta con
    la fila escrita sin un segundo SELECT.
    """
    del config  # este paso no llama al LLM ni abre su propio span — ver docstring.

    db: AsyncSession = state["db"]
    athlete: "Athlete" = state["athlete"]
    target_record: Any = state["target_record"]
    use_case: str = state["use_case"]
    actor: "User" = state["actor"]
    insight: "AnthropometryInsightV1" = state["insight"]
    critic_verdict: str = state["critic_verdict"]
    rendered_text: str = state["guardrail_rendered_text"]
    prompt_version: str = state["prompt_version"]
    model: str = state["model"]
    provider: str = state["provider"]
    age_group: str = state["age_group"]
    maturation_status: str = state["maturation_status"]
    generated_at: datetime = state["generated_at"]
    tokens_in: int = state["tokens_in"]
    tokens_out: int = state["tokens_out"]
    cost_usd: float = state["cost_usd"]
    latency_ms: int = state["latency_ms"]
    langfuse_trace_id: Optional[str] = state.get("langfuse_trace_id")

    previous_id = await _cached_explanation_id(
        db,
        athlete_id=athlete.id,
        anthropometric_record_id=target_record.id,
        use_case=use_case,
    )

    structured_json = insight.model_dump(mode="json")

    stmt = mysql_insert(AthleteAIExplanation).values(
        athlete_id=athlete.id,
        anthropometric_record_id=target_record.id,
        use_case=use_case,
        text=rendered_text,
        model=model,
        provider=provider,
        generated_at=generated_at,
        age_group=age_group,
        maturation_status=maturation_status,
        generated_by_user_id=actor.id,
        schema_version=_ROW_SCHEMA_VERSION,
        structured_json=structured_json,
        critic_verdict=critic_verdict,
        prompt_version=prompt_version,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=round(cost_usd, 6),
        latency_ms=latency_ms,
        langfuse_trace_id=langfuse_trace_id,
    )
    stmt = stmt.on_duplicate_key_update(
        text=stmt.inserted.text,
        model=stmt.inserted.model,
        provider=stmt.inserted.provider,
        generated_at=stmt.inserted.generated_at,
        age_group=stmt.inserted.age_group,
        maturation_status=stmt.inserted.maturation_status,
        generated_by_user_id=stmt.inserted.generated_by_user_id,
        schema_version=stmt.inserted.schema_version,
        structured_json=stmt.inserted.structured_json,
        critic_verdict=stmt.inserted.critic_verdict,
        prompt_version=stmt.inserted.prompt_version,
        tokens_in=stmt.inserted.tokens_in,
        tokens_out=stmt.inserted.tokens_out,
        cost_usd=stmt.inserted.cost_usd,
        latency_ms=stmt.inserted.latency_ms,
        langfuse_trace_id=stmt.inserted.langfuse_trace_id,
    )
    await db.execute(stmt)

    entity_id = previous_id
    if entity_id is None:
        entity_id = await _cached_explanation_id(
            db,
            athlete_id=athlete.id,
            anthropometric_record_id=target_record.id,
            use_case=use_case,
        )

    # Mismo criterio §4.3 que la explicación PHV/por-medición legada: solo el
    # hecho (create/update) y los identificadores viajan a la auditoría, nunca
    # el texto generado ni ningún dato del menor.
    await record_audit(
        db,
        action=AuditAction.create if previous_id is None else AuditAction.update,
        entity_type=AuditEntityType.athlete_ai_explanation,
        entity_id=entity_id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=(
            None if previous_id is None else list(_EXPLANATION_REWRITTEN_FIELDS)
        ),
        meta={"related_entity_id": target_record.id},
    )

    return {
        "persisted_explanation_id": entity_id,
        "persisted_action": "create" if previous_id is None else "update",
    }
