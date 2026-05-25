"""Use case: generar reporte mensual de entrenamiento del club.

Produce un resumen agregado para el comité del club. NUNCA incluye
nombres reales de atletas — solo pseudónimos (A1, A2, …).
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel


from app.services.ai.guardrails import Guardrails
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.protocols import LLMProvider
from app.services.ai.use_cases.base import BaseUseCase


# Umbral mínimo de atletas para emitir filas individuales de asistencia.
# Por debajo de este valor (grupo pequeño), las filas A1/A2/... son trivialmente
# re-identificables aun con pseudónimos: el comité del club sabe quiénes son
# los 3-4 atletas y puede triangular por porcentajes. Por debajo del umbral
# se emite SOLO un agregado (n, promedio, rango), sin filas por atleta.
MIN_ATHLETES_FOR_INDIVIDUAL_ROWS = 5


class MonthlyReportLLMTimeout(Exception):
    """Se lanza cuando el proveedor LLM no responde dentro del tiempo límite."""


class AnonymizedAthleteStats(BaseModel):
    """Estadísticas de asistencia con pseudónimo, sin nombre real."""

    pseudonym: str
    count_present: int
    count_total: int
    percentage: float


class MonthlyReportContext(BaseModel):
    """Contexto de privacidad segura para el prompt de reporte mensual.

    Cuando el club tiene menos de `MIN_ATHLETES_FOR_INDIVIDUAL_ROWS` atletas,
    `attendance_stats` queda vacío y `attendance_summary` contiene un string
    agregado (n, promedio, rango). En caso contrario, `attendance_summary` es
    None y `attendance_stats` lleva las filas por pseudónimo.
    """

    club_name: str
    period_year: int
    period_month: int
    total_sessions_planned: int
    total_sessions_executed: int
    total_sessions_cancelled: int
    attendance_stats: list[AnonymizedAthleteStats]
    attendance_summary: str | None = None
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


def _ascii_fold(text: str) -> str:
    """Normaliza NFKD y elimina caracteres de combinación (acentos, diacríticos)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _word_boundary_pattern(name: str) -> re.Pattern[str]:
    """Compila un patrón con word boundaries Unicode-aware para ``name``.

    Nombres compuestos (ej: "Juan Diego") se tokeniza por espacios y cada token
    se separa con ``\\s+`` para tolerar espacios múltiples, preservando el
    boundary al inicio y al final del nombre completo.
    """
    tokens = name.split()
    inner = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<!\w){inner}(?!\w)", re.IGNORECASE | re.UNICODE)


