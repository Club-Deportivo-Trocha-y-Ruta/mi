"""``RaceChatAgent`` — agente conversacional con tools (sin HITL).

Implementación intencionalmente **simple** (no usa
``langgraph.prebuilt.create_react_agent`` ni ``AgentExecutor`` de
LangChain) por dos razones:

1. **Testabilidad:** un loop manual ``llm.bind_tools(...)`` → check
   ``tool_calls`` → ejecutar tools → repeat es trivial de mockear con un
   stub LLM que retorna respuestas pre-grabadas.
2. **Sin deps nuevas:** ``langchain.agents`` no está instalado en
   requirements y el workflow §"No hagas" prohíbe agregar.

Sesión in-memory con TTL de 1h (workflow §3.4) — un dict global con
limpieza perezosa en cada ``chat()``. Si crece, escalar a Redis.

Anonimización: para MVP el frontend pasa ``athlete_id`` explícito; el
agente nunca ve nombres reales en la query del coach. (Resolución
fuzzy nombre→id queda fuera de este sprint, workflow §"No hagas".)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.race.agents._llm import build_chat_llm, extract_text, extract_usage
from app.services.race.agents.pricing import (
    PROMPT_VERSION_CHAT,
    compute_cost_usd,
)
from app.services.race.prompts import render_prompt
from app.services.race.queries import fetch_results_for_athlete
from app.services.race.rag.tools import consultar_marco_teorico
from app.services.race.schemas import ChatResponse

logger = logging.getLogger(__name__)

# TTL para sesiones in-memory.
SESSION_TTL_SECONDS = 3600
# Tope de turns por sesión (anti-abuse + anti-context-bloat).
MAX_TURNS_PER_SESSION = 50
# Tope de iteraciones del loop tool-calling (anti-loop infinito si el LLM
# se queda llamando tools indefinidamente).
MAX_TOOL_ITERATIONS = 5

_CITE_RE = re.compile(r"\[(\d+)\]")


# ---------------------------------------------------------------------------
# Tools del chat
# ---------------------------------------------------------------------------


def _build_obtener_insights_atleta_tool(db_factory: Optional[Callable[[], AsyncSession]] = None):
    """Fábrica del tool ``obtener_insights_atleta``.

    Args:
        db_factory: callable que retorna una ``AsyncSession`` (real o
            fake). Si ``None``, el tool falla con mensaje claro — útil
            en MVP que aún no integra con el grafo.
    """
    from langchain_core.tools import tool

    @tool("obtener_insights_atleta")
    async def obtener_insights_atleta(athlete_id: int, n: int = 5) -> str:
        """Recupera los últimos N insights aprobados de un atleta.

        Devuelve un string con los resúmenes formateados o
        ``"(sin insights persistidos para este atleta)"``.

        Args:
            athlete_id: PK del atleta en la tabla ``athletes``.
            n: número máximo de insights (default 5, max 10).
        """
        if db_factory is None:
            return "(tool no configurado: db_factory faltante)"
        n = max(1, min(int(n), 10))
        db = db_factory()
        try:
            # Query plana — el modelo AthleteAIInsight aún no existe (sprint
            # F3 solo persiste schema vía migración); usamos SQL crudo.
            result = await db.execute(
                text(
                    """
                    SELECT id, season, valida_num, use_case, summary_text,
                           confidence, generated_at
                    FROM athlete_ai_insights
                    WHERE athlete_id = :aid
                      AND coach_approved = 1
                      AND archived_at IS NULL
                    ORDER BY season DESC, valida_num DESC, generated_at DESC
                    LIMIT :n
                    """
                ),
                {"aid": athlete_id, "n": n},
            )
            rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
        except Exception as exc:  # pragma: no cover - defensa runtime
            logger.warning("Error consultando insights: %s", exc)
            return f"(error consultando insights: {type(exc).__name__})"

        if not rows:
            return "(sin insights persistidos para este atleta)"

        out: list[str] = []
        for r in rows:
            valida = getattr(r, "valida_num", None)
            valida_str = f"Válida {valida}" if valida else "(sin válida)"
            season = getattr(r, "season", "?")
            use_case = getattr(r, "use_case", "")
            summary = (getattr(r, "summary_text", "") or "")[:300]
            confidence = getattr(r, "confidence", "")
            out.append(
                f"- {valida_str} {season} [{use_case}, conf={confidence}]: {summary}"
            )
        return "\n".join(out)

    return obtener_insights_atleta


def _build_fetch_results_tool(db_factory: Optional[Callable[[], AsyncSession]] = None):
    """Fábrica del tool ``fetch_results``."""
    from langchain_core.tools import tool

    @tool("fetch_results")
    async def fetch_results(athlete_id: int, season: int) -> str:
        """Recupera los resultados de carrera de un atleta en una temporada.

        Devuelve string formateado con valida_num, posición y tiempo. Si
        no hay datos: ``"(sin resultados)"``.
        """
        if db_factory is None:
            return "(tool no configurado: db_factory faltante)"
        db = db_factory()
        try:
            results = await fetch_results_for_athlete(db, athlete_id, season)
        except Exception as exc:  # pragma: no cover
            logger.warning("Error en fetch_results: %s", exc)
            return f"(error consultando resultados: {type(exc).__name__})"

        if not results:
            return "(sin resultados)"

        out: list[str] = []
        for r in results:
            pos = getattr(r, "position", "—")
            time_ms = getattr(r, "race_time_ms", None)
            time_str = f"{time_ms} ms" if time_ms else "—"
            event_id = getattr(r, "event_id", "?")
            out.append(f"- event_id={event_id}, pos={pos}, race_time={time_str}")
        return "\n".join(out)

    return fetch_results


# ---------------------------------------------------------------------------
# Sesiones in-memory con TTL
# ---------------------------------------------------------------------------


class _SessionStore:
    """Almacén in-memory con TTL perezoso (sin background sweeper).

    Limpieza ocurre en cada ``get_or_create`` y ``set`` — evita threads
    extra y es suficiente para MVP single-process.
    """

    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._sessions: dict[str, tuple[float, list[Any]]] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> list[Any]:
        """Retorna los messages de la sesión (lista nueva si expiró/no existe)."""
        async with self._lock:
            self._sweep_locked()
            entry = self._sessions.get(session_id)
            if entry is None:
                return []
            return list(entry[1])

    async def set(self, session_id: str, messages: list[Any]) -> None:
        async with self._lock:
            self._sweep_locked()
            # Cap por sesión.
            self._sessions[session_id] = (time.monotonic(), messages[-MAX_TURNS_PER_SESSION:])

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    def _sweep_locked(self) -> None:
        now = time.monotonic()
        expired = [
            sid for sid, (last, _msgs) in self._sessions.items() if now - last > self._ttl
        ]
        for sid in expired:
            self._sessions.pop(sid, None)


# Singleton compartido por defecto. Tests crean uno propio.
_DEFAULT_STORE = _SessionStore()


# ---------------------------------------------------------------------------
# RaceChatAgent
# ---------------------------------------------------------------------------


class RaceChatAgent:
    """Agente chat con tools y memoria por ``session_id``.

    Args:
        llm: chat model con métodos ``bind_tools`` + ``ainvoke``. Si
            ``None``, se construye lazy en :meth:`chat`.
        tools: lista de tools LangChain. Si ``None``, se arma el set
            default (consultar_marco_teorico, obtener_insights_atleta,
            fetch_results) — los dos últimos requieren ``db_factory``.
        db_factory: callable que produce ``AsyncSession`` para los tools
            que consultan MySQL. En tests se pasa un fake o ``None``.
        session_store: override del store in-memory (tests).
    """

    def __init__(
        self,
        llm: Any | None = None,
        tools: Optional[list[Any]] = None,
        db_factory: Optional[Callable[[], AsyncSession]] = None,
        session_store: Optional[_SessionStore] = None,
    ) -> None:
        self._llm = llm
        self._tools = tools if tools is not None else self._default_tools(db_factory)
        self._tools_by_name = {t.name: t for t in self._tools}
        self._store = session_store or _DEFAULT_STORE
        self._prompt_version = PROMPT_VERSION_CHAT

    @staticmethod
    def _default_tools(db_factory: Optional[Callable[[], AsyncSession]]) -> list[Any]:
        return [
            consultar_marco_teorico,
            _build_obtener_insights_atleta_tool(db_factory),
            _build_fetch_results_tool(db_factory),
        ]

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def chat(
        self,
        session_id: str,
        query: str,
        athlete_id: Optional[int] = None,
    ) -> ChatResponse:
        """Procesa un turn conversacional.

        Args:
            session_id: id estable proporcionado por el frontend.
            query: pregunta del coach.
            athlete_id: si se provee, se inyecta al system prompt como
                contexto activo (no se filtra automáticamente a los
                tools — el LLM decide cuándo usarlo).
        """
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        llm = self._llm or build_chat_llm()

        # Bind tools si el LLM soporta — en tests con FakeLLM, asumimos
        # que ya viene bindeado o no necesita.
        bound_llm = llm.bind_tools(self._tools) if hasattr(llm, "bind_tools") else llm

        history = await self._store.get(session_id)
        if not history:
            system_prompt = render_prompt(
                "race_chat_v1",
                {"athlete_id": athlete_id} if athlete_id else {},
                strict=False,
            )
            history = [SystemMessage(content=system_prompt)]

        history.append(HumanMessage(content=query))

        tools_called: list[str] = []
        citations: list[str] = []
        final_text = ""

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await bound_llm.ainvoke(history)
            history.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                final_text = extract_text(response)
                break

            for tc in tool_calls:
                # tc puede ser dict (LangChain >=0.2) o un objeto.
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                call_id = (
                    tc.get("id")
                    if isinstance(tc, dict)
                    else getattr(tc, "id", None) or "call_0"
                )
                if not name or name not in self._tools_by_name:
                    tool_output = f"(tool desconocida: {name})"
                else:
                    tools_called.append(name)
                    try:
                        tool = self._tools_by_name[name]
                        result = await tool.ainvoke(args or {})
                        tool_output = str(result)
                        if name == "consultar_marco_teorico":
                            for m in _CITE_RE.finditer(tool_output):
                                pass  # citations se computan al final desde final_text
                    except Exception as exc:
                        logger.warning("Tool '%s' falló: %s", name, exc)
                        tool_output = f"(error ejecutando {name}: {type(exc).__name__})"
                history.append(ToolMessage(content=tool_output, tool_call_id=call_id))
        else:
            # No alcanzamos sin tool_calls — usamos el último AIMessage como fallback.
            last_ai = next(
                (m for m in reversed(history) if isinstance(m, AIMessage)),
                None,
            )
            final_text = extract_text(last_ai) if last_ai else "(sin respuesta del modelo)"

        # Recolectar citas referenciadas en el output final.
        if final_text:
            for m in _CITE_RE.finditer(final_text):
                cid = m.group(1)
                if cid not in citations:
                    citations.append(cid)

        await self._store.set(session_id, history)

        return ChatResponse(
            answer=final_text or "(sin respuesta)",
            citations_used=citations,
            tools_called=tools_called,
        )

    async def reset(self, session_id: str) -> None:
        """Limpia la sesión (útil para tests + futuro endpoint /chat/reset)."""
        await self._store.clear(session_id)
