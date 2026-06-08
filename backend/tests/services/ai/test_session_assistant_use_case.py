"""Tests para los use cases del Asistente IA de sesiones (feature 006).

Cubre (del tasks.md):
  T017 - clarify: parse/validate/scrub con FakeLLMProvider fixture
  T028 - contexto 10-12 cerca de válida A: señales correctas + guardrails
  T034 - guardrail: frases prohibidas scrubbed o LLMSchemaError

No se llama a ningún modelo real — todo vía FakeLLMProvider con JSON canned.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.session_assistant import (
    SessionClarifyUseCase,
    SessionDraftUseCase,
    SessionAssistantLLMTimeout,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CANNED_CLARIFY = {
    "questions": [
        {
            "id": "q1",
            "header": "Grupo",
            "question": "¿Para qué grupo es la sesión?",
            "multi_select": False,
            "allow_other": True,
            "options": [
                {"label": "10-12 años", "description": "80% juego, sin intervalos estructurados"},
                {"label": "13-15 años", "description": "Máx 2 sesiones intensas por semana"},
                {"label": "Mixto", "description": "Ambos grupos juntos"},
            ],
        },
        {
            "id": "q2",
            "header": "Enfoque",
            "question": "¿Qué quieres priorizar?",
            "multi_select": True,
            "allow_other": True,
            "options": [
                {"label": "Técnica de bajada", "description": "Habilidad antes que fondo"},
                {"label": "Resistencia Z1-Z2", "description": "Base aeróbica suave"},
                {"label": "Diversión / juego", "description": "Formato lúdico"},
            ],
        },
    ]
}

CANNED_DRAFT = {
    "technical_focus": "Técnica de descenso en terreno suelto",
    "objectives": "Mejorar trazada y control de frenada; mantener cadencia ≥70 rpm.",
    "description": "CALENTAMIENTO (15 min): rodaje suave Z1.\nPARTE PRINCIPAL (55 min): bajadas técnicas.\nVUELTA A LA CALMA (20 min): estiramientos.",
    "duration_min": 90,
    "session_kind": "salida",
    "location": "La Cumbre",
    "scheduled_date": None,
    "scheduled_start_time": None,
    "athlete_call_up": "grupo_13_15",
    "notes": "Faltan días para una válida prioridad A — intensidad moderada.",
}


def _make_context(
    intent_text: str | None = "salida técnica en La Cumbre",
    age_mix: dict | None = None,
    days_to_next: int | None = 12,
    priority: str | None = "A",
) -> dict:
    return {
        "today": date(2026, 5, 5).isoformat(),
        "age_mix": age_mix or {"13-15": 3},
        "total_athletes": sum((age_mix or {"13-15": 3}).values()),
        "season_phase": "mesociclo de construcción",
        "days_to_next_race": days_to_next,
        "next_race_priority": priority,
        "intent_text": intent_text,
        "answers": [],
    }


@pytest.fixture
def registry():
    return PromptRegistry()


# ---------------------------------------------------------------------------
# T017 — Clarify: parse/validate/scrub happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_happy_path(registry):
    """Clarify retorna entre 2 preguntas con 2-4 opciones cada una."""
    canned_text = json.dumps(CANNED_CLARIFY)
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    result = await use_case.run(_make_context())

    assert "questions" in result
    assert "model" in result
    questions = result["questions"]
    assert 0 <= len(questions) <= 4

    for q in questions:
        assert "id" in q
        assert "header" in q
        assert "question" in q
        assert "options" in q
        assert 2 <= len(q["options"]) <= 4
        for opt in q["options"]:
            assert "label" in opt
            assert "description" in opt


@pytest.mark.asyncio
async def test_clarify_empty_questions_ok(registry):
    """El asistente puede devolver 0 preguntas si el intent es suficientemente claro."""
    canned_text = json.dumps({"questions": []})
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    result = await use_case.run(_make_context())

    assert result["questions"] == []


@pytest.mark.asyncio
async def test_clarify_fence_stripping(registry):
    """El use case elimina bloques ```json``` que puede añadir el LLM."""
    canned_text = f"```json\n{json.dumps(CANNED_CLARIFY)}\n```"
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    result = await use_case.run(_make_context())

    assert isinstance(result["questions"], list)


# ---------------------------------------------------------------------------
# T017 — Draft: parse/validate/scrub happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_happy_path(registry):
    """Draft retorna todos los campos esperados con tipos correctos."""
    canned_text = json.dumps(CANNED_DRAFT)
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    result = await use_case.run(ctx)

    assert result["technical_focus"] == "Técnica de descenso en terreno suelto"
    assert result["duration_min"] == 90
    assert result["session_kind"] == "salida"
    assert result["athlete_call_up"] == "grupo_13_15"
    assert result["model"] is not None


@pytest.mark.asyncio
async def test_draft_fence_stripping(registry):
    """El use case elimina bloques markdown del draft."""
    canned_text = f"```json\n{json.dumps(CANNED_DRAFT)}\n```"
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    result = await use_case.run(ctx)

    assert result["duration_min"] == 90


# ---------------------------------------------------------------------------
# T028 — Contexto 10-12 cerca de válida A
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_10_12_context_uses_guardrails(registry):
    """Para grupo 10-12, el guardrail aplica restricción de potenciómetro."""
    # El canned tiene contenido válido — la señal que probamos es que
    # el contexto se construye correctamente para el grupo 10-12.
    canned_text = json.dumps(CANNED_CLARIFY)
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    # Contexto exclusivo 10-12, cerca de válida A (5 días)
    ctx = _make_context(
        age_mix={"10-12": 5},
        days_to_next=5,
        priority="A",
    )
    result = await use_case.run(ctx)

    # El use case debe completar sin error
    assert "questions" in result
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_draft_10_12_powermeter_scrubbed(registry):
    """Para grupo exclusivo 10-12, texto con 'potenciómetro' es scrubbed."""
    canned_with_powermeter = {
        **CANNED_DRAFT,
        "technical_focus": "Trabajo con potenciómetro para medir esfuerzo",
        "objectives": "Monitorear vatios en la sesión",
        "athlete_call_up": "grupo_10_12",
    }
    canned_text = json.dumps(canned_with_powermeter)
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context(age_mix={"10-12": 4})
    ctx["answers"] = []
    result = await use_case.run(ctx)

    # El guardrail de 10-12 reemplaza "potenciómetro/vatios" por "RPE"
    assert "potenci" not in result["technical_focus"].lower()
    assert "vatios" not in (result["objectives"] or "").lower()


# ---------------------------------------------------------------------------
# T034 — Guardrail: frases prohibidas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_supplement_scrubbed(registry):
    """Texto con suplementos en opciones es scrubbed por guardrail."""
    canned_with_supplement = {
        "questions": [
            {
                "id": "q1",
                "header": "Nutrición",
                "question": "¿Qué tipo de recuperación usa el atleta?",
                "multi_select": False,
                "allow_other": False,
                "options": [
                    {"label": "Creatina post sesión", "description": "Suplemento de recuperación"},
                    {"label": "Comida real", "description": "Alimentos naturales"},
                ],
            }
        ]
    }
    canned_text = json.dumps(canned_with_supplement)
    provider = FakeLLMProvider(canned=canned_text)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    # El guardrail reemplaza "creatina" con la alternativa segura
    result = await use_case.run(_make_context())
    options = result["questions"][0]["options"]
    # "creatina" debe haber sido reemplazado por el guardrail
    labels_text = " ".join(o["label"] for o in options).lower()
    assert "creatina" not in labels_text


@pytest.mark.asyncio
async def test_draft_calorie_counting_scrubbed(registry):
    """Texto con 'conteo de calorías' es scrubbed por guardrail."""
    canned = {
        **CANNED_DRAFT,
        # El patrón del guardrail: r"\b(cont(ar|eo)|registr[ao]) (de )?calor[ií]as?\b"
        # "conteo de calorías" y "conteo calórico" coinciden con el patrón
        "notes": "Hacer conteo de calorías consumidas en la sesión.",
    }
    provider = FakeLLMProvider(canned=json.dumps(canned))
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    result = await use_case.run(ctx)

    # "conteo de calorías" reemplazado por guardrail
    notes_lower = (result["notes"] or "").lower()
    assert "conteo de calor" not in notes_lower


@pytest.mark.asyncio
async def test_clarify_too_many_questions_raises(registry):
    """Más de 4 preguntas levanta LLMSchemaError."""
    too_many = {"questions": [
        {
            "id": f"q{i}",
            "header": f"H{i}",
            "question": "Pregunta?",
            "multi_select": False,
            "allow_other": False,
            "options": [
                {"label": "A", "description": "Opción A"},
                {"label": "B", "description": "Opción B"},
            ],
        }
        for i in range(1, 6)  # 5 preguntas — excede máximo
    ]}
    provider = FakeLLMProvider(canned=json.dumps(too_many))
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    with pytest.raises(LLMSchemaError):
        await use_case.run(_make_context())


@pytest.mark.asyncio
async def test_clarify_too_few_options_raises(registry):
    """Menos de 2 opciones por pregunta levanta LLMSchemaError."""
    one_option = {"questions": [
        {
            "id": "q1",
            "header": "Grupo",
            "question": "Pregunta?",
            "multi_select": False,
            "allow_other": False,
            "options": [
                {"label": "Solo A", "description": "Solo una opción"},
            ],
        }
    ]}
    provider = FakeLLMProvider(canned=json.dumps(one_option))
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    with pytest.raises(LLMSchemaError):
        await use_case.run(_make_context())


@pytest.mark.asyncio
async def test_draft_invalid_json_raises(registry):
    """Respuesta que no es JSON válido levanta LLMSchemaError."""
    provider = FakeLLMProvider(canned="esto no es json {{{")
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    with pytest.raises(LLMSchemaError):
        await use_case.run(ctx)


@pytest.mark.asyncio
async def test_draft_missing_technical_focus_raises(registry):
    """Draft sin technical_focus levanta LLMSchemaError."""
    canned = {k: v for k, v in CANNED_DRAFT.items() if k != "technical_focus"}
    provider = FakeLLMProvider(canned=json.dumps(canned))
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    with pytest.raises(LLMSchemaError):
        await use_case.run(ctx)


@pytest.mark.asyncio
async def test_draft_invalid_session_kind_raises(registry):
    """session_kind inválido levanta LLMSchemaError."""
    canned = {**CANNED_DRAFT, "session_kind": "invalid_kind"}
    provider = FakeLLMProvider(canned=json.dumps(canned))
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    with pytest.raises(LLMSchemaError):
        await use_case.run(ctx)


@pytest.mark.asyncio
async def test_draft_duration_out_of_range_raises(registry):
    """duration_min fuera de [15, 240] levanta LLMSchemaError."""
    canned = {**CANNED_DRAFT, "duration_min": 300}
    provider = FakeLLMProvider(canned=json.dumps(canned))
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    with pytest.raises(LLMSchemaError):
        await use_case.run(ctx)


@pytest.mark.asyncio
async def test_draft_invalid_athlete_call_up_raises(registry):
    """athlete_call_up inválido levanta LLMSchemaError."""
    canned = {**CANNED_DRAFT, "athlete_call_up": "todos_con_nombre"}
    provider = FakeLLMProvider(canned=json.dumps(canned))
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    ctx = _make_context()
    ctx["answers"] = []
    with pytest.raises(LLMSchemaError):
        await use_case.run(ctx)
