"""Capa agéntica race-results v2 (Fase 4).

Exports principales:
- :class:`RaceAnalystState` — TypedDict del grafo.
- :func:`build_graph` — factory del grafo compilado.
- :func:`get_compiled_graph` — singleton lazy.
- :func:`set_db_factory` — inyección de sesión async para nodos.
"""

from app.services.race.ai.db import set_db_factory  # noqa: F401
from app.services.race.ai.graph import (  # noqa: F401
    build_graph,
    build_graph_with_default_saver,
    get_compiled_graph,
)
from app.services.race.ai.state import RaceAnalystState  # noqa: F401

__all__ = [
    "RaceAnalystState",
    "build_graph",
    "build_graph_with_default_saver",
    "get_compiled_graph",
    "set_db_factory",
]
