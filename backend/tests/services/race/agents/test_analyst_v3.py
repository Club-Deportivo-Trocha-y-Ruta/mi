"""Tests de ``RaceAnalystAgent.invoke_v3`` (feature 037, T201).

Cubre los tres caminos de obtención del JSON (structured output → JSON en
texto → reintento de reparación), el fallback determinista, el cap de
concurrencia, el grounding numérico y el scrubbing de nombres reales.

Ningún test toca la red ni la DB: se inyectan LLMs falsos.
Datos 100 % ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage

from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V3,
    PROMPT_VERSION_SEASON_SUMMARY_V3,
    AnalystV3Input,
    RaceAnalystAgent,
    parse_insight_v3,
    scrub_insight_v3,
    v3_prompt_version,
)
from app.services.race.ai.fallback import is_fallback_output
from app.services.race.insight_v3 import InsightV3

VALID_PAYLOAD: dict = {
    "schema_version": "v3",
    "headline": "Perdió 2 puestos frente a lo esperado tras la ventana con 62.5% de asistencia",
    "field_reading": {
        "percentile": 58.3,
        "expected_position": 5,
        "actual_position": 7,
        "delta_vs_expected": -2,
        "gap_to_p3_hhmmss": "0:03:12",
        "series_label": "Válida IV · Copa",
        "summary": "Rindió por debajo de su índice previo.",
    },
    "trend": "declining",
    "observations": [
        {
            "claim": "El retroceso coincide con la ventana de entrenamiento más floja.",
            "evidence": ["asistencia 62.5%", "RPE medio 4.1"],
            "domain": "training",
            "confidence": "medium",
        },
        {
            "claim": "El tiempo perdido está en el terreno técnico.",
            "evidence": ["gap a P3 0:03:12"],
            "domain": "field",
            "confidence": "low",
        },
    ],
    "actions": [
        {
            "text": "Recuperar 4 sesiones semanales antes de la próxima válida.",
            "category": "volume",
            "priority": "high",
            "horizon": "next_week",
            "catalog_ref": None,
            "derived_from": 0,
        },
        {
            "text": "Dos bloques de 20 min de descensos por semana.",
            "category": "technique",
            "priority": "med",
            "horizon": "next_race",
            "catalog_ref": {"kind": "interval_template", "code": "12", "label": None},
            "derived_from": 1,
        },
    ],
    "watch_signals": [],
    "coach_question": "¿Hubo algo distinto en las tres semanas previas?",
    "data_gaps": [],
    "principles_cited": [],
}

FIELD_METRICS = {
    "valida_num": 4,
    "event_date": "2026-05-10",
    "series_kind": "cup",
    "series_level": "departmental",
    "is_championship": False,
    "field_size": 18,
    "position": 7,
    "percentile": 58.3,
    "gap_to_p1_ms": 243000,
    "gap_pct": 9.4,
    "gap_to_p3_ms": 192000,
    "gap_to_median_pct": -2.7,
    "laps_behind": 0,
    "expected_position": 5,
    "delta_vs_expected": -2,
    "field_strength": 10.2,
    "coverage_with_prior": 0.7,
}


def make_input(**overrides) -> AnalystV3Input:
    base = {
        "valida_num": 4,
        "athlete_ref": "la deportista",
        "age": 13,
        "ltad_group": "juvenil",
        "season": 2026,
        "field_metrics": FIELD_METRICS,
    }
    base.update(overrides)
    return AnalystV3Input(**base)


def _message(text: str) -> AIMessage:
    return AIMessage(
        content=text,
        usage_metadata={"input_tokens": 900, "output_tokens": 300, "total_tokens": 1200},
    )


class _StructuredBinding:
    def __init__(self, payload: dict, include_raw: bool):
        self._payload = payload
        self._include_raw = include_raw

    async def ainvoke(self, messages):
        parsed = InsightV3.model_validate(self._payload)
        if self._include_raw:
            return {
                "raw": _message(json.dumps(self._payload)),
                "parsed": parsed,
                "parsing_error": None,
            }
        return parsed


class FakeStructuredLLM:
    """LLM con ``with_structured_output`` funcional (camino feliz)."""

    def __init__(self, payload: dict = None, supports_include_raw: bool = True):
        self._payload = payload or VALID_PAYLOAD
        self._supports_include_raw = supports_include_raw
        self.structured_calls = 0

    def with_structured_output(self, schema, include_raw=False):
        if include_raw and not self._supports_include_raw:
            raise TypeError("include_raw no soportado")
        self.structured_calls += 1
        return _StructuredBinding(self._payload, include_raw)

    async def ainvoke(self, messages):  # pragma: no cover - no debería usarse
        raise AssertionError("no debería caer al camino de texto")


class FakeTextLLM:
    """LLM sin structured output: devuelve el JSON como texto."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        self.prompts.append(messages[0].content)
        text = self._responses.pop(0) if self._responses else self._responses_last()
        return _message(text)

    def _responses_last(self) -> str:
        return "{}"


