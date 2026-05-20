"""Grafo principal LangGraph del módulo agéntico race (F4 §4.3).

Topología (lineal con conditional edges para error handling y fallback):

    validate_input
        ├─ errors? → END
        └─ ok    → load_race_data → anonymize → compute_metrics
                                 → retrieve_principles → recall_memory
                                 → analyst_agent
                                       ├─ failed? → fallback_render →
                                       │            render_outputs → notify → END
                                       └─ ok    → critic_agent → hitl_gate_review
                                                  (interrupt si must_block / explain_mode)
                                                  → persist_insight → rehydrate_names
                                                  → render_outputs → notify_coach → END

Checkpointer:
- Default: SQLite persistido en ``./data/langgraph_state.sqlite``
  (path override via env :envvar:`LANGGRAPH_STATE_PATH`).
- Tests usan :class:`SqliteSaver` con conexión in-memory.

Para reanudar tras HITL::

    compiled_graph.invoke(
        Command(resume={"decision": "approve"}),
        config={"configurable": {"thread_id": run_id}},
    )
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph

from app.services.race.ai.fallback import deterministic_fallback
from app.services.race.ai.nodes.analyst_agent import analyst_agent
from app.services.race.ai.nodes.anonymize import anonymize
from app.services.race.ai.nodes.compute_metrics import compute_metrics
from app.services.race.ai.nodes.critic_agent import critic_agent
from app.services.race.ai.nodes.hitl_gate_review import hitl_gate_review
from app.services.race.ai.nodes.load_race_data import load_race_data
from app.services.race.ai.nodes.notify_coach import notify_coach
from app.services.race.ai.nodes.persist_insight import persist_insight
from app.services.race.ai.nodes.recall_memory import recall_memory
from app.services.race.ai.nodes.rehydrate_names import rehydrate_names
from app.services.race.ai.nodes.render_outputs import render_outputs
from app.services.race.ai.nodes.retrieve_principles import retrieve_principles
from app.services.race.ai.nodes.validate_input import validate_input
from app.services.race.ai.state import RaceAnalystState

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "./data/langgraph_state.sqlite"


# ---------------------------------------------------------------------------
# Wrappers para nodos con error handling especial
# ---------------------------------------------------------------------------


async def _analyst_agent_with_fallback(state: dict) -> dict[str, Any]:
    """Envuelve analyst_agent: si las 3 retries internas fallan, activa fallback.

    El decorador ``with_retry`` del nodo ya reintenta 3 veces; si re-raise,
    aquí capturamos y construimos un :class:`AnalysisOutput` determinista
    para que el grafo siga avanzando sin romper la UX.
    """
    try:
        return await analyst_agent(state)
    except Exception as exc:
        logger.error("analyst_agent: fallback activado por %s", type(exc).__name__)
        pseudonym = (state.get("anonymized_data") or {}).get("pseudonym", "AtletaAnonimo")
        fallback = deterministic_fallback(pseudonym)
        prior_errors = list(state.get("errors") or [])
        prior_errors.append(
            {
                "node": "analyst_agent",
                "error": type(exc).__name__,
                "message": str(exc)[:200],
                "recovered_with": "deterministic_fallback",
            }
        )
        return {
            "draft_analysis": fallback,
            "errors": prior_errors,
        }


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------


def _after_validate(state: dict) -> str:
    """Si hay errors → END. Si no → load_race_data."""
    if state.get("errors"):
        return END
    return "load_race_data"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _resolve_db_path() -> Path:
    return Path(os.environ.get("LANGGRAPH_STATE_PATH", DEFAULT_DB_PATH))


async def _build_default_checkpointer():
    """Construye el AsyncSqliteSaver con conexión persistente.

    Asegura que el directorio existe. Devuelve la instancia ready
    con ``setup()`` ejecutado.

    Nota: LangGraph 1.2 requiere AsyncSqliteSaver (NO SqliteSaver) cuando
    el grafo se invoca con ``ainvoke``. SqliteSaver es solo síncrono.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(db_path))
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver


def build_graph(checkpointer: Optional[Any] = None):
    """Construye y compila el grafo race-analyst.

    Args:
        checkpointer: opcional. Si se pasa, debe ser un saver compatible
            con ``ainvoke`` (AsyncSqliteSaver, MemorySaver, etc.).
            Si ``None``, NO se setea checkpointer en la compilación —
            el caller debe envolver con :func:`build_graph_with_default_saver`
            (async) para obtener el AsyncSqliteSaver default.

    Returns:
        Grafo compilado. Sin checkpointer no soporta interrupts persistidos.
    """
    sg: StateGraph = StateGraph(RaceAnalystState)

    # Registrar nodos.
    sg.add_node("validate_input", validate_input)
    sg.add_node("load_race_data", load_race_data)
    sg.add_node("anonymize", anonymize)
    sg.add_node("compute_metrics", compute_metrics)
    sg.add_node("retrieve_principles", retrieve_principles)
    sg.add_node("recall_memory", recall_memory)
    sg.add_node("analyst_agent", _analyst_agent_with_fallback)
    sg.add_node("critic_agent", critic_agent)
    sg.add_node("hitl_gate_review", hitl_gate_review)
    sg.add_node("persist_insight", persist_insight)
    sg.add_node("rehydrate_names", rehydrate_names)
    sg.add_node("render_outputs", render_outputs)
    sg.add_node("notify_coach", notify_coach)

    # Edges.
    sg.add_edge(START, "validate_input")
    sg.add_conditional_edges(
        "validate_input",
        _after_validate,
        {END: END, "load_race_data": "load_race_data"},
    )
    sg.add_edge("load_race_data", "anonymize")
    sg.add_edge("anonymize", "compute_metrics")
    sg.add_edge("compute_metrics", "retrieve_principles")
    sg.add_edge("retrieve_principles", "recall_memory")
    sg.add_edge("recall_memory", "analyst_agent")
    sg.add_edge("analyst_agent", "critic_agent")
    sg.add_edge("critic_agent", "hitl_gate_review")
    sg.add_edge("hitl_gate_review", "persist_insight")
    sg.add_edge("persist_insight", "rehydrate_names")
    sg.add_edge("rehydrate_names", "render_outputs")
    sg.add_edge("render_outputs", "notify_coach")
    sg.add_edge("notify_coach", END)

    if checkpointer is not None:
        return sg.compile(checkpointer=checkpointer)
    return sg.compile()


async def build_graph_with_default_saver():
    """Versión async que monta el AsyncSqliteSaver default.

    Usar al startup de FastAPI (en F5)::

        compiled = await build_graph_with_default_saver()
    """
    saver = await _build_default_checkpointer()
    return build_graph(checkpointer=saver)


# Singleton del grafo runtime (cargado lazy en el primer call para no
# requerir DB ni env vars al importar el módulo).
_compiled_graph: Any = None


async def get_compiled_graph():
    """Lazy singleton async del grafo compilado con checkpointer default."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = await build_graph_with_default_saver()
    return _compiled_graph


__all__ = [
    "build_graph",
    "build_graph_with_default_saver",
    "get_compiled_graph",
    "DEFAULT_DB_PATH",
]
