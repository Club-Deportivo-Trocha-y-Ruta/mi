"""Nodo 8: ``critic_agent`` — revisión defensiva del/los draft(s).

Si la feature flag :envvar:`RACE_AGENT_CRITIC_ENABLED` es ``false``,
es un no-op (state sin cambios).

v1: invoca :class:`RaceCriticAgent.invoke` sobre ``draft_analysis`` y guarda
``critic_feedback``.

v2 (feature 011): cuando hay ``per_valida_drafts``, itera TODOS los drafts
(cap=4), construye la verdad de campo (condiciones registradas + fila de
resultado + podio) de cada válida y la pasa a ``invoke_v2``. Emite
``per_valida_verdicts: dict[int, CriticFeedback]`` y mantiene ``critic_feedback``
(verdicto de la primera válida) para compatibilidad con nodos v1 downstream.
"""

from __future__ import annotations

from typing import Any

from app.services.race.agents.analyst import (
    _format_ms_hhmmss,
    format_course_meta,
    format_race_meta,
)
from app.services.race.agents.critic import RaceCriticAgent
from app.services.race.ai.confidence import (
    DataCompleteness,
    compute_confidence,
    compute_confidence_v3,
)
from app.services.race.ai.events import with_events
from app.services.race.ai.grounding import is_adult_age
from app.services.race.ai.prechecks import run_prechecks
from app.services.race.ai.retry import with_retry
from app.services.race.race_labels import series_display_name
from app.services.race.schemas import CriticFeedback, CriticIssueSeverity

NODE_NAME = "critic_agent"

# Cap de válidas revisadas por run (coincide con el cap del analyst v2).
_V2_CAP = 4


def _accumulate(aggregate: dict, run_metrics: Any, *, prompt_key: str) -> dict:
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
    aggregate[prompt_key] = run_metrics.prompt_version
    return aggregate


def _event_ground_truth_label(full_season: list[dict], event_id: Any) -> str:
    """``"Válida N · Copa"`` de un evento de la temporada, para encabezar
    un bloque de verdad de campo agrupado por evento (runs de temporada,
    hotfix identidad de válida). Cae a ``"Evento <id>"`` sin datos de fila.
    """
    row = next((r for r in full_season if r.get("event_id") == event_id), None)
    if row is None:
        return f"Evento {event_id}"
    parts: list[str] = []
    valida_num = row.get("valida_num")
    if valida_num is not None:
        parts.append(f"Válida {valida_num}")
    copa = series_display_name(row.get("series_name"), row.get("series_short_name"))
    if copa:
        parts.append(copa)
    return " · ".join(parts) if parts else f"Evento {event_id}"


def _course_ground_truth(state: dict, valida_num: int) -> list[str]:
    """Circuito registrado tal como lo vio el analista v3 (feature 043).

    Reutiliza ``format_course_meta`` sobre ``course_context``, que nunca
    trae ``course_notes`` — el critic no recibe nada que el analista no viera.
    La temporada (``valida_num=0``) lista un bloque por válida con dato.

    Hotfix identidad de válida: en temporada, ``course_context`` (keyed por
    ``valida_num``) es ambiguo entre copas que comparten número — se prefiere
    ``course_context_by_event`` (keyed por ``event_id``, provisto por
    ``load_race_data`` en runs de temporada) cuando está presente, con
    encabezado ``"Válida N · Copa"`` por evento. Sin esa clave (state viejo o
    pipeline aún sin el fix) se cae al comportamiento previo, keyed por
    válida.
    """
    lines = ["", "### Circuito registrado"]
    if (state.get("analysis_kind") or "valida") == "season":
        by_event: dict[Any, dict] | None = state.get("course_context_by_event")
        if by_event:
            full_season: list[dict] = state.get("full_season_results") or []
            blocks = [
                (event_id, block)
                for event_id in by_event.keys()
                if (block := format_course_meta(by_event.get(event_id)))
            ]
            if not blocks:
                lines.append("sin circuito registrado")
            for event_id, block in blocks:
                lines.append(f"{_event_ground_truth_label(full_season, event_id)}:")
                lines.append(block)
            return lines

        course_context: dict[int, dict] = state.get("course_context") or {}
        blocks = [
            (v, block)
            for v in sorted(course_context.keys())
            if (block := format_course_meta(course_context.get(v)))
        ]
        if not blocks:
            lines.append("sin circuito registrado")
        for v, block in blocks:
            lines.append(f"Válida {v}:")
            lines.append(block)
        return lines

    course_context: dict[int, dict] = state.get("course_context") or {}
    block = format_course_meta(course_context.get(valida_num))
    lines.append(block if block else "sin circuito registrado")
    return lines


