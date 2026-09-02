"""Nodo 9: ``hitl_gate_review`` — interrupt nativo de LangGraph para HITL.

Reglas de interrupción (workflow §"Decisiones cerradas"):

- ``critic.must_block == True`` → SIEMPRE interrumpe (PII leak, violación
  a principios CLAUDE.md, etc.).
- ``explain_mode == True`` → interrumpe (coach quiere revisar antes de
  publicar análisis "educativo").
- :envvar:`RACE_HITL_ALWAYS` ``=true`` → fuerza interrupción.
- Caso contrario → sin interrupt, draft pasa directo a persist.

Si interrumpe, el grafo pausa. El coach reanuda vía
``compiled_graph.invoke(Command(resume={"decision": "approve" | "reject", "edits": ...}),
config={"configurable": {"thread_id": run_id}})``.

El payload de :func:`interrupt` lleva ``draft`` (markdown) y
``critic_feedback`` para que la UI lo renderice.
"""

from __future__ import annotations

import os
from typing import Any

from langgraph.types import interrupt

from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

NODE_NAME = "hitl_gate_review"

_ALWAYS_ENV = "RACE_HITL_ALWAYS"


def _always_hitl() -> bool:
    raw = os.environ.get(_ALWAYS_ENV, "false").strip().lower()
    return raw in {"true", "1", "yes", "on"}


def _should_interrupt(state: dict) -> bool:
    fb = state.get("critic_feedback")
    must_block = bool(getattr(fb, "must_block", False)) if fb else False
    # Feature 011: en v2 se revisan N drafts → interrumpir si CUALQUIER verdicto
    # por válida exige bloqueo (no solo el singular de compat v1).
    per_valida_verdicts = state.get("per_valida_verdicts") or {}
    any_blocked = any(
        bool(getattr(v, "must_block", False)) for v in per_valida_verdicts.values()
    )
    explain = bool(state.get("explain_mode", False))
    return must_block or any_blocked or explain or _always_hitl()


def _structured_draft(state: dict) -> dict[str, Any] | None:
    """Primer ``InsightV3`` del run, serializado a JSON (o ``None``).

    El contrato del evento (data-model.md §API deltas) es **singular**:
    ``structured_draft``. Cuando el run analiza varias válidas se envía la de
    ``valida_num`` más bajo — la misma que ``draft_analysis`` expone como
    markdown, para que ambos campos del payload describan el mismo draft.
    """
    drafts: dict = state.get("per_valida_drafts_v3") or {}
    if not drafts:
        return None
    try:
        first_key = sorted(drafts)[0]
    except TypeError:  # pragma: no cover - claves heterogéneas
        return None
    candidate = drafts.get(first_key)
    dump = getattr(candidate, "model_dump", None)
    if dump is None:
        return None
    try:
        return dump(mode="json")
    except Exception:  # noqa: BLE001 - el HITL no puede caerse por serializar
        return None


def _structured_drafts(state: dict) -> dict[Any, dict[str, Any]]:
    """Todos los ``InsightV3`` del run, serializados, por ``valida_num``.

    Complementa el ``structured_draft`` singular (compat) con el mapeo
    completo para runs multi-válida (feature 037, T405) — sin romper el
    contrato existente, que sigue siendo la primera entrada de este dict.
    """
    drafts: dict = state.get("per_valida_drafts_v3") or {}
    result: dict[Any, dict[str, Any]] = {}
    for key, candidate in drafts.items():
        dump = getattr(candidate, "model_dump", None)
        if dump is None:
            continue
        try:
            result[key] = dump(mode="json")
        except Exception:  # noqa: BLE001 - el HITL no puede caerse por serializar
            continue
    return result


@with_events(NODE_NAME)
@with_retry(max_attempts=1, backoff=0)
async def hitl_gate_review(state: dict) -> dict[str, Any]:
    if not _should_interrupt(state):
        return {"hitl_decision": {"decision": "auto-approve", "edits": None}}

    draft = state.get("draft_analysis")
    fb = state.get("critic_feedback")

    # Payload de interrupt — NO incluir el mapping ni athlete_id real.
    payload = {
        "step": "review",
        "draft_markdown": getattr(draft, "raw_markdown", "") if draft else "",
        "pseudonym": getattr(draft, "pseudonym", "") if draft else "",
        # Feature 037 (T201): draft estructurado v3 para que la tarjeta de
        # aprobación muestre bloques (hallazgo, observaciones, acciones) en vez
        # de markdown crudo. ``None`` en runs v1/v2 → la UI cae al markdown.
        "structured_draft": _structured_draft(state),
        # Feature 037 (T405): mapeo completo valida_num → InsightV3 para runs
        # multi-válida. Compat: ``structured_draft`` sigue siendo la primera
        # entrada; los consumidores que no lo conozcan lo ignoran sin romper.
        "structured_drafts": _structured_drafts(state),
        "critic": {
            "approved": getattr(fb, "approved", None) if fb else None,
            "must_block": getattr(fb, "must_block", None) if fb else None,
            "severity": (
                getattr(fb.severity, "value", str(fb.severity)) if fb and fb.severity else None
            ),
        },
    }

    # interrupt() pausa el grafo y suspende esta tarea hasta resume.
    # Al hacer resume con Command(resume=value), `interrupt()` retorna
    # `value` aquí. Esperamos un dict {"decision": "approve|reject", "edits": ...}.
    decision: Any = interrupt(payload)

    if not isinstance(decision, dict):
        decision = {"decision": str(decision), "edits": None}

    return {"hitl_decision": decision}


__all__ = ["hitl_gate_review", "NODE_NAME"]
