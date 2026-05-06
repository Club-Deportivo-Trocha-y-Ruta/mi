"""Use case: generar reporte mensual de entrenamiento del club.

Produce un resumen agregado para el comité del club. NUNCA incluye
nombres reales de atletas — solo pseudónimos (A1, A2, …).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from app.services.ai.guardrails import Guardrails
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.protocols import LLMProvider
from app.services.ai.use_cases.base import BaseUseCase


class AnonymizedAthleteStats(BaseModel):
    """Estadísticas de asistencia con pseudónimo, sin nombre real."""

    pseudonym: str
    count_present: int
    count_total: int
    percentage: float


class MonthlyReportContext(BaseModel):
    """Contexto de privacidad segura para el prompt de reporte mensual."""

    club_name: str
    period_year: int
    period_month: int
    total_sessions_planned: int
    total_sessions_executed: int
    total_sessions_cancelled: int
    attendance_stats: list[AnonymizedAthleteStats]
    focos_técnicos: list[str]
    avg_rpe: float | None
    avg_rubric_effort: float | None
    avg_rubric_attitude: float | None
    avg_rubric_technique: float | None
    coach_observations: str | None
    forbidden_names: frozenset[str] = frozenset()

    model_config = {"frozen": True}


@dataclass(frozen=True)
class MonthlyReportResult:
    text: str
    model: str
    provider: str
    generated_at: datetime
    period_year: int
    period_month: int


def _redact_names(text: str, forbidden: frozenset[str]) -> str:
    """Reemplaza nombres reales con '[REDACTADO]' en texto libre del entrenador."""
    if not text or not forbidden:
        return text
    for name in forbidden:
        if not name.strip():
            continue
        pattern = re.compile(re.escape(name.strip()), re.IGNORECASE)
        text = pattern.sub("[REDACTADO]", text)
    return text


class MonthlyReportUseCase(BaseUseCase):
    """Caso de uso `monthly_report`."""

    template_id = "monthly_report"

    def __init__(
        self,
        provider: LLMProvider,
        registry: PromptRegistry,
    ) -> None:
        super().__init__(provider, registry, guardrails=None)

    def build_context_from_metrics(
        self,
        *,
        club_name: str,
        year: int,
        month: int,
        metrics,
        coach_observations: str | None = None,
        real_names: set[str] | None = None,
    ) -> MonthlyReportContext:
        """Construye el contexto a partir de un objeto MonthlyMetrics.

        Anonimiza athlete_id -> pseudónimo. Redacta observaciones del entrenador.
        Nunca incluye nombres reales en el contexto devuelto.
        """
        forbidden: frozenset[str] = frozenset(real_names or set())

        sorted_ids = sorted(metrics.attendance_by_athlete.keys())
        pseudonym_map = {aid: f"A{i + 1}" for i, aid in enumerate(sorted_ids)}

        attendance_stats: list[AnonymizedAthleteStats] = []
        for aid, stats in metrics.attendance_by_athlete.items():
            pseudonym = pseudonym_map[aid]
            count_present = stats.count_present + stats.count_late
            attendance_stats.append(
                AnonymizedAthleteStats(
                    pseudonym=pseudonym,
                    count_present=count_present,
                    count_total=stats.total_sessions,
                    percentage=stats.attendance_pct,
                )
            )

        redacted_obs = None
        if coach_observations:
            redacted_obs = _redact_names(coach_observations, forbidden)

        return MonthlyReportContext(
            club_name=club_name,
            period_year=year,
            period_month=month,
            total_sessions_planned=metrics.total_sessions_planned,
            total_sessions_executed=metrics.total_sessions_executed,
            total_sessions_cancelled=metrics.total_sessions_cancelled,
            attendance_stats=attendance_stats,
            focos_técnicos=metrics.technical_focus_list,
            avg_rpe=metrics.avg_rpe,
            avg_rubric_effort=metrics.avg_rubric_effort,
            avg_rubric_attitude=metrics.avg_rubric_attitude,
            avg_rubric_technique=metrics.avg_rubric_technique,
            coach_observations=redacted_obs,
            forbidden_names=forbidden,
        )

    async def run(self, ctx: MonthlyReportContext) -> MonthlyReportResult:
        self._guardrails = MonthlyReportGuardrails(
            forbidden_names=ctx.forbidden_names,
        )

        context_dict = ctx.model_dump(exclude={"forbidden_names"})
        context_dict["attendance_stats"] = [
            s.model_dump() for s in ctx.attendance_stats
        ]

        response = await self._ask(context_dict)
        sanitized = self._scrub(response.text)

        return MonthlyReportResult(
            text=sanitized,
            model=response.model or self._provider.model,
            provider=response.provider or self._provider.name,
            generated_at=response.generated_at,
            period_year=ctx.period_year,
            period_month=ctx.period_month,
        )


class MonthlyReportGuardrails(Guardrails):
    """Guardrails extendidos para el reporte mensual del club."""

    MAX_WORDS = 700
    MIN_WORDS = 50

    _MEDICAL_PATTERN = re.compile(
        r"\b(suplement\w*|creatina|proteína en polvo|proteínas en polvo|"
        r"medicament\w*|prescrip\w*|dosis\w*|batido\w* proteico\w*|aminoácidos?)\b",
        re.IGNORECASE,
    )

    def __init__(self, *, forbidden_names: frozenset[str] = frozenset()) -> None:
        super().__init__(age_group=None)
        self._forbidden_names = forbidden_names

    def scrub(self, text: str) -> str:
        from app.services.ai.errors import LLMSchemaError

        words = text.split()

        if len(words) < self.MIN_WORDS:
            raise LLMSchemaError(
                f"Reporte mensual demasiado corto ({len(words)} palabras, mínimo {self.MIN_WORDS})."
            )

        if len(words) > self.MAX_WORDS:
            raise LLMSchemaError(
                f"Reporte mensual demasiado largo ({len(words)} palabras, máximo {self.MAX_WORDS})."
            )

        if self._MEDICAL_PATTERN.search(text):
            raise LLMSchemaError(
                "Reporte rechazado: contiene términos médicos/nutricionales no permitidos."
            )

        for name in self._forbidden_names:
            name_stripped = name.strip()
            if not name_stripped:
                continue
            if re.search(re.escape(name_stripped), text, re.IGNORECASE):
                raise LLMSchemaError(
                    f"Reporte rechazado: contiene nombre real de atleta (violación de privacidad)."
                )

        return super().scrub(text)
