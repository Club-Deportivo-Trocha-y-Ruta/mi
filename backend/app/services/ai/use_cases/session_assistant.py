"""Use cases para el Asistente IA de sesiones (feature 006).

Dos use cases:
  - SessionClarifyUseCase: genera preguntas de clarificación (0–4).
  - SessionDraftUseCase: genera un borrador editable de sesión.

Ambos siguen exactamente el patrón de AthleteNewsletterUseCase:
  render(context) → _ask() → strip fences → json.loads → guardrail scrub → Pydantic validate.

PRIVACIDAD: el contexto que llega a estos use cases NUNCA contiene IDs ni
nombres de atletas. Solo age_mix (conteos), season_phase, race proximity y today.
El guardrail hace scrub de todos los strings de salida visibles para el coach.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.services.ai.guardrails import Guardrails
from app.services.ai.protocols import LLMProvider
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.use_cases.base import BaseUseCase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excepciones específicas
# ---------------------------------------------------------------------------


class SessionAssistantLLMTimeout(Exception):
    """El proveedor LLM no respondió en el tiempo configurado."""


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------


def _strip_json_fences(text: str) -> str:
    """Elimina bloques de código markdown ``` que el LLM puede añadir."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text.strip())
    return text.strip()


def _scrub_string(guardrails: Guardrails, value: str | None) -> str | None:
    """Aplica guardrails a un string nullable; None se devuelve sin tocar."""
    if value is None:
        return None
    return guardrails.scrub(value)


# ---------------------------------------------------------------------------
# SessionClarifyUseCase
# ---------------------------------------------------------------------------


class SessionClarifyUseCase(BaseUseCase):
    """Caso de uso: generar preguntas de clarificación para una sesión XCO.

    Retorna 0–4 preguntas con 2–4 opciones cada una.
    """

    template_id = "session_clarify"

    def __init__(self, provider: LLMProvider, registry: PromptRegistry) -> None:
        super().__init__(provider, registry, guardrails=None)

    async def run(
        self,
        context: dict[str, Any],
        *,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Genera las preguntas de clarificación.

        Args:
            context: Contexto agregado de ``build_aggregate_context`` +
                ``intent_text`` añadido por el router.
            timeout_seconds: Máximo de espera al LLM.

        Returns:
            Dict con ``questions`` (lista) y ``model`` (str).

        Raises:
            SessionAssistantLLMTimeout: si el LLM no responde en tiempo.
            LLMSchemaError: si la respuesta no cumple el schema.
        """
        from app.services.ai.errors import LLMSchemaError

        guardrails = Guardrails(age_group=None)

        try:
            response = await asyncio.wait_for(
                self._ask(context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise SessionAssistantLLMTimeout(
                f"El proveedor LLM no respondió en {timeout_seconds:.0f}s."
            ) from exc

        raw_text = _strip_json_fences(response.text)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMSchemaError(
                f"La respuesta IA del asistente no es JSON válido: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMSchemaError("La respuesta IA debe ser un objeto JSON.")

        questions_raw = parsed.get("questions", [])
        if not isinstance(questions_raw, list):
            raise LLMSchemaError("El campo 'questions' debe ser una lista.")

        if len(questions_raw) > 4:
            raise LLMSchemaError(
                f"El asistente devolvió {len(questions_raw)} preguntas; máximo 4."
            )

        # Guardrail scrub + validación de conteos por pregunta
        questions_out: list[dict] = []
        for q in questions_raw:
            if not isinstance(q, dict):
                raise LLMSchemaError("Cada pregunta debe ser un objeto JSON.")

            for key in ("id", "header", "question"):
                if key not in q:
                    raise LLMSchemaError(f"Pregunta sin clave requerida: '{key}'.")
                if not isinstance(q[key], str):
                    raise LLMSchemaError(f"Clave '{key}' de pregunta debe ser string.")

            options_raw = q.get("options", [])
            if not isinstance(options_raw, list):
                raise LLMSchemaError("El campo 'options' de una pregunta debe ser lista.")
            if len(options_raw) < 2 or len(options_raw) > 4:
                raise LLMSchemaError(
                    f"Pregunta '{q.get('id', '?')}' tiene {len(options_raw)} opciones; "
                    "debe tener entre 2 y 4."
                )

            # Scrub strings visibles para el coach
            scrubbed_q: dict[str, Any] = {
                "id": q["id"],
                "header": guardrails.scrub(q["header"]),
                "question": guardrails.scrub(q["question"]),
                "multi_select": bool(q.get("multi_select", False)),
                "allow_other": bool(q.get("allow_other", False)),
                "options": [],
            }

            for opt in options_raw:
                if not isinstance(opt, dict):
                    raise LLMSchemaError("Cada opción debe ser un objeto JSON.")
                label = opt.get("label", "")
                description = opt.get("description", "")
                if not isinstance(label, str) or not isinstance(description, str):
                    raise LLMSchemaError("Los campos 'label' y 'description' de una opción deben ser strings.")
                scrubbed_q["options"].append(
                    {
                        "label": guardrails.scrub(label),
                        "description": guardrails.scrub(description),
                    }
                )

            questions_out.append(scrubbed_q)

        model_id = response.model or self._provider.model
        logger.debug(
            "session_clarify.run questions_count=%d model=%s",
            len(questions_out),
            model_id,
        )

        return {
            "questions": questions_out,
            "model": model_id,
        }


# ---------------------------------------------------------------------------
# SessionDraftUseCase
# ---------------------------------------------------------------------------


class SessionDraftUseCase(BaseUseCase):
    """Caso de uso: generar un borrador editable de sesión XCO.

    Los campos de texto libre se scrubbean con Guardrails antes de retornar.
    `athlete_call_up` es un criterio no identificante.
    """

    template_id = "session_draft"

    def __init__(self, provider: LLMProvider, registry: PromptRegistry) -> None:
        super().__init__(provider, registry, guardrails=None)

    async def run(
        self,
        context: dict[str, Any],
        *,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Genera el borrador de la sesión.

        Args:
            context: Contexto agregado + intent_text + answers (lista de dicts).
            timeout_seconds: Máximo de espera al LLM.

        Returns:
            Dict con los campos del borrador de sesión y ``model``.

        Raises:
            SessionAssistantLLMTimeout: si el LLM no responde en tiempo.
            LLMSchemaError: si la respuesta no cumple el schema o falla guardrail.
        """
        from app.services.ai.errors import LLMSchemaError

        # Usar age_mix para determinar el group context del guardrail
        age_mix: dict[str, int] = context.get("age_mix") or {}
        only_under_13 = (
            age_mix.get("10-12", 0) > 0
            and age_mix.get("13-15", 0) == 0
            and age_mix.get("16+", 0) == 0
        )
        age_group_for_guardrail = "10-12" if only_under_13 else None
        guardrails = Guardrails(age_group=age_group_for_guardrail)

        try:
            response = await asyncio.wait_for(
                self._ask(context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise SessionAssistantLLMTimeout(
                f"El proveedor LLM no respondió en {timeout_seconds:.0f}s."
            ) from exc

        raw_text = _strip_json_fences(response.text)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMSchemaError(
                f"La respuesta IA del borrador no es JSON válido: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMSchemaError("La respuesta IA debe ser un objeto JSON.")

        # Validar campo requerido
        if "technical_focus" not in parsed or not isinstance(parsed.get("technical_focus"), str):
            raise LLMSchemaError("Respuesta IA falta clave requerida: 'technical_focus'.")

        # Validar duration_min
        duration = parsed.get("duration_min")
        if duration is None:
            raise LLMSchemaError("Respuesta IA falta clave requerida: 'duration_min'.")
        try:
            duration = int(duration)
        except (TypeError, ValueError) as exc:
            raise LLMSchemaError(f"'duration_min' no es un entero válido: {duration}") from exc
        if not 15 <= duration <= 240:
            raise LLMSchemaError(
                f"'duration_min' fuera de rango (15–240): {duration}."
            )

        # Validar session_kind
        from app.models.training_session import SessionKind
        valid_kinds = {e.value for e in SessionKind}
        session_kind_raw = parsed.get("session_kind", "entrenamiento")
        if session_kind_raw not in valid_kinds:
            raise LLMSchemaError(
                f"'session_kind' inválido: '{session_kind_raw}'. "
                f"Valores aceptados: {sorted(valid_kinds)}."
            )

        # Validar athlete_call_up
        from app.schemas.session_assistant import AthleteCallUpCriterion
        valid_criteria = {e.value for e in AthleteCallUpCriterion}
        call_up_raw = parsed.get("athlete_call_up", "ninguno")
        if call_up_raw not in valid_criteria:
            raise LLMSchemaError(
                f"'athlete_call_up' inválido: '{call_up_raw}'. "
                f"Valores aceptados: {sorted(valid_criteria)}."
            )

        # Scrub de todos los campos de texto libre visibles para el coach
        technical_focus = guardrails.scrub(parsed["technical_focus"])
        objectives = _scrub_string(guardrails, parsed.get("objectives"))
        description = _scrub_string(guardrails, parsed.get("description"))
        location = _scrub_string(guardrails, parsed.get("location"))
        notes = _scrub_string(guardrails, parsed.get("notes"))

        model_id = response.model or self._provider.model
        logger.debug(
            "session_draft.run session_kind=%s duration_min=%d athlete_call_up=%s model=%s",
            session_kind_raw,
            duration,
            call_up_raw,
            model_id,
        )

        return {
            "technical_focus": technical_focus,
            "objectives": objectives,
            "description": description,
            "duration_min": duration,
            "session_kind": session_kind_raw,
            "location": location,
            "scheduled_date": parsed.get("scheduled_date"),
            "scheduled_start_time": parsed.get("scheduled_start_time"),
            "athlete_call_up": call_up_raw,
            "notes": notes,
            "model": model_id,
        }
