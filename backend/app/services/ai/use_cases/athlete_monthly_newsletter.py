"""Use case: generar narrativa IA para el boletín mensual individual de un atleta.

Salida JSON estructurada con 3 bloques:
  - strengths: fortalezas observadas en el mes (2-3 frases)
  - area_to_develop: área de mejora (2-3 frases, constructivo)
  - milestone: hito del mes (2-3 frases, celebración del progreso)

Guardrails (igual que monthly_report.py):
  - _redact_names: elimina nombre del atleta y compañeros del club
  - MAX_WORDS_PER_BLOCK: 80 palabras por bloque
  - MIN_WORDS_PER_BLOCK: 10 palabras por bloque
  - Sin términos médicos/nutricionales prohibidos

Confidence:
  - 'low'    si <3 sesiones O <2 carreras
  - 'high'   si >=8 sesiones Y >=3 carreras
  - 'medium' en otro caso
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.services.ai.guardrails import Guardrails
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.protocols import LLMProvider
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.use_cases.base import BaseUseCase
# Importar _redact_names y _ascii_fold desde monthly_report (fuente única)
from app.services.ai.use_cases.monthly_report import _redact_names, _ascii_fold

logger = logging.getLogger(__name__)

_PROMPT_VERSION = "athlete_monthly_newsletter_v1"
_LLM_TIMEOUT_SECONDS = 45.0


class AthleteNewsletterLLMTimeout(Exception):
    """Se lanza cuando el proveedor LLM no responde en tiempo."""


class AthleteNewsletterNarrativeOut(BaseModel):
    """Narrativa IA validada por Pydantic tras respuesta del LLM."""

    strengths: str = Field(..., min_length=10, max_length=500)
    area_to_develop: str = Field(..., min_length=10, max_length=500)
    milestone: str = Field(..., min_length=10, max_length=500)
    model: str
    prompt_version: str
    confidence: str  # 'low' | 'medium' | 'high'


@dataclass(frozen=True)
class AthleteNewsletterContext:
    """Contexto anonimizado para el prompt del boletín individual."""

    period_year: int
    period_month: int
    # Asistencia
    sessions_present: int
    sessions_total: int
    attendance_pct: float
    attendance_pct_prev_month: float | None
    streak_days: int
    # Técnico
    focos_tecnicos: list[str]
    avg_rpe: float | None
    avg_rubric_technique: float | None
    total_training_hours: float
    # Carreras (lista de dicts con position, gap_to_winner_pct, valida_num)
    has_races: bool
    race_results: list[dict[str, Any]]
    num_races: int
    # Insignias
    badges: list[dict[str, Any]]
    # Guardrails
    confidence: str
    forbidden_names: frozenset[str]


def _compute_confidence(sessions_total: int, num_races: int) -> str:
    """Calcula el nivel de confianza del análisis IA.

    Basado en volumen de sesiones (evidencia para narrar progreso técnico).
    `num_races` se mantiene en la firma por compatibilidad pero no penaliza
    meses-bloque sin carrera (Copa Valle solo tiene ~7 válidas al año).
    """
    del num_races  # no se usa: meses sin carrera no deben bajar confianza
    if sessions_total < 3:
        return "low"
    if sessions_total >= 8:
        return "high"
    return "medium"


def build_context_from_metrics(
    metrics_snapshot: dict[str, Any],
    year: int,
    month: int,
    forbidden_names: frozenset[str],
) -> AthleteNewsletterContext:
    """Construye el contexto del prompt a partir del metrics_snapshot del builder.

    Nunca incluye nombres reales (ya fueron redactados por el builder).
    """
    email_blocks = metrics_snapshot.get("email_blocks", {})

    attendance = email_blocks.get("attendance", {})
    technical = email_blocks.get("technical", {})
    race_block = email_blocks.get("race_results", {})
    badges_block = email_blocks.get("badges", {})

    sessions_present = attendance.get("sessions_present", 0)
    sessions_total = attendance.get("sessions_total", 0)
    attendance_pct = attendance.get("attendance_pct", 0.0)
    attendance_pct_prev = attendance.get("attendance_pct_prev_month")
    streak = attendance.get("streak_days", 0)

    focos = technical.get("focos_tecnicos", [])
    avg_rpe = technical.get("avg_rpe")
    avg_technique = technical.get("avg_rubric_technique")
    total_hours = technical.get("total_training_hours", 0.0)

    has_races = race_block.get("has_races", False)
    race_results = race_block.get("results", [])
    num_races = len(race_results)

    badges = badges_block.get("items", []) if badges_block else []

    confidence = _compute_confidence(sessions_total, num_races)

    return AthleteNewsletterContext(
        period_year=year,
        period_month=month,
        sessions_present=sessions_present,
        sessions_total=sessions_total,
        attendance_pct=attendance_pct,
        attendance_pct_prev_month=attendance_pct_prev,
        streak_days=streak,
        focos_tecnicos=focos,
        avg_rpe=avg_rpe,
        avg_rubric_technique=avg_technique,
        total_training_hours=total_hours,
        has_races=has_races,
        race_results=race_results,
        num_races=num_races,
        badges=badges,
        confidence=confidence,
        forbidden_names=forbidden_names,
    )


class AthleteNewsletterGuardrails(Guardrails):
    """Guardrails para el boletín mensual individual."""

    MAX_WORDS_PER_BLOCK = 80
    MIN_WORDS_PER_BLOCK = 10

    _MEDICAL_PATTERN = re.compile(
        r"\b(suplement\w*|creatina|proteína en polvo|proteínas en polvo|"
        r"medicament\w*|prescrip\w*|dosis\w*|batido\w* proteico\w*|aminoácidos?|"
        # Términos nutricionales clasificatorios — Ley 1098/2006 Art. 27:
        # solo personal de salud autorizado puede emitir etiquetas diagnósticas
        # sobre menores. Cubren los 5 términos del spec de curvas de percentiles.
        r"obesidad|sobrepeso|bajo\s+peso|talla\s+baja|desnutrici[oó]n)\b",
        re.IGNORECASE,
    )

    def __init__(self, *, forbidden_names: frozenset[str] = frozenset()) -> None:
        super().__init__(age_group=None)
        self._forbidden_names = forbidden_names

    def scrub(self, text: str) -> str:
        """No se usa directamente — se aplica por bloque en scrub_json."""
        return text

    def scrub_block(self, text: str) -> str:
        """Valida y redacta un bloque individual de narrativa."""
        from app.services.ai.errors import LLMSchemaError

        words = text.split()
        if len(words) < self.MIN_WORDS_PER_BLOCK:
            raise LLMSchemaError(
                f"Bloque demasiado corto ({len(words)} palabras, mínimo {self.MIN_WORDS_PER_BLOCK})."
            )
        if len(words) > self.MAX_WORDS_PER_BLOCK:
            raise LLMSchemaError(
                f"Bloque demasiado largo ({len(words)} palabras, máximo {self.MAX_WORDS_PER_BLOCK})."
            )
        if self._MEDICAL_PATTERN.search(text):
            raise LLMSchemaError(
                "Bloque rechazado: contiene términos médicos/nutricionales no permitidos."
            )

        # Verificar y redactar nombres prohibidos
        cleaned = _redact_names(text, self._forbidden_names)

        # Verificar que no queden nombres después de redactar
        folded = _ascii_fold(cleaned)
        for name in self._forbidden_names:
            name_stripped = name.strip()
            if not name_stripped:
                continue
            folded_name = _ascii_fold(name_stripped)
            for variant in {name_stripped, folded_name}:
                if re.search(re.escape(_ascii_fold(variant)), folded, re.IGNORECASE):
                    raise LLMSchemaError(
                        "Bloque rechazado: nombre real detectado tras redacción."
                    )

        return cleaned


class AthleteNewsletterUseCase(BaseUseCase):
    """Caso de uso: generar narrativa IA para el boletín mensual individual."""

    template_id = "athlete_monthly_newsletter_v1"

    def __init__(
        self,
        provider: LLMProvider,
        registry: PromptRegistry,
    ) -> None:
        super().__init__(provider, registry, guardrails=None)

    async def run(
        self,
        ctx: AthleteNewsletterContext,
    ) -> AthleteNewsletterNarrativeOut:
        """Genera la narrativa IA para el boletín.

        Raises:
            AthleteNewsletterLLMTimeout: si el LLM no responde en 45s.
            LLMSchemaError: si la respuesta no pasa los guardrails.
        """
        from app.services.ai.errors import LLMSchemaError

        guardrails = AthleteNewsletterGuardrails(forbidden_names=ctx.forbidden_names)

        context_dict = {
            "period_year": ctx.period_year,
            "period_month": ctx.period_month,
            "sessions_present": ctx.sessions_present,
            "sessions_total": ctx.sessions_total,
            "attendance_pct": ctx.attendance_pct,
            "attendance_pct_prev_month": ctx.attendance_pct_prev_month,
            "streak_days": ctx.streak_days,
            "focos_tecnicos": ctx.focos_tecnicos,
            "avg_rpe": ctx.avg_rpe,
            "avg_rubric_technique": ctx.avg_rubric_technique,
            "total_training_hours": ctx.total_training_hours,
            "has_races": ctx.has_races,
            "race_results": ctx.race_results,
            "num_races": ctx.num_races,
            "badges": ctx.badges,
            "confidence": ctx.confidence,
        }

        try:
            response = await asyncio.wait_for(
                self._ask(context_dict),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise AthleteNewsletterLLMTimeout(
                f"El proveedor LLM no respondió en {_LLM_TIMEOUT_SECONDS:.0f}s."
            ) from exc

        # Parsear JSON de la respuesta
        raw_text = response.text.strip()
        # Eliminar posibles bloques markdown si el LLM los añadió
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text.strip())

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMSchemaError(
                f"La respuesta IA no es JSON válido: {exc}"
            ) from exc

        # Validar estructura
        for key in ("strengths", "area_to_develop", "milestone"):
            if key not in parsed:
                raise LLMSchemaError(
                    f"Respuesta IA falta clave requerida: '{key}'."
                )
            if not isinstance(parsed[key], str):
                raise LLMSchemaError(
                    f"Clave '{key}' debe ser string."
                )

        # Aplicar guardrails bloque a bloque
        cleaned_strengths = guardrails.scrub_block(parsed["strengths"])
        cleaned_area = guardrails.scrub_block(parsed["area_to_develop"])
        cleaned_milestone = guardrails.scrub_block(parsed["milestone"])

        return AthleteNewsletterNarrativeOut(
            strengths=cleaned_strengths,
            area_to_develop=cleaned_area,
            milestone=cleaned_milestone,
            model=response.model or self._provider.model,
            prompt_version=_PROMPT_VERSION,
            confidence=ctx.confidence,
        )
