"""Use case: narrativa IA v2 ("bitácora de etapa") para el boletín mensual
individual de un atleta (feature 038, T201).

Diferencias clave frente a ``athlete_monthly_newsletter.py`` (v1):

  - Salida estructurada por bloque (:class:`StageNarrative`, data-model.md
    §2) en vez de 3 párrafos fijos: ``stage_title``, ``summit_caption``,
    ``observations`` (exactamente 3, cada una anclada a un número),
    ``next_segment_text``, ``family_compass`` y, opcionalmente,
    ``analyst_reading`` (paráfrasis familiar del análisis de carrera 037,
    ver ``app.services.training.family_translation``).
  - Guardrails con grounding numérico (todo número citado debe existir en
    el prompt renderizado — ``app.services.race.insight_v3.extract_numeric_tokens``),
    frases prohibidas, solapamiento con el título/observaciones del mes
    anterior y verificación de "?" en ``conversation_question``.
  - **Fallback por bloque, nunca por narrativa completa**: cuando un bloque
    individual viola un guardrail, ese bloque queda en ``None`` en el
    :class:`StageNarrative` devuelto — exactamente el mismo efecto que si
    la IA nunca lo hubiera producido — y la violación queda registrada en
    ``StageNarrative.grounding_violations``. ``build_stage_log``
    (``app/services/training/stage_log_builder.py``, Wave 1) ya trata
    cualquier campo ausente/``None`` de la narrativa como "sin IA para este
    bloque" y cae al copy estático correspondiente (ver su
    ``_narrative_field``) — así que este use case nunca necesita lanzar una
    excepción por la violación de UN bloque. Solo se lanza
    :class:`StageNarrativeLLMTimeout` / ``LLMSchemaError`` cuando el
    proveedor no responde o la respuesta es JSON inválido incluso tras el
    reintento de reparación — el router (mismo criterio que v1) degrada
    entonces la narrativa completa a estático, igual que hoy hace
    ``_generate_newsletter_for_athlete`` con v1.

Desviación documentada de ``data-model.md`` §2: ahí ``StageNarrative``
tipa ``stage_title``, ``observations`` y ``family_compass`` como
obligatorios. Acá se tipan como opcionales (``| None``) para poder
representar "este bloque cayó a estático por guardrails" sin recurrir a un
tipo/wrapper paralelo — ver docstring de :class:`StageNarrative`. El JSON
persistido en ``ai_narrative`` es idéntico en forma (un ``dict`` con esas
claves); Python/JSON no distinguen "clave ausente" de "clave con valor
``None``" a los efectos de ``build_stage_log``.

Structured output: si el proveedor implementa
``app.services.ai.protocols.StructuredOutput`` (todos los proveedores
reales del repo lo hacen hoy) se intenta ``complete_json`` primero. Si
falla con ``LLMSchemaError`` (JSON inválido — el riesgo documentado en
plan.md: "Gemini structured output rejects nested schema") se cae al modo
manual: ``complete()`` + parseo de JSON + **un** reintento de reparación
(se reenvía la respuesta inválida pidiendo que la corrija). Si ese
reintento también falla, se lanza ``LLMSchemaError`` — el router entonces
degrada la narrativa completa a estático (mismo patrón que v1).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field, ValidationError

from app.services.ai.errors import LLMSchemaError
from app.services.ai.guardrails import Guardrails
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.protocols import LLMProvider, StructuredOutput
from app.services.ai.use_cases.base import BaseUseCase
from app.services.ai.use_cases.monthly_report import _redact_names
from app.services.race.insight_v3 import extract_numeric_tokens
from app.services.training.stage_log import FamilyCompass, Observation

logger = logging.getLogger(__name__)

_PROMPT_VERSION = "athlete_monthly_newsletter_v2"
_LLM_TIMEOUT_SECONDS = 45.0

# Claves regenerables individualmente (contracts/api.md §Coach POST .../regenerate-block).
_ALLOWED_BLOCKS: tuple[str, ...] = (
    "stage_title",
    "summit_caption",
    "observations",
    "next_segment_text",
    "family_compass",
    "analyst_reading",
)

_REPAIR_INSTRUCTION = (
    "Tu respuesta anterior no era JSON válido. Responde de nuevo ÚNICAMENTE "
    "con el JSON correcto, sin texto adicional, sin ```json ni markdown."
)

# Schema laxo — solo documenta la forma esperada al proveedor (ver
# providers/google_provider.py::complete_json, que lo serializa en el system
# prompt; no se usa para validar la respuesta, eso lo hacen los guardrails).
_STAGE_NARRATIVE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stage_title": {"type": "string"},
        "summit_caption": {"type": ["string", "null"]},
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "evidence": {"type": "string"},
                    "block_ref": {
                        "type": "string",
                        "enum": ["attendance", "technical", "race", "badges", "streak"],
                    },
                },
            },
        },
        "next_segment_text": {"type": ["string", "null"]},
        "family_compass": {
            "type": "object",
            "properties": {
                "conversation_question": {"type": "string"},
                "monthly_challenge": {"type": "string"},
                "what_to_watch": {"type": "string"},
            },
        },
        "analyst_reading": {
            "type": "object",
            "properties": {
                "headline_family": {"type": "string"},
                "action_family": {"type": "string"},
            },
        },
    },
}


class StageNarrativeLLMTimeout(Exception):
    """Se lanza cuando el proveedor LLM no responde en tiempo (narrativa v2)."""


# ---------------------------------------------------------------------------
# Salida validada
# ---------------------------------------------------------------------------


class AnalystReadingText(BaseModel):
    """Paráfrasis familiar del análisis de carrera (data-model.md §2)."""

    headline_family: str
    action_family: str


class StageNarrative(BaseModel):
    """Narrativa IA v2 — ver docstring del módulo para la desviación de tipos
    frente a ``data-model.md`` §2 (``stage_title``/``observations``/
    ``family_compass`` opcionales acá, para permitir fallback por bloque).
    """

    stage_title: str | None = None
    summit_caption: str | None = None
    observations: list[Observation] | None = None
    next_segment_text: str | None = None
    family_compass: FamilyCompass | None = None
    analyst_reading: AnalystReadingText | None = None
    model: str
    prompt_version: str = _PROMPT_VERSION
    confidence: Literal["low", "medium", "high"]
    # No es parte del contrato de StageNarrative en data-model.md §2 (que solo
    # describe lo persistido para consumo del builder) — es el canal por el
    # que este use case le reporta al router qué bloques cayeron a estático y
    # por qué. El router lo copia a ``StageLog.grounding_violations`` (coach
    # DTO) después de llamar a ``build_stage_log`` — ``stage_log_builder.py``
    # (Wave 1) no lo lee y no se modificó para leerlo (fuera de alcance T201).
    grounding_violations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Contexto de entrada
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageNarrativeContext:
    """Contexto anonimizado para el prompt v2. Nunca incluye nombres reales."""

    period_year: int
    period_month: int
    period_label: str
    athlete_reference: str
    sessions_present: int
    sessions_total: int
    attendance_pct: float
    attendance_pct_prev_month: float | None
    streak_sessions: int
    effort_weeks: list[dict[str, Any]]
    focos_tecnicos: list[str]
    avg_rpe: float | None
    avg_rubric_technique: float | None
    race_results: list[dict[str, Any]]
    badges: list[dict[str, Any]]
    planned_focus_groups: list[str]
    next_race: dict[str, Any] | None
    previous_stage_title: str | None
    analyst_reading_input: Mapping[str, Any] | None
    confidence: str
    forbidden_names: frozenset[str]
    # Usado SOLO por el guardrail de solapamiento (Jaccard) — nunca se
    # muestra al LLM tal cual (el prompt solo expone previous_stage_title,
    # ver T201 spec: "próximo tramo ... título del mes anterior"). Concatena
    # título + observaciones del boletín v2 anterior del mismo atleta.
    previous_stage_text: str | None = None


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


def _derive_athlete_reference(athlete_sex: str | None) -> str:
    """Deriva la referencia de género para narrar sin usar el nombre real.

    'M' -> "su hijo", 'F' -> "su hija", None/otro -> "su hijo/a" (neutro).
    Nunca debe loguearse junto al nombre real del atleta.
    """
    if athlete_sex == "M":
        return "su hijo"
    if athlete_sex == "F":
        return "su hija"
    return "su hijo/a"


def build_context_from_metrics_v2(
    metrics_snapshot: dict[str, Any],
    year: int,
    month: int,
    forbidden_names: frozenset[str],
    athlete_sex: str | None = None,
    analyst_reading_input: Mapping[str, Any] | None = None,
    previous_stage_title: str | None = None,
    previous_stage_text: str | None = None,
) -> StageNarrativeContext:
    """Construye el contexto del prompt v2 a partir del ``metrics_snapshot``.

    Reutiliza las funciones puras de ``stage_log_builder`` (Wave 1) para el
    perfil semanal y el próximo tramo en vez de reimplementar esa lógica —
    mismo criterio que usará ``build_stage_log`` para renderizar la bitácora
    final, así el prompt y la bitácora nunca ven un dato distinto.
    """
    from app.services.training.stage_log import badge_label_for
    from app.services.training.stage_log_builder import effort_profile, next_segment

    email_blocks = metrics_snapshot.get("email_blocks", {}) or {}

    attendance = email_blocks.get("attendance", {}) or {}
    technical = email_blocks.get("technical", {}) or {}
    race_block = email_blocks.get("race_results", {}) or {}
    badges_block = email_blocks.get("badges", {}) or {}
    period = email_blocks.get("period", {}) or {}

    sessions_present = attendance.get("sessions_present", 0)
    sessions_total = attendance.get("sessions_total", 0)
    attendance_pct = attendance.get("attendance_pct", 0.0)
    attendance_pct_prev = attendance.get("attendance_pct_prev_month")
    streak = attendance.get("streak_sessions", attendance.get("streak_days", 0))

    athlete_reference = _derive_athlete_reference(athlete_sex)

    effort_weeks = [w.model_dump(mode="json") for w in effort_profile(metrics_snapshot)]

    segment = next_segment(metrics_snapshot)
    planned_focus_groups = list(segment.focus_groups) if segment else []
    next_race = (
        segment.next_race.model_dump(mode="json")
        if segment is not None and segment.next_race is not None
        else None
    )

    race_results = list(race_block.get("results") or [])
    badges = [
        {"label": badge_label_for(item.get("badge_type", ""))}
        for item in (badges_block.get("items") or [])
    ]

    num_races = len(race_results)
    confidence = _compute_confidence(sessions_total, num_races)

    return StageNarrativeContext(
        period_year=year,
        period_month=month,
        period_label=period.get("label", f"{month}/{year}"),
        athlete_reference=athlete_reference,
        sessions_present=sessions_present,
        sessions_total=sessions_total,
        attendance_pct=attendance_pct,
        attendance_pct_prev_month=attendance_pct_prev,
        streak_sessions=streak,
        effort_weeks=effort_weeks,
        focos_tecnicos=list(technical.get("focos_tecnicos") or []),
        avg_rpe=technical.get("avg_rpe"),
        avg_rubric_technique=technical.get("avg_rubric_technique"),
        race_results=race_results,
        badges=badges,
        planned_focus_groups=planned_focus_groups,
        next_race=next_race,
        previous_stage_title=previous_stage_title,
        analyst_reading_input=dict(analyst_reading_input) if analyst_reading_input else None,
        confidence=confidence,
        forbidden_names=forbidden_names,
        previous_stage_text=previous_stage_text,
    )


# ---------------------------------------------------------------------------
# Guardrails v2
# ---------------------------------------------------------------------------


def _ascii_fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokenize(text: str) -> frozenset[str]:
    folded = _ascii_fold(text.lower())
    return frozenset(re.findall(r"[a-z0-9]+", folded))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def _violation_reason(exc: LLMSchemaError) -> str:
    msg = str(exc)
    if "corto" in msg:
        return "too_short"
    if "largo" in msg:
        return "too_long"
    if "médicos" in msg or "nutricionales" in msg:
        return "medical_term"
    if "nombre real" in msg:
        return "forbidden_name"
    return "guardrail_rejected"


class StageNarrativeGuardrails(Guardrails):
    """Guardrails de la bitácora v2: longitud por bloque, términos
    médicos/nutricionales prohibidos y redacción de nombres del club, más
    grounding numérico, frases prohibidas, solapamiento con el mes anterior
    y verificación de "?" (data-model.md §2 / plan.md §"AI v2").
    """

    # Los bloques v2 son frases cortas (claim/evidence/captions), no párrafos
    # de 2-3 oraciones — un mínimo alto rechazaría evidencias legítimas como
    # "9/10 sesiones asistidas." (3 palabras).
    MAX_WORDS_PER_BLOCK = 80
    MIN_WORDS_PER_BLOCK = 1

    _MEDICAL_PATTERN = re.compile(
        r"\b(suplement\w*|creatina|proteína en polvo|proteínas en polvo|"
        r"medicament\w*|prescrip\w*|dosis\w*|batido\w* proteico\w*|aminoácidos?|"
        # Términos nutricionales clasificatorios — Ley 1098/2006 Art. 27:
        # solo personal de salud autorizado puede emitir etiquetas diagnósticas
        # sobre menores.
        r"obesidad|sobrepeso|bajo\s+peso|talla\s+baja|desnutrici[oó]n)\b",
        re.IGNORECASE,
    )

    FORBIDDEN_PHRASES: tuple[str, ...] = (
        "percentil",
        "esperado",
        "ranking",
        "mejor que",
        "por debajo",
        "podio",
        "ganar",
    )
    OVERLAP_THRESHOLD = 0.85

    def __init__(
        self,
        *,
        forbidden_names: frozenset[str],
        grounding_numbers: set[str],
        previous_stage_text: str | None = None,
    ) -> None:
        super().__init__(age_group=None)
        self._forbidden_names = forbidden_names
        self._grounding_numbers = grounding_numbers
        self._previous_stage_tokens = _tokenize(previous_stage_text) if previous_stage_text else frozenset()

    def scrub(self, text: str) -> str:
        """No se usa directamente — se aplica por bloque en ``check_block``."""
        return text

    def scrub_block(self, text: str) -> str:
        """Valida y redacta un bloque individual de narrativa."""
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

    def check_block(
        self, block_name: str, text: str, *, require_question: bool = False
    ) -> tuple[str | None, list[str]]:
        """Valida y sanea un bloque corto. Nunca lanza — devuelve
        ``(None, violaciones)`` cuando el bloque debe caer a estático."""
        try:
            cleaned = self.scrub_block(text)
        except LLMSchemaError as exc:
            return None, [f"{block_name}:{_violation_reason(exc)}"]

        violations: list[str] = []
        folded = _ascii_fold(cleaned.lower())
        for phrase in self.FORBIDDEN_PHRASES:
            if _ascii_fold(phrase) in folded:
                violations.append(f"{block_name}:forbidden_phrase:{phrase.replace(' ', '_')}")

        ungrounded = extract_numeric_tokens(cleaned) - self._grounding_numbers
        if ungrounded:
            violations.append(f"{block_name}:ungrounded_number")

        if require_question and not cleaned.rstrip().endswith("?"):
            violations.append(f"{block_name}:missing_question_mark")

        if self._previous_stage_tokens and _jaccard(_tokenize(cleaned), self._previous_stage_tokens) >= self.OVERLAP_THRESHOLD:
            violations.append(f"{block_name}:overlap_previous_month")

        if violations:
            logger.warning(
                "ai.newsletter_v2.guardrail_violation block=%s violations=%s",
                block_name, violations,
            )
            return None, violations
        return cleaned, []


def _accept_text_field(
    block_name: str,
    raw: Any,
    guardrails: StageNarrativeGuardrails,
    violations: list[str],
    *,
    require_question: bool = False,
) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    cleaned, block_violations = guardrails.check_block(
        block_name, raw, require_question=require_question
    )
    violations.extend(block_violations)
    return cleaned


def _accept_observations(
    raw: Any, guardrails: StageNarrativeGuardrails, violations: list[str]
) -> list[Observation] | None:
    if not isinstance(raw, list) or len(raw) != 3:
        if raw:
            violations.append("observations:invalid_count")
        return None

    accepted: list[Observation] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            violations.append(f"observations[{idx}]:invalid_shape")
            return None
        block_ref = item.get("block_ref")
        if block_ref not in {"attendance", "technical", "race", "badges", "streak"}:
            violations.append(f"observations[{idx}]:invalid_block_ref")
            return None
        claim = _accept_text_field(f"observations[{idx}].claim", item.get("claim"), guardrails, violations)
        evidence = _accept_text_field(f"observations[{idx}].evidence", item.get("evidence"), guardrails, violations)
        if claim is None or evidence is None:
            return None
        try:
            accepted.append(Observation(claim=claim, evidence=evidence, block_ref=block_ref))
        except ValidationError:
            violations.append(f"observations[{idx}]:invalid_model")
            return None
    return accepted


def _accept_family_compass(
    raw: Any, guardrails: StageNarrativeGuardrails, violations: list[str]
) -> FamilyCompass | None:
    if not isinstance(raw, dict):
        if raw:
            violations.append("family_compass:invalid_shape")
        return None
    question = _accept_text_field(
        "family_compass.conversation_question",
        raw.get("conversation_question"),
        guardrails,
        violations,
        require_question=True,
    )
    challenge = _accept_text_field(
        "family_compass.monthly_challenge", raw.get("monthly_challenge"), guardrails, violations
    )
    watch = _accept_text_field(
        "family_compass.what_to_watch", raw.get("what_to_watch"), guardrails, violations
    )
    if question is None or challenge is None or watch is None:
        return None
    try:
        return FamilyCompass(
            conversation_question=question, monthly_challenge=challenge, what_to_watch=watch
        )
    except ValidationError:
        violations.append("family_compass:invalid_model")
        return None


def _accept_analyst_reading(
    raw: Any, guardrails: StageNarrativeGuardrails, violations: list[str]
) -> AnalystReadingText | None:
    if not isinstance(raw, dict):
        if raw:
            violations.append("analyst_reading:invalid_shape")
        return None
    headline = _accept_text_field(
        "analyst_reading.headline_family", raw.get("headline_family"), guardrails, violations
    )
    action = _accept_text_field(
        "analyst_reading.action_family", raw.get("action_family"), guardrails, violations
    )
    if headline is None or action is None:
        return None
    return AnalystReadingText(headline_family=headline, action_family=action)


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class AthleteMonthlyNewsletterV2UseCase(BaseUseCase):
    """Genera la narrativa IA v2 (bitácora de etapa) de un boletín mensual."""

    template_id = _PROMPT_VERSION

    def __init__(self, provider: LLMProvider, registry: PromptRegistry) -> None:
        super().__init__(provider, registry, guardrails=None)

    async def run(self, ctx: StageNarrativeContext) -> StageNarrative:
        """Genera la narrativa completa (todos los bloques).

        Raises:
            StageNarrativeLLMTimeout: el proveedor no respondió a tiempo.
            LLMSchemaError: la respuesta no fue JSON válido ni tras el
                reintento de reparación. Un rechazo de guardrails de UN
                bloque NUNCA llega hasta acá como excepción (ver docstring
                del módulo) — solo un fallo total de parseo/timeout.
        """
        context_dict = self._context_dict(ctx, only_block=None, instruction=None)
        return await self._generate(ctx, context_dict, only_block=None)

    async def regenerate_block(
        self,
        ctx: StageNarrativeContext,
        block_name: str,
        instruction: str | None = None,
    ) -> Any:
        """Regenera SOLO ``block_name`` y devuelve el valor de ese bloque.

        El valor de retorno tiene el tipo del bloque (``str`` para
        ``stage_title``/``summit_caption``/``next_segment_text``,
        ``list[Observation]`` para ``observations``, ``FamilyCompass`` para
        ``family_compass``, ``AnalystReadingText`` para
        ``analyst_reading``), o ``None`` si el bloque regenerado no pasó los
        guardrails (contracts/api.md §Coach: el router deja el bloque
        anterior intacto en ese caso, igual que ante un 503 del proveedor).
        """
        if block_name not in _ALLOWED_BLOCKS:
            raise ValueError(f"Bloque desconocido para regenerar: {block_name!r}.")
        context_dict = self._context_dict(ctx, only_block=block_name, instruction=instruction)
        narrative = await self._generate(ctx, context_dict, only_block=block_name)
        return getattr(narrative, block_name)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _context_dict(
        ctx: StageNarrativeContext, *, only_block: str | None, instruction: str | None
    ) -> dict[str, Any]:
        return {
            "period_year": ctx.period_year,
            "period_month": ctx.period_month,
            "period_label": ctx.period_label,
            "athlete_reference": ctx.athlete_reference,
            "sessions_present": ctx.sessions_present,
            "sessions_total": ctx.sessions_total,
            "attendance_pct": ctx.attendance_pct,
            "attendance_pct_prev_month": ctx.attendance_pct_prev_month,
            "streak_sessions": ctx.streak_sessions,
            "effort_weeks": ctx.effort_weeks,
            "focos_tecnicos": ctx.focos_tecnicos,
            "avg_rpe": ctx.avg_rpe,
            "avg_rubric_technique": ctx.avg_rubric_technique,
            "race_results": ctx.race_results,
            "badges": ctx.badges,
            "planned_focus_groups": ctx.planned_focus_groups,
            "next_race": ctx.next_race,
            "previous_stage_title": ctx.previous_stage_title,
            "analyst_reading_input": ctx.analyst_reading_input,
            "confidence": ctx.confidence,
            "only_block": only_block,
            "instruction": instruction,
        }

    @staticmethod
    def _try_parse(raw_text: str) -> dict[str, Any] | None:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text.strip())
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _call_llm(self, context_dict: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Obtiene el JSON crudo del LLM + el prompt renderizado (para grounding).

        Structured output primero si el proveedor lo soporta; si falla con
        JSON inválido, o si el proveedor no lo soporta, cae al modo manual
        (``complete()`` + parseo + un reintento de reparación).
        """
        rendered = self._registry.render(self.template_id, context_dict)
        request = LLMRequest(
            system=self._registry.system_prompt(),
            messages=(LLMMessage(role="user", content=rendered),),
        )

        if isinstance(self._provider, StructuredOutput):
            try:
                parsed = await self._provider.complete_json(request, _STAGE_NARRATIVE_JSON_SCHEMA)
                if isinstance(parsed, dict):
                    return parsed, rendered
            except LLMSchemaError:
                logger.info("ai.newsletter_v2.structured_output_fallback reason=invalid_json")
            except Exception:
                logger.warning("ai.newsletter_v2.structured_output_fallback reason=provider_error")

        response = await self._provider.complete(request)
        parsed = self._try_parse(response.text)
        if parsed is not None:
            return parsed, rendered

        repair_response = await self._provider.complete(
            LLMRequest(
                system=self._registry.system_prompt(),
                messages=(
                    LLMMessage(role="user", content=rendered),
                    LLMMessage(role="assistant", content=response.text.strip() or "(vacío)"),
                    LLMMessage(role="user", content=_REPAIR_INSTRUCTION),
                ),
            )
        )
        parsed = self._try_parse(repair_response.text)
        if parsed is None:
            raise LLMSchemaError(
                "La respuesta IA v2 no es JSON válido tras un reintento de reparación."
            )
        return parsed, rendered

    async def _generate(
        self,
        ctx: StageNarrativeContext,
        context_dict: dict[str, Any],
        *,
        only_block: str | None,
    ) -> StageNarrative:
        try:
            parsed, rendered = await asyncio.wait_for(
                self._call_llm(context_dict), timeout=_LLM_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError as exc:
            raise StageNarrativeLLMTimeout(
                f"El proveedor LLM no respondió en {_LLM_TIMEOUT_SECONDS:.0f}s (narrativa v2)."
            ) from exc

        grounding_numbers = extract_numeric_tokens(rendered)
        guardrails = StageNarrativeGuardrails(
            forbidden_names=ctx.forbidden_names,
            grounding_numbers=grounding_numbers,
            previous_stage_text=ctx.previous_stage_text,
        )

        violations: list[str] = []
        wants = _ALLOWED_BLOCKS if only_block is None else (only_block,)

        stage_title = (
            _accept_text_field("stage_title", parsed.get("stage_title"), guardrails, violations)
            if "stage_title" in wants else None
        )
        summit_caption = (
            _accept_text_field("summit_caption", parsed.get("summit_caption"), guardrails, violations)
            if "summit_caption" in wants else None
        )
        next_segment_text = (
            _accept_text_field("next_segment_text", parsed.get("next_segment_text"), guardrails, violations)
            if "next_segment_text" in wants else None
        )
        observations = (
            _accept_observations(parsed.get("observations"), guardrails, violations)
            if "observations" in wants else None
        )
        family_compass = (
            _accept_family_compass(parsed.get("family_compass"), guardrails, violations)
            if "family_compass" in wants else None
        )
        analyst_reading = (
            _accept_analyst_reading(parsed.get("analyst_reading"), guardrails, violations)
            if "analyst_reading" in wants and ctx.analyst_reading_input is not None else None
        )

        return StageNarrative(
            stage_title=stage_title,
            summit_caption=summit_caption,
            observations=observations,
            next_segment_text=next_segment_text,
            family_compass=family_compass,
            analyst_reading=analyst_reading,
            model=self._provider.model,
            prompt_version=_PROMPT_VERSION,
            confidence=ctx.confidence,
            grounding_violations=violations,
        )
