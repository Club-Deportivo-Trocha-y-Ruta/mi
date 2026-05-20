"""``RaceCriticAgent`` — revisa el draft del analyst contra reglas inviolables.

Flujo:

1. Renderiza ``race_critic_v1.md`` con el ``raw_markdown`` del draft.
2. Invoca Gemini Flash Lite (mismo modelo que el analyst — más barato
   que un Pro y suficiente para detección de patrones explícitos).
3. Parsea JSON estricto → :class:`CriticFeedback`.
4. Feature flag :envvar:`RACE_AGENT_CRITIC_ENABLED` (default ``True``).
   Si ``False``, :meth:`invoke` retorna un feedback "pasa-todo" sin
   gastar tokens.

Decisiones:
- **Output JSON, no markdown.** El critic produce datos estructurados
  consumidos por el nodo ``hitl_gate_review`` del grafo — JSON es
  trivial de parsear y el modelo es bueno en JSON con instrucciones
  explícitas.
- **Parseo defensivo:** si el modelo emite texto antes/después del JSON
  (a veces lo envuelve en ``` ```json), extraemos el primer bloque ``{
  ... }`` balanceado. Si falla → degradamos a "must_block + severity=high
  + issue=parsing_failed" para forzar HITL manual.
- **Sin estado.**
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from app.services.race.agents._llm import LLMCallResult, build_chat_llm, call_llm
from app.services.race.agents.pricing import PROMPT_VERSION_CRITIC
from app.services.race.prompts import render_prompt
from app.services.race.schemas import (
    AnalysisOutput,
    CriticFeedback,
    CriticIssue,
    CriticIssueSeverity,
    RunMetrics,
)

logger = logging.getLogger(__name__)

_FEATURE_FLAG_ENV = "RACE_AGENT_CRITIC_ENABLED"

# Regex: detecta el primer "{ ... }" balanceado en el texto del modelo.
# No usamos JSONDecoder.raw_decode porque el modelo a veces emite
# espacios/prosa antes del primer "{".
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _critic_enabled() -> bool:
    """Lee la flag de entorno (no de Settings — más fácil de toggle en tests)."""
    raw = os.environ.get(_FEATURE_FLAG_ENV, "true").strip().lower()
    return raw not in {"false", "0", "no", "off"}


def _bypass_feedback() -> CriticFeedback:
    """Feedback "pasa-todo" cuando el critic está deshabilitado."""
    return CriticFeedback(
        approved=True,
        severity=CriticIssueSeverity.LOW,
        issues=[],
        must_block=False,
    )


def _zero_metrics() -> RunMetrics:
    """Métricas vacías cuando no se invocó el LLM."""
    return RunMetrics(
        tokens_in=0,
        tokens_out=0,
        latency_ms=0,
        cost_usd=0.0,
        prompt_version=PROMPT_VERSION_CRITIC,
    )


def _extract_json_block(text: str) -> Optional[dict[str, Any]]:
    """Extrae el primer ``{ ... }`` balanceado del texto.

    Estrategia:
    1. Strip de ``` ```json fences (caso común).
    2. Buscar primera ``{`` y caminar contando braces para encontrar la
       ``}`` que cierra.
    3. ``json.loads`` el sub-string.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    # Walk braces to find the first complete object.
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None

    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        logger.warning("Critic JSON malformado: %s — fragment=%r", exc, candidate[:200])
        return None


def _parse_feedback(text: str) -> CriticFeedback:
    """Parsea el output del LLM → CriticFeedback (defensivo)."""
    obj = _extract_json_block(text)
    if obj is None:
        return CriticFeedback(
            approved=False,
            severity=CriticIssueSeverity.HIGH,
            issues=[
                CriticIssue(
                    section="global",
                    problem="El critic no produjo JSON parseable",
                    suggested_fix="Forzar HITL: revisar draft manualmente.",
                )
            ],
            must_block=True,
        )

    # Normalizar tipos antes de pasar a Pydantic.
    raw_issues = obj.get("issues") or []
    issues: list[CriticIssue] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        try:
            issues.append(
                CriticIssue(
                    section=str(item.get("section", "global"))[:200],
                    problem=str(item.get("problem", ""))[:500] or "(sin descripción)",
                    suggested_fix=str(item.get("suggested_fix", ""))[:500]
                    or "(sin sugerencia)",
                )
            )
        except Exception:  # pragma: no cover - defensa Pydantic edge
            logger.debug("Issue descartado por validación: %s", item)

    severity_raw = str(obj.get("severity", "low")).lower()
    severity = (
        CriticIssueSeverity(severity_raw)
        if severity_raw in {s.value for s in CriticIssueSeverity}
        else CriticIssueSeverity.MED
    )
    return CriticFeedback(
        approved=bool(obj.get("approved", False)),
        severity=severity,
        issues=issues,
        must_block=bool(obj.get("must_block", False)),
    )


class RaceCriticAgent:
    """Critic stateless. Feature flag por env var; sin flag de Settings.

    Razón: Settings.ai_* es global; el critic conviene desactivarse en
    tests específicos y en entornos de cost-saving sin reiniciar el
    proceso.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm
        self._prompt_version = PROMPT_VERSION_CRITIC

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    @staticmethod
    def is_enabled() -> bool:
        """Helper público para el grafo / tests."""
        return _critic_enabled()

    async def invoke(self, draft: AnalysisOutput) -> tuple[CriticFeedback, RunMetrics]:
        """Revisa el draft. Si la flag está OFF, retorna pasa-todo."""
        if not _critic_enabled():
            return _bypass_feedback(), _zero_metrics()

        llm = self._llm or build_chat_llm()
        prompt = render_prompt(
            "race_critic_v1",
            {"draft_analysis": draft.raw_markdown},
            strict=False,
        )

        call: LLMCallResult = await call_llm(llm, prompt)
        feedback = _parse_feedback(call.text)

        metrics = RunMetrics(
            tokens_in=call.tokens_in,
            tokens_out=call.tokens_out,
            latency_ms=call.latency_ms,
            cost_usd=call.cost_usd,
            prompt_version=self._prompt_version,
        )
        return feedback, metrics
