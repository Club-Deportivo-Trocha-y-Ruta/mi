"""Nodo 7: ``analyst_agent`` — invoca :class:`RaceAnalystAgent`.

Construye :class:`AnalysisInput` a partir del state (datos ya
anonimizados, métricas, principios, memoria) e invoca el agente. Si el
agente falla con excepción no-retryable, ``with_events`` la propaga y
el grafo enruta a fallback (ver ``graph.py``).

Acumula tokens / cost / latency en ``state["aggregate_metrics"]``.

v2 (``state["prompt_version"] == "race_analyst_v2"``)
======================================================
En vez de un único análisis agregado, lanza ``asyncio.gather`` con una
llamada por cada válida en ``state["valida_nums"]`` (cap=4). Emite
``state["per_valida_drafts"]: dict[int, AnalysisOutput]`` en lugar del
campo singular ``draft_analysis``.

``state["forbidden_names"]`` se carga upstream (nodo load_race_data o
validate_input) y se pasa a los guardrails; NUNCA va al prompt del LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V2,
    PROMPT_VERSION_ANALYST_V3,
    PROMPT_VERSION_SEASON_SUMMARY_V3,
    AnalystV3Input,
    RaceAnalystAgent,
    v3_prompt_version,
)
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.race_labels import build_race_label
from app.services.race.schemas import AnalysisInput, LTADGroup

logger = logging.getLogger(__name__)

NODE_NAME = "analyst_agent"

# Cap de válidas por run v2 (debe coincidir con RaceAnalystAgent._V2_CAP).
_V2_CAP = 4

# Mismo cap para v3: el fan-out sigue siendo una llamada por válida.
_V3_CAP = 4

# prompt_version que activan la rama v3 (feature 037, T201).
_V3_PROMPT_VERSIONS = {PROMPT_VERSION_ANALYST_V3, PROMPT_VERSION_SEASON_SUMMARY_V3}


def _resolve_athlete_ref(state: dict) -> str:
    """``athlete_sex`` → referencia de género usada por los prompts.

    Cierra el bug de spec.md §problem 7 ("la deportista" hardcodeado para
    todo atleta): el router inyecta ``athlete_sex`` (``"M"``/``"F"``/None) y
    acá se traduce. Sin dato → "la deportista" (default histórico, sin
    regresión para las filas ya generadas).
    """
    sex = state.get("athlete_sex")
    if isinstance(sex, str) and sex.strip().upper().startswith("M"):
        return "el deportista"
    return "la deportista"


def _resolve_ltad(state: dict) -> LTADGroup:
    raw = state.get("ltad_group")
    if isinstance(raw, LTADGroup):
        return raw
    if isinstance(raw, str):
        try:
            return LTADGroup(raw)
        except ValueError:
            pass
    # Fallback excepcional (feature 011): los routers ahora inyectan ltad_group
    # real desde age_decimal. Llegar aquí significa que initial_state no lo trajo
    # → log de warning para detectarlo, sin romper el grafo.
    logger.warning(
        "analyst_agent: ltad_group ausente o inválido en state (valor=%r); "
        "usando fallback=bambino. Verificar que el router inyecta 'ltad_group'.",
        raw,
    )
    return LTADGroup.BAMBINO


def _resolve_age(state: dict) -> int:
    age = state.get("athlete_age")
    if isinstance(age, int) and 6 <= age <= 20:
        return age
    logger.warning(
        "analyst_agent: athlete_age ausente o fuera de rango en state "
        "(valor=%r); usando fallback=12. Verificar que el router inyecta "
        "'athlete_age' en initial_state (Fix 1).",
        age,
    )
    return 12


# ---------------------------------------------------------------------------
# Resolución de la carrera analizada (feature 039, T035)
# ---------------------------------------------------------------------------
#
# Desde spec 014 la válida I de una copa y un campeonato pueden compartir
# ``sequence_number``, así que ``metrics.progression`` puede traer dos filas
# con el mismo ``valida_num``. Reglas de ``contracts/ai-context.md``:
#
#   1. Con ``state["event_id"]`` (lanzamiento anclado desde la competencia),
#      la fila analizada es la que tiene ese ``event_id`` — nunca solo por
#      ``valida_num``.
#   2. Sin ancla, ``valida_num`` resuelve SOLO entre filas de copa; un
#      campeonato únicamente se analiza vía lanzamiento anclado.
#
# Ambas reglas degradan sin romper los states viejos: una fila sin
# ``series_kind`` cuenta como copa y, si el ancla no aparece en la
# progresión, se cae al match por ``valida_num``.


def _is_championship_row(row: dict) -> bool:
    """``True`` si la fila de progresión corresponde a un campeonato.

    Tolerante con filas legadas: ``series_kind`` ausente/desconocido ⇒ copa.
    """
    kind = row.get("series_kind")
    kind_value = getattr(kind, "value", kind)
    return str(kind_value or "").lower() == RaceSeriesKind.championship.value


def _same_event(row: dict, event_id: Any) -> bool:
    """Compara ``row["event_id"]`` con el ancla tolerando int vs str."""
    raw = row.get("event_id")
    if raw is None or event_id is None:
        return False
    return str(raw) == str(event_id)


def _cup_rows_for_valida(rows: list[dict], valida_num: int) -> list[dict]:
    """Filas de copa con ese ``valida_num`` (regla 2)."""
    return [
        r
        for r in rows
        if r.get("valida_num") == valida_num and not _is_championship_row(r)
    ]


def _records_for_valida(
    rows: list[dict], valida_num: int, anchored_event_id: Any
) -> list[dict]:
    """Filas de progresión que describen la carrera analizada.

    ``valida_num == 0`` es el sentinel de "toda la progresión" (temporada)
    y se respeta tal cual. Con ancla se devuelve exactamente la fila
    anclada; sin ella, solo las filas de copa de esa válida.
    """
    if valida_num == 0:
        return list(rows)
    if anchored_event_id is not None:
        anchored = [r for r in rows if _same_event(r, anchored_event_id)]
        if anchored:
            return anchored
    return _cup_rows_for_valida(rows, valida_num)


def _resolve_race_row(
    rows: list[dict], valida_num: int, anchored_event_id: Any
) -> dict | None:
    """Fila única de la carrera analizada (``None`` si no hay candidata)."""
    records = _records_for_valida(rows, valida_num, anchored_event_id)
    return records[0] if records else None


def _valida_label(race_row: dict | None, field_metrics: dict | None) -> str | None:
    """Etiqueta canónica de la carrera analizada para el prompt v3.

    Delega en ``race_labels.build_race_label`` con el ``series_level``, así
    un campeonato nacional se rotula ``"Cto. Nal. — {ciudad}"`` y nunca
    como una válida más (AC-2.3 / regla 10 del prompt v3). Devuelve ``None``
    cuando no hay metadatos de serie — ahí el agente cae en
    ``series_label_v3(field_metrics)``, el comportamiento previo.
    """
    sources = [s for s in (race_row, field_metrics) if isinstance(s, dict)]
    if not sources:
        return None

    def pick(key: str) -> Any:
        for source in sources:
            value = source.get(key)
            if value not in (None, ""):
                return value
        return None

    kind_raw = pick("series_kind")
    if kind_raw is None and pick("is_championship"):
        kind_raw = RaceSeriesKind.championship.value
    if kind_raw is None:
        return None

    level_raw = pick("series_level")
    try:
        kind = RaceSeriesKind(str(getattr(kind_raw, "value", kind_raw)))
        level = (
            RaceSeriesLevel(str(getattr(level_raw, "value", level_raw)))
            if level_raw
            else RaceSeriesLevel.departmental
        )
        sequence_number = int(pick("valida_num") or 1)
    except (ValueError, TypeError):
        return None

    return build_race_label(kind, sequence_number, pick("location"), level=level)


def _build_input(
    state: dict,
    progression_records: list | None = None,
    race_meta: str | None = None,
) -> AnalysisInput:
    """Construye AnalysisInput desde el state del grafo.

    Feature 011: ``race_meta`` (condiciones formateadas de ESTA válida) y
    ``maturation_status`` (fase madurativa real, leída del state) se inyectan
    explícitamente. Ambos pueden ser ``None`` (sin condiciones / sin registro
    antropométrico) y en ese caso el prompt no afirma esos hechos.
    """
    anon = state.get("anonymized_data") or {}
    pseudonym = anon.get("pseudonym") or "AtletaAnonimo"
    metrics = state.get("metrics") or {}
    records = progression_records if progression_records is not None else (
        metrics.get("progression", []) or []
    )
    podium_ctx = state.get("podium_context") or {}
    memory = state.get("memory") or []

    # Season context (T014): inject comparative data computed by compute_metrics.
    season_comparative: list = state.get("season_comparative") or []
    progression_assessment: str = (
        state.get("progression_assessment") or "first_reference"
    )

    maturation_status = state.get("maturation_status")

    return AnalysisInput(
        athlete_pseudonym=pseudonym,
        age=_resolve_age(state),
        ltad_group=_resolve_ltad(state),
        progression_df_records=records,
        podium_context=podium_ctx,
        memory_recent_insights=memory[:10],
        explain_mode=bool(state.get("explain_mode", False)),
        season_comparative=season_comparative,
        progression_assessment=progression_assessment,
        race_meta=race_meta,
        maturation_status=maturation_status,
        # Feature 037 (T201): cierra el cableado que T101 dejó abierto —
        # AnalysisInput.athlete_ref existía pero nadie lo llenaba desde
        # state["athlete_sex"], así que todo insight decía "la deportista".
        athlete_ref=_resolve_athlete_ref(state),
        athlete_id=state["athlete_id"],
        season=state["season"],
    )


def _accumulate_metrics(aggregate: dict, run_metrics: Any) -> dict:
    """Suma métricas de un RunMetrics al dict acumulado del state."""
    aggregate.setdefault("tokens_in_total", 0)
    aggregate.setdefault("tokens_out_total", 0)
    aggregate.setdefault("latency_ms_total", 0)
    aggregate.setdefault("cost_usd_total", 0.0)
    aggregate["tokens_in_total"] += run_metrics.tokens_in
    aggregate["tokens_out_total"] += run_metrics.tokens_out
    aggregate["latency_ms_total"] += run_metrics.latency_ms
    aggregate["cost_usd_total"] = round(
        aggregate["cost_usd_total"] + run_metrics.cost_usd, 6
    )
    aggregate["prompt_version_analyst"] = run_metrics.prompt_version
    return aggregate


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def analyst_agent(state: dict) -> dict[str, Any]:
    prompt_version: str = state.get("prompt_version") or "race_analyst_v1"

    # ------------------------------------------------------------------ v3
    if prompt_version in _V3_PROMPT_VERSIONS:
        return await _analyst_agent_v3(state)

    # ------------------------------------------------------------------ v2
    if prompt_version == PROMPT_VERSION_ANALYST_V2:
        return await _analyst_agent_v2(state)

    # ------------------------------------------------------------------ v1
    input_ = _build_input(state)
    agent = state.get("_analyst_agent") or RaceAnalystAgent()
    output, run_metrics = await agent.invoke(input_)

    aggregate = _accumulate_metrics(dict(state.get("aggregate_metrics") or {}), run_metrics)

    return {
        "draft_analysis": output,
        "aggregate_metrics": aggregate,
    }


async def _analyst_agent_v2(state: dict) -> dict[str, Any]:
    """Implementación v2: gather por válida con cap=4.

    Emite ``per_valida_drafts`` además de ``draft_analysis`` (el primero
    en la lista) para compatibilidad con nodos downstream que leen
    ``draft_analysis``.

    La regla N=1 se basa en ``is_first_in_season`` (toda la temporada)
    en vez del tamaño del set lanzado. ``full_season_results`` alimenta
    el contexto de la sección "Recorrido hasta acá".
    """
    valida_nums: list[int] = list(state.get("valida_nums") or [])

    if len(valida_nums) > _V2_CAP:
        raise ValueError(
            f"Cap v2: máximo {_V2_CAP} válidas por análisis. "
            "Genera resumen temporada para visión global."
        )

    forbidden_names: list[str] = list(state.get("forbidden_names") or [])
    agent: RaceAnalystAgent = state.get("_analyst_agent") or RaceAnalystAgent(
        prompt_version=PROMPT_VERSION_ANALYST_V2
    )

    # is_first_in_season desde state (cargado en load_race_data).
    is_first_in_season: bool = bool(state.get("is_first_in_season", False))
    season_validas_count: int = int(state.get("season_validas_count", 0))

    # Progresión del set lanzado (para "Qué pasó").
    metrics_base = state.get("metrics") or {}
    progression_all: list[dict] = metrics_base.get("progression", []) or []

    # Progresión completa de la temporada (para "Recorrido hasta acá").
    full_season_results: list[dict] | None = state.get("full_season_results")

    # Condiciones registradas por válida (feature 011) — formateadas a un
    # bloque markdown o None (omisión + veto anti-fabricación).
    from app.services.race.agents.analyst import format_race_meta

    event_conditions: dict[int, dict] = state.get("event_conditions") or {}

    # T021 — scrubbed per-válida coach notes (already scrubbed by anonymize).
    # Key present → coach wrote a note for that válida.
    # Key absent or value None → no note; do NOT fabricate context (FR-009).
    coach_notes_by_valida: dict[int, str | None] = (
        state.get("coach_notes_by_valida") or {}
    )

    # Construir pares (valida_num, AnalysisInput) filtrando por válida.
    # T035: la fila se resuelve por el ancla state["event_id"] y, sin ancla,
    # solo entre filas de copa (vn == 0 sigue significando "toda la progresión").
    anchored_event_id = state.get("event_id")
    pairs: list[tuple[int, AnalysisInput]] = []
    for vn in valida_nums:
        records_for_vn = _records_for_valida(progression_all, vn, anchored_event_id)
        race_meta = format_race_meta(event_conditions.get(vn))

        # T021 — append scrubbed coach note to race_meta so the analyst
        # has qualitative coach context alongside race conditions.
        # When note is absent/None, race_meta is unchanged (FR-009).
        coach_note = coach_notes_by_valida.get(vn)
        if coach_note:
            note_line = f"- Nota del entrenador: {coach_note.strip()}"
            race_meta = f"{race_meta}\n{note_line}" if race_meta else note_line

        inp = _build_input(
            state, progression_records=records_for_vn, race_meta=race_meta
        )
        pairs.append((vn, inp))

    if not pairs:
        # Sin datos: emitir fallback por cada válida solicitada.
        from app.services.race.ai.fallback import (
            deterministic_fallback,
            deterministic_fallback_n1,
        )
        anon = state.get("anonymized_data") or {}
        pseudonym = anon.get("pseudonym") or "AtletaAnonimo"
        fallback = (
            deterministic_fallback_n1(pseudonym)
            if is_first_in_season
            else deterministic_fallback(pseudonym)
        )
        per_valida = {vn: fallback for vn in (valida_nums or [0])}
        return {"per_valida_drafts": per_valida, "draft_analysis": fallback}

    results: dict[int, tuple] = await agent.invoke_per_valida(
        pairs,
        forbidden_names=forbidden_names,
        is_first_in_season=is_first_in_season,
        full_season_records=full_season_results,
        athlete_age=state.get("athlete_age"),
    )

    aggregate = dict(state.get("aggregate_metrics") or {})
    per_valida_drafts: dict[int, Any] = {}
    first_output = None
    for vn, (out, met) in results.items():
        per_valida_drafts[vn] = out
        aggregate = _accumulate_metrics(aggregate, met)
        if first_output is None:
            first_output = out

    aggregate["is_first_in_season"] = is_first_in_season
    aggregate["season_validas_count"] = season_validas_count

    return {
        "per_valida_drafts": per_valida_drafts,
        "draft_analysis": first_output,  # compat con nodos v1 downstream
        "aggregate_metrics": aggregate,
    }


def _field_metrics_by_valida(state: dict) -> dict[int, dict]:
    """``field_context`` (keyed by event_id) → índice por ``valida_num``.

    ``compute_metrics`` indexa por ``event_id`` porque es la única clave
    única; el analista razona por válida. Cuando hay un evento anclado
    (``event_id``) su entrada gana, para no confundir la válida N de copa
    con un campeonato que comparta ``sequence_number``.
    """
    field_context: dict = state.get("field_context") or {}
    by_valida: dict[int, dict] = {}
    for value in field_context.values():
        valida_num = value.get("valida_num") if isinstance(value, dict) else None
        if valida_num is None:
            continue
        by_valida.setdefault(int(valida_num), value)

    anchored_id = state.get("event_id")
    if anchored_id is not None:
        anchored = field_context.get(anchored_id) or field_context.get(str(anchored_id))
        if isinstance(anchored, dict) and anchored.get("valida_num") is not None:
            by_valida[int(anchored["valida_num"])] = anchored
    return by_valida


def _field_metrics_for_row(
    field_context: dict,
    field_by_valida: dict[int, dict],
    race_row: dict | None,
    valida_num: int,
) -> dict | None:
    """Métricas de pelotón de la carrera resuelta.

    Busca primero por el ``event_id`` de la fila analizada — así la válida
    anclada usa SU entrada y no la de otra carrera que comparta
    ``valida_num``. Sin coincidencia cae al índice por válida.
    """
    event_id = race_row.get("event_id") if isinstance(race_row, dict) else None
    if event_id is not None:
        entry = field_context.get(event_id) or field_context.get(str(event_id))
        if isinstance(entry, dict):
            return entry
    return field_by_valida.get(valida_num)


def _season_rows_for_prompt(state: dict) -> list[dict]:
    """Filas de temporada con métricas de pelotón, ordenadas cronológicamente."""
    field_context: dict = state.get("field_context") or {}
    rows = [v for v in field_context.values() if isinstance(v, dict)]
    return sorted(rows, key=lambda r: (r.get("event_date") or "", r.get("valida_num") or 0))


def _race_meta_for_valida(state: dict, valida_num: int) -> str | None:
    """Condiciones registradas + nota del coach para esa válida (o ``None``)."""
    from app.services.race.agents.analyst import format_race_meta

    event_conditions: dict[int, dict] = state.get("event_conditions") or {}
    race_meta = format_race_meta(event_conditions.get(valida_num))

    coach_notes: dict[int, str | None] = state.get("coach_notes_by_valida") or {}
    note = coach_notes.get(valida_num)
    if note:
        note_line = f"- Nota del entrenador: {note.strip()}"
        race_meta = f"{race_meta}\n{note_line}" if race_meta else note_line
    return race_meta


def _build_v3_inputs(state: dict, athlete_ref: str) -> list[AnalystV3Input]:
    """Construye una entrada v3 por válida (o una sola para la temporada)."""
    analysis_kind = state.get("analysis_kind") or "valida"
    metrics_base = state.get("metrics") or {}
    progression_all: list[dict] = metrics_base.get("progression", []) or []
    season_rows = _season_rows_for_prompt(state)
    memory: list[str] = list(state.get("memory") or [])[:3]

    common = {
        "athlete_ref": athlete_ref,
        "age": state.get("athlete_age"),
        "ltad_group": str(_resolve_ltad(state).value),
        "season": state.get("season"),
        "validas_count": int(state.get("season_validas_count") or 0),
        "season_rows": season_rows,
        "anthro_context": state.get("anthro_context"),
        "training_window": state.get("training_window"),
        "coach_dialogue": list(state.get("coach_dialogue") or []),
        "catalog_context": dict(state.get("catalog_context") or {}),
        "memory_recent_insights": memory,
    }

    if analysis_kind == "season":
        # La temporada no tiene fila de carrera ni lectura de pelotón propia:
        # la tabla de temporada es todo el insumo (spec §US5).
        return [AnalystV3Input(valida_num=0, analysis_kind="season", **common)]

    field_context: dict = state.get("field_context") or {}
    field_by_valida = _field_metrics_by_valida(state)
    anchored_event_id = state.get("event_id")
    inputs: list[AnalystV3Input] = []
    for valida_num in list(state.get("valida_nums") or []):
        race_row = _resolve_race_row(progression_all, valida_num, anchored_event_id)
        # El pelotón se busca por el event_id de la fila resuelta (única clave
        # única); si esa entrada no existe se cae al índice por válida, que ya
        # prefiere el evento anclado.
        field_metrics = _field_metrics_for_row(
            field_context, field_by_valida, race_row, valida_num
        )
        inputs.append(
            AnalystV3Input(
                valida_num=valida_num,
                analysis_kind="valida",
                valida_label=_valida_label(race_row, field_metrics),
                race_row=race_row,
                field_metrics=field_metrics,
                race_meta=_race_meta_for_valida(state, valida_num),
                **common,
            )
        )
    return inputs


async def _analyst_agent_v3(state: dict) -> dict[str, Any]:
    """Implementación v3: draft estructurado (``InsightV3``) por válida.

    Emite las claves nuevas (``per_valida_drafts_v3``, ``grounding_numbers``)
    y, por compatibilidad, sigue llenando ``per_valida_drafts`` /
    ``draft_analysis`` con el markdown renderizado desde el JSON — así HITL,
    persist, rehydrate y render no necesitan saber que hubo un cambio de
    contrato (plan.md §State keys).
    """
    from app.services.race.ai.fallback import deterministic_fallback_v3
    from app.services.race.insight_v3 import (
        insight_v3_sections,
        insight_v3_to_legacy_recommendations,
        render_insight_v3_markdown,
    )
    from app.services.race.schemas import AnalysisOutput

    analysis_kind = state.get("analysis_kind") or "valida"
    prompt_version = v3_prompt_version(analysis_kind)
    athlete_ref = _resolve_athlete_ref(state)

    valida_nums: list[int] = list(state.get("valida_nums") or [])
    if analysis_kind != "season" and len(valida_nums) > _V3_CAP:
        raise ValueError(
            f"Cap v3: máximo {_V3_CAP} válidas por análisis. "
            "Genera resumen temporada para visión global."
        )

    anon = state.get("anonymized_data") or {}
    pseudonym = anon.get("pseudonym") or "AtletaAnonimo"
    forbidden_names: list[str] = list(
        state.get("club_forbidden_names") or state.get("forbidden_names") or []
    )

    inputs = _build_v3_inputs(state, athlete_ref)
    agent: RaceAnalystAgent = state.get("_analyst_agent") or RaceAnalystAgent(
        prompt_version=prompt_version
    )

    if not inputs:
        # Sin válidas seleccionadas: emitimos el fallback determinista para el
        # sentinel 0 en vez de dejar el run sin draft.
        fallback = deterministic_fallback_v3(analysis_kind=analysis_kind)
        markdown = render_insight_v3_markdown(fallback, athlete_ref)
        compat = AnalysisOutput(
            pseudonym=pseudonym,
            sections=insight_v3_sections(fallback),
            citations_used=[],
            recommendations=insight_v3_to_legacy_recommendations(fallback),
            risk_flags=[],
            raw_markdown=markdown,
            word_count=len(markdown.split()),
        )
        return {
            "per_valida_drafts_v3": {0: fallback},
            "grounding_numbers": {0: []},
            "per_valida_drafts": {0: compat},
            "draft_analysis": compat,
        }

    results = await agent.invoke_v3(inputs, forbidden_names=forbidden_names)

    aggregate = dict(state.get("aggregate_metrics") or {})
    per_valida_drafts_v3: dict[int, Any] = {}
    grounding_numbers: dict[int, list[str]] = {}
    per_valida_drafts: dict[int, Any] = {}
    first_output: Any = None

    for valida_num in sorted(results):
        result = results[valida_num]
        insight = result.insight
        markdown = render_insight_v3_markdown(insight, athlete_ref)
        compat = AnalysisOutput(
            pseudonym=pseudonym,
            sections=insight_v3_sections(insight),
            citations_used=[],
            recommendations=insight_v3_to_legacy_recommendations(insight),
            risk_flags=[],
            raw_markdown=markdown,
            word_count=len(markdown.split()),
        )
        per_valida_drafts_v3[valida_num] = insight
        grounding_numbers[valida_num] = list(result.grounding_numbers)
        per_valida_drafts[valida_num] = compat
        aggregate = _accumulate_metrics(aggregate, result.metrics)
        if first_output is None:
            first_output = compat

    aggregate["analysis_kind"] = analysis_kind
    aggregate["season_validas_count"] = int(state.get("season_validas_count") or 0)

    return {
        "per_valida_drafts_v3": per_valida_drafts_v3,
        "grounding_numbers": grounding_numbers,
        "per_valida_drafts": per_valida_drafts,
        "draft_analysis": first_output,  # compat con nodos v1/v2 downstream
        "aggregate_metrics": aggregate,
    }


__all__ = ["analyst_agent", "NODE_NAME"]
