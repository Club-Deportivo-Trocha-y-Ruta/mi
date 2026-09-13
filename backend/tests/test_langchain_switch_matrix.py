"""Tests — matriz de regresión del interruptor `AI_USE_LANGCHAIN` (feature 042, T071).

Defiende SC-006: "The migrated generations produce byte-identical outputs to
the previous transport for the same fake-model inputs, and their existing
tests pass unchanged with the switch in either position."

Los cinco casos de uso puenteados (`contracts/llm-transport.md` §0):

  - `SessionClarifyUseCase` / `SessionDraftUseCase`
    (`app/services/ai/use_cases/session_assistant.py`)
  - `MonthlyReportUseCase` (`app/services/ai/use_cases/monthly_report.py`)
  - `MonthlyReportBlocksUseCase`
    (`app/services/ai/use_cases/monthly_report_blocks.py`)
  - `AthleteMonthlyNewsletterV2UseCase`
    (`app/services/ai/use_cases/athlete_monthly_newsletter_v2.py`)

Cada uno de los cinco recibe su `LLMProvider` por inyección de dependencias
(`BaseUseCase.__init__`, `app/services/ai/use_cases/base.py`) y NUNCA lee
`Settings.ai_use_langchain` por su cuenta — esa lectura vive exclusivamente
en `app/services/ai/factory.py::create_llm_provider`, que decide qué
concreto de `LLMProvider` construir (`LangChainProvider` vs. el SDK nativo)
antes de entregárselo al caso de uso. La sección 1 de este archivo bloquea
justo la regresión contraria: que algún caso de uso empiece a leer el
switch directamente y su salida deje de ser estable frente a él.

`GenericFakeChatModel` (langchain_core) NO aparece en este archivo — sus dos
únicas ubicaciones legales en todo el repo son `tests/test_langchain_provider.py`
y `tests/anthro/**` (`contracts/llm-transport.md` §7). El doble
determinístico correcto para los cinco casos de uso puenteados es, por
diseño, `FakeLLMProvider` (`contracts/llm-transport.md` §0, fila "Test
double" — la misma columna documenta que `AI_PROVIDER=fake` nunca se
bridgea al adapter, con o sin el switch, `§6`): es el mismo doble que ya
usan las ~40 aserciones de privacidad que dependen de `FakeLLMProvider.
last_request` (FR-038). Por eso "byte-idéntico bajo ambas posiciones del
switch" se verifica aquí ejecutando cada caso de uso dos veces con el mismo
`FakeLLMProvider` (mismo `canned`/`canned_json`, mismo contexto) mientras
`Settings.ai_use_langchain` (el singleton real que consulta la factoría en
producción) vale `False` y luego `True` — si algún caso de uso llegara a
consultar ese switch, esta prueba lo detectaría como una salida distinta
entre las dos corridas.

Sección 2 comprueba que el short-circuit `AI_ENABLED=false` -> siempre
`FakeLLMProvider` (con `.last_request` legible) sobrevive bajo ambos
valores del switch. Sección 3 comprueba que el switch no abre una vía nueva
para que `RACE_AI_*` se filtre al stack app (regla de herencia de una sola
vía, `contracts/config-env.md` §0).

Privacidad: todos los contextos de abajo son ficticios y agregados — sin
nombres reales, sin fechas de nacimiento, sin datos identificantes de
menores — igual que los fixtures de los tests propios de cada caso de uso
de los que estos se derivan.
"""

from __future__ import annotations

import json

import pytest

from app.config import settings as global_settings
from app.services.ai.factory import create_llm_provider
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
    AthleteMonthlyNewsletterV2UseCase,
    build_context_from_metrics_v2,
)
from app.services.ai.use_cases.monthly_report import (
    AnonymizedAthleteStats,
    MonthlyReportContext,
    MonthlyReportUseCase,
)
from app.services.ai.use_cases.monthly_report_blocks import MonthlyReportBlocksUseCase
from app.services.ai.use_cases.session_assistant import (
    SessionClarifyUseCase,
    SessionDraftUseCase,
)
from app.services.llm.factory import resolve_app_config, resolve_configured_model

# ---------------------------------------------------------------------------
# Fixtures compartidas — recortadas de los tests propios de cada caso de uso
# (`tests/services/ai/test_session_assistant_use_case.py`,
# `tests/test_ai_monthly_report.py`, `tests/test_monthly_report_blocks.py`,
# `tests/services/ai/test_athlete_monthly_newsletter_v2.py`) para no
# depender de esos módulos de test, manteniendo la propiedad de archivo de
# este slice (T071) estricta.
# ---------------------------------------------------------------------------

