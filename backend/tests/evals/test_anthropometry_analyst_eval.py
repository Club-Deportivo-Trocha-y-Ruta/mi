"""Runner pytest del eval golden del análisis antropométrico (feature 042, T048).

Implementa ``specs/042-traceable-growth-ai/contracts/golden-eval-case.md`` §6/§7 y
mirroriza el patrón de ``backend/tests/evals/test_race_analyst_eval.py`` (marker,
skip explícito sin clave real, scoreboard markdown, sanity tests offline que
corren siempre) — sin reimplementar nada de ese archivo: el scorer/juez de este
feature viven en ``app/services/ai/anthro/eval/{scorer,judge}.py`` (T044/T045,
otro ownership) y este runner solo los invoca.

Marker: el ``golden`` YA REGISTRADO en ``pyproject.toml`` (compartido con el eval
de carreras), filtrado con ``-k anthropometry`` — el contrato es explícito: "no
new pytest marker" (golden-eval-case.md, sección "Marker").

Por qué este runner NO llama a ``pipeline.run_analysis``
==========================================================
``pipeline.run_analysis`` (T039) exige ``state["athlete"]``/``state["target_record"]``
— instancias ORM reales — porque su primer paso, ``context.build_context``, deriva
identidad/deltas/velocidad/banda a partir de esos objetos y de una sesión de DB.
El contrato del caso golden (``golden-eval-case.md`` §1) es explícito en lo
contrario: "``input`` is the full ``AnalysisContext`` shape (``analysis-context.md``
§2), not a subset — the judge and the deterministic prechecks both need the whole
context to check grounding." Es decir: cada caso YA ES un ``AnalysisContext``
completo y saneado, no un fixture de atleta del que derivarlo.

Por eso este runner reconstruye, a partir del ``input`` de cada caso:

1. Un ``AnalysisContext`` (``context.py``, T028) directo — sin pasar por
   ``build_context``.
2. Los ``context_blocks`` (los mismos seis bloques de texto Jinja que
   ``build_context`` produce al final) invocando sus funciones de renderizado
   privadas de un solo dict (``_render_identity_block`` etc.) — son funciones
   puras sobre exactamente la forma de dict que trae ``case["input"]``, así que
   reusarlas aquí (en vez de reimplementar el formato del prompt en este
   archivo) mantiene el texto que ve el analista idéntico al de producción.
3. El resto de la máquina de estados de ``data-model.md`` §3 (analista →
   prechecks → crítico → a lo sumo una reinvocación → aprobado/revisado/
   marcado/fallback), reusando ``analyst.run_analyst``, ``prechecks.run_prechecks``,
   ``critic.run_critic``, ``fallback.build_fallback_insight`` y los dos helpers
   privados de ``pipeline.py`` que combinan sus resultados
   (``_apply_confidence_low_override``, ``_augment_context_blocks_with_critic_feedback``)
   — nunca reimplementados, solo orquestados en el orden que ``pipeline.py`` ya
   documenta, porque ese orden es la especificación (data-model.md §3), no un
   detalle de implementación de este runner.

Este runner deliberadamente NO invoca ``guardrails_step`` (el scrub final): el
``rule_based_score`` del contrato (§2) puntúa el insight final resuelto por el
paso 2-4 de la máquina de estados directamente vía ``render_markdown_free`` — la
integración del guardrail final con el pipeline completo es responsabilidad de
``tests/anthro/test_pipeline.py`` (otro ownership), no de este gate de calidad.

SC-003 (spec.md) — verificado directamente, no inferido
=========================================================
"100% of cases with fewer than 26 weeks between measurements describe velocity
as an early signal, and 100% of uncorroborated phase crossings are NOT stated as
confirmed" se mide corriendo las reglas R05/R11 (``prechecks.py``, ya
implementadas en T029) sobre el INSIGHT FINAL que produjo el modelo real para
cada caso — no sobre los datos de entrada del caso (que ya declaran
``velocity_confidence``/``phase_crossing_corroborated`` por construcción; lo que
está bajo prueba es si el modelo respetó esa calibración en su salida). R05
dispara exactamente cuando el modelo presentó una velocidad no confiable como
confiable; R11 dispara exactamente cuando el modelo afirmó un cruce de fase
como confirmado sin corroboración — ambas son, por diseño del catálogo
(``golden-eval-case.md`` §3), la comprobación determinista de este acuerdo de
servicio, no una reinterpretación de él.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.services.ai.anthro.analyst import run_analyst
from app.services.ai.anthro.context import (
    AnalysisContext,
    _render_growth_summary_block,
    _render_identity_block,
    _render_longitudinal_series_block,
    _render_measurement_deltas_block,
    _render_previous_analysis_block,
    _render_training_load_block,
)
from app.services.ai.anthro.critic import run_critic
from app.services.ai.anthro.eval.judge import (
    NO_MODEL_KEY_REASON,
    has_configured_model_key,
    llm_judge_score,
)
from app.services.ai.anthro.eval.scorer import (
    COMPOSITE_THRESHOLD,
    composite_score,
    rule_based_score,
)
from app.services.ai.anthro.fallback import build_fallback_insight
from app.services.ai.anthro.guardrails_step import render_markdown_free
from app.services.ai.anthro.pipeline import (
    _apply_confidence_low_override,
    _augment_context_blocks_with_critic_feedback,
)
from app.services.ai.anthro.prechecks import (
    check_r05_unreliable_velocity_claimed_reliable,
    check_r11_uncorroborated_phase_crossing,
    run_prechecks,
)
from app.services.ai.anthro.schemas import AnthropometryInsightV1

GOLDEN_DIR = Path(__file__).parent.parent.parent / "evals" / "anthropometry_analyst" / "golden"
RESULTS_DIR = Path(__file__).parent.parent.parent / "evals" / "anthropometry_analyst" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_THIS_FILE = Path(__file__).resolve()
_BACKEND_DIR = _THIS_FILE.parent.parent.parent

# Almacén compartido entre los tests parametrizados — populado por cada caso,
# consumido por el test de threshold y por el de SC-003 (mismo patrón que
# ``test_race_analyst_eval.py::_RUN_RESULTS``).
_RUN_RESULTS: list[dict[str, Any]] = []
_SC003_RESULTS: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Schema validation + loading (golden-eval-case.md §1)
# ---------------------------------------------------------------------------


_REQUIRED_KEYS = {
    "case_id",
    "description",
    "audience",
    "input",
    "expected_themes",
    "forbidden_terms",
    "max_words",
    "ideal_output_excerpt",
}

_REQUIRED_INPUT_KEYS = {
    "identity",
    "measurement_deltas",
    "longitudinal_series",
    "growth_summary",
    "training_load_window",
    "previous_analysis",
}


def _validate_case_schema(case: dict[str, Any], path: Path) -> None:
    """Valida que el caso golden tenga las claves esperadas (§1 del contrato).

    Diagnostica errores temprano con mensaje accionable — el mismo criterio
    que el precedente de carreras: un JSON incompleto debe fallar aquí, no
    cinco minutos después de haber gastado tokens de un modelo real.
    """
    missing = _REQUIRED_KEYS - set(case.keys())
    assert not missing, f"{path.name}: faltan claves {missing}"
    assert case["audience"] in ("family", "coach"), f"{path.name}: audience inválida"
    assert isinstance(case["input"], dict), f"{path.name}: input debe ser dict"
    missing_input = _REQUIRED_INPUT_KEYS - set(case["input"].keys())
    assert not missing_input, f"{path.name}: input le faltan claves {missing_input}"
    assert isinstance(case["expected_themes"], list), f"{path.name}: expected_themes debe ser list"
    assert isinstance(case["forbidden_terms"], list), f"{path.name}: forbidden_terms debe ser list"
    assert isinstance(case["max_words"], int) and case["max_words"] > 50, (
        f"{path.name}: max_words debe ser int >50"
    )


def _load_all_cases() -> list[tuple[str, dict[str, Any]]]:
    """Carga todos los ``case_*.json`` del directorio golden, ordenados por filename."""
    paths = sorted(GOLDEN_DIR.glob("case_*.json"))
    out: list[tuple[str, dict[str, Any]]] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            pytest.fail(f"JSON inválido en {p.name}: {e}")
        _validate_case_schema(data, p)
        out.append((str(data["case_id"]), data))
    return out


_ALL_CASES = _load_all_cases()


# ---------------------------------------------------------------------------
# Reconstrucción de AnalysisContext + context_blocks desde un caso golden
# ---------------------------------------------------------------------------


def _build_analysis_context_and_blocks(case: dict[str, Any]) -> tuple[AnalysisContext, dict[str, Any]]:
    """Reconstruye el ``AnalysisContext`` + los seis bloques de texto de un caso golden.

    Ver el docstring del módulo para por qué esto NO pasa por
    ``context.build_context`` (que exige objetos ORM reales). ``identity`` del
    JSON del caso no trae ``audience`` (es un dato de la petición, no del
    atleta — ``context.py::_build_identity`` lo agrega desde fuera igual que
    aquí) — se inyecta desde ``case["audience"]``, mismo criterio.
    """
    case_input = case["input"]
    identity = dict(case_input["identity"])
    identity.setdefault("audience", case["audience"])

    measurement_deltas = case_input.get("measurement_deltas")
    longitudinal_series = list(case_input.get("longitudinal_series") or [])
    growth_summary = dict(case_input["growth_summary"])
    training_load_window = case_input.get("training_load_window")
    previous_analysis = case_input.get("previous_analysis")

    context = AnalysisContext(
        identity=identity,
        measurement_deltas=measurement_deltas,
        longitudinal_series=longitudinal_series,
        growth_summary=growth_summary,
        training_load_window=training_load_window,
        previous_analysis=previous_analysis,
    )
    context_blocks = {
        "identity_block": _render_identity_block(identity),
        "measurement_deltas_block": _render_measurement_deltas_block(measurement_deltas),
        "longitudinal_series_block": _render_longitudinal_series_block(longitudinal_series),
        "growth_summary_block": _render_growth_summary_block(growth_summary),
        "training_load_block": _render_training_load_block(training_load_window),
        "previous_analysis_block": _render_previous_analysis_block(previous_analysis),
    }
    return context, context_blocks


async def _run_case_pipeline(
    case: dict[str, Any],
) -> tuple[AnthropometryInsightV1, AnalysisContext, str, dict[str, Any]]:
    """Corre analista → prechecks → crítico (con la única reinvocación permitida)
    sobre un caso golden, replicando la máquina de estados de ``data-model.md``
    §3 tal como la orquesta ``pipeline.run_analysis`` desde su "paso 2" en
    adelante (el "paso 1", ``build_context``, se sustituye por
    :func:`_build_analysis_context_and_blocks` — ver docstring del módulo).

    Returns:
        ``(insight, context, critic_verdict, metrics)`` — ``critic_verdict`` es
        el vocabulario persistido de cinco valores (``data-model.md`` §3);
        ``metrics`` trae ``tokens_in``/``tokens_out``/``cost_usd`` acumulados
        de todas las llamadas LLM de esta corrida (una a cuatro).
    """
    context, context_blocks = _build_analysis_context_and_blocks(case)
    state = {"analysis_context": context, "context_blocks": context_blocks}

    metrics = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    def _accumulate(update: dict[str, Any], prefix: str) -> None:
        metrics["tokens_in"] += update[f"{prefix}_tokens_in"]
        metrics["tokens_out"] += update[f"{prefix}_tokens_out"]
        metrics["cost_usd"] = round(metrics["cost_usd"] + update[f"{prefix}_cost_usd"], 6)

    analyst_update = await run_analyst(state)
    _accumulate(analyst_update, "analyst")

    if analyst_update["analyst_failed"]:
        # data-model.md §3: fallo del analista (dos intentos agotados) va
        # DIRECTO al fallback — el crítico ni siquiera se invoca.
        return build_fallback_insight(context), context, "fallback", metrics

    draft: AnthropometryInsightV1 = analyst_update["analyst_draft"]
    precheck_result = run_prechecks(draft, context, forbidden_names=())

    if precheck_result.must_block:
        # data-model.md §3: violación must_block va DIRECTO al fallback sin
        # gastar una llamada al crítico (FR-014).
        return build_fallback_insight(context), context, "fallback", metrics

    critic_state = {**state, "analyst_draft": draft, "precheck_result": precheck_result}
    critic_update = await run_critic(critic_state)
    _accumulate(critic_update, "critic")
    decision = critic_update["critic_decision"]

    if decision == "approved":
        insight = critic_update["critic_output"]
        if precheck_result.violations:
            # data-model.md §3: "approve, pero con violaciones confidence-only"
            # → forzado determinista a "low".
            insight = _apply_confidence_low_override(insight)
        return insight, context, "approved", metrics
    if decision == "revised_mechanical":
        return critic_update["critic_output"], context, "revised", metrics
    if decision == "rejected":
        # FR-013: "at most one revision" se gasta en "revise", no en "reject".
        return critic_update["critic_output"], context, "flagged", metrics
    if decision == "skipped":
        return critic_update["critic_output"], context, "skipped", metrics

    # decision == "needs_reanalysis": la ÚNICA reinvocación permitida del
    # analista (FR-013), con las violaciones del crítico anexadas.
    violations = critic_update["critic_violations"]
    reanalysis_state = {
        **state,
        "context_blocks": _augment_context_blocks_with_critic_feedback(context_blocks, violations),
    }
    analyst2_update = await run_analyst(reanalysis_state)
    _accumulate(analyst2_update, "analyst")

    if analyst2_update["analyst_failed"]:
        return build_fallback_insight(context), context, "fallback", metrics

    draft2: AnthropometryInsightV1 = analyst2_update["analyst_draft"]
    precheck2 = run_prechecks(draft2, context, forbidden_names=())
    if precheck2.must_block:
        return build_fallback_insight(context), context, "fallback", metrics

    critic2_state = {**state, "analyst_draft": draft2, "precheck_result": precheck2}
    critic2_update = await run_critic(critic2_state)
    _accumulate(critic2_update, "critic")
    decision2 = critic2_update["critic_decision"]

    if decision2 in ("approved", "revised_mechanical"):
        # data-model.md §3: la segunda vuelta que llega a approve o a una
        # revisión mecánica cuenta como REVISED en conjunto.
        return critic2_update["critic_output"], context, "revised", metrics
    # "rejected"/"skipped"/otro "needs_reanalysis" en la segunda vuelta: FR-013
    # ya gastó su única revisión, esto cae a FLAGGED (data-model.md §3).
    return critic2_update["critic_output"], context, "flagged", metrics


# ---------------------------------------------------------------------------
# Skip guard: clave de modelo real requerida (golden-eval-case.md §6, spec.md
# edge case "the developer runs the golden evaluation without a real model key")
# ---------------------------------------------------------------------------

# Única fuente de verdad para "¿hay un modelo real configurado?" — la misma
# que usa el propio juez (``judge.py::has_configured_model_key``, docstring:
# "el runner del eval (T048) debe usarla también para su propio skipif
# declarativo, en vez de reinventar el chequeo de variables de entorno").
_HAS_MODEL_KEY = has_configured_model_key()

_skip_no_model_key = pytest.mark.skipif(not _HAS_MODEL_KEY, reason=NO_MODEL_KEY_REASON)


# ---------------------------------------------------------------------------
# Parametrized run (golden, bloqueante)
# ---------------------------------------------------------------------------


@pytest.mark.golden
@_skip_no_model_key
@pytest.mark.parametrize("case_id,case", _ALL_CASES, ids=[cid for cid, _ in _ALL_CASES])
async def test_golden_case(case_id: str, case: dict[str, Any]) -> None:
    """Corre un caso golden contra el pipeline real (analista+crítico, Gemini) y
    calcula el score compuesto (rule 0.4 + judge 0.6, ``golden-eval-case.md`` §2).

    El test PASA si ``composite`` es un score válido en ``[0, 1]``; el test
    bloqueante es :func:`test_eval_average_meets_threshold`, al final. También
    acumula, en :data:`_SC003_RESULTS`, si R05/R11 dispararon sobre el insight
    final — consumido por :func:`test_sc003_velocity_and_phase_crossing_calibration`.

    Si no hay clave de modelo real, el juez levanta
    :class:`JudgeModelUnavailableError` — pero este test ya está deseleccionado
    por :data:`_skip_no_model_key` antes de llegar a ejecutarse, así que esa
    rama nunca corre aquí (documentada solo para que quede claro que no hace
    falta un segundo try/except).
    """
    insight, context, critic_verdict, metrics = await _run_case_pipeline(case)
    rendered_text = render_markdown_free(insight)

    rule = rule_based_score(insight, context, case, forbidden_names=())
    judge_result = await llm_judge_score(insight, rendered_text, context, case)
    composite = composite_score(rule, judge_result.score)

    _RUN_RESULTS.append(
        {
            "case_id": case_id,
            "description": case.get("description", ""),
            "critic_verdict": critic_verdict,
            "rule_score": rule,
            "judge_score": judge_result.score,
            "judge_parse_ok": judge_result.parse_ok,
            "composite": composite,
            "word_count": len(rendered_text.split()),
            "tokens_in": metrics["tokens_in"],
            "tokens_out": metrics["tokens_out"],
            "cost_usd": metrics["cost_usd"],
        }
    )

    deltas = case["input"].get("measurement_deltas") or {}
    velocity_present = deltas.get("growth_velocity_cm_per_year") is not None
    is_early_signal_case = velocity_present and deltas.get("velocity_confidence") == "early_signal"
    is_uncorroborated_crossing_case = bool(deltas.get("crossed_phv_phase")) and not deltas.get(
        "phase_crossing_corroborated"
    )
    _SC003_RESULTS.append(
        {
            "case_id": case_id,
            "is_early_signal_case": is_early_signal_case,
            "r05_violated": check_r05_unreliable_velocity_claimed_reliable(insight, context) is not None
            if is_early_signal_case
            else None,
            "is_uncorroborated_crossing_case": is_uncorroborated_crossing_case,
            "r11_violated": check_r11_uncorroborated_phase_crossing(insight, context) is not None
            if is_uncorroborated_crossing_case
            else None,
        }
    )

    assert 0.0 <= composite <= 1.0


@pytest.mark.golden
@_skip_no_model_key
def test_eval_average_meets_threshold() -> None:
    """Test bloqueante (FR-035): promedio compuesto debe ser ≥ ``COMPOSITE_THRESHOLD``
    (0.75, importado de ``eval/scorer.py`` — el mismo valor que usa el contrato,
    nunca un literal repetido en este archivo).

    También escribe el scoreboard markdown (``results/last_run.md``), separado
    del fixture para que falle visible si el archivo no se puede escribir —
    mismo criterio que el precedente de carreras.
    """
    threshold = COMPOSITE_THRESHOLD
    assert _RUN_RESULTS, "No se ejecutó ningún caso golden — chequear discovery/collection."

    avg = sum(r["composite"] for r in _RUN_RESULTS) / len(_RUN_RESULTS)
    _write_scoreboard(_RUN_RESULTS, avg, threshold)

    assert avg >= threshold, (
        f"Score promedio {avg:.3f} < threshold {threshold:.2f}. Revisar los prompts "
        "anthropometry_analyst_v1.md / anthropometry_critic_v1.md o "
        "app/services/ai/anthro/{analyst,critic}.py. "
        "Detalle en evals/anthropometry_analyst/results/last_run.md."
    )


@pytest.mark.golden
@_skip_no_model_key
def test_sc003_velocity_and_phase_crossing_calibration() -> None:
    """SC-003 (spec.md), bloqueante: verificado sobre el insight FINAL real, no
    sobre los datos de entrada del caso — ver docstring del módulo.

    - 100% de los casos con velocidad calculada y ``velocity_confidence ==
      "early_signal"`` deben describirla como señal temprana en la salida —
      es decir, R05 (``check_r05_unreliable_velocity_claimed_reliable``) NUNCA
      dispara sobre esos casos.
    - 100% de los cruces de fase sin corroborar (``crossed_phv_phase=True`` y
      ``phase_crossing_corroborated=False``) NUNCA se presentan como
      confirmados — es decir, R11 (``check_r11_uncorroborated_phase_crossing``)
      NUNCA dispara sobre esos casos.

    Depende de que :func:`test_golden_case` ya haya corrido para los 12 casos
    (population de :data:`_SC003_RESULTS`) — mismo patrón de dependencia
    intra-módulo que :func:`test_eval_average_meets_threshold` tiene con
    :data:`_RUN_RESULTS`.
    """
    assert _SC003_RESULTS, "No se acumuló ningún resultado SC-003 — chequear discovery/collection."

    early_signal_cases = [r for r in _SC003_RESULTS if r["is_early_signal_case"]]
    crossing_cases = [r for r in _SC003_RESULTS if r["is_uncorroborated_crossing_case"]]

    assert early_signal_cases, (
        "Ningún caso golden ejercita velocity_confidence='early_signal' con "
        "velocidad calculada — SC-003 no se puede verificar."
    )
    assert crossing_cases, (
        "Ningún caso golden ejercita un cruce de fase sin corroborar — SC-003 "
        "no se puede verificar."
    )

    r05_failures = [r["case_id"] for r in early_signal_cases if r["r05_violated"]]
    assert not r05_failures, (
        "SC-003: la velocidad con confianza 'early_signal' se presentó como "
        f"confiable (R05) en los casos {r05_failures} — debe describirse como "
        "señal temprana en el 100% de estos casos."
    )

    r11_failures = [r["case_id"] for r in crossing_cases if r["r11_violated"]]
    assert not r11_failures, (
        "SC-003: un cruce de fase sin corroborar se presentó como confirmado "
        f"(R11) en los casos {r11_failures} — debe ser 0 en todo el set golden."
    )


# ---------------------------------------------------------------------------
# Scoreboard writer
# ---------------------------------------------------------------------------


def _write_scoreboard(results: list[dict[str, Any]], avg: float, threshold: float) -> None:
    """Persiste el scoreboard markdown en ``results/last_run.md`` (mismo formato
    que el precedente de carreras, adaptado a las columnas de este eval)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Anthropometry Analyst Golden Eval — Last Run",
        "",
        f"- **Fecha:** {now}",
        f"- **Threshold CI:** {threshold:.2f}",
        f"- **Casos ejecutados:** {len(results)}",
        f"- **Promedio compuesto:** **{avg:.3f}**",
        f"- **Verdict:** {'PASS' if avg >= threshold else 'FAIL'}",
        "",
        "## Detalle por caso",
        "",
        "| case_id | verdict | rule | judge | composite | words | tokens_in | tokens_out | cost_usd |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['case_id']} | {r['critic_verdict']} | {r['rule_score']:.3f} | "
            f"{r['judge_score']:.3f}{'' if r['judge_parse_ok'] else '*'} | "
            f"{r['composite']:.3f} | {r['word_count']} | {r['tokens_in']} | "
            f"{r['tokens_out']} | {r['cost_usd']:.6f} |"
        )
    lines.append("")
    lines.append("> `*` indica que el parser del juez usó fallback neutral 0.5.")
    lines.append("")
    lines.append("## Descripción de los casos")
    lines.append("")
    for r in results:
        lines.append(f"- **{r['case_id']}**: {r['description']}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "last_run.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Cheap sanity tests — corren SIEMPRE (sin marker golden, sin clave real)
# ---------------------------------------------------------------------------


def test_loader_finds_twelve_cases() -> None:
    """``golden-eval-case.md`` §4: exactamente doce casos sintéticos."""
    assert len(_ALL_CASES) == 12, (
        f"Se esperaban 12 casos golden, encontrados {len(_ALL_CASES)} en {GOLDEN_DIR}"
    )


def test_loader_validates_all_case_schemas() -> None:
    """Re-corre la validación con un mensaje agregado para diagnóstico rápido."""
    paths = sorted(GOLDEN_DIR.glob("case_*.json"))
    errors: list[str] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            _validate_case_schema(data, p)
        except (AssertionError, json.JSONDecodeError) as exc:
            errors.append(f"{p.name}: {exc}")
    assert not errors, "Casos golden con schema inválido: " + " | ".join(errors)


def test_loader_can_build_context_for_all_cases() -> None:
    """Cada caso debe reconstruir ``AnalysisContext`` + ``context_blocks`` sin error.

    Previene descubrir, después de gastar tokens de un modelo real, que un
    caso golden tiene un campo con una forma que las funciones de renderizado
    de ``context.py`` no esperan (mismo motivo que el test análogo del
    precedente de carreras).
    """
    errors: list[str] = []
    for case_id, case in _ALL_CASES:
        try:
            context, context_blocks = _build_analysis_context_and_blocks(case)
            assert context.identity.get("audience") == case["audience"]
            assert context_blocks["growth_summary_block"], "growth_summary_block vacío"
        except Exception as exc:  # noqa: BLE001 — se reporta, no se relanza.
            errors.append(f"case_{case_id}: {exc}")
    assert not errors, "Casos golden con input inválido para AnalysisContext: " + " | ".join(errors)


def test_dataset_covers_the_required_scenarios() -> None:
    """El dataset cubre los doce escenarios exigidos por ``golden-eval-case.md`` §4:
    primera medición, <8 semanas, <26 semanas, ≥26 semanas confiable, cruce sin
    corroborar, cruce corroborado, borde de edad, velocidad por encima de lo
    típico, señales de aviso, sin ventana de entrenamiento, historial largo
    (>16 puntos) y audiencia entrenador vs familia.
    """
    inputs = [case["input"] for _, case in _ALL_CASES]
    audiences = {case["audience"] for _, case in _ALL_CASES}
    deltas_list = [i.get("measurement_deltas") for i in inputs]

    assert {"family", "coach"} <= audiences, "faltan casos coach y/o family"
    assert any(i.get("measurement_deltas") is None for i in inputs), "falta caso de primera medición"
    assert any(
        d is not None and d.get("weeks_since_prev_measurement", 999) < 8 for d in deltas_list
    ), "falta caso bajo el piso de 8 semanas"
    assert any(
        d is not None and d.get("velocity_confidence") == "early_signal" for d in deltas_list
    ), "falta caso <26 semanas (velocity_confidence='early_signal')"
    assert any(
        d is not None and d.get("velocity_confidence") == "reliable" for d in deltas_list
    ), "falta caso ≥26 semanas (velocity_confidence='reliable')"
    assert any(
        d is not None and d.get("crossed_phv_phase") and not d.get("phase_crossing_corroborated")
        for d in deltas_list
    ), "falta caso de cruce de fase sin corroborar"
    assert any(
        d is not None and d.get("crossed_phv_phase") and d.get("phase_crossing_corroborated")
        for d in deltas_list
    ), "falta caso de cruce de fase corroborado"
    assert any(i.get("training_load_window") is None for i in inputs), (
        "falta caso sin ventana de entrenamiento"
    )
    assert any(
        len(i.get("longitudinal_series") or []) > 16 for i in inputs
    ), "falta caso con historial largo (>16 puntos)"
    assert any(
        (i.get("identity") or {}).get("age_decimal", 0) >= 15.0 for i in inputs
    ), "falta caso de borde de edad (≥15 años)"
    assert any(i.get("previous_analysis") is not None for i in inputs), (
        "falta caso con análisis estructurado previo (para el caso 011 de continuidad)"
    )


def test_case_dataset_contains_no_real_athlete_data() -> None:
    """Privacidad (CLAUDE.md, Ley 1581 / golden-eval-case.md §5): ningún caso
    puede llevar un identificador de atleta/club real, ni un dato clínico
    crudo (z-score, percentil) ni una fecha absoluta.

    Escanea el JSON crudo completo de cada caso (input **e** metadata) — es
    exactamente lo que terminaría en un prompt si alguien lo copiara para
    depurar.
    """
    banned_keys = ("athlete_id", "club_id", "birth_date", "nombre", "name", "cedula", "documento")
    # ``age_decimal``/``category``/``sex`` son campos LEGÍTIMOS del contrato
    # (identity ya sanitizada) — no se prohíben; solo se prohíbe lo que
    # identificaría a una persona real o un dato clínico crudo prohibido por
    # el contrato de insight (percentil/z-score exactos, fecha calendario).
    banned_value_patterns = (
        r"\bz-?score\b",
        r"\bpercentil\b",
        r"\b20\d{2}-\d{2}-\d{2}\b",  # fecha ISO absoluta
    )

    def _walk_keys(node: Any, path: Path) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                hits = [b for b in banned_keys if b == str(key).lower()]
                assert not hits, f"{path.name}: clave prohibida {key!r} ({hits})"
                _walk_keys(value, path)
        elif isinstance(node, list):
            for item in node:
                _walk_keys(item, path)

    for path in sorted(GOLDEN_DIR.glob("case_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        # Solo se camina ``data`` completo por CLAVES prohibidas (identificadores) —
        # el chequeo de PATRONES de valor (z-score/percentil/fecha absoluta) se
        # limita a ``input`` (los datos de contexto reales que verían el prompt),
        # nunca a ``forbidden_terms``/``expected_themes``, que LEGÍTIMAMENTE listan
        # esas mismas palabras como términos que el modelo NO debe usar.
        _walk_keys(data, path)
        raw_input = json.dumps(data.get("input", {}), ensure_ascii=False).lower()
        hits = [p for p in banned_value_patterns if re.search(p, raw_input)]
        assert not hits, f"{path.name}: input contiene un dato prohibido {hits}"


def test_baseline_file_exists_and_matches_threshold() -> None:
    """``baseline.json`` (T047) debe existir y declarar el mismo threshold que
    :data:`COMPOSITE_THRESHOLD` — evita que el baseline y el gate se
    desincronicen silenciosamente si alguien cambia uno sin el otro."""
    baseline_path = GOLDEN_DIR.parent / "baseline.json"
    assert baseline_path.exists(), f"Falta {baseline_path}"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["threshold"] == COMPOSITE_THRESHOLD


@pytest.mark.skipif(
    _HAS_MODEL_KEY,
    reason="Este test solo tiene sentido sin clave real configurada (verifica el skip mismo).",
)
def test_golden_eval_skipped_without_model_key_not_silently_passed() -> None:
    """Edge case de spec.md / ``golden-eval-case.md`` §7: correr ``-m golden -k
    anthropometry`` sin clave real reporta un skip EXPLÍCITO, nunca un pass
    verde silencioso ni un error.

    Corre este mismo archivo en un subproceso real de pytest (no una
    inspección de los decoradores) para verificar el comportamiento
    end-to-end que un desarrollador vería — mismo comando documentado en
    ``golden-eval-case.md`` §6. Se salta a sí mismo cuando SÍ hay clave real
    (otro entorno/CI) para no gastar tokens reales duplicando la corrida
    completa solo para probar el guard de skip.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_THIS_FILE),
            "-m",
            "golden",
            "-k",
            "anthropometry",
            "-q",
        ],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined_output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"El run sin clave debía salir en verde (todo skipeado), returncode="
        f"{result.returncode}. Salida:\n{combined_output}"
    )
    assert "passed" not in combined_output or re.search(r"\b0 passed\b", combined_output), (
        f"Un test golden se ejecutó (pass) sin clave real configurada — debía "
        f"skipearse. Salida:\n{combined_output}"
    )
    assert re.search(r"\bskipped\b", combined_output), (
        f"Se esperaba al menos un test skipeado explícitamente. Salida:\n{combined_output}"
    )
    assert "error" not in combined_output.lower(), (
        f"El run sin clave no debía producir ningún error de colección/ejecución. "
        f"Salida:\n{combined_output}"
    )