class FakeStructuredFailsLLM(FakeTextLLM):
    """``with_structured_output`` existe pero explota → cae a texto."""

    def with_structured_output(self, schema, include_raw=False):
        raise RuntimeError("schema no soportado por el proveedor")


class FakeConcurrencyLLM:
    """Mide cuántas llamadas hay en vuelo a la vez."""

    def __init__(self):
        self.in_flight = 0
        self.max_in_flight = 0

    async def ainvoke(self, messages):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return _message(json.dumps(VALID_PAYLOAD))


# ---------------------------------------------------------------------------
# Camino feliz: structured output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_v3_uses_structured_output_when_available():
    llm = FakeStructuredLLM()
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    assert llm.structured_calls == 1
    result = results[4]
    assert isinstance(result.insight, InsightV3)
    assert result.insight.trend == "declining"
    assert result.metrics.prompt_version == PROMPT_VERSION_ANALYST_V3
    assert result.metrics.tokens_in == 900
    assert result.metrics.tokens_out == 300


@pytest.mark.asyncio
async def test_invoke_v3_falls_back_to_plain_structured_binding():
    """Si el proveedor no acepta ``include_raw`` se usa el binding simple."""
    llm = FakeStructuredLLM(supports_include_raw=False)
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    assert isinstance(results[4].insight, InsightV3)
    # Sin ``raw`` no hay usage_metadata: los tokens se estiman por caracteres.
    assert results[4].metrics.tokens_in > 0


# ---------------------------------------------------------------------------
# Camino de texto + reparación
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_v3_parses_json_from_text_when_no_structured_output():
    llm = FakeTextLLM([f"```json\n{json.dumps(VALID_PAYLOAD)}\n```"])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    assert results[4].insight.headline.startswith("Perdió 2 puestos")
    assert len(llm.prompts) == 1


@pytest.mark.asyncio
async def test_invoke_v3_repairs_invalid_json_once():
    llm = FakeTextLLM(["no soy JSON, soy prosa", json.dumps(VALID_PAYLOAD)])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    assert len(llm.prompts) == 2
    assert "Corrección obligatoria" in llm.prompts[1]
    assert isinstance(results[4].insight, InsightV3)
    # Las métricas suman ambos intentos.
    assert results[4].metrics.tokens_in == 1800


@pytest.mark.asyncio
async def test_invoke_v3_repairs_schema_violations_too():
    """JSON bien formado pero con 1 sola observación → reintento de reparación."""
    broken = {**VALID_PAYLOAD, "observations": VALID_PAYLOAD["observations"][:1]}
    llm = FakeTextLLM([json.dumps(broken), json.dumps(VALID_PAYLOAD)])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    assert len(results[4].insight.observations) == 2


@pytest.mark.asyncio
async def test_invoke_v3_falls_back_when_repair_also_fails():
    llm = FakeTextLLM(["prosa", "sigo sin devolver JSON"])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    insight = results[4].insight
    assert insight.headline == "Análisis no disponible"
    assert is_fallback_output(insight) is True
    assert results[4].metrics.tokens_in == 0


@pytest.mark.asyncio
async def test_invoke_v3_uses_text_path_when_structured_binding_raises():
    llm = FakeStructuredFailsLLM([json.dumps(VALID_PAYLOAD)])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    assert isinstance(results[4].insight, InsightV3)


@pytest.mark.asyncio
async def test_one_failing_valida_does_not_break_the_others():
    class _MixedLLM:
        async def ainvoke(self, messages):
            if "Válida 4" in messages[0].content:
                return _message("prosa sin JSON")
            return _message(json.dumps(VALID_PAYLOAD))

    agent = RaceAnalystAgent(llm=_MixedLLM(), prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3(
        [
            make_input(valida_num=4),
            make_input(valida_num=5, field_metrics={**FIELD_METRICS, "valida_num": 5}),
        ]
    )

    assert is_fallback_output(results[4].insight) is True
    assert is_fallback_output(results[5].insight) is False


# ---------------------------------------------------------------------------
# Concurrencia, grounding, temporada, scrubbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_v3_caps_concurrency_at_two():
    llm = FakeConcurrencyLLM()
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    inputs = [
        make_input(valida_num=n, field_metrics={**FIELD_METRICS, "valida_num": n})
        for n in (1, 2, 3, 4)
    ]
    results = await agent.invoke_v3(inputs)

    assert len(results) == 4
    assert llm.max_in_flight <= 2


@pytest.mark.asyncio
async def test_grounding_numbers_come_from_the_rendered_prompt():
    llm = FakeStructuredLLM()
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3([make_input()])

    grounding = set(results[4].grounding_numbers)
    assert "58.3" in grounding  # percentil del bloque de pelotón
    assert "9.4" in grounding  # gap_pct
    assert "0:03:12" in grounding  # gap a P3 formateado
    assert "1234.5" not in grounding


@pytest.mark.asyncio
async def test_season_kind_uses_the_season_prompt():
    llm = FakeTextLLM([json.dumps({**VALID_PAYLOAD, "field_reading": None})])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_SEASON_SUMMARY_V3)

    results = await agent.invoke_v3(
        [AnalystV3Input(valida_num=0, analysis_kind="season", season=2026)]
    )

    assert results[0].metrics.prompt_version == PROMPT_VERSION_SEASON_SUMMARY_V3
    assert "cierre de la temporada" in llm.prompts[0]


