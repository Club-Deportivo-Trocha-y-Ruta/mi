"""Guardrails post-procesamiento.

Aplica reglas regex sobre la salida del LLM para enforce los principios
no negociables del CLAUDE.md. Estas reglas son de defensa en profundidad:
el system prompt ya pide cumplirlos, pero el guardrail garantiza que
nunca se entregue al usuario un texto que los contradiga.

Principios cubiertos:
  - Cero suplementos para menores.
  - Máx 5 días/semana de entrenamiento.
  - Cadencia ≥60 rpm.
  - Sin potenciómetros para <13 años.
  - Sin conteo calórico hablando con atletas.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Si se exceden estas violaciones la respuesta se considera no recuperable.
MAX_VIOLATIONS_BEFORE_REJECT = 3


@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    replacement: str | None  # None → eliminar la frase entera
    description: str


_SUPPLEMENT_KEYWORDS = (
    r"creatina|proteína en polvo|proteinas en polvo|"
    r"suplementos?|batidos? proteicos?|aminoácidos?"
)

_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="suplements",
        pattern=re.compile(rf"\b({_SUPPLEMENT_KEYWORDS})\b", re.IGNORECASE),
        replacement="alimentación basada en comida real",
        description="Cero suplementos para menores de 18.",
    ),
    _Rule(
        name="days_per_week_excess",
        pattern=re.compile(
            r"\b([67])\s*d[ií]as?\s*(por|a la|/)\s*semana", re.IGNORECASE
        ),
        replacement="máximo 5 días por semana",
        description="Máximo 5 días de entrenamiento por semana.",
    ),
    _Rule(
        name="low_cadence",
        pattern=re.compile(
            r"\b([1-5]?\d)\s*rpm\b", re.IGNORECASE
        ),
        replacement="≥60 rpm",
        description="Cadencia mínima 60 rpm.",
    ),
    _Rule(
        name="calorie_counting_with_athlete",
        pattern=re.compile(
            r"\b(cont(ar|eo)|registr[ao]) (de )?calor[ií]as?\b", re.IGNORECASE
        ),
        replacement="enfoque en variedad y calidad de la comida",
        description="Sin conteo calórico con atletas menores.",
    ),
)

# Patrones que ameritan reemplazo solo en texto dirigido a 10-12.
_AGE_DEPENDENT_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="powermeter_under_13",
        pattern=re.compile(r"\b(potenci[óo]metro|powermeter|vatios|watt(s)?)\b", re.IGNORECASE),
        replacement="RPE (percepción de esfuerzo)",
        description="No usar potenciómetro para <13 años.",
    ),
)


@dataclass(frozen=True)
class GuardrailReport:
    """Resultado del scrub para que el caller pueda auditar."""

    text: str
    violations: tuple[str, ...]
    rejected: bool


class Guardrails:
    """Sanea texto generado por el LLM.

    Args:
        age_group: Grupo de edad del destinatario (`"10-12"` activa reglas
            extra como bloqueo de potenciómetro).
    """

    def __init__(self, *, age_group: str | None = None) -> None:
        self._age_group = age_group

    def scrub(self, text: str) -> str:
        """Devuelve `text` saneado. Si hubo demasiadas violaciones, lanza."""
        report = self.scrub_with_report(text)
        if report.rejected:
            from app.services.ai.errors import LLMSchemaError

            raise LLMSchemaError(
                f"Respuesta rechazada por guardrails: {report.violations}"
            )
        return report.text

    def scrub_with_report(self, text: str) -> GuardrailReport:
        sanitized = text
        violations: list[str] = []

        rules = list(_RULES)
        if self._age_group == "10-12":
            rules.extend(_AGE_DEPENDENT_RULES)

        for rule in rules:
            new_text, count = rule.pattern.subn(
                rule.replacement or "", sanitized
            )
            if count:
                violations.extend([rule.name] * count)
                logger.warning(
                    "ai.guardrail.violation rule=%s count=%d", rule.name, count
                )
                sanitized = new_text

        rejected = len(violations) >= MAX_VIOLATIONS_BEFORE_REJECT
        return GuardrailReport(
            text=sanitized.strip(),
            violations=tuple(violations),
            rejected=rejected,
        )