_SESSION_CONTEXT: dict = {
    "today": "2026-05-05",
    "age_mix": {"13-15": 3},
    "total_athletes": 3,
    "season_phase": "mesociclo de construcción",
    "days_to_next_race": 12,
    "next_race_priority": "A",
    "intent_text": "salida técnica en La Cumbre",
    "answers": [],
}

_CANNED_CLARIFY_JSON: dict = {
    "questions": [
        {
            "id": "q1",
            "header": "Grupo",
            "question": "¿Para qué grupo es la sesión?",
            "multi_select": False,
            "allow_other": True,
            "options": [
                {"label": "10-12 años", "description": "80% juego, sin intervalos"},
                {"label": "13-15 años", "description": "Máx 2 sesiones intensas"},
            ],
        }
    ]
}

_CANNED_DRAFT_JSON: dict = {
    "technical_focus": "Técnica de descenso en terreno suelto",
    "objectives": "Mejorar trazada y control de frenada; cadencia ≥70 rpm.",
    "description": "CALENTAMIENTO (15 min): rodaje suave Z1.\nPARTE PRINCIPAL (55 min): bajadas técnicas.",
    "duration_min": 90,
    "session_kind": "salida",
    "location": "La Cumbre",
    "scheduled_date": None,
    "scheduled_start_time": None,
    "athlete_call_up": "grupo_13_15",
    "notes": "Faltan días para una válida prioridad A — intensidad moderada.",
}


def _monthly_report_ctx() -> MonthlyReportContext:
    return MonthlyReportContext(
        club_name="Trocha y Ruta",
        period_year=2026,
        period_month=4,
        total_sessions_planned=12,
        total_sessions_executed=10,
        total_sessions_cancelled=2,
        attendance_stats=[
            AnonymizedAthleteStats(
                pseudonym="A1", count_present=8, count_total=10, percentage=80.0
            ),
            AnonymizedAthleteStats(
                pseudonym="A2", count_present=6, count_total=10, percentage=60.0
            ),
        ],
        focos_técnicos=["Frenado progresivo", "Pedaleo en terreno técnico"],
        avg_rpe=6.5,
        avg_rubric_effort=3.8,
        avg_rubric_attitude=4.1,
        avg_rubric_technique=3.5,
        coach_observations=None,
        forbidden_names=frozenset(),
    )


_MONTHLY_REPORT_CANNED_TEXT = (
    "Durante el mes se ejecutaron 10 de las 12 sesiones planificadas, con una "
    "tasa de cancelación moderada y asistencia grupal sostenida por encima "
    "del 70% en la mayoría del grupo de alto rendimiento. Los focos técnicos "
    "trabajados —frenado progresivo y pedaleo en terreno técnico— fueron "
    "consistentes con el plan mensual aprobado por el comité del club. Los "
    "promedios de rúbrica muestran niveles adecuados en esfuerzo y actitud, "
    "por lo que se recomienda continuar reforzando el foco en técnica durante "
    "las próximas semanas del mesociclo en curso."
)

_MONTHLY_BLOCK_CANNED_TEXT = (
    "El plan de entrenamiento priorizó frenado progresivo y cadencia en "
    "subida, alineado con el mesociclo vigente del grupo de alto rendimiento. "
    "Se mantuvo la relación entrenamiento-competencia definida para el "
    "período, con ajustes puntuales por clima y disponibilidad de pista. El "
    "foco principal estuvo en consolidar la lectura de terreno técnico y "
    "reforzar hábitos de calentamiento antes de cada sesión planificada del "
    "mesociclo, ajustando cargas de forma progresiva según la respuesta "
    "observada del grupo durante las semanas evaluadas."
)