def _season_conditions_ground_truth(state: dict) -> list[str]:
    """Condiciones registradas por evento de temporada (hotfix multicopa).

    Espejo de ``_course_ground_truth`` para el bloque de clima/superficie:
    prefiere ``event_conditions_by_event`` (keyed por ``event_id``,
    inequívoco entre copas) sobre ``event_conditions`` (keyed por
    ``valida_num``, ambiguo si dos series comparten número) cuando está
    presente.
    """
    by_event: dict[Any, dict] | None = state.get("event_conditions_by_event")
    if by_event:
        full_season: list[dict] = state.get("full_season_results") or []
        blocks = [
            (event_id, block)
            for event_id in by_event.keys()
            if (block := format_race_meta(by_event.get(event_id)))
        ]
        if not blocks:
            return ["sin condiciones registradas"]
        lines: list[str] = []
        for event_id, block in blocks:
            lines.append(f"{_event_ground_truth_label(full_season, event_id)}:")
            lines.append(block)
        return lines

    event_conditions: dict[int, dict] = state.get("event_conditions") or {}
    blocks = [
        (v, block)
        for v in sorted(event_conditions.keys())
        if (block := format_race_meta(event_conditions.get(v)))
    ]
    if not blocks:
        return ["sin condiciones registradas"]
    lines = []
    for v, block in blocks:
        lines.append(f"Válida {v}:")
        lines.append(block)
    return lines


def _resolve_athlete_row(
    full_season: list[dict], valida_num: int, event_id: Any | None
) -> dict | None:
    """Fila de resultado del atleta para la carrera realmente analizada.

    Hotfix identidad de válida: con ancla (``event_id``) se prefiere la fila
    de ESE evento — evita mezclar, p.ej., Copa A V4 con Copa B V4 cuando
    ambas comparten ``valida_num`` (spec 014). El ancla solo se usa si la
    fila que identifica corresponde al mismo ``valida_num`` que se está
    reportando: en un lanzamiento multi-válida (cap 4) el ancla identifica
    una sola de las hasta 4 válidas del run — las demás siguen resolviéndose
    por ``valida_num`` únicamente (limitación conocida: un solo ancla por
    run no alcanza para desambiguar un cruce de copas en las otras filas;
    lo cubre la escritura de datos de origen ya scoped por serie).
    """
    if event_id is not None:
        anchored = next((r for r in full_season if r.get("event_id") == event_id), None)
        if anchored is not None and anchored.get("valida_num") == valida_num:
            return anchored
    return next((r for r in full_season if r.get("valida_num") == valida_num), None)


