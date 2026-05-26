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

    Campos v2 añadidos (race-results-v2-foundation):
    - ``per_valida_drafts``: dict ``{valida_num: AnalysisOutput}`` emitido
      por ``analyst_agent`` en modo v2. Persiste una fila distinta por
      válida en ``persist_insight``.
    - ``forbidden_names``: lista de nombres reales cargados dinámicamente
      desde DB (athlete.full_name, athlete.nickname, padres). Se inyectan
      en los guardrails post-generación; NUNCA van al LLM ni a los logs.
    - ``prompt_version``: versión del prompt activa. Default
      ``race_analyst_v1`` para compat con flujos existentes.

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
    # Edad cronológica del atleta calculada en el router desde birth_date.
    # NULL → fallback warning en analyst_agent + retrieve_principles.
    athlete_age: int | None

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

    # ---- v2: análisis por válida + privacidad ----
    # Dict {valida_num: AnalysisOutput} emitido por analyst_agent en modo v2.
    # Cada entrada produce una fila independiente en athlete_ai_insights.
    per_valida_drafts: dict[int, AnalysisOutput] | None

    # Nombres reales prohibidos: cargados desde DB antes de invocar el LLM.
    # Alimentan guardrails._RACE_V2_RULES. NUNCA se pasan al modelo.
    forbidden_names: list[str]

    # Versión del prompt activa. Default "race_analyst_v1" para compat.
    # "race_analyst_v2" activa flujo por-válida con 4 secciones nuevas.
    prompt_version: str

    # ---- v2: contexto de temporada completa ----
    # Resultados de TODAS las válidas de la temporada para el atleta
    # (sin filtrar por valida_nums del set lanzado). Usado en sección
    # "Recorrido hasta acá" para construir tendencia longitudinal real.
    full_season_results: list[dict] | None

    # COUNT(DISTINCT valida_num) de resultados válidos (excluye DNS/DNF)
    # de TODA la temporada, no solo el set lanzado.
    season_validas_count: int

    # True si el atleta tiene exactamente 1 valid en TODA la temporada.
    # Regla N=1 aplica cuando es True — independiente del tamaño del set.
    is_first_in_season: bool

    # ---- Outputs ----
    rendered_markdown: str
    notified: bool
    no_data_for_season: bool
    status: str


__all__ = ["RaceAnalystState"]