def _newsletter_snapshot() -> dict:
    return {
        "email_blocks": {
            "period": {"year": 2026, "month": 6, "label": "Junio 2026"},
            "attendance": {
                "sessions_present": 9,
                "sessions_total": 10,
                "attendance_pct": 90.0,
                "attendance_pct_prev_month": 85.0,
                "streak_sessions": 6,
            },
            "technical": {
                "focos_tecnicos": ["Frenado", "Curvas cerradas"],
                "avg_rpe": 6.2,
                "avg_rubric_technique": 3.8,
            },
            "race_results": {
                "has_races": True,
                "results": [
                    {
                        "position": 4,
                        "label": "Válida III — Cali",
                        "gap_to_winner_pct": 3.2,
                        "event_date": "2026-06-14",
                        "category_label": "Prejuvenil A",
                    }
                ],
            },
            "badges": {"items": [{"badge_type": "attendance_90"}]},
            "calendar": {
                "next_race_events": [
                    {
                        "date": "2026-07-12",
                        "valida": "IV",
                        "location": "Ginebra",
                        "priority": "A",
                    }
                ]
            },
        },
        "pdf_only_blocks": {
            "weekly": [
                {"date": "2026-06-02", "attended": True, "rpe": 6, "rubric_avg": 3.5},
                {"date": "2026-06-09", "attended": True, "rpe": 7, "rubric_avg": 4.0},
            ],
            "next_focus_groups": [{"name": "Frenado"}, {"name": "Salto"}],
        },
    }


def _newsletter_ctx():
    return build_context_from_metrics_v2(
        _newsletter_snapshot(), 2026, 6, frozenset(), athlete_sex="F"
    )


# Fixture verificado por `tests/services/ai/test_athlete_monthly_newsletter_v2.py`
# (`_happy_canned_json`) como camino feliz de `_newsletter_ctx()` sin
# `grounding_violations` — reutilizado tal cual aquí para no reintroducir un
# caso que se rompa por un número no anclado en el prompt renderizado.
_NEWSLETTER_CANNED_JSON: dict = {
    "stage_title": "Una etapa de constancia: 9 de 10 sesiones y un P4 en la Válida III — Cali",
    "summit_caption": (
        "El P4 en la Válida III — Cali confirma lo que se vio en cada "
        "entrenamiento del mes."
    ),
    "observations": [
        {
            "claim": "La constancia fue la base de esta etapa.",
            "evidence": "9/10 sesiones asistidas.",
            "block_ref": "attendance",
        },
        {
            "claim": "El trabajo de frenado ya se nota en pista.",
            "evidence": "Foco técnico: frenado y curvas cerradas.",
            "block_ref": "technical",
        },
        {
            "claim": "La racha de entrenamiento se sostuvo todo el mes.",
            "evidence": "Racha actual de 6 sesiones.",
            "block_ref": "streak",
        },
    ],
    "next_segment_text": (
        "El próximo tramo sigue afinando frenado y curvas cerradas, con la "
        "mira en la próxima carrera."
    ),
    "family_compass": {
        "conversation_question": "¿Qué fue lo que más disfrutaste entrenar este mes?",
        "monthly_challenge": (
            "Celebrar cada sesión completa, sin importar el resultado de la "
            "próxima carrera."
        ),
        "what_to_watch": (
            "Cómo se siente en las frenadas fuertes durante los próximos "
            "entrenamientos."
        ),
    },
    "analyst_reading": {
        "headline_family": (
            "El entrenador notó que el trabajo de frenado ya se refleja en carrera."
        ),
        "action_family": "Seguir practicando frenado en curvas cerradas dos veces por semana.",
    },
}


