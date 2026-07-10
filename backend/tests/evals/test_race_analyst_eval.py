"""Runner pytest del eval golden ``RaceAnalystAgent`` (Fase 7 §7.3).

Características:

- **Marker** ``@pytest.mark.golden`` — registrado en ``pyproject.toml``.
  No corre en CI normal (opt-in con ``-m golden``).
- **Skip si ``AI_API_KEY`` ausente** — eval real necesita Gemini; en CI
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
- ``input`` (dict con campos de :class:`AnalysisInput`)
- ``expected_themes`` (list[str])
- ``forbidden_terms`` (list[str])
- ``must_cite`` (bool)
- ``max_words`` (int)
- ``ideal_output_excerpt`` (str)

Threshold CI: ``RACE_EVAL_THRESHOLD`` env (default ``0.75``). Si el
promedio cae por debajo → test ``test_eval_average_meets_threshold`` falla
y bloquea el merge (workflow §7.7).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.services.race.eval.scorer import composite_score, rule_based_score
from app.services.race.schemas import AnalysisInput

GOLDEN_DIR = Path(__file__).parent.parent.parent / "evals" / "race_analyst" / "golden"
RESULTS_DIR = Path(__file__).parent.parent.parent / "evals" / "race_analyst" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_THRESHOLD = 0.75

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


# ---------------------------------------------------------------------------
# Skip guard: RACE_AI_API_KEY required for the real eval
# ---------------------------------------------------------------------------


def _api_key_available() -> bool:
    """``True`` si hay clave para llamar Gemini.

    Acepta ``RACE_AI_API_KEY`` (dedicada al pipeline race/agents/, que sigue
    en Gemini — ver CLAUDE.md notas 2026-07-10) o ``GOOGLE_API_KEY`` (SDK
    convención). ``AI_API_KEY`` ya NO aplica aquí: apunta a Anthropic.
    """
    return bool(os.getenv("RACE_AI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


_skip_no_api = pytest.mark.skipif(
    not _api_key_available(),
    reason="RACE_AI_API_KEY/GOOGLE_API_KEY no disponible; eval real necesita Gemini.",
)


# ---------------------------------------------------------------------------
# Parametrized run
# ---------------------------------------------------------------------------


_ALL_CASES = _load_all_cases()


@pytest.mark.golden
@_skip_no_api
@pytest.mark.parametrize(
    "case_id,case",
    _ALL_CASES,
    ids=[cid for cid, _ in _ALL_CASES],
)
async def test_golden_case(case_id: str, case: dict[str, Any]) -> None:
    """Corre un caso golden contra el agente real y calcula score compuesto.

    Pasos:
    1. Construye ``AnalysisInput`` desde ``case['input']``.
    2. Invoca :class:`RaceAnalystAgent.invoke` (Gemini real).
    3. Calcula ``rule_based_score`` (determinístico).
    4. Calcula ``llm_judge_score`` (Gemini, neutral 0.5 si parse falla).
    5. Combina con ``composite_score(rule, judge)``.
    6. Acumula en ``_RUN_RESULTS`` para scoreboard.

    El test PASA si ``composite >= 0.0`` (sólo verifica que se pueda
    correr); el test bloqueante es ``test_eval_average_meets_threshold``
    al final.
    """
    from app.services.race.agents.analyst import RaceAnalystAgent
    from app.services.race.eval.judge import llm_judge_score

    inp = _build_analysis_input(case["input"])
    agent = RaceAnalystAgent()
    output, metrics = await agent.invoke(inp)

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

    assert avg >= threshold, (
        f"Score promedio {avg:.3f} < threshold {threshold:.2f}. "
        f"Revisar últimos cambios en prompts/agents/race_analyst_v1.md. "
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