def _build_ground_truth(
    state: dict,
    valida_num: int,
    *,
    include_course: bool = False,
    event_id: int | None = None,
) -> str:
    """Construye el bloque de verdad de campo para una válida (feature 011).

    Incluye: condiciones registradas (o "sin condiciones registradas"), la fila
    de resultado del atleta (posición, tiempo, gap al líder, copa) y los
    tiempos de podio del evento foco. Sirve para que el critic detecte
    contradicciones.

    ``include_course`` solo lo activa la rama v3: el analista v2 nunca recibe
    el bloque de circuito, así que su critic tampoco debe verlo.

    ``event_id`` (hotfix identidad de válida, multicopa): ancla explícita al
    evento analizado. Si no se pasa, se usa ``state["event_id"]`` — el ancla
    que setean los lanzamientos por-válida. Con ella, la fila de resultado
    del atleta se busca por evento (no solo por ``valida_num``, ambiguo
    cuando dos copas comparten número — spec 014) y se agrega una línea
    ``"- Copa: <nombre>"`` con el nombre corto (o largo) de la serie.
    """
    is_season = (state.get("analysis_kind") or "valida") == "season"

    lines: list[str] = ["### Condiciones registradas"]
    if is_season:
        lines.extend(_season_conditions_ground_truth(state))
    else:
        event_conditions: dict[int, dict] = state.get("event_conditions") or {}
        conditions_block = format_race_meta(event_conditions.get(valida_num))
        lines.append(conditions_block if conditions_block else "sin condiciones registradas")

    if include_course:
        lines.extend(_course_ground_truth(state, valida_num))

    # Fila de resultado del atleta para esta válida (desde full_season_results).
    full_season: list[dict] = state.get("full_season_results") or []
    resolved_event_id = event_id if event_id is not None else state.get("event_id")
    row = _resolve_athlete_row(full_season, valida_num, resolved_event_id)
    lines.append("")
    lines.append(f"### Resultado del atleta (Válida {valida_num})")
    if row:
        lines.append(f"- Posición: {row.get('position', '—')}")
        lines.append(f"- Tiempo: {_format_ms_hhmmss(row.get('race_time_ms'))}")
        lines.append(
            f"- Gap al líder: {_format_ms_hhmmss(row.get('gap_to_winner_ms'))}"
        )
        copa = series_display_name(row.get("series_name"), row.get("series_short_name"))
        if copa:
            lines.append(f"- Copa: {copa}")
    else:
        lines.append("- (sin fila de resultado registrada para esta válida)")

    # Maduración real (o sin registro). En runs v3 la fuente de verdad es
    # ``anthro_context`` (misma que ve el analista, anclada a la fecha de la
    # carrera); ``maturation_status`` (último registro, sin fecha) solo aplica
    # a runs v1/v2. Usar el último registro aquí contradecía al analista cuando
    # la única medición era posterior a la carrera (SC-1, 2026-09-02).
    lines.append("")
    lines.append("### Maduración")
    if "anthro_context" in state:
        anthro = state.get("anthro_context") or {}
        latest = anthro.get("latest") or {}
        status_txt = latest.get("maturation_status")
        if status_txt:
            note = (
                " (medición posterior a la carrera — aproximación)"
                if "measured_after_event" in (anthro.get("flags") or [])
                else ""
            )
            lines.append(f"{status_txt}{note}")
        else:
            lines.append(
                "sin registro de maduración a la fecha de la carrera "
                "(el análisis puede declararlo como vacío de datos)"
            )
    else:
        maturation = state.get("maturation_status")
        lines.append(maturation if maturation else "sin registro de maduración")

    # Podio del evento foco (tiempos P1-P3).
    podium_ctx = state.get("podium_context") or {}
    podium_rows = podium_ctx.get("podium") or []
    lines.append("")
    lines.append("### Podio (evento foco)")
    if podium_rows:
        for p in podium_rows:
            lines.append(
                f"- P{p.get('position')}: {_format_ms_hhmmss(p.get('race_time_ms'))}"
            )
    else:
        lines.append("- (sin datos de podio)")

    return "\n".join(lines)


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def critic_agent(state: dict) -> dict[str, Any]:
    if not RaceCriticAgent.is_enabled():
        # No-op explícito: emite eventos start/end pero no toca state.
        return {}

    agent = state.get("_critic_agent") or RaceCriticAgent()
    aggregate = dict(state.get("aggregate_metrics") or {})

    per_valida_drafts_v3: dict[int, Any] | None = state.get("per_valida_drafts_v3")

    # ------------------------------------------------------------------ v3
    if per_valida_drafts_v3:
        has_training_window = bool(state.get("training_window"))
        has_anthro = bool(state.get("anthro_context"))
        season_n = int(state.get("season_validas_count", 0))
        athlete_age = state.get("athlete_age")
        catalog_context = state.get("catalog_context")
        forbidden_names = state.get("club_forbidden_names") or state.get("forbidden_names") or []
        grounding_by_valida: dict[int, list[str]] = state.get("grounding_numbers") or {}
        previous_headlines = [
            d.get("headline") for d in (state.get("coach_dialogue") or []) if d.get("headline")
        ]

        verdicts: dict[int, CriticFeedback] = {}
        confidence: dict[int, Any] = {}
        precheck_issues_out: dict[int, list[Any]] = {}
        sanitized_drafts = dict(per_valida_drafts_v3)
        first_feedback: CriticFeedback | None = None

        for vn in list(per_valida_drafts_v3.keys())[:_V2_CAP]:
            draft = per_valida_drafts_v3[vn]
            if draft is None:
                continue

            # Verdad de campo primero: la necesita tanto el precheck de
            # invención de estado de carrera (hotfix identidad de válida)
            # como la llamada al critic LLM más abajo.
            ground_truth = _build_ground_truth(state, vn, include_course=True)

            precheck_result = run_prechecks(
                draft,
                grounding_numbers=grounding_by_valida.get(vn) or [],
                catalog_context=catalog_context,
                athlete_age=athlete_age,
                ltad_group=state.get("ltad_group"),
                is_adult=is_adult_age(athlete_age),
                forbidden_names=forbidden_names,
                previous_headlines=previous_headlines,
                ground_truth=ground_truth,
            )
            sanitized_drafts[vn] = precheck_result.sanitized_draft
            precheck_issues_out[vn] = precheck_result.issues

            llm_feedback, run_metrics = await agent.invoke_v3(
                precheck_result.sanitized_draft, ground_truth, precheck_result.issues
            )
            aggregate = _accumulate(
                aggregate, run_metrics, prompt_key="prompt_version_critic"
            )

            must_block = precheck_result.must_block or llm_feedback.must_block
            combined_issues = [pi.issue for pi in precheck_result.issues] + list(
                llm_feedback.issues
            )
            severity = llm_feedback.severity
            if precheck_result.must_block:
                severity = CriticIssueSeverity.HIGH
            elif precheck_result.issues and severity == CriticIssueSeverity.LOW:
                severity = CriticIssueSeverity.MED

            combined_feedback = CriticFeedback(
                approved=llm_feedback.approved and not precheck_result.issues,
                severity=severity,
                issues=combined_issues,
                must_block=must_block,
            )
            verdicts[vn] = combined_feedback
            if first_feedback is None:
                first_feedback = combined_feedback

            is_fallback = not getattr(draft, "observations", None)
            confidence[vn] = compute_confidence_v3(
                is_fallback=is_fallback,
                must_block=must_block,
                issues=precheck_result.issues,
                has_training_window=has_training_window,
                has_anthro=has_anthro,
                season_n=season_n,
            )

        out_v3: dict[str, Any] = {
            "per_valida_verdicts": verdicts,
            "confidence": confidence,
            "aggregate_metrics": aggregate,
            "precheck_issues": precheck_issues_out,
            "per_valida_drafts_v3": sanitized_drafts,
        }
        if first_feedback is not None:
            out_v3["critic_feedback"] = first_feedback
        return out_v3

    per_valida_drafts: dict[int, Any] | None = state.get("per_valida_drafts")

    # ------------------------------------------------------------------ v2
    if per_valida_drafts:
        event_conditions: dict[int, dict] = state.get("event_conditions") or {}
        has_maturation = bool(state.get("maturation_status"))
        season_n = int(state.get("season_validas_count", 0))

        verdicts: dict[int, Any] = {}
        confidence: dict[int, Any] = {}
        first_feedback = None
        for vn in list(per_valida_drafts.keys())[:_V2_CAP]:
            draft = per_valida_drafts[vn]
            if draft is None:
                continue
            ground_truth = _build_ground_truth(state, vn)
            feedback, run_metrics = await agent.invoke_v2(draft, ground_truth)
            verdicts[vn] = feedback
            aggregate = _accumulate(
                aggregate, run_metrics, prompt_key="prompt_version_critic"
            )
            if first_feedback is None:
                first_feedback = feedback

            # Confianza determinista por válida (feature 011, US4).
            cond = event_conditions.get(vn) or {}
            has_conditions = any(v is not None for v in cond.values())
            # El fallback de falla (no N=1) trae sections vacías.
            is_fallback = not getattr(draft, "sections", None)
            confidence[vn] = compute_confidence(
                feedback,
                DataCompleteness(
                    has_conditions=has_conditions,
                    has_maturation=has_maturation,
                    season_n=season_n,
                    is_fallback=is_fallback,
                ),
            )

        out: dict[str, Any] = {
            "per_valida_verdicts": verdicts,
            "confidence": confidence,
            "aggregate_metrics": aggregate,
        }
        if first_feedback is not None:
            out["critic_feedback"] = first_feedback
        return out

    # ------------------------------------------------------------------ v1
    draft = state.get("draft_analysis")
    if draft is None:
        # Sin draft (fallback ejecutado), no hay nada que criticar.
        return {}

    feedback, run_metrics = await agent.invoke(draft)
    aggregate = _accumulate(aggregate, run_metrics, prompt_key="prompt_version_critic")

    return {
        "critic_feedback": feedback,
        "aggregate_metrics": aggregate,
    }


__all__ = ["critic_agent", "NODE_NAME"]
