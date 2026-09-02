"""Chat scoped a atleta (feature 037, T203).

Cuando el coach abre el chat desde el PERFIL de un atleta (``athlete_id``
sin ``race_event_id``), las tools quedan horneadas a ese atleta — sus
firmas no piden ``athlete_id`` — y se suma
``obtener_contexto_entrenamiento(desde, hasta)``, que devuelve SOLO los
agregados de :func:`app.services.race.ai.athlete_context.load_training_window`
(nunca texto libre sin resumir).

Cubre:
- ``_default_tools(scope_athlete_id=...)`` sin ``race_event_id``: firmas de
  ``obtener_insights_atleta``/``fetch_results`` no piden ``athlete_id``.
- ``obtener_contexto_entrenamiento`` registrada solo con scope de atleta.
- El scope de evento (``race_event_id``) tiene prioridad sobre el de atleta.
- Turn completo: la tool devuelve agregados (JSON), nunca listas de sesiones
  individuales sin resumir ni texto libre.
- ``RaceChatAgent.chat(athlete_id=..., race_event_id=None)`` selecciona las
  tools scoped automáticamente.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.race.agents.chat import RaceChatAgent, _SessionStore
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage


def _schema(tool: Any) -> dict:
    args_schema = tool.args_schema
    if hasattr(args_schema, "model_json_schema"):
        return args_schema.model_json_schema()
    return args_schema.schema()


def _by_name(tools: list[Any]) -> dict[str, Any]:
    return {t.name: t for t in tools}


# ---------------------------------------------------------------------------
# Firmas de tools scoped a atleta
# ---------------------------------------------------------------------------


def test_athlete_scoped_tools_do_not_require_athlete_id():
    tools = _by_name(RaceChatAgent._default_tools(None, scope_athlete_id=144))

    insights_schema = _schema(tools["obtener_insights_atleta"])
    assert "athlete_id" not in insights_schema.get("properties", {})

    fetch_schema = _schema(tools["fetch_results"])
    assert "athlete_id" not in fetch_schema.get("properties", {})
    assert fetch_schema.get("required", []) == ["season"]


def test_athlete_scoped_tools_include_training_context_tool():
    tools = _by_name(RaceChatAgent._default_tools(None, scope_athlete_id=144))
    assert "obtener_contexto_entrenamiento" in tools
    schema = _schema(tools["obtener_contexto_entrenamiento"])
    assert set(schema.get("required", [])) == {"desde", "hasta"}


def test_unscoped_tools_have_no_training_context_tool_and_require_athlete_id():
    tools = _by_name(RaceChatAgent._default_tools(None))
    assert "obtener_contexto_entrenamiento" not in tools
    insights_schema = _schema(tools["obtener_insights_atleta"])
    assert "athlete_id" in insights_schema.get("required", [])


def test_event_scope_takes_priority_over_athlete_scope():
    """Un chat con AMBOS athlete_id y race_event_id sigue restringido al
    evento (comportamiento previo, feature 010) — el scope de atleta no
    debe filtrarse ni registrar `obtener_contexto_entrenamiento`."""
    tools = _by_name(
        RaceChatAgent._default_tools(
            None,
            scope_season=2026,
            scope_valida_num=3,
            race_event_id=6,
            scope_athlete_id=144,
        )
    )
    assert "obtener_contexto_entrenamiento" not in tools
    fetch_schema = _schema(tools["fetch_results"])
    assert fetch_schema.get("required", []) == ["athlete_id"]


# ---------------------------------------------------------------------------
# Turn completo — la tool devuelve solo agregados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_athlete_scope_calls_training_context_tool_and_returns_aggregates(
    monkeypatch,
):
    from app.services.race.agents import chat as chat_mod

    captured_call: dict[str, Any] = {}

    async def _fake_load_training_window(db, athlete_id, club_id, date_from, date_to):
        captured_call["athlete_id"] = athlete_id
        captured_call["club_id"] = club_id
        captured_call["date_from"] = date_from
        captured_call["date_to"] = date_to
        return {
            "window_days": 28,
            "attendance_pct": 85.0,
            "rpe_mean": 6.2,
            "rubric_effort_mean": 4.0,
            "rubric_attitude_mean": 4.5,
            "rubric_technique_mean": 3.8,
            "technical_foci": ["frenado", "curvas"],
            "coach_feedback": ["Buena progresión en curvas."],
        }

    monkeypatch.setattr(
        chat_mod, "load_training_window", _fake_load_training_window
    )

    class _AthleteRow:
        def scalar_one_or_none(self):
            return 7  # club_id

    class _DB:
        async def execute(self, *args, **kwargs):
            return _AthleteRow()

        async def close(self):
            pass

    def db_factory():
        return _DB()

    responses = [
        StubAIMessage(
            content="",
            tool_calls=[
                {
                    "name": "obtener_contexto_entrenamiento",
                    "args": {"desde": "2026-05-01", "hasta": "2026-05-28"},
                    "id": "call_1",
                }
            ],
        ),
        StubAIMessage(content="Asistencia del 85% en las últimas 4 semanas."),
    ]
    llm = FakeChatLLM(responses)

    agent = RaceChatAgent(
        llm=llm,
        db_factory=db_factory,
        session_store=_SessionStore(),
    )

    response = await agent.chat(
        session_id="s1",
        query="¿cómo viene entrenando?",
        athlete_id=144,
        race_event_id=None,
    )

    assert "obtener_contexto_entrenamiento" in response.tools_called
    assert captured_call["athlete_id"] == 144
    assert captured_call["club_id"] == 7

    # La tool devolvió JSON de agregados — nunca texto libre de sesiones.
    tool_message = next(
        m for m in llm.calls[-1] if getattr(m, "tool_call_id", None) == "call_1"
    )
    payload = json.loads(tool_message.content)
    assert payload["attendance_pct"] == 85.0
    assert "coach_feedback" in payload  # agregado (lista truncada), no texto crudo
    assert "session_id" not in payload
    assert response.answer == "Asistencia del 85% en las últimas 4 semanas."


@pytest.mark.asyncio
async def test_chat_athlete_scope_no_training_data_returns_placeholder(monkeypatch):
    from app.services.race.agents import chat as chat_mod

    async def _fake_load_training_window_none(db, athlete_id, club_id, date_from, date_to):
        return None

    monkeypatch.setattr(
        chat_mod, "load_training_window", _fake_load_training_window_none
    )

    class _AthleteRow:
        def scalar_one_or_none(self):
            return 7

    class _DB:
        async def execute(self, *args, **kwargs):
            return _AthleteRow()

        async def close(self):
            pass

    def db_factory():
        return _DB()

    responses = [
        StubAIMessage(
            content="",
            tool_calls=[
                {
                    "name": "obtener_contexto_entrenamiento",
                    "args": {"desde": "2026-01-01", "hasta": "2026-01-28"},
                    "id": "call_1",
                }
            ],
        ),
        StubAIMessage(content="No hay datos de entrenamiento en ese rango."),
    ]
    llm = FakeChatLLM(responses)
    agent = RaceChatAgent(
        llm=llm, db_factory=db_factory, session_store=_SessionStore()
    )

    response = await agent.chat(
        session_id="s2", query="¿entrenó en enero?", athlete_id=144, race_event_id=None
    )

    tool_message = next(
        m for m in llm.calls[-1] if getattr(m, "tool_call_id", None) == "call_1"
    )
    assert tool_message.content == "(sin datos de entrenamiento en ese rango)"
    assert response.answer == "No hay datos de entrenamiento en ese rango."
