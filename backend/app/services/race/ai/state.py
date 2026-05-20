"""TypedDict :class:`RaceAnalystState` — estado del grafo LangGraph (F4).

Diseño:

- ``total=False`` para que los nodos solo escriban las claves que les
  corresponden. LangGraph fusiona dict updates devueltos por cada nodo
  con merge superficial (sin reducers custom para este grafo lineal).
- Claves de **input** llegan en el ``invoke`` inicial.
- Claves **derivadas** las pueblan los nodos 2..7 secuencialmente.
- Claves de **audit / observability** (``events``, ``errors``,
  ``aggregate_metrics``) son listas/dicts que cada nodo **extiende**
  via las funciones helpers de :mod:`app.services.race.ai.events`.

Privacidad (CLAUDE.md):
- ``mapping`` (pseudónimo → id real) se mantiene en el estado para que
  el nodo ``rehydrate_names`` pueda revertirlo al final, pero **nunca**
  se serializa hacia el LLM ni se emite en ``events``.
- ``raw_data`` siempre se anonimiza antes de exponerse al modelo.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.services.race.schemas import AnalysisOutput, Citation, CriticFeedback


class RaceAnalystState(TypedDict, total=False):
    """Estado mutable del grafo ``race-analyst``.

    El grafo es secuencial (no fork-join), por lo que basta con merge
    de dict para fusionar updates. Si en F8 metemos paralelismo
    (ramas analyst + critic en paralelo), habrá que migrar a
    ``Annotated[list, operator.add]`` para campos acumulables.
    """

    # ---- Input ----
    athlete_id: int
    season: int
    valida_nums: list[int] | None
    coach_id: int  # audit
    explain_mode: bool

    # ---- Derivado por nodos ----
    raw_data: list[dict]
    competitor_id: int
    category_id: int
    anonymized_data: dict
    mapping: dict[str, int]  # pseudónimo → id; NUNCA al LLM
    metrics: dict

    principles: list[Citation]
    memory: list[str]  # últimos 3 insights del atleta

    draft_analysis: AnalysisOutput | None
    critic_feedback: CriticFeedback | None
    final_analysis: AnalysisOutput | None

    # ---- HITL ----
    hitl_decision: dict | None  # poblado por el coach via Command(resume=...)

    # ---- Audit / observability ----
    run_id: str
    errors: list[dict]  # [{node, error, timestamp}]
    events: list[dict]  # stream para polling: [{seq, ts, type, payload}]
    aggregate_metrics: dict  # totales tokens/cost/latency

    # ---- Outputs ----
    rendered_markdown: str
    notified: bool


__all__ = ["RaceAnalystState"]
