"""LLM-as-judge para eval del ``RaceAnalystAgent`` (Fase 7 §7.5).

Diseño:

- Prompt en ``app/services/race/eval/prompts/judge_v1.md`` (Jinja2).
- Modelo: Gemini 2.5 Flash Lite (mismo del analyst, factory inyectable).
- Output esperado: JSON ``{"score": 0.0-1.0, "reasoning": str}``.
- Parseo defensivo:
    * Acepta JSON puro o JSON envuelto en fences ``` ```json ... ``` ```.
    * Si el parseo falla → ``0.5`` (neutral) + WARNING log.
    * Si ``score`` fuera de [0, 1] → clampea + WARNING log.
- Mock-friendly: factory ``llm_factory`` permite inyectar ``FakeChatLLM``
  en tests; default = :func:`build_chat_llm` real.

Razón del fallback neutral 0.5:
- Falla del juez NO debe propagar como 0 (perjudica al output bueno).
- Falla del juez NO debe propagar como 1 (esconde regresiones reales).
- 0.5 es la opción menos sesgada; el log warning visible permite
  detectar problemas sistemáticos del prompt del juez.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.race.agents._llm import call_llm
from app.services.race.schemas import AnalysisOutput

logger = logging.getLogger(__name__)

__all__ = [
    "JUDGE_PROMPT_PATH",
    "JUDGE_V2_PROMPT_PATH",
    "JudgeResult",
    "build_judge_prompt",
    "build_judge_v2_prompt",
    "llm_judge_score",
    "llm_judge_score_v3",
    "parse_judge_output",
]

JUDGE_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge_v1.md"

# Juez del eval v3 (feature 037, T401). Prompt separado —no una versión
# nueva del mismo archivo— porque el eval v2 sigue corriendo con
# ``RACE_EVAL_VERSION=v2`` y debe seguir midiendo con su rúbrica histórica.
JUDGE_V2_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge_v2.md"

# Score neutral cuando el parseo falla — declarado explícitamente.
_NEUTRAL_SCORE = 0.5

# Regex para extraer un bloque JSON dentro de fences ```json ... ``` (o ```).
# Tolerante a saltos de línea y a "json" opcional.
_FENCE_RE = re.compile(
    r"```(?:json)?\s*(?P<body>\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

# Regex fallback: busca el primer objeto JSON balanceado (heurística simple).
_BARE_JSON_RE = re.compile(r"\{[^{}]*\"score\"[^{}]*\}", re.DOTALL)


class JudgeResult:
    """Resultado del LLM-as-judge.

    Atributos:
        score: ∈ [0.0, 1.0].
        reasoning: explicación textual (puede ser vacía si parse falló).
        parse_ok: ``True`` si el LLM devolvió JSON válido (telemetría).
    """

    __slots__ = ("score", "reasoning", "parse_ok")

    def __init__(self, score: float, reasoning: str, parse_ok: bool) -> None:
        self.score = score
        self.reasoning = reasoning
        self.parse_ok = parse_ok

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"JudgeResult(score={self.score:.3f}, parse_ok={self.parse_ok})"


def _load_judge_template() -> str:
    """Carga el contenido bruto del template (sin renderizar)."""
    return JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


def build_judge_prompt(case: dict[str, Any], actual_output: str) -> str:
    """Renderiza ``judge_v1.md`` con el caso golden + output real.

    Args:
        case: dict del case (debe traer ``case_id``, ``description``,
            ``expected_themes``, ``forbidden_terms``, ``max_words``,
            ``ideal_output_excerpt``).
        actual_output: ``raw_markdown`` del :class:`AnalysisOutput`.

    Returns:
        Prompt renderizado listo para enviar al LLM.

    Notas defensivas:
        Si una clave esperada falta, se sustituye por default vacío:
        evita romper la eval por un caso golden incompleto (el runner
        loggea un warning).
    """
    # Import lazy del entorno Jinja: reaprovecha la convención del módulo
    # de prompts del analyst.
    from jinja2 import ChainableUndefined, Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(JUDGE_PROMPT_PATH.parent)),
        autoescape=False,
        keep_trailing_newline=True,
        undefined=ChainableUndefined,
    )
    template = env.get_template(JUDGE_PROMPT_PATH.name)
    return template.render(
        case_id=case.get("case_id", "unknown"),
        case_description=case.get("description", ""),
        ideal_output_excerpt=case.get("ideal_output_excerpt", ""),
        actual_output=actual_output or "(output vacío)",
        expected_themes=list(case.get("expected_themes") or []),
        forbidden_terms=list(case.get("forbidden_terms") or []),
        max_words=int(case.get("max_words") or 600),
    )


def parse_judge_output(raw_text: str) -> JudgeResult:
    """Parsea defensivamente el JSON emitido por el juez.

    Estrategia de fallback (en orden):

    1. ``json.loads(raw_text)`` directo.
    2. Buscar ``{...}`` dentro de fences ``` ```json``` ```.
    3. Buscar el primer objeto JSON balanceado con clave ``score``.
    4. Si todo falla → :data:`_NEUTRAL_SCORE` (0.5) + warning.

    Returns:
        :class:`JudgeResult` con ``parse_ok=False`` si se usó fallback.
    """
    if not raw_text or not raw_text.strip():
        logger.warning("llm_judge: output vacío — usando neutral 0.5")
        return JudgeResult(score=_NEUTRAL_SCORE, reasoning="", parse_ok=False)

    text = raw_text.strip()

    # Intento 1: parseo directo.
    parsed: Optional[dict[str, Any]] = None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    # Intento 2: fence ```json ... ```.
    if parsed is None:
        m = _FENCE_RE.search(text)
        if m:
            try:
                parsed = json.loads(m.group("body"))
            except (json.JSONDecodeError, ValueError):
                parsed = None

    # Intento 3: primer objeto JSON balanceado con "score".
    if parsed is None:
        m2 = _BARE_JSON_RE.search(text)
        if m2:
            try:
                parsed = json.loads(m2.group(0))
            except (json.JSONDecodeError, ValueError):
                parsed = None

    if not isinstance(parsed, dict) or "score" not in parsed:
        logger.warning(
            "llm_judge: no se pudo parsear JSON (%s chars) — usando neutral 0.5",
            len(text),
        )
        return JudgeResult(
            score=_NEUTRAL_SCORE,
            reasoning="parse_error",
            parse_ok=False,
        )

    # Coerción defensiva del score.
    try:
        score = float(parsed.get("score", _NEUTRAL_SCORE))
    except (TypeError, ValueError):
        logger.warning("llm_judge: score no numérico — usando neutral 0.5")
        return JudgeResult(
            score=_NEUTRAL_SCORE,
            reasoning=str(parsed.get("reasoning", "score_invalid")),
            parse_ok=False,
        )

    # Clamp [0, 1].
    if score < 0.0 or score > 1.0:
        logger.warning("llm_judge: score fuera de rango (%s) — clampeando", score)
        score = max(0.0, min(1.0, score))

    reasoning = str(parsed.get("reasoning", "")).strip()
    return JudgeResult(score=round(score, 4), reasoning=reasoning, parse_ok=True)


async def llm_judge_score(
    output: AnalysisOutput,
    case: dict[str, Any],
    llm_factory: Optional[Callable[[], Any]] = None,
) -> JudgeResult:
    """Invoca el LLM-as-judge contra un output del analyst.

    Args:
        output: :class:`AnalysisOutput` producido por
            :class:`RaceAnalystAgent.invoke`.
        case: dict del caso golden cargado de ``case_NNN.json``.
        llm_factory: callable ``() -> chat_model``. Si ``None`` usa
            :func:`build_chat_llm` (requiere ``AI_API_KEY``).

    Returns:
        :class:`JudgeResult`.

    Notas:
        - Para tests, pasar ``llm_factory=lambda: FakeChatLLM([...])``.
        - El factory se instancia **una vez por llamada** — el caller
          puede compartir clientes entre casos vía closure si quiere
          reutilizar conexiones.
    """
    prompt = build_judge_prompt(case, output.raw_markdown)

    if llm_factory is None:
        from app.services.race.agents._llm import build_chat_llm

        llm = build_chat_llm(temperature=0.0)  # Determinístico para juez.
    else:
        llm = llm_factory()

    try:
        call = await call_llm(llm, prompt)
    except Exception as exc:
        logger.warning("llm_judge: llamada al LLM falló (%s) — neutral 0.5", exc)
        return JudgeResult(score=_NEUTRAL_SCORE, reasoning="llm_error", parse_ok=False)

    return parse_judge_output(call.text)


# ---------------------------------------------------------------------------
# Juez v2 — eval del InsightV3 (feature 037, T401)
# ---------------------------------------------------------------------------


def _render_prompt_file(path: Path, context: dict[str, Any]) -> str:
    """Renderiza un template Jinja2 del directorio de prompts del eval."""
    from jinja2 import ChainableUndefined, Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(path.parent)),
        autoescape=False,
        keep_trailing_newline=True,
        undefined=ChainableUndefined,
    )
    return env.get_template(path.name).render(**context)


def _insight_to_json(draft: Any) -> str:
    """Serializa un ``InsightV3`` (o dict) a JSON legible para el juez."""
    if draft is None:
        return "null"
    dump = getattr(draft, "model_dump", None)
    payload = dump(mode="json") if callable(dump) else draft
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def build_judge_v2_prompt(case: dict[str, Any], draft: Any) -> str:
    """Renderiza ``judge_v2.md`` con el caso golden v3 + el draft real.

    A diferencia de :func:`build_judge_prompt` (v1), el juez recibe **los
    bloques de datos que vio el analista** (``scorer_v3.case_data_blocks``):
    sin ellos, la dimensión de precisión sería una opinión y no una
    verificación. El resto del prompt (método, reglas, ejemplo resuelto)
    queda fuera a propósito — el juez evalúa el output, no el prompt.

    Args:
        case: dict del caso golden v3 (``golden_v3/case_NNN.json``).
        draft: :class:`~app.services.race.insight_v3.InsightV3` o dict.

    Returns:
        Prompt renderizado. Claves faltantes del caso → defaults vacíos
        (nunca lanza por un caso golden incompleto; el runner valida el
        schema por separado).
    """
    from app.services.race.eval.scorer_v3 import case_data_blocks

    case_input = dict(case.get("input") or {})
    return _render_prompt_file(
        JUDGE_V2_PROMPT_PATH,
        {
            "case_id": case.get("case_id", "unknown"),
            "case_description": case.get("description", ""),
            "analysis_kind": case_input.get("analysis_kind", "valida"),
            "athlete_ref": case_input.get("athlete_ref", "la deportista"),
            "age": case_input.get("age"),
            "ltad_group": case_input.get("ltad_group", "bambino"),
            "data_blocks": case_data_blocks(case) or "(sin datos)",
            "ideal_output_json": _insight_to_json(case.get("ideal_output")),
            "actual_output_json": _insight_to_json(draft),
            "expected_themes": list(case.get("expected_themes") or []),
            "forbidden_terms": list(case.get("forbidden_terms") or []),
            "expected_headline_keywords": list(
                case.get("expected_headline_keywords") or []
            ),
            "max_words": int(case.get("max_words") or 450),
        },
    )


async def llm_judge_score_v3(
    draft: Any,
    case: dict[str, Any],
    llm_factory: Optional[Callable[[], Any]] = None,
) -> JudgeResult:
    """Invoca el juez v2 sobre un ``InsightV3`` del analista.

    Mismo contrato defensivo que :func:`llm_judge_score`: cualquier fallo
    del proveedor o del parseo devuelve el neutral 0.5 con
    ``parse_ok=False`` en vez de propagar (una caída del juez no debe
    hundir ni inflar el gate).

    Args:
        draft: draft estructurado a evaluar.
        case: caso golden v3.
        llm_factory: callable ``() -> chat_model`` para tests. ``None`` usa
            :func:`build_chat_llm` con el modelo legacy ``RACE_AI_MODEL``
            (el juez es deliberadamente independiente de los modelos de
            analyst/critic: si mejoramos el analista, el juez no cambia).
    """
    prompt = build_judge_v2_prompt(case, draft)

    if llm_factory is None:
        from app.services.race.agents._llm import build_chat_llm

        llm = build_chat_llm(temperature=0.0)  # Determinístico para juez.
    else:
        llm = llm_factory()

    try:
        call = await call_llm(llm, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_judge_v3: llamada al LLM falló (%s) — neutral 0.5", exc)
        return JudgeResult(score=_NEUTRAL_SCORE, reasoning="llm_error", parse_ok=False)

    return parse_judge_output(call.text)
