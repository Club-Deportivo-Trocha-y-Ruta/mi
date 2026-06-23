"""LLM interpretation of a competitive-anxiety assessment (US4, FR-013/015).

Mirrors the project's JSON use-case pattern: render → ask → strip fences →
json.loads → guardrail scrub → schema validate. Output is the fixed Spanish
schema shared with the rule-based fallback. Pseudonyms only — no real athlete
name ever reaches the provider (FR-027). On any failure the caller falls back
to ``rule_interpreter`` (FR-016).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.services.ai.guardrails import Guardrails
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.protocols import LLMProvider
from app.services.ai.use_cases.base import BaseUseCase
from app.services.anxiety.instrument_keys import load_key

logger = logging.getLogger(__name__)

USE_CASE_KEY = "anxiety_interpretation"

_LOW = 0.33
_HIGH = 0.66

_REQUIRED_DIMENSIONS = ("cognitiva", "somatica", "autoconfianza")


class AnxietyInterpretationTimeout(Exception):
    """The LLM provider did not respond within the configured timeout."""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


def _band_label(value: float | None, rng: tuple[int, int]) -> str:
    if value is None:
        return "sin dato"
    lo, hi = rng
    pos = 0.0 if hi == lo else max(0.0, min(1.0, (value - lo) / (hi - lo)))
    if pos < _LOW:
        return "bajo"
    if pos >= _HIGH:
        return "alto"
    return "moderado"


def _fmt(value: float | None) -> str:
    return "sin dato" if value is None else f"{value:g}"


class AnxietyInterpretationUseCase(BaseUseCase):
    """Use case ``anxiety_interpretation``."""

    template_id = "anxiety_interpretation_v1"

    def __init__(self, provider: LLMProvider, registry: PromptRegistry) -> None:
        super().__init__(provider, registry, guardrails=None)

    def _build_context(
        self,
        *,
        instrument_type: str,
        scores: dict[str, float | None],
        baselines: dict[str, float | None],
        age_group: str,
        event_label: str,
        priority: str | None,
        is_partial: bool,
    ) -> dict[str, Any]:
        key = load_key(instrument_type)

        def rng(name: str) -> tuple[int, int]:
            sub = key.subscale(name)
            return sub.range if sub else (0, 1)

        has_conf = key.subscale("selfconfidence") is not None
        return {
            "instrument_type": instrument_type,
            "age_group": age_group,
            "event_label": event_label,
            "priority": priority or "—",
            "is_partial": is_partial,
            "cognitive_score": _fmt(scores.get("cognitive")),
            "cognitive_band": _band_label(scores.get("cognitive"), rng("cognitive")),
            "cognitive_baseline": _fmt(baselines.get("cognitive")),
            "somatic_score": _fmt(scores.get("somatic")),
            "somatic_band": _band_label(scores.get("somatic"), rng("somatic")),
            "somatic_baseline": _fmt(baselines.get("somatic")),
            "has_selfconfidence": has_conf,
            "selfconfidence_score": _fmt(scores.get("selfconfidence")),
            "selfconfidence_band": _band_label(
                scores.get("selfconfidence"), rng("selfconfidence")
            ),
            "selfconfidence_baseline": _fmt(baselines.get("selfconfidence")),
        }

    async def run(
        self,
        *,
        instrument_type: str,
        scores: dict[str, float | None],
        baselines: dict[str, float | None],
        age_group: str,
        event_label: str = "sin evento",
        priority: str | None = None,
        is_partial: bool = False,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Generate the interpretation. Returns ``{"interpretation": {...}, "model": str}``.

        Raises ``LLMSchemaError`` / ``AnxietyInterpretationTimeout`` /
        ``LLM*Error`` on failure so the caller can fall back to rules.
        """
        from app.services.ai.errors import LLMSchemaError

        context = self._build_context(
            instrument_type=instrument_type,
            scores=scores,
            baselines=baselines,
            age_group=age_group,
            event_label=event_label,
            priority=priority,
            is_partial=is_partial,
        )
        guardrails = Guardrails(age_group=age_group)

        try:
            response = await asyncio.wait_for(
                self._ask(context), timeout=timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise AnxietyInterpretationTimeout(
                f"El proveedor LLM no respondió en {timeout_seconds:.0f}s."
            ) from exc

        raw_text = _strip_json_fences(response.text)
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMSchemaError(
                f"La interpretación IA no es JSON válido: {exc}"
            ) from exc

        interpretation = self._validate_and_scrub(parsed, guardrails)
        model_id = response.model or self._provider.model
        return {"interpretation": interpretation, "model": model_id}

    @staticmethod
    def _validate_and_scrub(parsed: Any, guardrails: Guardrails) -> dict[str, Any]:
        from app.services.ai.errors import LLMSchemaError

        if not isinstance(parsed, dict):
            raise LLMSchemaError("La interpretación IA debe ser un objeto JSON.")

        for key in ("resumen", "mensaje_para_el_atleta"):
            if not isinstance(parsed.get(key), str) or not parsed[key].strip():
                raise LLMSchemaError(f"Falta o es inválida la clave '{key}'.")

        por_dim = parsed.get("por_dimension")
        if not isinstance(por_dim, dict):
            raise LLMSchemaError("'por_dimension' debe ser un objeto.")
        for dim in _REQUIRED_DIMENSIONS:
            if not isinstance(por_dim.get(dim), str):
                raise LLMSchemaError(f"'por_dimension.{dim}' debe ser string.")

        estrategias = parsed.get("estrategias", [])
        if not isinstance(estrategias, list) or not all(
            isinstance(s, str) for s in estrategias
        ):
            raise LLMSchemaError("'estrategias' debe ser una lista de strings.")

        banderas = parsed.get("banderas", [])
        if not isinstance(banderas, list) or not all(
            isinstance(s, str) for s in banderas
        ):
            raise LLMSchemaError("'banderas' debe ser una lista de strings.")

        return {
            "resumen": guardrails.scrub(parsed["resumen"]),
            "por_dimension": {
                dim: guardrails.scrub(por_dim[dim]) for dim in _REQUIRED_DIMENSIONS
            },
            "estrategias": [guardrails.scrub(s) for s in estrategias],
            "mensaje_para_el_atleta": guardrails.scrub(
                parsed["mensaje_para_el_atleta"]
            ),
            "banderas": [guardrails.scrub(s) for s in banderas],
        }