def test_v3_prompt_version_maps_the_analysis_kind():
    assert v3_prompt_version("season") == PROMPT_VERSION_SEASON_SUMMARY_V3
    assert v3_prompt_version("valida") == PROMPT_VERSION_ANALYST_V3
    assert v3_prompt_version(None) == PROMPT_VERSION_ANALYST_V3


@pytest.mark.asyncio
async def test_forbidden_names_never_reach_the_prompt():
    llm = FakeTextLLM([json.dumps(VALID_PAYLOAD)])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    await agent.invoke_v3([make_input()], forbidden_names=["Nombre Ficticio"])

    assert "Nombre Ficticio" not in llm.prompts[0]


@pytest.mark.asyncio
async def test_real_names_in_the_output_are_scrubbed():
    leaked = {
        **VALID_PAYLOAD,
        "headline": "Nombre Ficticio perdió 2 puestos frente a lo esperado",
    }
    llm = FakeTextLLM([json.dumps(leaked)])
    agent = RaceAnalystAgent(llm=llm, prompt_version=PROMPT_VERSION_ANALYST_V3)

    results = await agent.invoke_v3(
        [make_input(athlete_ref="el deportista")], forbidden_names=["Nombre Ficticio"]
    )

    assert "Nombre Ficticio" not in results[4].insight.headline
    assert results[4].insight.headline.startswith("el deportista")


def test_scrub_insight_v3_is_a_noop_without_forbidden_names():
    insight = InsightV3.model_validate(VALID_PAYLOAD)
    assert scrub_insight_v3(insight, [], "la deportista") is insight


def test_scrub_insight_v3_cleans_every_text_field():
    payload = {
        **VALID_PAYLOAD,
        "coach_question": "¿Nombre Ficticio durmió bien?",
        "watch_signals": ["Vigilar a Nombre Ficticio la próxima semana"],
        "data_gaps": ["Falta la antropometría de Nombre Ficticio"],
    }
    insight = InsightV3.model_validate(payload)

    cleaned = scrub_insight_v3(insight, ["Nombre Ficticio"], "la deportista")

    dumped = json.dumps(cleaned.model_dump(), ensure_ascii=False)
    assert "Nombre Ficticio" not in dumped


# ---------------------------------------------------------------------------
# Parseo tolerante
# ---------------------------------------------------------------------------


def test_parse_insight_v3_tolerates_prose_around_the_object():
    text = "Claro, acá va:\n" + json.dumps(VALID_PAYLOAD) + "\nEspero que sirva."
    assert isinstance(parse_insight_v3(text), InsightV3)


def test_parse_insight_v3_rejects_text_without_json():
    with pytest.raises(ValueError):
        parse_insight_v3("no hay ningún objeto acá")


def test_grounding_source_text_excludes_few_shot_example():
    """Las cifras del ejemplo resuelto no cuentan como evidencia (feature 037)."""
    from app.services.race.agents.analyst import grounding_source_text
    from app.services.race.insight_v3 import extract_numeric_tokens

    prompt = (
        "## Resultado de la carrera\n- Posición: 5 de 7\n- gap 8.6%\n\n"
        "# Ejemplo resuelto (datos ficticios — NO son de esta carrera)\n"
        "percentil 58.3, gap 0:03:12, 9.4%\n"
    )
    tokens = extract_numeric_tokens(grounding_source_text(prompt))
    assert "58.3" not in tokens
    assert "9.4" not in tokens
    assert any(tok in tokens for tok in ("8.6", "8,6"))


def test_grounding_source_text_without_example_returns_prompt():
    from app.services.race.agents.analyst import grounding_source_text

    assert grounding_source_text("sin ejemplo 12.5") == "sin ejemplo 12.5"