def _set_switch(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """Fija `Settings.ai_use_langchain` en el singleton real que consulta
    `create_llm_provider` en producción. Ningún caso de uso de este archivo
    lee este atributo — el punto de la sección 1 es probar precisamente eso."""
    monkeypatch.setattr(global_settings, "ai_use_langchain", value)


# ---------------------------------------------------------------------------
# 1. Byte-idéntico para las cinco entradas fake bajo ambas posiciones del switch
# ---------------------------------------------------------------------------


async def test_session_clarify_byte_identical_across_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PromptRegistry()

    _set_switch(monkeypatch, False)
    fake_off = FakeLLMProvider(canned_json=_CANNED_CLARIFY_JSON, canned=json.dumps(_CANNED_CLARIFY_JSON))
    result_off = await SessionClarifyUseCase(fake_off, registry).run(dict(_SESSION_CONTEXT))

    _set_switch(monkeypatch, True)
    fake_on = FakeLLMProvider(canned_json=_CANNED_CLARIFY_JSON, canned=json.dumps(_CANNED_CLARIFY_JSON))
    result_on = await SessionClarifyUseCase(fake_on, registry).run(dict(_SESSION_CONTEXT))

    assert result_off == result_on


async def test_session_draft_byte_identical_across_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PromptRegistry()

    _set_switch(monkeypatch, False)
    fake_off = FakeLLMProvider(canned=json.dumps(_CANNED_DRAFT_JSON))
    result_off = await SessionDraftUseCase(fake_off, registry).run(dict(_SESSION_CONTEXT))

    _set_switch(monkeypatch, True)
    fake_on = FakeLLMProvider(canned=json.dumps(_CANNED_DRAFT_JSON))
    result_on = await SessionDraftUseCase(fake_on, registry).run(dict(_SESSION_CONTEXT))

    assert result_off == result_on


async def test_monthly_report_byte_identical_across_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PromptRegistry()
    ctx = _monthly_report_ctx()

    _set_switch(monkeypatch, False)
    fake_off = FakeLLMProvider(canned=_MONTHLY_REPORT_CANNED_TEXT)
    result_off = await MonthlyReportUseCase(fake_off, registry).run(ctx)

    _set_switch(monkeypatch, True)
    fake_on = FakeLLMProvider(canned=_MONTHLY_REPORT_CANNED_TEXT)
    result_on = await MonthlyReportUseCase(fake_on, registry).run(ctx)

    # `generated_at` es `datetime.now(timezone.utc)` en cada `FakeLLMProvider.
    # complete()` (`app/services/ai/models.py::LLMResponse`) — no forma parte
    # del texto producido por la IA y no debe compararse aquí; el resto del
    # resultado sí debe ser byte-idéntico.
    assert result_off.text == result_on.text
    assert result_off.model == result_on.model
    assert result_off.provider == result_on.provider


async def test_monthly_report_blocks_byte_identical_across_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PromptRegistry()
    ctx = _monthly_report_ctx()

    _set_switch(monkeypatch, False)
    fake_off = FakeLLMProvider(canned=_MONTHLY_BLOCK_CANNED_TEXT)
    draft_off = await MonthlyReportBlocksUseCase(fake_off, registry).run_block(
        ctx, "plan_entrenamiento"
    )

    _set_switch(monkeypatch, True)
    fake_on = FakeLLMProvider(canned=_MONTHLY_BLOCK_CANNED_TEXT)
    draft_on = await MonthlyReportBlocksUseCase(fake_on, registry).run_block(
        ctx, "plan_entrenamiento"
    )

    assert draft_off.error is None
    assert draft_on.error is None
    assert draft_off.ai_draft == draft_on.ai_draft
    assert draft_off.ai_model == draft_on.ai_model


async def test_athlete_monthly_newsletter_v2_byte_identical_across_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PromptRegistry()
    ctx = _newsletter_ctx()

    _set_switch(monkeypatch, False)
    fake_off = FakeLLMProvider(canned_json=_NEWSLETTER_CANNED_JSON)
    narrative_off = await AthleteMonthlyNewsletterV2UseCase(fake_off, registry).run(ctx)

    _set_switch(monkeypatch, True)
    fake_on = FakeLLMProvider(canned_json=_NEWSLETTER_CANNED_JSON)
    narrative_on = await AthleteMonthlyNewsletterV2UseCase(fake_on, registry).run(ctx)

    assert narrative_off.grounding_violations == []
    assert narrative_off == narrative_on


# ---------------------------------------------------------------------------
# 2. El short-circuit del fake sobrevive bajo ambas posiciones del switch
#    (FR-038) — ~40 tests de privacidad leen `FakeLLMProvider.last_request`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("use_langchain", [False, True])
async def test_ai_disabled_always_returns_fake_regardless_of_switch(
    monkeypatch: pytest.MonkeyPatch, use_langchain: bool
) -> None:
    """`AI_ENABLED=false` -> siempre `FakeLLMProvider`, sin importar
    `AI_USE_LANGCHAIN` — el short-circuit va ANTES que el switch
    (`app/services/ai/factory.py::create_llm_provider`)."""
    monkeypatch.setattr(global_settings, "ai_enabled", False)
    monkeypatch.setattr(global_settings, "ai_use_langchain", use_langchain)
    monkeypatch.setattr(global_settings, "ai_provider", "anthropic")

    provider = create_llm_provider(global_settings)

    assert isinstance(provider, FakeLLMProvider)


@pytest.mark.parametrize("use_langchain", [False, True])
async def test_fake_provider_last_request_survives_switch(
    monkeypatch: pytest.MonkeyPatch, use_langchain: bool
) -> None:
    """`FakeLLMProvider.last_request` sigue exponiendo el último prompt bajo
    ambos valores del switch — la superficie de la que dependen ~40
    aserciones de privacidad (`test_pii_never_reaches_llm` y equivalentes)
    en los cinco casos de uso puenteados. Se ejercita vía `BaseUseCase._ask`
    (el mismo camino que usan los cinco casos de uso reales), sin depender
    del parseo JSON de ninguno de ellos en particular."""
    monkeypatch.setattr(global_settings, "ai_enabled", False)
    monkeypatch.setattr(global_settings, "ai_use_langchain", use_langchain)
    monkeypatch.setattr(global_settings, "ai_provider", "google")

    provider = create_llm_provider(global_settings)
    assert isinstance(provider, FakeLLMProvider)
    assert provider.last_request is None

    registry = PromptRegistry()
    use_case = SessionClarifyUseCase(provider, registry)
    await use_case._ask(dict(_SESSION_CONTEXT))

    assert provider.last_request is not None
    assert provider.last_request.messages[-1].content  # el prompt renderizado real
    assert provider.call_count == 1


@pytest.mark.parametrize("use_langchain", [False, True])
async def test_ai_provider_fake_never_bridges_to_langchain(
    monkeypatch: pytest.MonkeyPatch, use_langchain: bool
) -> None:
    """`AI_PROVIDER=fake` (con `AI_ENABLED=true`) nunca se bridgea al
    adapter `LangChainProvider` — no es un transporte real que bridgear
    (`contracts/llm-transport.md` §6), con o sin el switch."""
    monkeypatch.setattr(global_settings, "ai_enabled", True)
    monkeypatch.setattr(global_settings, "ai_provider", "fake")
    monkeypatch.setattr(global_settings, "ai_use_langchain", use_langchain)

    provider = create_llm_provider(global_settings)

    assert isinstance(provider, FakeLLMProvider)


# ---------------------------------------------------------------------------
# 3. El switch nunca abre una vía para que RACE_AI_* se filtre al stack app
#    (regla de herencia de una sola vía, `contracts/config-env.md` §0).
# ---------------------------------------------------------------------------

_RACE_SENTINEL = "qqq-race-only-sentinel-nunca-en-app-switch-matrix"


@pytest.mark.parametrize("use_langchain", [False, True])
def test_app_stack_resolution_ignores_race_ai_settings_under_both_switch_values(
    monkeypatch: pytest.MonkeyPatch, use_langchain: bool
) -> None:
    """Se fija cada variable `RACE_AI_*` relevante a un valor centinela
    distintivo, se fija `AI_USE_LANGCHAIN` en cada una de sus dos
    posiciones, y se comprueba que `resolve_app_config`/
    `resolve_configured_model(stack="app")` nunca devuelven el centinela —
    la resolución del stack app depende solo de `AI_*`, nunca del switch."""
    monkeypatch.setattr(global_settings, "ai_use_langchain", use_langchain)

    monkeypatch.setattr(global_settings, "race_ai_provider", "openai")  # != ai_provider
    monkeypatch.setattr(global_settings, "race_ai_model", _RACE_SENTINEL)
    monkeypatch.setattr(global_settings, "race_ai_api_key", _RACE_SENTINEL)
    monkeypatch.setattr(global_settings, "race_ai_base_url", _RACE_SENTINEL)
    monkeypatch.setattr(global_settings, "race_ai_analyst_model", _RACE_SENTINEL)
    monkeypatch.setattr(global_settings, "race_ai_critic_model", _RACE_SENTINEL)
    monkeypatch.setattr(global_settings, "race_ai_temperature", 987654.0)

    monkeypatch.setattr(global_settings, "ai_provider", "google")
    monkeypatch.setattr(global_settings, "ai_model", "gemini-app-legacy")
    monkeypatch.setattr(global_settings, "ai_api_key", "app-real-key")
    monkeypatch.setattr(global_settings, "ai_base_url", "https://app.example/v1")
    monkeypatch.setattr(global_settings, "ai_analyst_model", "gemini-app-analyst")
    monkeypatch.setattr(global_settings, "ai_critic_model", "gemini-app-critic")
    monkeypatch.setattr(global_settings, "ai_temperature", 0.4)

    for role in (None, "analyst", "critic"):
        config = resolve_app_config(role=role)
        assert config.provider == "google"
        assert config.model != _RACE_SENTINEL
        assert config.api_key != _RACE_SENTINEL
        assert config.base_url != _RACE_SENTINEL
        assert config.temperature != 987654.0

    assert resolve_app_config(role=None).model == "gemini-app-legacy"
    assert resolve_app_config(role="analyst").model == "gemini-app-analyst"
    assert resolve_app_config(role="critic").model == "gemini-app-critic"
    assert resolve_configured_model(stack="app") == "gemini-app-legacy"
    assert resolve_configured_model(stack="app", role="analyst") == "gemini-app-analyst"
