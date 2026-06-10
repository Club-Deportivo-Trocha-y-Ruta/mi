"""Regresión del chat scoped a evento (fix «¿a qué válida te refieres?»).

Causa raíz diagnosticada: el prompt decía «las tools ya están restringidas
a esta válida», pero los schemas de las tools seguían marcando ``season`` /
``valida_num`` como REQUIRED — para el LLM un parámetro required pesa más
que una frase del prompt, así que pedía al coach la válida/temporada que la
UI ya conocía. Además no existía ninguna tool grupal: toda pregunta tipo
«¿cómo estuvieron los muchachos?» carecía de camino válido.

Cubre:
- Firmas de tools scoped NO exponen ``season`` ni ``valida_num``.
- Tool grupal ``obtener_resultados_evento`` registrada solo con evento activo.
- Prompt scoped contiene la regla dura «NUNCA preguntes» + guía grupal.
- Formato del tool grupal: pseudónimos, sin nombres reales.
- Turn completo: pregunta grupal se responde vía tool grupal sin pedir válida.
- ``_SessionStore`` preserva el SystemMessage al truncar.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.race.agents.chat import (
    MAX_TURNS_PER_SESSION,
    RaceChatAgent,
    _build_obtener_resultados_evento_tool,
    _SessionStore,
)
from app.services.race.ai.anonymizer import make_pseudonym
from app.services.race.prompts import render_prompt
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage

EVENT_LABEL = "Válida CD 2026 — Ginebra — 12/06/2026"


def _schema(tool: Any) -> dict:
    args_schema = tool.args_schema
    if hasattr(args_schema, "model_json_schema"):
        return args_schema.model_json_schema()
    return args_schema.schema()


def _by_name(tools: list[Any]) -> dict[str, Any]:
    return {t.name: t for t in tools}


# ---------------------------------------------------------------------------
# Firmas de tools (el fix central: schema y prompt no pueden contradecirse)
# ---------------------------------------------------------------------------


def test_scoped_tools_do_not_require_season_nor_valida():
    tools = _by_name(
        RaceChatAgent._default_tools(
            None, scope_season=2026, scope_valida_num=99, race_event_id=6
        )
    )

    fetch_schema = _schema(tools["fetch_results"])
    assert fetch_schema.get("required", []) == ["athlete_id"]
    assert "season" not in fetch_schema.get("properties", {})

    cond_schema = _schema(tools["obtener_condiciones_evento"])
    assert cond_schema.get("required", []) == []
    assert "valida_num" not in cond_schema.get("properties", {})
    assert "season" not in cond_schema.get("properties", {})


def test_scoped_tools_include_group_results_tool():
    tools = _by_name(
        RaceChatAgent._default_tools(
            None, scope_season=2026, scope_valida_num=99, race_event_id=6
        )
    )
    assert "obtener_resultados_evento" in tools
    assert _schema(tools["obtener_resultados_evento"]).get("properties", {}) == {}


def test_unscoped_tools_keep_explicit_params_and_no_group_tool():
    tools = _by_name(RaceChatAgent._default_tools(None))

    fetch_schema = _schema(tools["fetch_results"])
    assert set(fetch_schema.get("required", [])) == {"athlete_id", "season"}

    cond_schema = _schema(tools["obtener_condiciones_evento"])
    assert set(cond_schema.get("required", [])) == {"valida_num", "season"}

    assert "obtener_resultados_evento" not in tools


# ---------------------------------------------------------------------------
# Prompt scoped
# ---------------------------------------------------------------------------


def test_prompt_scoped_has_never_ask_rule_and_group_guidance():
    out = render_prompt("race_chat_v1", {"event_label": EVENT_LABEL}, strict=False)
    assert EVENT_LABEL in out
    assert "NUNCA preguntes" in out
    assert "obtener_resultados_evento" in out
    assert "los muchachos" in out
    # Firmas scoped en la lista de tools — sin season/valida_num.
    assert "fetch_results(athlete_id)" in out
    assert "obtener_condiciones_evento()" in out


def test_prompt_unscoped_keeps_legacy_signatures_and_no_event_rules():
    out = render_prompt("race_chat_v1", {}, strict=False)
    assert "NUNCA preguntes" not in out
    assert "obtener_resultados_evento" not in out
    assert "fetch_results(athlete_id, season)" in out
    assert "obtener_condiciones_evento(valida_num, season)" in out
    # Grounding (feature 011) intacto.
    assert "no quedó registrado" in out
    assert "PROHIBIDO" in out


# ---------------------------------------------------------------------------
# Tool grupal — formato y privacidad
# ---------------------------------------------------------------------------


class _FakeRow:
    """Emula la fila (RaceResult, RaceCategory) del JOIN."""

    def __init__(self, rr: Any, cat: Any):
        self._items = (rr, cat)

    def __getitem__(self, idx: int) -> Any:
        return self._items[idx]


class _FakeResult:
    def __init__(self, rows: list[_FakeRow]):
        self._rows = rows

    def all(self) -> list[_FakeRow]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[_FakeRow]):
        self._rows = rows

    async def execute(self, stmt: Any) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeRaceResult:
    def __init__(
        self,
        athlete_id: int,
        status: str = "finished",
        position: int | None = None,
        race_time_ms: int | None = None,
        laps_behind: int | None = None,
    ):
        self.athlete_id = athlete_id
        self.status = status
        self.position = position
        self.race_time_ms = race_time_ms
        self.laps_behind = laps_behind


class _FakeCategory:
    def __init__(self, code: str):
        self.code = code


async def test_obtener_resultados_evento_formats_pseudonyms_only():
    rows = [
        _FakeRow(
            _FakeRaceResult(athlete_id=42, position=5, race_time_ms=1_800_000),
            _FakeCategory("INF_B"),
        ),
        _FakeRow(_FakeRaceResult(athlete_id=43, status="dnf"), _FakeCategory("INF_B")),
    ]
    tool = _build_obtener_resultados_evento_tool(
        db_factory=lambda: _FakeSession(rows), race_event_id=6
    )
    out = await tool.ainvoke({})

    assert make_pseudonym(42) in out
    assert "athlete_id=42" in out
    assert "categoría INF_B" in out
    assert "pos=5" in out
    assert "tiempo=0:30:00" in out
    assert "DNF" in out


async def test_obtener_resultados_evento_sin_resultados():
    tool = _build_obtener_resultados_evento_tool(
        db_factory=lambda: _FakeSession([]), race_event_id=6
    )
    out = await tool.ainvoke({})
    assert out == "(sin resultados importados para este evento)"


async def test_obtener_resultados_evento_sin_configurar():
    tool = _build_obtener_resultados_evento_tool(db_factory=None, race_event_id=None)
    out = await tool.ainvoke({})
    assert "no configurado" in out


# ---------------------------------------------------------------------------
# Regresión end-to-end: pregunta grupal en chat scoped
# ---------------------------------------------------------------------------


async def test_scoped_chat_answers_group_question_via_group_tool():
    """«¿Cómo estuvieron los muchachos?» debe resolverse con la tool grupal,

    con el evento ya presente en el system prompt — nunca pidiendo al coach
    el número de válida o la temporada.
    """
    rows = [
        _FakeRow(
            _FakeRaceResult(athlete_id=42, position=5, race_time_ms=1_800_000),
            _FakeCategory("INF_B"),
        ),
    ]
    llm = FakeChatLLM(
        [
            StubAIMessage(
                content="",
                tool_calls=[
                    {"name": "obtener_resultados_evento", "args": {}, "id": "c1"}
                ],
            ),
            StubAIMessage(content="El equipo tuvo una buena válida: top 5 en INF_B."),
        ]
    )
    agent = RaceChatAgent(
        llm=llm,
        db_factory=lambda: _FakeSession(rows),
        session_store=_SessionStore(ttl_seconds=3600),
    )

    resp = await agent.chat(
        session_id="grp",
        query="¿Cómo estuvieron los muchachos?",
        race_event_id=6,
        event_scope=(2026, 99, EVENT_LABEL),
    )

    assert resp.tools_called == ["obtener_resultados_evento"]
    assert "buena válida" in resp.answer

    system_content = str(llm.calls[0][0].content)
    assert EVENT_LABEL in system_content
    assert "NUNCA preguntes" in system_content


# ---------------------------------------------------------------------------
# _SessionStore: el SystemMessage sobrevive al cap de turns
# ---------------------------------------------------------------------------


async def test_session_store_truncation_preserves_system_message():
    store = _SessionStore(ttl_seconds=3600)
    messages: list[Any] = [SystemMessage(content="contexto del evento")]
    messages += [HumanMessage(content=f"turn {i}") for i in range(MAX_TURNS_PER_SESSION + 10)]

    await store.set("s", messages)
    got = await store.get("s")

    assert len(got) == MAX_TURNS_PER_SESSION
    assert isinstance(got[0], SystemMessage)
    assert got[0].content == "contexto del evento"
    assert got[-1].content == f"turn {MAX_TURNS_PER_SESSION + 9}"
