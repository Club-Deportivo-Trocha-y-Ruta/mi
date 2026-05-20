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
    explain = bool(state.get("explain_mode", False))
    return must_block or explain or _always_hitl()


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
