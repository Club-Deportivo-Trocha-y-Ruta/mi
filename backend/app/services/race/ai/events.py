"""Stream de eventos para polling del coach (F4 §4.2 evento+decorador).

Cada nodo emite ``node_start`` y ``node_end`` (o ``node_error``) al
estado a través de :func:`emit_event`. El endpoint
``GET /agent-runs/{run_id}/events?since=N`` (F5) consume estos eventos
en orden monotónico de ``seq``.

Estructura de un evento::

    {
        "seq": int,        # auto-incremental por run
        "ts": str,         # ISO8601 UTC
        "type": str,       # node_start | node_end | node_error | hitl_request | done
        "node": str,       # nombre del nodo (None para eventos globales)
        "payload": dict,   # contenido — NUNCA PII real
    }

Privacidad:
- El payload de ``node_end`` puede incluir ``pseudonym`` pero NO nombre
  real. El test sentinela (``test_anonymize.py``) valida esto.
- ``errors`` en payload solo lleva el ``type(exc).__name__`` y un mensaje
  truncado (≤200 chars).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, Optional

from langgraph.errors import GraphInterrupt

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(
    state: dict,
    type_: str,
    node: Optional[str] = None,
    payload: Optional[dict] = None,
) -> dict:
    """Agrega un evento al ``state["events"]`` con ``seq`` monotónico.

    Mutación in-place del state para mantener consistencia con LangGraph
    (los updates de nodo se hacen vía return dict, pero los wrappers
    pueden actualizar directamente cuando el nodo aún no devolvió).

    Retorna el evento creado.
    """
    events = state.setdefault("events", [])
    seq = (events[-1]["seq"] + 1) if events else 1
    ev = {
        "seq": seq,
        "ts": _now_iso(),
        "type": type_,
        "node": node,
        "payload": payload or {},
    }
    events.append(ev)
    return ev


def with_events(node_name: str) -> Callable:
    """Decorador que emite ``node_start`` / ``node_end`` / ``node_error``.

    Importante: el nodo recibe ``state`` y debe retornar un ``dict``
    (LangGraph patch update). El decorador inyecta los eventos al
    state dict ANTES y DESPUÉS de la ejecución, y los acumula también
    en el update returned para que LangGraph propague el cambio en el
    checkpointing.

    Si el nodo lanza una excepción:
    1. Se emite ``node_error`` con ``{exc: ClassName, msg: first 200 chars}``.
    2. Se acumula en ``state["errors"]``.
    3. Se re-raise para que el wrapper de grafo decida (fallback / END).

    Caso especial — ``GraphInterrupt`` (LangGraph HITL):
    LangGraph implementa ``interrupt()`` lanzando ``GraphInterrupt`` para
    pausar el grafo. NO es un error: es flujo de control. Se emite
    ``hitl_request`` (no ``node_error``, no ``node_end``) y se re-raise
    para que LangGraph procese la suspensión.
    """

    def decorator(fn: Callable[[dict], Awaitable[dict]]) -> Callable[[dict], Awaitable[dict]]:
        @wraps(fn)
        async def wrapper(state: dict) -> dict:
            emit_event(state, "node_start", node=node_name)
            try:
                update = await fn(state) or {}
            except GraphInterrupt:
                # interrupt() del nodo: flujo de control, no error.
                # Emitimos hitl_request (sin payload de excepción) y
                # re-raise para que LangGraph suspenda el grafo.
                emit_event(state, "hitl_request", node=node_name)
                raise
            except Exception as exc:
                logger.exception("Nodo %s falló", node_name)
                errors = state.setdefault("errors", [])
                err_record = {
                    "node": node_name,
                    "error": type(exc).__name__,
                    "message": str(exc)[:200],
                    "timestamp": _now_iso(),
                }
                errors.append(err_record)
                emit_event(
                    state,
                    "node_error",
                    node=node_name,
                    payload={"exc": err_record["error"], "msg": err_record["message"]},
                )
                # Importante: re-raise para que el grafo pueda enrutar a
                # fallback o terminar el run.
                raise

            emit_event(state, "node_end", node=node_name)
            # Propagamos events + errors en el update para LangGraph.
            update.setdefault("events", state.get("events", []))
            if "errors" in state:
                update.setdefault("errors", state["errors"])
            return update

        return wrapper

    return decorator


__all__ = ["emit_event", "with_events"]