def _redact_names(text: str, forbidden: frozenset[str]) -> str:
    """Reemplaza nombres reales con '[REDACTADO]' en texto libre del entrenador.

    Detección accent-insensitive: 'Pérez' y 'Perez' se redactan en ambas
    direcciones (forbidden con/sin acento ↔ texto con/sin acento). Match se
    realiza sobre la forma NFKD-folded del texto y se mapea a los índices del
    original cuando las longitudes coinciden (típico en español con caracteres
    precompuestos).

    Word boundaries: se usan lookbehind/lookahead ``(?<!\\w)``/``(?!\\w)`` en
    lugar de ``\\b`` para evitar que substrings como "test" dentro de
    "testimonio" sean redactados cuando el forbidden name es "Test".
    """
    if not text or not forbidden:
        return text

    folded_text = _ascii_fold(text)
    if len(folded_text) != len(text):
        # Compatibilidad NFKD alteró longitud; fallback a sustitución doble (puede no
        # cubrir todos los casos pero preserva el texto original).
        out = text
        for name in forbidden:
            original = name.strip()
            if not original:
                continue
            folded = _ascii_fold(original)
            for variant in {original, folded}:
                pat = _word_boundary_pattern(variant)
                out = pat.sub("[REDACTADO]", out)
        return out

    spans: list[tuple[int, int]] = []
    for name in forbidden:
        n = _ascii_fold(name).strip()
        if not n:
            continue
        pat = _word_boundary_pattern(n)
        for m in pat.finditer(folded_text):
            spans.append((m.start(), m.end()))

    if not spans:
        return text

    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    out_parts: list[str] = []
    cursor = 0
    for start, end in merged:
        out_parts.append(text[cursor:start])
        out_parts.append("[REDACTADO]")
        cursor = end
    out_parts.append(text[cursor:])
    return "".join(out_parts)


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
        club_id: int,
        club_name: str,
        year: int,
        month: int,
        metrics,
        coach_observations: str | None = None,
        real_names: set[str] | None = None,
    ) -> MonthlyReportContext:
        """Construye el contexto a partir de un objeto MonthlyMetrics.

        Anonimiza athlete_id -> pseudónimo con shuffle determinista por
        (club_id, year, month). Redacta observaciones del entrenador.
        Nunca incluye nombres reales en el contexto devuelto.

        Si `len(attendance_by_athlete) < MIN_ATHLETES_FOR_INDIVIDUAL_ROWS`,
        suprime filas individuales y deja solo un agregado en
        `attendance_summary` para evitar re-identificación trivial.
        """
        forbidden: frozenset[str] = frozenset(real_names or set())

        # Shuffle determinista: misma (club_id, year, month) -> mismo mapping;
        # mes/club distintos -> permutación distinta. SHA-256 estable entre
        # procesos (a diferencia de hash() builtin que cambia con PYTHONHASHSEED).
        sorted_ids = sorted(metrics.attendance_by_athlete.keys())
        seed_material = f"{club_id}|{year}|{month}".encode("utf-8")
        seed = int(hashlib.sha256(seed_material).hexdigest()[:16], 16)
        shuffled_ids = list(sorted_ids)
        random.Random(seed).shuffle(shuffled_ids)
        pseudonym_map = {aid: f"A{i + 1}" for i, aid in enumerate(shuffled_ids)}

        num_athletes = len(metrics.attendance_by_athlete)
        suppress_individual_rows = (
            0 < num_athletes < MIN_ATHLETES_FOR_INDIVIDUAL_ROWS
        )

        attendance_stats: list[AnonymizedAthleteStats] = []
        if not suppress_individual_rows:
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

        attendance_summary: str | None = None
        if suppress_individual_rows:
            percentages = [
                s.attendance_pct for s in metrics.attendance_by_athlete.values()
            ]
            avg_pct = sum(percentages) / len(percentages)
            min_pct = min(percentages)
            max_pct = max(percentages)
            attendance_summary = (
                f"{num_athletes} atletas con asistencia promedio "
                f"{avg_pct:.0f}% (rango {min_pct:.0f}-{max_pct:.0f}%)."
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
            attendance_summary=attendance_summary,
            focos_técnicos=metrics.technical_focus_list,
            avg_rpe=metrics.avg_rpe,
            avg_rubric_effort=metrics.avg_rubric_effort,
            avg_rubric_attitude=metrics.avg_rubric_attitude,
            avg_rubric_technique=metrics.avg_rubric_technique,
            coach_observations=redacted_obs,
            forbidden_names=forbidden,
        )

    _LLM_TIMEOUT_SECONDS = 25.0

    async def run(self, ctx: MonthlyReportContext) -> MonthlyReportResult:
        # Guardrails específicos por request: dependen de los nombres
        # prohibidos de este reporte concreto. Se construyen como variable
        # local para que dos requests concurrentes (clubes distintos, con
        # listas de nombres distintas) no se pisen mutuamente las reglas.
        guardrails = MonthlyReportGuardrails(
            forbidden_names=ctx.forbidden_names,
        )

        context_dict = ctx.model_dump(exclude={"forbidden_names"})
        context_dict["attendance_stats"] = [
            s.model_dump() for s in ctx.attendance_stats
        ]

        try:
            response = await asyncio.wait_for(
                self._ask(context_dict),
                timeout=self._LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise MonthlyReportLLMTimeout(
                f"El proveedor LLM no respondió en {self._LLM_TIMEOUT_SECONDS:.0f}s."
            ) from exc

        sanitized = self._scrub(response.text, guardrails=guardrails)

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

    # Alineado con `prompts/monthly_report.j2` v1, que pide "Máximo 500 palabras".
    # Tolerar 700 sin avisar añadiría ruido al comité sin valor; el contrato del
    # prompt es de 500 y el guardrail lo enforce.
    MAX_WORDS = 500
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

        folded_text = _ascii_fold(text)
        for name in self._forbidden_names:
            name_stripped = name.strip()
            if not name_stripped:
                continue
            # Verificar tanto la forma original como la ASCII-folded del nombre
            folded_name = _ascii_fold(name_stripped)
            for variant in {name_stripped, folded_name}:
                if re.search(re.escape(_ascii_fold(variant)), folded_text, re.IGNORECASE):
                    raise LLMSchemaError(
                        "Reporte rechazado: contiene nombre real de atleta (violación de privacidad)."
                    )

        return super().scrub(text)
