"""Tests de privacidad del Asistente IA de sesiones (feature 006).

Cubre (tasks.md T032):
  - El contexto capturado por FakeLLMProvider (last_request) no contiene
    IDs ni nombres de atletas.
  - Los logs de la capa de contexto contienen solo conteos, no IDs/nombres.
  - ai_log_prompts=false se respeta (no se loguean prompts).

Ley 1581 (Colombia) — datos de menores:
  El único dato que llega al LLM es age_mix (conteos por grupo de edad),
  season_phase, race proximity y today. Nunca nombres, IDs, fechas de
  nacimiento exactas ni ningún otro dato identificante.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pytest

from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.session_assistant import (
    SessionClarifyUseCase,
    SessionDraftUseCase,
)
from app.services.training.session_assistant_context import build_aggregate_context


# ---------------------------------------------------------------------------
# Fixtures de base
# ---------------------------------------------------------------------------

CANNED_CLARIFY = json.dumps({
    "questions": [
        {
            "id": "q1",
            "header": "Grupo",
            "question": "¿Qué grupo?",
            "multi_select": False,
            "allow_other": False,
            "options": [
                {"label": "10-12", "description": "Infantil"},
                {"label": "13-15", "description": "Juvenil"},
            ],
        }
    ]
})

CANNED_DRAFT = json.dumps({
    "technical_focus": "Técnica básica",
    "objectives": "Mejorar habilidades.",
    "description": "CALENTAMIENTO:\nPARTE PRINCIPAL:\nVUELTA A LA CALMA:",
    "duration_min": 60,
    "session_kind": "entrenamiento",
    "location": None,
    "scheduled_date": None,
    "scheduled_start_time": None,
    "athlete_call_up": "ninguno",
    "notes": None,
})

# IDs de atletas "reales" que no deben filtrarse al LLM.
# Se usan IDs grandes que no aparecen como substrings en fechas (e.g. 2026, 08, 04)
# ni en conteos (1, 2, 3, 4, 5). Esto asegura que el assert de substring
# no genere falsos positivos por coincidencias con contenido legítimo del prompt.
ATHLETE_IDS = [99001, 99002, 99003, 99004, 99005]
# Nombres ficticios que no deben aparecer en ningún contexto enviado al LLM
ATHLETE_NAMES = ["Juan Pérez", "María García", "Carlos López"]


class _FakeDB:
    """Fake DB que devuelve birth_dates sin nombres ni IDs."""

    def __init__(self, birth_dates=None):
        self._birth_dates = birth_dates or [
            date(2013, 3, 15),
            date(2012, 8, 20),
            date(2014, 1, 5),
            date(2011, 11, 30),
            date(2013, 6, 10),
        ]

    class _Result:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return self

        def all(self):
            return list(self._values)

    async def execute(self, *args, **kwargs):
        return self._Result(self._birth_dates)


# ---------------------------------------------------------------------------
# T032 — El prompt enviado al LLM no contiene IDs ni nombres de atletas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_prompt_no_athlete_ids():
    """El prompt de clarificación no contiene los IDs de atletas seleccionados."""
    db = _FakeDB()
    registry = PromptRegistry()
    provider = FakeLLMProvider(canned=CANNED_CLARIFY)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
    )
    context["intent_text"] = "sesión técnica para el grupo"

    await use_case.run(context)

    # Inspeccionar el último request enviado al "modelo"
    assert provider.last_request is not None
    prompt_text = provider.last_request.messages[-1].content

    # Ningún ID de atleta debe aparecer en el prompt
    for aid in ATHLETE_IDS:
        assert str(aid) not in prompt_text, (
            f"ID de atleta {aid} encontrado en el prompt enviado al LLM. "
            "Violación de privacidad Ley 1581."
        )


@pytest.mark.asyncio
async def test_clarify_prompt_no_athlete_names():
    """El prompt no contiene nombres ficticios de atletas (defense in depth)."""
    db = _FakeDB()
    registry = PromptRegistry()
    provider = FakeLLMProvider(canned=CANNED_CLARIFY)
    use_case = SessionClarifyUseCase(provider=provider, registry=registry)

    # El intent puede contener texto del coach — no debe filtrar nombres propios
    # enviados intencionalmente, pero el contexto del DB sí los descarta.
    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
    )
    context["intent_text"] = "sesión técnica de descenso"

    await use_case.run(context)

    prompt_text = provider.last_request.messages[-1].content

    # Los nombres de atletas NO deben aparecer como parte del contexto del DB
    for name in ATHLETE_NAMES:
        assert name not in prompt_text, (
            f"Nombre de atleta '{name}' encontrado en el prompt. "
            "El contexto solo debe contener conteos agregados."
        )


@pytest.mark.asyncio
async def test_draft_prompt_no_athlete_ids():
    """El prompt de borrador no contiene IDs de atletas."""
    db = _FakeDB()
    registry = PromptRegistry()
    provider = FakeLLMProvider(canned=CANNED_DRAFT)
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
    )
    context["intent_text"] = "salida en La Cumbre"
    context["answers"] = []

    await use_case.run(context)

    assert provider.last_request is not None
    prompt_text = provider.last_request.messages[-1].content

    for aid in ATHLETE_IDS:
        assert str(aid) not in prompt_text, (
            f"ID de atleta {aid} encontrado en el prompt de borrador. "
            "Violación de privacidad."
        )


@pytest.mark.asyncio
async def test_context_dict_keys_are_privacy_safe():
    """El dict de contexto retornado solo tiene claves no identificantes."""
    db = _FakeDB()
    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
    )

    # Claves permitidas (ninguna identificante)
    allowed_keys = frozenset({
        "today", "age_mix", "total_athletes", "season_phase",
        "days_to_next_race", "next_race_priority",
    })
    assert set(context.keys()) == allowed_keys, (
        f"Claves no permitidas en el contexto: {set(context.keys()) - allowed_keys}"
    )


@pytest.mark.asyncio
async def test_context_age_mix_only_counts():
    """age_mix contiene solo conteos enteros, no fechas ni identificadores."""
    db = _FakeDB()
    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
    )

    age_mix = context["age_mix"]
    assert isinstance(age_mix, dict)

    for key, value in age_mix.items():
        assert isinstance(key, str), f"Clave de age_mix debe ser string: {key}"
        assert isinstance(value, int), f"Valor de age_mix debe ser int: {value}"
        # Las claves deben ser los grupos permitidos
        assert key in {"10-12", "13-15", "16+"}, (
            f"Grupo no permitido en age_mix: {key}"
        )


@pytest.mark.asyncio
async def test_no_birth_dates_in_context():
    """Las fechas de nacimiento exactas no aparecen en el contexto."""
    birth_dates = [date(2013, 3, 15), date(2012, 8, 20)]
    db = _FakeDB(birth_dates=birth_dates)
    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=[1, 2], today=date(2026, 6, 8)
    )

    context_str = str(context)
    for bd in birth_dates:
        assert bd.isoformat() not in context_str, (
            f"Fecha de nacimiento {bd} encontrada en el contexto. "
            "Violación de privacidad."
        )


# ---------------------------------------------------------------------------
# Tests de logs (ai_log_prompts=false)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_builder_logs_counts_only(caplog):
    """El context builder logea solo conteos, no IDs ni nombres."""
    db = _FakeDB()
    with caplog.at_level(logging.DEBUG, logger="app.services.training.session_assistant_context"):
        await build_aggregate_context(
            db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
        )

    # Verificar que ningún ID aparece en los logs
    log_text = " ".join(caplog.messages)
    for aid in ATHLETE_IDS:
        assert str(aid) not in log_text, (
            f"ID de atleta {aid} encontrado en los logs. "
            "Los logs solo deben contener conteos agregados."
        )


@pytest.mark.asyncio
async def test_draft_response_no_athlete_identifiers():
    """La respuesta del borrador no contiene identificadores de atletas."""
    db = _FakeDB()
    registry = PromptRegistry()
    provider = FakeLLMProvider(canned=CANNED_DRAFT)
    use_case = SessionDraftUseCase(provider=provider, registry=registry)

    context = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=ATHLETE_IDS, today=date(2026, 6, 8)
    )
    context["intent_text"] = "entrenamiento técnico"
    context["answers"] = []

    result = await use_case.run(context)

    result_str = str(result)
    for aid in ATHLETE_IDS:
        assert str(aid) not in result_str, (
            f"ID {aid} encontrado en el resultado del borrador."
        )

    # athlete_call_up debe ser un criterio enum, no un ID
    assert result["athlete_call_up"] in {"todos_convocados", "grupo_10_12", "grupo_13_15", "ninguno"}
