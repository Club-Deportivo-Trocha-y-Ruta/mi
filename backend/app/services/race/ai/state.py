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

from app.models.athlete_ai_insight import InsightConfidence
from app.services.race.schemas import AnalysisOutput, CriticFeedback


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
    # Ancla explícita al evento analizado (``race_events.id``). La resuelven
    # los routers de lanzamiento y DEBE viajar en el schema: LangGraph
    # descarta las claves que no están declaradas aquí, y sin ella el
    # pipeline solo puede identificar la carrera por ``sequence_number`` —
    # que NO es único dentro de una temporada (feature 014: la válida 1 de
    # copa y un campeonato comparten ``sequence_number=1``). Su ausencia
    # causaba dos fallos: ``persist_insight`` guardaba ``event_id=NULL`` y
    # ``load_race_data`` recortaba el contexto histórico por la fecha del
    # evento MÁS TARDÍO que compartiera el número, filtrando carreras
    # posteriores dentro de un análisis retrospectivo.
    event_id: int | None
    coach_id: int  # audit
    explain_mode: bool
    # Edad cronológica del atleta calculada en el router desde birth_date.
    # NULL → fallback warning en analyst_agent.
    athlete_age: int | None
    # Feature 011: grupo LTAD real (derivado de age_decimal en el router) y
    # fase madurativa real (último registro antropométrico, None si no hay).
    # Inyectados en initial_state por los routers de lanzamiento.
    ltad_group: str
    maturation_status: str | None

    # ---- Derivado por nodos ----
    raw_data: list[dict]
    competitor_id: int
    category_id: int
    anonymized_data: dict
    mapping: dict[str, int]  # pseudónimo → id; NUNCA al LLM
    metrics: dict
    # Feature 011: condiciones registradas por válida {valida_num: {...}}.
    # Producido por load_race_data; weather_notes scrubeado por anonymize.
    event_conditions: dict[int, dict]

    memory: list[str]  # últimos 3 insights del atleta
    # Feature 037 (T104): últimos 3 insights v3 aprobados (con structured_json),
    # cada uno {headline, coach_question, coach_answer_text, coach_rating,
    # valida_label, generated_at}. [] si no hay insights v3 previos o si la
    # query best-effort falló. Poblado por recall_memory.
    coach_dialogue: list[dict]

    draft_analysis: AnalysisOutput | None
    critic_feedback: CriticFeedback | None
    final_analysis: AnalysisOutput | None
    # Feature 011: un verdicto por draft (válida) — el critic v2 itera todos
    # los per_valida_drafts. critic_feedback singular queda como compat v1.
    per_valida_verdicts: dict[int, CriticFeedback]
    # Confianza computada determinísticamente por válida (post-critic).
    confidence: dict[int, InsightConfidence] | InsightConfidence | str | None

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

    # ---- v3: contexto causal por-atleta (feature 037, T103) ----
    # "valida" (default) | "season" — determina la fecha de referencia y la
    # ventana usada por load_athlete_context (28 días vs. temporada completa).
    analysis_kind: str

    # Maduración del atleta a la fecha de referencia — ver
    # data-model.md §AnthroContext. NUNCA incluye weight_kg/bmi/nutritional_status.
    # None cuando el atleta no tiene registros hasta esa fecha.
    anthro_context: dict[str, Any] | None

    # Agregados de asistencia/RPE/rúbricas/foco técnico en la ventana previa
    # al evento — ver data-model.md §TrainingWindow. None cuando el atleta no
    # tiene ninguna fila de asistencia en la ventana.
    training_window: dict[str, Any] | None

    # Catálogo del club (skills técnicas, bloques de fuerza, plantillas de
    # intervalos) para que las acciones sugeridas referencien recursos reales.
    catalog_context: dict[str, Any]

    # Nombres reales de TODOS los atletas del club + sus padres/acudientes —
    # superset de forbidden_names. NUNCA al LLM; solo scrubbing/guardrails.
    club_forbidden_names: list[str]

    # ---- Outputs ----
    rendered_markdown: str
    notified: bool
    no_data_for_season: bool
    status: str

    # ---- v3 (feature 037, T101): input ----
    # Sexo del atleta ("M"|"F") → resuelve athlete_ref ("el deportista" |
    # "la deportista") en el prompt v2/v3. None → default "la deportista".
    athlete_sex: str | None
    # ---- v3: compute_metrics (T102) ----
    # {event_id (str): FieldMetrics} — percentil, posición esperada, gap a
    # P1/P3/mediana, fuerza de campo. Ver data-model.md §FieldMetrics.
    field_context: dict

    # ---- v3: analyst_agent ----
    # {valida_num (0=season): InsightV3} — drafts estructurados v3. El
    # analyst v3 también rellena per_valida_drafts (AnalysisOutput) para
    # que HITL/persist/render sigan funcionando sin cambios (compat).
    per_valida_drafts_v3: dict[int, Any]
    # Tokens numéricos presentes en el prompt renderizado, por válida —
    # insumo del precheck determinista de grounding del critic v3.
    grounding_numbers: dict[int, list[str]]

    # ---- v3: critic_agent ----
    # Issues detectados por los prechecks deterministas (Python, sin LLM),
    # por válida — se pasan al critic LLM para que no los repita.
    precheck_issues: dict[int, list[Any]]


__all__ = ["RaceAnalystState"]
