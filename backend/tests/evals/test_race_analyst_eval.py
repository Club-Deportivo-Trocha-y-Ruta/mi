"""Runner pytest del eval golden ``RaceAnalystAgent`` (Fase 7 §7.3).

Características:

- **Marker** ``@pytest.mark.golden`` — registrado en ``pyproject.toml``.
  No corre en CI normal (opt-in con ``-m golden``).
- **Skip si ``RACE_AI_API_KEY``/``GOOGLE_API_KEY`` ausentes** — eval real
  necesita Gemini (``google``/``gemini-3.1-flash-lite``, el par que
  realmente corre en producción — ver ``backend/.env`` y
  ``specs/036-ai-insights-tab-review/IMPLEMENTATION_STATE.md``); en CI
  dedicado se ejecuta con el secret, en local sin key se skipea para
  no romper desarrollo offline.
- **Auto-discovery** vía ``glob('case_*.json')`` y ``pytest.mark.parametrize``
  para que cada caso aparezca individualmente en el reporte.
- **Scoreboard markdown** se genera al final del run (session-scoped
  finalizer) en ``evals/race_analyst/results/last_run.md`` con fecha,
  scores por caso y promedio.

Convenciones del schema golden — validadas en :func:`_validate_case_schema`:
- ``case_id`` (str)
- ``description`` (str)
- ``input`` (dict con campos de :class:`AnalysisInput` — incluye
  opcionalmente ``season_comparative``/``progression_assessment`` para
  ejercer el camino "con historial", T014/T053)
- ``expected_themes`` (list[str])
- ``forbidden_terms`` (list[str])
- ``must_cite`` (bool)
- ``max_words`` (int)
- ``ideal_output_excerpt`` (str)

Threshold CI: ``RACE_EVAL_THRESHOLD`` env (default ``0.75``). Si el
promedio cae por debajo → test ``test_eval_average_meets_threshold`` falla
y bloquea el merge (workflow §7.7).

Pipeline evaluado (specs/036 T050): el runner invoca
``RaceAnalystAgent.invoke_per_valida`` con ``prompt_version="race_analyst_v2"``
— el método y prompt que production usa realmente
(``services/race/ai/nodes/analyst_agent.py``). Antes de T050 este runner
llamaba al método v1 (``agent.invoke``, prompt de 5 secciones), que ningún
coach dispara hoy — el gate medía un pipeline fantasma.

Feature 037 (T401) — dos rutas seleccionables por ``RACE_EVAL_VERSION``
======================================================================

- ``v3`` (**default**): dataset ``evals/race_analyst/golden_v3/``, invoca
  ``RaceAnalystAgent.invoke_v3`` (salida ``InsightV3``, prompts
  ``race_analyst_v3`` / ``race_season_summary_v3``), puntúa con
  ``eval/scorer_v3.py`` + juez ``prompts/judge_v2.md``. Es el pipeline que
  production usa desde T204.
- ``v2``: dataset ``evals/race_analyst/golden/``, ruta histórica intacta
  (``invoke_per_valida`` + ``scorer.py`` + ``judge_v1.md``). Se conserva
  para el rollback documentado en T204 (``RACE_AI_PROMPT_VERSION=v2``):
  si se revierte el prompt, el gate debe poder revertirse con él.

Ambas rutas comparten el threshold (``RACE_EVAL_THRESHOLD``, default 0.75),
el acumulador ``_RUN_RESULTS`` y el scoreboard: en un run solo corre una de
las dos, así que el promedio nunca mezcla escalas.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.services.race.eval.scorer import composite_score, rule_based_score
from app.services.race.eval.scorer_v3 import (
    case_grounding_numbers,
    rule_based_score_v3,
    rule_subscores_v3,
)
from app.services.race.schemas import AnalysisInput

GOLDEN_DIR = Path(__file__).parent.parent.parent / "evals" / "race_analyst" / "golden"
GOLDEN_V3_DIR = (
    Path(__file__).parent.parent.parent / "evals" / "race_analyst" / "golden_v3"
)
RESULTS_DIR = Path(__file__).parent.parent.parent / "evals" / "race_analyst" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_THRESHOLD = 0.75

# Versión del eval a ejecutar. Default v3 (T401): es el pipeline que corre en
# producción desde T204. ``v2`` conserva la ruta histórica para el rollback.
_EVAL_VERSION = (os.getenv("RACE_EVAL_VERSION") or "v3").strip().lower()

# Almacén compartido entre tests parametrizados — populado por cada caso,
# consumido por el test de threshold final + el writer del scoreboard.
_RUN_RESULTS: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Schema validation + loading
# ---------------------------------------------------------------------------


_REQUIRED_KEYS = {
    "case_id",
    "description",
    "input",
    "expected_themes",
    "forbidden_terms",
    "must_cite",
    "max_words",
    "ideal_output_excerpt",
}


def _validate_case_schema(case: dict[str, Any], path: Path) -> None:
    """Valida que el caso golden tenga las claves esperadas.

    Diagnostica errores temprano con mensaje accionable (``path`` apunta
    al archivo problemático), evita debug doloroso después.
    """
    missing = _REQUIRED_KEYS - set(case.keys())
    assert not missing, f"{path.name}: faltan claves {missing}"
    assert isinstance(case["expected_themes"], list), f"{path.name}: expected_themes debe ser list"
    assert isinstance(case["forbidden_terms"], list), f"{path.name}: forbidden_terms debe ser list"
    assert isinstance(case["must_cite"], bool), f"{path.name}: must_cite debe ser bool"
    assert isinstance(case["max_words"], int), f"{path.name}: max_words debe ser int"
    assert case["max_words"] > 50, f"{path.name}: max_words debe ser >50"


def _load_all_cases() -> list[tuple[str, dict[str, Any]]]:
    """Carga todos los ``case_*.json`` del directorio golden.

    Returns:
        Lista de tuplas ``(case_id, case_dict)`` ordenada por filename
        (case_001, case_002, ...).
    """
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


def _build_analysis_input(case_input: dict[str, Any]) -> AnalysisInput:
    """Construye :class:`AnalysisInput` desde el dict del caso golden.

    ``principles_citations`` ya no es un campo de ``AnalysisInput`` (RAG
    removido) — se descarta si el JSON golden todavía lo trae.
    """
    payload = dict(case_input)
    payload.pop("principles_citations", None)
    return AnalysisInput(**payload)


def _derive_valida_num(case_input: dict[str, Any]) -> int:
    """Deriva la válida "actual" del caso: la última fila de ``progression_df_records``.

    Las filas anteriores son el historial de la temporada; la última es la
    válida que el caso está analizando. Default ``1`` si el caso no trae
    registros (defensivo — hoy los 11 casos golden siempre traen ≥1).
    """
    records = case_input.get("progression_df_records") or []
    if not records:
        return 1
    return int(records[-1].get("valida_num", 1))


def _derive_is_first_in_season(case_input: dict[str, Any]) -> bool:
    """``True`` si el caso trae 1 sola fila de progresión (activa la REGLA N=1 del prompt v2).

    Heurística local al runner basada únicamente en los datos del propio
    caso golden — no asume cómo production deriva la bandera real para un
    lanzamiento (eso es specs/036 T057, fuera de este scope; ver
    ``services/race/ai/nodes/analyst_agent.py``).
    """
    records = case_input.get("progression_df_records") or []
    return len(records) <= 1


# ---------------------------------------------------------------------------
# Golden v3 (feature 037, T401) — carga y validación de schema
# ---------------------------------------------------------------------------


_REQUIRED_KEYS_V3 = {
    "case_id",
    "description",
    "input",
    "expected_themes",
    "forbidden_terms",
    "expected_headline_keywords",
    "must_reference_catalog",
    "max_words",
    "ideal_output",
}


def _validate_case_schema_v3(case: dict[str, Any], path: Path) -> None:
    """Valida el schema de un caso golden v3 con mensajes accionables."""
    missing = _REQUIRED_KEYS_V3 - set(case.keys())
    assert not missing, f"{path.name}: faltan claves {missing}"
    assert isinstance(case["input"], dict), f"{path.name}: input debe ser dict"
    for list_key in ("expected_themes", "forbidden_terms", "expected_headline_keywords"):
        assert isinstance(case[list_key], list), f"{path.name}: {list_key} debe ser list"
        assert case[list_key], f"{path.name}: {list_key} no puede estar vacío"
    assert isinstance(case["must_reference_catalog"], bool), (
        f"{path.name}: must_reference_catalog debe ser bool"
    )
    assert isinstance(case["max_words"], int) and case["max_words"] > 50, (
        f"{path.name}: max_words debe ser int >50"
    )
    assert isinstance(case["ideal_output"], dict), (
        f"{path.name}: ideal_output debe ser el dict de un InsightV3"
    )


def _load_all_cases_v3() -> list[tuple[str, dict[str, Any]]]:
    """Carga todos los ``case_*.json`` de ``golden_v3/`` ordenados por filename."""
    paths = sorted(GOLDEN_V3_DIR.glob("case_*.json"))
    out: list[tuple[str, dict[str, Any]]] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            pytest.fail(f"JSON inválido en {p.name}: {e}")
        _validate_case_schema_v3(data, p)
        out.append((str(data["case_id"]), data))
    return out


def _build_analyst_v3_input(case: dict[str, Any]) -> Any:
    """Construye el ``AnalystV3Input`` de un caso golden v3."""
    from app.services.race.agents.analyst import AnalystV3Input

    return AnalystV3Input(**dict(case["input"]))


# ---------------------------------------------------------------------------
# Skip guard: RACE_AI_API_KEY required for the real eval
# ---------------------------------------------------------------------------


def _api_key_available() -> bool:
    """``True`` si hay clave para llamar al proveedor real del pipeline race/agents/.

    Acepta ``RACE_AI_API_KEY`` (la variable que ``build_chat_llm`` /
    ``Settings.race_ai_api_key`` realmente lee) o ``GOOGLE_API_KEY`` (SDK
    convención de Gemini). ``AI_API_KEY``/``AI_PROVIDER``/``AI_MODEL`` NO
    aplican aquí: son la configuración de ``app/services/ai/`` (el stack
    del asistente de sesiones, informes y newsletters) — un pipeline
    completamente distinto con su propio proveedor/modelo, aunque hoy
    ambos apunten a Google (ver ``backend/.env`` y
    ``specs/036-ai-insights-tab-review/IMPLEMENTATION_STATE.md``, sección
    "The Gemini correction"). El workflow CI (``race-eval.yml``) exporta
    ``RACE_AI_API_KEY``/``RACE_AI_PROVIDER=google``/
    ``RACE_AI_MODEL=gemini-3.1-flash-lite`` — exactamente lo que este
    guard busca.
    """
    return bool(os.getenv("RACE_AI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


_skip_no_api = pytest.mark.skipif(
    not _api_key_available(),
    reason="RACE_AI_API_KEY/GOOGLE_API_KEY no disponible; eval real necesita Gemini.",
)

_skip_unless_v2 = pytest.mark.skipif(
    _EVAL_VERSION != "v2",
    reason=f"RACE_EVAL_VERSION={_EVAL_VERSION!r}: la ruta v2 solo corre con 'v2'.",
)

_skip_unless_v3 = pytest.mark.skipif(
    _EVAL_VERSION != "v3",
    reason=f"RACE_EVAL_VERSION={_EVAL_VERSION!r}: la ruta v3 solo corre con 'v3'.",
)


# ---------------------------------------------------------------------------
# Parametrized run
# ---------------------------------------------------------------------------


_ALL_CASES = _load_all_cases()
_ALL_CASES_V3 = _load_all_cases_v3()


@pytest.mark.golden
@_skip_no_api
@_skip_unless_v2
@pytest.mark.parametrize(
    "case_id,case",
    _ALL_CASES,
    ids=[cid for cid, _ in _ALL_CASES],
)
async def test_golden_case(case_id: str, case: dict[str, Any]) -> None:
    """Corre un caso golden contra el agente real y calcula score compuesto.

    Pasos:
    1. Construye ``AnalysisInput`` desde ``case['input']``.
    2. Invoca :meth:`RaceAnalystAgent.invoke_per_valida` (v2, Gemini real)
       para la válida derivada de ``progression_df_records`` — el método
       y prompt (``race_analyst_v2.md``) que production usa realmente
       (specs/036 T050; antes se invocaba el v1 ``agent.invoke``, que
       ningún coach dispara hoy).
    3. Calcula ``rule_based_score`` (determinístico).
    4. Calcula ``llm_judge_score`` (Gemini, neutral 0.5 si parse falla).
    5. Combina con ``composite_score(rule, judge)``.
    6. Acumula en ``_RUN_RESULTS`` para scoreboard.

    El test PASA si ``composite >= 0.0`` (sólo verifica que se pueda
    correr); el test bloqueante es ``test_eval_average_meets_threshold``
    al final.

    Notas sobre los parámetros v2:
    - ``forbidden_names=[]``: los 11 casos golden son 100% sintéticos —
      no hay nombre real de un menor que proteger. Las guardrails de
      edad (``athlete_age``) y de veto duro N=1 sí corren igual.
    - NO se pasa ``full_season_records``: ese parámetro activa el bloque
      "Contexto temporada" del prompt, que exige citar ``gap_pct`` por
      válida — un campo que ningún caso golden trae en
      ``progression_df_records``. Pasarlo forzaría al modelo a una
      instrucción imposible de cumplir (el mismo patrón de alucinación
      forzada que la muletilla de vueltas documentada en spec.md US2).
      El camino "con historial" que sí se ejercita es
      ``AnalysisInput.season_comparative`` (T014/T053), poblado en
      ``case['input']`` cuando el caso lo declara.
    """
    from app.services.race.agents.analyst import PROMPT_VERSION_ANALYST_V2, RaceAnalystAgent
    from app.services.race.eval.judge import llm_judge_score

    case_input = case["input"]
    inp = _build_analysis_input(case_input)
    valida_num = _derive_valida_num(case_input)
    is_first_in_season = _derive_is_first_in_season(case_input)

    agent = RaceAnalystAgent(prompt_version=PROMPT_VERSION_ANALYST_V2)
    per_valida_results = await agent.invoke_per_valida(
        [(valida_num, inp)],
        forbidden_names=[],
        is_first_in_season=is_first_in_season,
        athlete_age=inp.age,
    )
    output, metrics = per_valida_results[valida_num]

    rule = rule_based_score(output, case)
    judge_result = await llm_judge_score(output, case)
    composite = composite_score(rule, judge_result.score)

    _RUN_RESULTS.append(
        {
            "case_id": case_id,
            "description": case.get("description", ""),
            "rule_score": rule,
            "judge_score": judge_result.score,
            "judge_parse_ok": judge_result.parse_ok,
            "composite": composite,
            "word_count": output.word_count,
            "citations_count": len(output.citations_used),
            "tokens_in": metrics.tokens_in,
            "tokens_out": metrics.tokens_out,
            "cost_usd": metrics.cost_usd,
        }
    )

    # Sanity check: score válido [0, 1]. La aserción de threshold es global.
    assert 0.0 <= composite <= 1.0


@pytest.mark.golden
@_skip_no_api
@_skip_unless_v3
@pytest.mark.parametrize(
    "case_id,case",
    _ALL_CASES_V3,
    ids=[cid for cid, _ in _ALL_CASES_V3],
)
async def test_golden_case_v3(case_id: str, case: dict[str, Any]) -> None:
    """Corre un caso golden v3 contra el agente real y calcula score compuesto.

    Pasos:
    1. Construye ``AnalystV3Input`` desde ``case['input']`` (misma forma que
       arma ``nodes/analyst_agent.py::_build_v3_inputs`` en producción).
    2. Invoca :meth:`RaceAnalystAgent.invoke_v3` con el prompt que
       corresponde a ``analysis_kind`` (``race_analyst_v3`` o
       ``race_season_summary_v3``).
    3. ``rule_based_score_v3`` con los números de los **bloques de datos**
       del caso — no ``V3CallResult.grounding_numbers``, que incluye las
       cifras del ejemplo resuelto del prompt y haría invisible a un modelo
       que las copie (ver docstring de ``scorer_v3``).
    4. ``llm_judge_score_v3`` (juez v2, neutral 0.5 si el parseo falla).
    5. ``composite_score(rule, judge)`` y acumulación para el scoreboard.

    El test pasa si el composite es un score válido; el bloqueante es
    ``test_eval_average_meets_threshold``.

    ``forbidden_names=[]``: los 8 casos son 100 % ficticios, no hay nombre
    real de un menor que escrubear. Las guardrails de edad y LTAD del
    prompt/prechecks corren igual.
    """
    from app.services.race.agents.analyst import RaceAnalystAgent, v3_prompt_version
    from app.services.race.eval.judge import llm_judge_score_v3
    from app.services.race.insight_v3 import render_insight_v3_markdown

    input_ = _build_analyst_v3_input(case)
    agent = RaceAnalystAgent(prompt_version=v3_prompt_version(input_.analysis_kind))
    results = await agent.invoke_v3([input_], forbidden_names=[])
    result = results[input_.valida_num]
    draft = result.insight

    rule = rule_based_score_v3(
        draft, case, grounding_numbers=case_grounding_numbers(case)
    )
    judge_result = await llm_judge_score_v3(draft, case)
    composite = composite_score(rule, judge_result.score)

    rendered = render_insight_v3_markdown(draft, input_.athlete_ref)
    _RUN_RESULTS.append(
        {
            "case_id": case_id,
            "description": case.get("description", ""),
            "rule_score": rule,
            "judge_score": judge_result.score,
            "judge_parse_ok": judge_result.parse_ok,
            "composite": composite,
            "word_count": len([w for w in rendered.split() if w]),
            # En v3 la columna "cites" del scoreboard cuenta principios
            # citados: el RAG de citas se removió y ``principles_cited`` es
            # su equivalente verificable (catálogo cerrado).
            "citations_count": len(draft.principles_cited),
            "tokens_in": result.metrics.tokens_in,
            "tokens_out": result.metrics.tokens_out,
            "cost_usd": result.metrics.cost_usd,
            "subscores": rule_subscores_v3(
                draft, case, grounding_numbers=case_grounding_numbers(case)
            ),
        }
    )

    assert 0.0 <= composite <= 1.0


@pytest.mark.golden
@_skip_no_api
def test_eval_average_meets_threshold() -> None:
    """Test bloqueante: promedio compuesto debe ser ≥ threshold (default 0.75).

    Threshold configurable vía ``RACE_EVAL_THRESHOLD`` (env). En CI normal
    este test no corre (sin marker ``golden``); en CI dedicado bloquea
    el merge si la regresión supera el umbral.

    También dispara el writer del scoreboard markdown (``last_run.md``)
    — separado del fixture para que falle visible si el archivo no se
    puede escribir.
    """
    threshold = float(os.getenv("RACE_EVAL_THRESHOLD", str(_DEFAULT_THRESHOLD)))
    assert _RUN_RESULTS, "No se ejecutó ningún caso golden — chequear discovery."

    avg = sum(r["composite"] for r in _RUN_RESULTS) / len(_RUN_RESULTS)
    _write_scoreboard(_RUN_RESULTS, avg, threshold)

    prompt_hint = (
        "prompts/race_analyst_v3.md · race_season_summary_v3.md"
        if _EVAL_VERSION == "v3"
        else "prompts/race_analyst_v2.md"
    )
    assert avg >= threshold, (
        f"Score promedio {avg:.3f} < threshold {threshold:.2f} (eval {_EVAL_VERSION}). "
        f"Revisar últimos cambios en {prompt_hint} o agents/analyst.py. "
        f"Detalle en evals/race_analyst/results/last_run.md."
    )


# ---------------------------------------------------------------------------
# Scoreboard writer
# ---------------------------------------------------------------------------


def _write_scoreboard(results: list[dict[str, Any]], avg: float, threshold: float) -> None:
    """Persiste el scoreboard markdown en ``results/last_run.md``.

    Formato amigable para code review: encabezado con fecha + threshold,
    tabla por caso con scores y métricas, footer con promedio + verdict.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Race Analyst Golden Eval — Last Run",
        "",
        f"- **Fecha:** {now}",
        f"- **Versión del eval:** {_EVAL_VERSION}",
        f"- **Threshold CI:** {threshold:.2f}",
        f"- **Casos ejecutados:** {len(results)}",
        f"- **Promedio compuesto:** **{avg:.3f}**",
        f"- **Verdict:** {'PASS' if avg >= threshold else 'FAIL'}",
        "",
        "## Detalle por caso",
        "",
        "| case_id | rule | judge | composite | words | cites | tokens_in | tokens_out | cost_usd |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['case_id']} | {r['rule_score']:.3f} | "
            f"{r['judge_score']:.3f}{'' if r['judge_parse_ok'] else '*'} | "
            f"{r['composite']:.3f} | {r['word_count']} | {r['citations_count']} | "
            f"{r['tokens_in']} | {r['tokens_out']} | {r['cost_usd']:.6f} |"
        )
    lines.append("")
    lines.append("> `*` indica que el parser del juez usó fallback neutral 0.5.")
    if _EVAL_VERSION == "v3":
        lines.append(
            "> En v3 la columna `cites` cuenta principios citados "
            "(`principles_cited`), no chunks de RAG."
        )
        sub_rows = [r for r in results if r.get("subscores")]
        if sub_rows:
            keys = sorted(sub_rows[0]["subscores"])
            lines.append("")
            lines.append("## Sub-rúbricas rule-based (v3)")
            lines.append("")
            lines.append("| case_id | " + " | ".join(keys) + " |")
            lines.append("|---" * (len(keys) + 1) + "|")
            for r in sub_rows:
                cells = " | ".join(f"{r['subscores'][k]:.2f}" for k in keys)
                lines.append(f"| {r['case_id']} | {cells} |")
    lines.append("")
    lines.append("## Descripción de los casos")
    lines.append("")
    for r in results:
        lines.append(f"- **{r['case_id']}**: {r['description']}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "last_run.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Cheap sanity tests — corren SIEMPRE (sin marker golden, sin API key)
# Permiten verificar el loader/schema sin requerir Gemini.
# ---------------------------------------------------------------------------


def test_loader_finds_at_least_ten_cases() -> None:
    """El golden dataset debe tener ≥10 casos (workflow §7.1)."""
    assert len(_ALL_CASES) >= 10, (
        f"Se esperaban ≥10 casos golden, encontrados {len(_ALL_CASES)} en {GOLDEN_DIR}"
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


def test_loader_can_build_analysis_input_for_all_cases() -> None:
    """Cada caso debe convertirse a :class:`AnalysisInput` sin error.

    Previene casos donde alguien edita el JSON con un campo inválido y la
    eval falla 5 minutos después de empezar.
    """
    errors: list[str] = []
    for case_id, case in _ALL_CASES:
        try:
            _build_analysis_input(case["input"])
        except Exception as exc:  # pragma: no cover - usaremos assert
            errors.append(f"case_{case_id}: {exc}")
    assert not errors, "Casos golden con input inválido: " + " | ".join(errors)


def test_derive_valida_num_uses_last_progression_record() -> None:
    """La válida analizada es la última fila de ``progression_df_records`` (T050)."""
    assert _derive_valida_num({"progression_df_records": [{"valida_num": 1}, {"valida_num": 4}]}) == 4
    assert _derive_valida_num({"progression_df_records": []}) == 1
    assert _derive_valida_num({}) == 1


def test_derive_is_first_in_season_only_true_for_single_record() -> None:
    """La REGLA N=1 del prompt v2 sólo debe activarse con exactamente 1 registro (T050)."""
    assert _derive_is_first_in_season({"progression_df_records": [{"valida_num": 1}]}) is True
    assert _derive_is_first_in_season({"progression_df_records": []}) is True
    assert (
        _derive_is_first_in_season({"progression_df_records": [{"valida_num": 1}, {"valida_num": 2}]})
        is False
    )


def test_at_least_one_case_exercises_season_comparative_path() -> None:
    """T053: al menos un caso golden trae ``season_comparative`` con 2+ válidas previas.

    Antes de T053 los 10 casos originales dejaban ``season_comparative``
    vacío (default de :class:`AnalysisInput`) — el bloque "Contexto de
    temporada" del prompt v2 (``race_analyst_v2.md:164-195``) nunca se
    ejercitaba con datos reales, sólo con la rama ``first_reference``.
    """
    cases_with_history = [
        (cid, case)
        for cid, case in _ALL_CASES
        if len(case["input"].get("season_comparative") or []) >= 2
    ]
    assert cases_with_history, (
        "Ningún caso golden pobla season_comparative con ≥2 válidas previas — "
        "el camino 'con historial' del prompt v2 (T014) no se ejercita."
    )
    # El caso también debe declarar progression_assessment != first_reference,
    # si no el prompt renderiza la tabla comparativa vacía bajo un mandato que
    # exige citarla (contradicción — ver notas de case_011.json).
    for cid, case in cases_with_history:
        assessment = case["input"].get("progression_assessment")
        assert assessment and assessment != "first_reference", (
            f"case_{cid}: trae season_comparative pero progression_assessment="
            f"{assessment!r} — el prompt v2 renderizaría la rama 'first_reference' "
            "(prohíbe comparar) sobre una tabla con datos reales."
        )


# ---------------------------------------------------------------------------
# T052 — sub-rúbricas de calidad narrativa (specs/036 US2)
#
# Viven aquí (no en tests/services/race/eval/test_scorer.py) por el límite
# estricto de ownership de archivos durante la Wave 3 de specs/036: ese
# archivo no está en el scope de este agente. Debería fusionarse con los
# tests unitarios de scorer.py en la integración de la feature — ver
# 'blockers' del reporte de esta tarea.
#
# Ninguno de estos tests llama al modelo real: usan markdown fijo
# (fixture), replicando literalmente los dos ejemplos citados en
# spec.md US2 ("El tiempo de carrera fue 0:36:19" repetido, la muletilla
# de vueltas). Demuestran la ordenación fail-antes/pasa-después exigida:
# el mismo texto (hoy real, sin cambios) puntuaba 1.0 con las 5
# sub-rúbricas anteriores a T052 y puntúa 0.70 con las 8 actuales.
# ---------------------------------------------------------------------------

# Texto adaptado verbatim de spec.md US2 (ya público, 100% genérico/sintético
# — "la deportista", sin edad/club/resultado identificable de un menor real)
# bajo los 3 headings v2, para aislar el efecto de T052 del de T050 (la
# estructura ya es v2-válida, así que sólo fallan las 3 rúbricas nuevas).
_TEMPLATED_OUTPUT_MD = (
    "## Qué pasó en esta válida\n\n"
    "La deportista completó la válida 1, registrando un tiempo de 0:36:19 y "
    "finalizando en la posición 4. El tiempo de carrera fue 0:36:19, con un "
    "gap al líder de 0:04:17. Alcanzó el número máximo de vueltas previsto "
    "para la categoría.\n\n"
    "## Recorrido hasta acá\n\n"
    "Se observa una evolución en el resultado de la deportista. El grupo "
    "LTAD es mini-bambino.\n\n"
    "## Hacia dónde va\n\n"
    "- Trabajar técnica de descenso (categoría=technique, prioridad=med)\n"
    "- Mantener volumen actual (categoría=volume, prioridad=low)\n"
) + ("palabra " * 40)  # empuja word_count por encima del piso de 50 sin afectar el resto

_TEMPLATED_OUTPUT_CASE: dict[str, Any] = {
    "expected_themes": ["evoluci"],
    "forbidden_terms": [],
    "max_words": 400,
    "must_cite": False,
    "input": {},  # sin clave "lap"/"vuelta" declarada → no_lap_filler debe fallar
}


class _FakeAnalysisOutput:
    """Doble mínimo de :class:`AnalysisOutput` — sólo los 3 campos que lee el scorer."""

    def __init__(self, markdown: str, citations: list[str] | None = None) -> None:
        self.raw_markdown = markdown
        self.word_count = len([w for w in markdown.split() if w])
        self.citations_used = citations or []


def test_templated_output_passes_pre_t052_rubric_but_fails_post_t052() -> None:
    """Ordenación fail-antes/pasa-después de T052, sin tocar código pre-T052.

    El scorer previo a T052 (5 sub-rúbricas: themes/forbidden/word_count/
    sections/citations, pesos 0.25/0.25/0.20/0.15/0.15 — ver historial de
    ``scorer.py``) es ciego a la repetición de cifras, a la ausencia de
    conectores y a la muletilla de vueltas: el texto templado de spec.md
    US2 puntuaba **1.0** con esas 5 sub-rúbricas (recalculado aquí con los
    pesos históricos, ya que el código viejo ya no existe en el módulo).
    Con las 3 sub-rúbricas nuevas de T052 el mismo texto, sin cambiar ni
    un carácter, cae a **0.70** — por debajo del ``RACE_EVAL_THRESHOLD``
    por defecto (0.75) ya en la componente determinística, antes incluso
    de sumar el juez LLM.
    """
    from app.services.race.eval import scorer as scorer_module

    output = _FakeAnalysisOutput(_TEMPLATED_OUTPUT_MD)

    # Pesos pre-T052 (histórico — ver docstring del módulo scorer.py).
    _PRE_T052_WEIGHTS = {
        "themes": 0.25,
        "forbidden": 0.25,
        "word_count": 0.20,
        "sections": 0.15,
        "citations": 0.15,
    }
    pre_t052_score = (
        _PRE_T052_WEIGHTS["themes"]
        * scorer_module._all_themes_present(
            output.raw_markdown, _TEMPLATED_OUTPUT_CASE["expected_themes"]
        )
        + _PRE_T052_WEIGHTS["forbidden"]
        * scorer_module._no_forbidden_terms(
            output.raw_markdown, _TEMPLATED_OUTPUT_CASE["forbidden_terms"]
        )
        + _PRE_T052_WEIGHTS["word_count"]
        * scorer_module._word_count_in_range(
            output.word_count, _TEMPLATED_OUTPUT_CASE["max_words"]
        )
        + _PRE_T052_WEIGHTS["sections"] * scorer_module._has_all_canonical_sections(output.raw_markdown)
        + _PRE_T052_WEIGHTS["citations"]
        * scorer_module._citations_satisfied(output.citations_used, must_cite=False)
    )
    assert pre_t052_score == pytest.approx(1.0), (
        "Precondición del test: el texto templado debía puntuar perfecto bajo "
        "las 5 sub-rúbricas pre-T052 (si esto falla, el fixture ya no aísla T052)."
    )

    post_t052_score = rule_based_score(output, _TEMPLATED_OUTPUT_CASE)
    assert post_t052_score == pytest.approx(0.70, abs=1e-6)
    assert post_t052_score < pre_t052_score
    assert post_t052_score < _DEFAULT_THRESHOLD <= pre_t052_score, (
        "T052 debe hacer que un texto templado deje de alcanzar el threshold "
        "por defecto en la componente rule-based; antes lo alcanzaba."
    )


def test_repeated_figure_in_section_1_fails_its_subrubric() -> None:
    """T052-a: la misma cifra en 2 oraciones de la Sección 1 penaliza ``no_repeated_figures``.

    Par mínimo que difiere en una sola cosa (la cifra del gap se repite o
    no) para aislar exactamente esta sub-rúbrica, sin confundirla con
    conectores o muletilla de vueltas (cubiertos por los tests siguientes).
    """
    from app.services.race.eval.scorer import _no_repeated_figures_in_section_1

    repeated_md = (
        "## Qué pasó en esta válida\n\n"
        "La deportista completó la válida 1, registrando un tiempo de 0:36:19 "
        "y finalizando en la posición 4. El tiempo de carrera fue 0:36:19, con "
        "un gap al líder de 0:04:17.\n"
    )
    not_repeated_md = (
        "## Qué pasó en esta válida\n\n"
        "La deportista completó la válida 1, registrando un tiempo de 0:36:19 "
        "y finalizando en la posición 4, con un gap al líder de 0:04:17.\n"
    )
    assert _no_repeated_figures_in_section_1(repeated_md) is False
    assert _no_repeated_figures_in_section_1(not_repeated_md) is True


def test_missing_connectors_fails_its_subrubric() -> None:
    """T052-b: ninguna sección con conector relacional penaliza ``connectors``."""
    from app.services.race.eval.scorer import _all_sections_have_connectors

    no_connectors_md = (
        "## Qué pasó en esta válida\n\nLa deportista completó la válida.\n\n"
        "## Recorrido hasta acá\n\nEl resultado se mantiene.\n\n"
        "## Hacia dónde va\n\nMantener el plan actual.\n"
    )
    with_connectors_md = (
        "## Qué pasó en esta válida\n\nGracias a sostener el ritmo, la deportista "
        "completó la válida.\n\n"
        "## Recorrido hasta acá\n\nEn comparación con válidas anteriores, el "
        "resultado se mantiene estable.\n\n"
        "## Hacia dónde va\n\nComo resultado de lo anterior, conviene mantener "
        "el plan actual.\n"
    )
    assert _all_sections_have_connectors(no_connectors_md) is False
    assert _all_sections_have_connectors(with_connectors_md) is True


def test_lap_filler_fails_when_case_declares_no_lap_data() -> None:
    """T052-c: la muletilla de vueltas penaliza ``no_lap_filler`` si el caso no declara el dato.

    Hoy ``AnalysisInput`` no define ningún campo de vueltas (grep confirma
    ausencia total en ``schemas.py``), así que ``has_lap_data`` es siempre
    ``False`` en la práctica — la detección por nombre de clave
    ("lap"/"vuelta") es defensiva ante un futuro campo real (T055).
    """
    from app.services.race.eval.scorer import _case_declares_lap_data, _no_lap_filler_when_absent

    filler_md = "## Qué pasó en esta válida\n\nAlcanzó el número máximo de vueltas previsto.\n"
    clean_md = "## Qué pasó en esta válida\n\nCompletó la válida sin abandono.\n"

    assert _case_declares_lap_data({}) is False
    assert _no_lap_filler_when_absent(filler_md, has_lap_data=False) is False
    assert _no_lap_filler_when_absent(clean_md, has_lap_data=False) is True
    # Si el caso SÍ declarara un dato de vueltas, mencionar la cifra es legítimo.
    assert _no_lap_filler_when_absent(filler_md, has_lap_data=True) is True


# ---------------------------------------------------------------------------
# T401 — sanity tests del dataset golden v3 (offline, sin API key)
#
# Corren SIEMPRE: validan que el dataset que alimenta el gate sea cargable,
# construible y consistente antes de gastar un solo token del proveedor.
# ---------------------------------------------------------------------------


def test_v3_loader_finds_at_least_eight_cases() -> None:
    """AC-7.1: el golden v3 debe tener ≥8 casos."""
    assert len(_ALL_CASES_V3) >= 8, (
        f"Se esperaban ≥8 casos golden v3, encontrados {len(_ALL_CASES_V3)} "
        f"en {GOLDEN_V3_DIR}"
    )


def test_v3_loader_validates_all_case_schemas() -> None:
    """Re-corre la validación de schema con diagnóstico agregado."""
    paths = sorted(GOLDEN_V3_DIR.glob("case_*.json"))
    errors: list[str] = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            _validate_case_schema_v3(data, p)
        except (AssertionError, json.JSONDecodeError) as exc:
            errors.append(f"{p.name}: {exc}")
    assert not errors, "Casos golden v3 con schema inválido: " + " | ".join(errors)


def test_v3_cases_build_analyst_input_and_ideal_output() -> None:
    """Cada caso debe construir ``AnalystV3Input`` y validar su ``ideal_output``.

    Previene el modo de falla más caro del eval: descubrir que un JSON tiene
    un campo inválido cinco minutos después de arrancar, con la mitad de las
    llamadas al proveedor ya gastadas.
    """
    from app.services.race.insight_v3 import InsightV3

    errors: list[str] = []
    for case_id, case in _ALL_CASES_V3:
        try:
            _build_analyst_v3_input(case)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"case_{case_id} input: {exc}")
        try:
            InsightV3.model_validate(case["ideal_output"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"case_{case_id} ideal_output: {exc}")
    assert not errors, "Casos golden v3 inválidos: " + " | ".join(errors)


def test_v3_ideal_outputs_score_at_least_090_with_rule_scorer() -> None:
    """El ``ideal_output`` de cada caso debe puntuar ≥0.90 en el scorer v3.

    Doble propósito, por eso vive en el runner y no en los tests unitarios
    del scorer:

    1. Valida el dataset: si una evidencia del ideal cita un número que no
       está en los bloques de datos, el caso está mal construido y el gate
       exigiría al modelo algo imposible.
    2. Valida el scorer contra un output "de referencia" real y completo,
       no contra fixtures mínimas.

    No se exige 1.0: las sub-rúbricas ``themes`` y ``word_limits`` son
    proporcionales y un ideal legítimo puede omitir un theme secundario.
    """
    low: list[str] = []
    for case_id, case in _ALL_CASES_V3:
        score = rule_based_score_v3(case["ideal_output"], case)
        if score < 0.90:
            subs = rule_subscores_v3(case["ideal_output"], case)
            detail = ", ".join(f"{k}={v:.2f}" for k, v in sorted(subs.items()))
            low.append(f"case_{case_id}: {score:.3f} ({detail})")
    assert not low, "Ideales del golden v3 por debajo de 0.90: " + " | ".join(low)


def test_v3_dataset_covers_the_required_scenarios() -> None:
    """El dataset cubre los escenarios exigidos por T401.

    Mini-bambino / bambino / juvenil, N=1, mejora, declive, campeonato,
    Circa-PHV, sin antropometría, sin ventana de entrenamiento y resumen de
    temporada. Sin esta aserción el dataset puede degradarse a ocho
    variantes del mismo caso fácil sin que nadie lo note.
    """
    inputs = [case["input"] for _, case in _ALL_CASES_V3]
    ideals = [case["ideal_output"] for _, case in _ALL_CASES_V3]

    ltad_groups = {str(i.get("ltad_group")) for i in inputs}
    assert {"mini-bambino", "bambino", "juvenil"} <= ltad_groups

    trends = {str(o.get("trend")) for o in ideals}
    assert {"improving", "declining", "first_reference"} <= trends

    assert any(i.get("analysis_kind") == "season" for i in inputs), "falta caso de temporada"
    assert any(
        (i.get("field_metrics") or {}).get("is_championship") for i in inputs
    ), "falta caso de campeonato"
    assert any(
        (i.get("field_metrics") or {}).get("expected_position") is None
        and i.get("analysis_kind") != "season"
        for i in inputs
    ), "falta caso N=1 sin expectativa calculable"
    assert any(
        ((i.get("field_metrics") or {}).get("delta_vs_expected") or 0) > 0
        for i in inputs
    ), "falta caso que termine por encima de lo esperado"
    assert any(i.get("anthro_context") is None for i in inputs), "falta caso sin antropometría"
    assert any(i.get("training_window") is None for i in inputs), (
        "falta caso sin ventana de entrenamiento"
    )
    assert any(
        ((i.get("anthro_context") or {}).get("latest") or {}).get("maturation_status")
        == "Circa-PHV"
        for i in inputs
    ), "falta caso Circa-PHV"
    assert any(
        (i.get("training_window") or {}).get("attendance_pct", 100) < 60 for i in inputs
    ), "falta caso con asistencia baja en la ventana"


def test_v3_cases_declare_data_gaps_when_a_block_is_missing() -> None:
    """Si falta antropometría o ventana, el ideal lo declara en ``data_gaps`` (AC-1.2)."""
    for case_id, case in _ALL_CASES_V3:
        case_input = case["input"]
        gaps = " ".join(case["ideal_output"].get("data_gaps") or []).lower()
        if case_input.get("anthro_context") is None and case_input.get("analysis_kind") != "season":
            assert "antropometr" in gaps or "maduraci" in gaps, (
                f"case_{case_id}: sin antropometría pero el ideal no lo declara"
            )
        if case_input.get("training_window") is None:
            assert "asistencia" in gaps or "entrena" in gaps, (
                f"case_{case_id}: sin ventana de entrenamiento pero el ideal no lo declara"
            )


def test_v3_cases_carry_no_body_composition_data() -> None:
    """Privacidad (CLAUDE.md, AC-1.3): ni peso, ni IMC, ni estado nutricional.

    Se inspecciona el JSON crudo completo de cada caso — input **e**
    ``ideal_output`` — porque el fixture es exactamente lo que terminaría en
    un prompt si alguien lo copiara para depurar.
    """
    banned_keys = ("weight", "peso", "bmi", "imc", "nutrition", "nutricional", "z_score", "zscore")
    # En los valores solo se prohíben las expresiones que SÍ son composición
    # corporal: "peso corporal" es el nombre de un bloque de fuerza (trabajo
    # con el propio cuerpo) y "peso centrado" es postura sobre la bici —
    # ninguno es un dato del menor.
    banned_value_patterns = (
        r"\bimc\b",
        r"estado nutricional",
        r"índice de masa",
        r"\d+\s*kg\b",
        r"kg\s*/\s*m",
    )

    def _walk_keys(node: Any, path: Path) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                hits = [b for b in banned_keys if b in str(key).lower()]
                assert not hits, f"{path.name}: clave prohibida {key!r} ({hits})"
                _walk_keys(value, path)
        elif isinstance(node, list):
            for item in node:
                _walk_keys(item, path)

    for path in sorted(GOLDEN_V3_DIR.glob("case_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        _walk_keys(data, path)
        raw = path.read_text(encoding="utf-8").lower()
        hits = [p for p in banned_value_patterns if re.search(p, raw)]
        assert not hits, f"{path.name}: contiene composición corporal {hits}"


def test_v3_ideal_outputs_use_only_catalog_refs_present_in_the_case() -> None:
    """Un ``catalog_ref`` del ideal debe existir en el catálogo del propio caso (AC-3.1)."""
    for case_id, case in _ALL_CASES_V3:
        catalog = case["input"].get("catalog_context") or {}
        by_kind = {
            "interval_template": {str(t.get("id")) for t in catalog.get("interval_templates") or []},
        }
        for action in case["ideal_output"].get("actions") or []:
            ref = action.get("catalog_ref")
            if not ref:
                continue
            kind = str(ref.get("kind"))
            assert str(ref.get("code")) in by_kind.get(kind, set()), (
                f"case_{case_id}: catalog_ref {kind}:{ref.get('code')} no existe en el caso"
            )
