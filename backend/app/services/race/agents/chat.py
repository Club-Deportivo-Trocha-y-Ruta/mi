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
import inspect
import logging
import re
import time
from typing import Any, Callable, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.race.agents._llm import build_chat_llm, extract_text
from app.services.race.agents.pricing import PROMPT_VERSION_CHAT
from app.services.race.ai.athlete_context import load_training_window
from app.services.race.prompts import render_prompt
from app.services.race.queries import (
    fetch_event_conditions,
    fetch_results_for_athlete,
)
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


async def _safe_close(db: Any) -> None:
    """Cierra la sesión devolviéndola al pool, tras usar el tool.

    CRÍTICO con un pool real (no NullPool): cada tool abre ``db_factory()``;
    si no se cierra, la conexión queda checked-out hasta el GC y agota el pool
    (``pool_size + max_overflow``), provocando timeouts. Tolerante a los fakes
    de test (``object()``, ``_FakeSession``) que no implementan ``close()``.
    """
    close = getattr(db, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:  # pragma: no cover - cleanup defensivo
        logger.debug("Error cerrando sesión del chat tool: %s", exc)


# ---------------------------------------------------------------------------
# Tools del chat
# ---------------------------------------------------------------------------


def _build_obtener_insights_atleta_tool(
    db_factory: Optional[Callable[[], AsyncSession]] = None,
    *,
    scope_season: Optional[int] = None,
    scope_valida_num: Optional[int] = None,
    scope_athlete_id: Optional[int] = None,
):
    """Fábrica del tool ``obtener_insights_atleta``.

    Args:
        db_factory: callable que retorna una ``AsyncSession`` (real o
            fake). Si ``None``, el tool falla con mensaje claro — útil
            en MVP que aún no integra con el grafo.
        scope_season: cuando se provee junto a ``scope_valida_num``, el
            tool filtra insights restringidos a esa (season, valida_num).
            Permite que el LLM no tenga que conocer el contexto de evento.
        scope_valida_num: ver ``scope_season``.
        scope_athlete_id: cuando se provee (chat con scope de atleta,
            feature 037 T203), la firma del tool NO pide ``athlete_id`` — el
            LLM no puede consultar a otro atleta desde este chat.
    """
    from langchain_core.tools import tool

    async def _run(athlete_id: int, n: int) -> str:
        if db_factory is None:
            return "(tool no configurado: db_factory faltante)"
        n = max(1, min(int(n), 10))
        db = db_factory()
        try:
            # Build query with optional event scope filter.
            if scope_season is not None and scope_valida_num is not None:
                # Constrained to a specific (season, valida_num) — the
                # comparative context includes the same season broadly.
                query_sql = text(
                    """
                    SELECT id, season, valida_num, use_case, summary_text,
                           confidence, generated_at
                    FROM athlete_ai_insights
                    WHERE athlete_id = :aid
                      AND coach_approved = 1
                      AND archived_at IS NULL
                      AND season = :season
                      AND valida_num = :valida_num
                    ORDER BY generated_at DESC
                    LIMIT :n
                    """
                )
                bind_params: dict[str, Any] = {
                    "aid": athlete_id,
                    "n": n,
                    "season": scope_season,
                    "valida_num": scope_valida_num,
                }
            else:
                query_sql = text(
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
                )
                bind_params = {"aid": athlete_id, "n": n}
            # Query plana — el modelo AthleteAIInsight aún no existe (sprint
            # F3 solo persiste schema vía migración); usamos SQL crudo.
            result = await db.execute(query_sql, bind_params)
            rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
        except Exception as exc:  # pragma: no cover - defensa runtime
            logger.warning("Error consultando insights: %s", exc)
            return f"(error consultando insights: {type(exc).__name__})"
        finally:
            await _safe_close(db)

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

    if scope_athlete_id is not None:

        @tool("obtener_insights_atleta")
        async def obtener_insights_atleta_scoped(n: int = 5) -> str:
            """Recupera los últimos N insights aprobados del atleta activo.

            El atleta ya está fijado por el contexto de este chat — no
            requiere ``athlete_id``. Devuelve un string con los resúmenes
            formateados o ``"(sin insights persistidos para este atleta)"``.

            Args:
                n: número máximo de insights (default 5, max 10).
            """
            return await _run(scope_athlete_id, n)

        return obtener_insights_atleta_scoped

    @tool("obtener_insights_atleta")
    async def obtener_insights_atleta(athlete_id: int, n: int = 5) -> str:
        """Recupera los últimos N insights aprobados de un atleta.

        Devuelve un string con los resúmenes formateados o
        ``"(sin insights persistidos para este atleta)"``.

        Args:
            athlete_id: PK del atleta en la tabla ``athletes``.
            n: número máximo de insights (default 5, max 10).
        """
        return await _run(athlete_id, n)

    return obtener_insights_atleta


def _build_fetch_results_tool(
    db_factory: Optional[Callable[[], AsyncSession]] = None,
    *,
    scope_season: Optional[int] = None,
    scope_valida_num: Optional[int] = None,
    forbidden_names: Optional[list[str]] = None,
    scope_athlete_id: Optional[int] = None,
):
    """Fábrica del tool ``fetch_results``.

    Args:
        db_factory: callable que retorna una ``AsyncSession``.
        scope_season: cuando se provee junto a ``scope_valida_num``, el tool
            scoped NO expone ``season`` en su firma — el schema que ve el LLM
            no puede contradecir al prompt pidiendo parámetros de evento
            (causa raíz del bug "¿a qué válida te refieres?").
        scope_valida_num: ver ``scope_season``.
        forbidden_names: nombres reales a scrubear del coach_note antes de
            exponerlo al LLM (T022 — privacidad menores).
    """
    from langchain_core.tools import tool

    _forbidden: list[str] = forbidden_names or []

    async def _run(athlete_id: int, season: Optional[int]) -> str:
        if db_factory is None:
            return "(tool no configurado: db_factory faltante)"
        db = db_factory()
        try:
            # When scoped to a specific event, override season and filter by
            # valida_num so results are constrained to that válida only.
            effective_season = scope_season if scope_season is not None else season
            effective_validas = [scope_valida_num] if scope_valida_num is not None else None
            results = await fetch_results_for_athlete(
                db,
                athlete_id,
                effective_season,
                valida_nums=effective_validas,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Error en fetch_results: %s", exc)
            return f"(error consultando resultados: {type(exc).__name__})"
        finally:
            await _safe_close(db)

        if not results:
            return "(sin resultados)"

        from app.services.race.agents.analyst import _format_ms_hhmmss

        out: list[str] = []
        for r in results:
            pos = getattr(r, "position", "—")
            time_ms = getattr(r, "race_time_ms", None)
            time_str = _format_ms_hhmmss(time_ms)
            event_id = getattr(r, "event_id", "?")
            # T022 — include scrubbed coach_note when present so chat answers
            # can incorporate it. Raw note is scrubbed before reaching the LLM;
            # when absent, no placeholder is emitted (FR-009).
            raw_note = getattr(r, "coach_note", None)
            if raw_note is not None:
                note_str = _scrub_coach_note_for_chat(raw_note, _forbidden)
                out.append(
                    f"- event_id={event_id}, pos={pos}, race_time={time_str},"
                    f" nota_entrenador={note_str}"
                )
            else:
                out.append(f"- event_id={event_id}, pos={pos}, race_time={time_str}")
        return "\n".join(out)

    if scope_season is not None and scope_valida_num is not None:

        @tool("fetch_results")
        async def fetch_results_scoped(athlete_id: int) -> str:
            """Recupera los resultados de carrera de un atleta en la válida activa.

            El evento ya está fijado por el contexto — no requiere temporada
            ni número de válida. Devuelve string formateado con posición y
            tiempo. Si no hay datos: ``"(sin resultados)"``.
            """
            return await _run(athlete_id, None)

        return fetch_results_scoped

    if scope_athlete_id is not None:

        @tool("fetch_results")
        async def fetch_results_athlete_scoped(season: int) -> str:
            """Recupera los resultados de carrera del atleta activo en una temporada.

            El atleta ya está fijado por el contexto de este chat — no
            requiere ``athlete_id``. Devuelve string formateado con
            valida_num, posición y tiempo. Si no hay datos: ``"(sin
            resultados)"``.
            """
            return await _run(scope_athlete_id, season)

        return fetch_results_athlete_scoped

    @tool("fetch_results")
    async def fetch_results(athlete_id: int, season: int) -> str:
        """Recupera los resultados de carrera de un atleta en una temporada.

        Devuelve string formateado con valida_num, posición y tiempo. Si
        no hay datos: ``"(sin resultados)"``.
        """
        return await _run(athlete_id, season)

    return fetch_results


def _build_obtener_condiciones_evento_tool(
    db_factory: Optional[Callable[[], AsyncSession]] = None,
    *,
    scope_season: Optional[int] = None,
    scope_valida_num: Optional[int] = None,
    forbidden_names: Optional[list[str]] = None,
):
    """Fábrica del tool ``obtener_condiciones_evento`` (feature 011).

    Devuelve las condiciones REGISTRADAS de una válida o ``{"registro": false}``
    cuando no hay registro (o todos los campos son NULL). El chat debe responder
    solo desde este resultado y decir "no quedó registrado" cuando es false.

    Args:
        db_factory: callable que retorna una ``AsyncSession``.
        scope_season / scope_valida_num: cuando se proveen, ignoran los args del
            LLM y restringen al evento activo (mismo patrón que las otras tools).
    """
    import json

    from langchain_core.tools import tool

    async def _run(valida_num: Optional[int], season: Optional[int]) -> str:
        if db_factory is None:
            return '{"registro": false, "error": "tool no configurado"}'
        effective_season = scope_season if scope_season is not None else season
        effective_valida = (
            scope_valida_num if scope_valida_num is not None else valida_num
        )
        db = db_factory()
        try:
            conds = await fetch_event_conditions(
                db, effective_season, [int(effective_valida)]
            )
        except Exception as exc:  # pragma: no cover - defensa runtime
            logger.warning("Error en obtener_condiciones_evento: %s", exc)
            return f'{{"registro": false, "error": "{type(exc).__name__}"}}'
        finally:
            await _safe_close(db)

        entry = conds.get(int(effective_valida))
        if not entry or all(v is None for v in entry.values()):
            return '{"registro": false}'
        entry = _scrub_weather_notes(entry, forbidden_names or [])
        payload = {"registro": True}
        payload.update({k: v for k, v in entry.items() if v is not None})
        return json.dumps(payload, ensure_ascii=False)

    if scope_season is not None and scope_valida_num is not None:

        @tool("obtener_condiciones_evento")
        async def obtener_condiciones_evento_scoped() -> str:
            """Recupera las condiciones registradas de la válida activa.

            El evento ya está fijado por el contexto — no requiere parámetros.
            Devuelve un JSON con las condiciones realmente registradas (clima,
            temperatura, superficie de pista, altitud, notas), o ``{"registro":
            false}`` si el evento no tiene condiciones registradas. NUNCA
            inventes condiciones: si ``registro`` es false, responde que no
            quedó registrado.
            """
            return await _run(None, None)

        return obtener_condiciones_evento_scoped

    @tool("obtener_condiciones_evento")
    async def obtener_condiciones_evento(valida_num: int, season: int) -> str:
        """Recupera las condiciones registradas de una válida.

        Devuelve un JSON con las condiciones realmente registradas (clima,
        temperatura, superficie de pista, altitud, notas), o ``{"registro":
        false}`` si el evento no tiene condiciones registradas. NUNCA inventes
        condiciones: si ``registro`` es false, responde que no quedó registrado.

        Args:
            valida_num: número de válida (1..7, 99=CD).
            season: año de temporada.
        """
        return await _run(valida_num, season)

    return obtener_condiciones_evento


def _build_obtener_contexto_entrenamiento_tool(
    db_factory: Optional[Callable[[], AsyncSession]] = None,
    *,
    scope_athlete_id: int,
):
    """Fábrica del tool ``obtener_contexto_entrenamiento`` (chat scoped a atleta, feature 037 T203).

    Solo se registra cuando el chat está scoped a un atleta (``athlete_id``
    sin ``race_event_id`` — ver :meth:`RaceChatAgent.chat`). Devuelve los
    agregados de la ventana de entrenamiento (:func:`load_training_window`)
    entre ``desde``/``hasta`` — asistencia %, RPE medio, medias de rúbrica,
    focos técnicos, feedback del entrenador ya truncado. NUNCA texto libre
    sin agregar: mismo contrato que ``TrainingWindow`` (data-model.md
    §TrainingWindow), solo agregados — nunca coach_feedback ilimitado.
    """
    import json as _json

    from langchain_core.tools import tool
    from sqlalchemy import select as sa_select

    from app.models.athlete import Athlete as _AthleteModel

    @tool("obtener_contexto_entrenamiento")
    async def obtener_contexto_entrenamiento(desde: str, hasta: str) -> str:
        """Recupera los agregados de entrenamiento del atleta activo en un rango de fechas.

        Úsala cuando el coach pregunte por asistencia, RPE, rúbricas de
        esfuerzo/actitud/técnica, foco técnico trabajado o carga de
        entrenamiento reciente del atleta activo. Devuelve un JSON con
        SOLO agregados (nunca texto libre de sesiones individuales sin
        resumir). ``"(sin datos de entrenamiento en ese rango)"`` cuando
        no hay asistencia registrada.

        Args:
            desde: fecha inicial ``YYYY-MM-DD`` (inclusive).
            hasta: fecha final ``YYYY-MM-DD`` (inclusive).
        """
        if db_factory is None:
            return "(tool no configurado: db_factory faltante)"
        from datetime import date as _date

        try:
            date_from = _date.fromisoformat(desde)
            date_to = _date.fromisoformat(hasta)
        except ValueError:
            return "(fechas inválidas: usa formato YYYY-MM-DD)"

        db = db_factory()
        try:
            athlete_row = await db.execute(
                sa_select(_AthleteModel.club_id).where(_AthleteModel.id == scope_athlete_id)
            )
            club_id = athlete_row.scalar_one_or_none()
            if club_id is None:
                return "(atleta no encontrado)"
            window = await load_training_window(
                db, scope_athlete_id, club_id, date_from, date_to
            )
        except Exception as exc:  # pragma: no cover - defensa runtime
            logger.warning("Error en obtener_contexto_entrenamiento: %s", exc)
            return f"(error consultando entrenamiento: {type(exc).__name__})"
        finally:
            await _safe_close(db)

        if window is None:
            return "(sin datos de entrenamiento en ese rango)"
        return _json.dumps(window, ensure_ascii=False, default=str)

    return obtener_contexto_entrenamiento


def _build_obtener_resultados_evento_tool(
    db_factory: Optional[Callable[[], AsyncSession]] = None,
    *,
    race_event_id: Optional[int] = None,
):
    """Fábrica del tool ``obtener_resultados_evento`` (solo chat scoped a evento).

    Responde preguntas grupales («¿cómo estuvieron los muchachos?») devolviendo
    los resultados de TODOS los atletas del club en el evento activo. Sin este
    tool, el agente solo dispone de tools por ``athlete_id`` y no tiene ningún
    camino válido para una pregunta grupal.

    Privacidad: identifica atletas por pseudónimo estable
    (:func:`make_pseudonym`, mismo salt que el pipeline v2) + ``athlete_id``
    opaco — NUNCA nombres reales (regla #1 del prompt).

    Args:
        db_factory: callable que retorna una ``AsyncSession``.
        race_event_id: PK del evento activo; sin él el tool no se registra
            (ver :meth:`RaceChatAgent._default_tools`).
    """
    from langchain_core.tools import tool

    @tool("obtener_resultados_evento")
    async def obtener_resultados_evento() -> str:
        """Recupera los resultados de TODOS los atletas del club en la válida activa.

        Úsala SIEMPRE para preguntas grupales («¿cómo estuvieron los
        muchachos?», «¿cómo le fue al equipo?», «¿quiénes corrieron?»). No
        requiere parámetros — el evento ya está fijado por el contexto.
        Devuelve una línea por atleta (pseudónimo, athlete_id, categoría,
        posición, tiempo y estado) o ``"(sin resultados importados para este
        evento)"`` cuando aún no hay resultados.
        """
        if db_factory is None or race_event_id is None:
            return "(tool no configurado: db_factory o evento faltante)"
        db = db_factory()
        try:
            from sqlalchemy import select

            from app.models.race_category import RaceCategory
            from app.models.race_result import RaceResult

            stmt = (
                select(RaceResult, RaceCategory)
                .join(RaceCategory, RaceResult.category_id == RaceCategory.id)
                .where(
                    RaceResult.event_id == race_event_id,
                    RaceResult.athlete_id.is_not(None),
                    RaceResult.deleted_at.is_(None),
                )
                .order_by(RaceCategory.code, RaceResult.position)
            )
            result = await db.execute(stmt)
            rows = result.all()
        except Exception as exc:  # pragma: no cover - defensa runtime
            logger.warning("Error en obtener_resultados_evento: %s", exc)
            return f"(error consultando resultados del evento: {type(exc).__name__})"
        finally:
            await _safe_close(db)

        if not rows:
            return "(sin resultados importados para este evento)"

        from app.services.race.agents.analyst import _format_ms_hhmmss
        from app.services.race.ai.anonymizer import make_pseudonym

        out: list[str] = []
        for row in rows:
            rr, cat = row[0], row[1]
            aid = getattr(rr, "athlete_id", None)
            pseudo = make_pseudonym(int(aid)) if aid is not None else "(sin id)"
            cat_code = getattr(cat, "code", "?")
            status = getattr(rr, "status", None)
            status_str = str(getattr(status, "value", status) or "?")
            pos = getattr(rr, "position", None)
            time_ms = getattr(rr, "race_time_ms", None)
            laps_behind = getattr(rr, "laps_behind", None)

            parts = [f"- {pseudo} (athlete_id={aid}, categoría {cat_code}):"]
            if status_str == "finished":
                parts.append(f"pos={pos if pos is not None else '—'}")
                if time_ms is not None:
                    parts.append(f"tiempo={_format_ms_hhmmss(time_ms)}")
                if laps_behind:
                    parts.append(f"-{laps_behind} vuelta(s)")
            else:
                parts.append(status_str.upper())
            out.append(" ".join(parts))
        return "\n".join(out)

    return obtener_resultados_evento


def _scrub_weather_notes(entry: dict, forbidden_names: list[str]) -> dict:
    """Scrub nombres reales del free-text ``weather_notes`` (privacidad menores).

    El campo ``weather_notes`` es el único PII-capable entre las condiciones.
    Reusa las reglas de nombres prohibidos de los guardrails v2. Sin nombres,
    devuelve el entry sin cambios.
    """
    notes = entry.get("weather_notes")
    if not notes or not forbidden_names:
        return entry
    from app.services.ai.guardrails import build_race_v2_forbidden_names_rules

    scrubbed = notes
    for rule in build_race_v2_forbidden_names_rules(forbidden_names):
        scrubbed = rule.pattern.sub(rule.replacement or "", scrubbed)
    out = dict(entry)
    out["weather_notes"] = scrubbed
    return out


def _scrub_coach_note_for_chat(note: str, forbidden_names: list[str]) -> str:
    """Scrub nombres reales del ``coach_note`` antes de exponerlo al LLM (T022).

    Privacidad: NUNCA registrar el contenido en logs. Reutiliza las mismas
    reglas de guardrails v2 que ``_scrub_weather_notes`` y ``_scrub_note``
    (en anonymize.py) para consistencia. Sin nombres prohibidos, el texto
    pasa sin cambios.
    """
    if not note or not forbidden_names:
        return note
    from app.services.ai.guardrails import build_race_v2_forbidden_names_rules

    scrubbed = note
    for rule in build_race_v2_forbidden_names_rules(forbidden_names):
        scrubbed = rule.pattern.sub(rule.replacement or "", scrubbed)
    return scrubbed


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
            # Cap por sesión — preservando el SystemMessage inicial: ahí viven
            # el contexto del evento activo y las reglas de privacidad, y un
            # slice plano los descartaría en sesiones largas.
            if len(messages) > MAX_TURNS_PER_SESSION:
                from langchain_core.messages import SystemMessage

                head = [messages[0]] if isinstance(messages[0], SystemMessage) else []
                messages = head + messages[-(MAX_TURNS_PER_SESSION - len(head)):]
            self._sessions[session_id] = (time.monotonic(), list(messages))

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
            default (obtener_insights_atleta, fetch_results, ...) —
            requieren ``db_factory``.
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
        forbidden_names: Optional[list[str]] = None,
    ) -> None:
        self._llm = llm
        self._db_factory = db_factory
        self._forbidden_names = forbidden_names or []
        self._tools = (
            tools
            if tools is not None
            else self._default_tools(db_factory, forbidden_names=self._forbidden_names)
        )
        self._tools_by_name = {t.name: t for t in self._tools}
        self._store = session_store or _DEFAULT_STORE
        self._prompt_version = PROMPT_VERSION_CHAT

    @staticmethod
    def _default_tools(
        db_factory: Optional[Callable[[], AsyncSession]],
        scope_season: Optional[int] = None,
        scope_valida_num: Optional[int] = None,
        forbidden_names: Optional[list[str]] = None,
        race_event_id: Optional[int] = None,
        scope_athlete_id: Optional[int] = None,
    ) -> list[Any]:
        """Arma el set de tools.

        ``scope_athlete_id`` (feature 037, T203): cuando se provee SIN
        ``race_event_id`` (chat abierto desde el perfil de un atleta, no
        desde una competencia), las tools quedan horneadas a ese atleta —
        sus firmas no piden ``athlete_id``, así el LLM no puede consultar a
        otro atleta desde este chat — y se suma
        ``obtener_contexto_entrenamiento``. El scope de evento
        (``race_event_id`` + ``scope_season``/``scope_valida_num``) tiene
        prioridad: si ambos vienen, el scope de atleta se ignora (un chat
        abierto desde una competencia sigue restringido a esa competencia,
        no a un único atleta).
        """
        effective_athlete_scope = (
            scope_athlete_id if race_event_id is None else None
        )
        tools = [
            _build_obtener_insights_atleta_tool(
                db_factory,
                scope_season=scope_season,
                scope_valida_num=scope_valida_num,
                scope_athlete_id=effective_athlete_scope,
            ),
            _build_fetch_results_tool(
                db_factory,
                scope_season=scope_season,
                scope_valida_num=scope_valida_num,
                forbidden_names=forbidden_names,
                scope_athlete_id=effective_athlete_scope,
            ),
            _build_obtener_condiciones_evento_tool(
                db_factory,
                scope_season=scope_season,
                scope_valida_num=scope_valida_num,
                forbidden_names=forbidden_names,
            ),
        ]
        # Tool grupal solo cuando hay un evento activo — fuera de un evento
        # no hay scope contra el cual listar resultados.
        if race_event_id is not None:
            tools.append(
                _build_obtener_resultados_evento_tool(
                    db_factory,
                    race_event_id=race_event_id,
                )
            )
        # Ventana de entrenamiento — solo con scope de atleta activo (chat
        # desde el perfil, no desde una competencia).
        if effective_athlete_scope is not None:
            tools.append(
                _build_obtener_contexto_entrenamiento_tool(
                    db_factory,
                    scope_athlete_id=effective_athlete_scope,
                )
            )
        return tools

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def chat(
        self,
        session_id: str,
        query: str,
        athlete_id: Optional[int] = None,
        race_event_id: Optional[int] = None,
        event_scope: Optional[Tuple[int, int, str]] = None,
    ) -> ChatResponse:
        """Procesa un turn conversacional.

        Args:
            session_id: id estable proporcionado por el frontend.
            query: pregunta del coach.
            athlete_id: si se provee, se inyecta al system prompt como
                contexto activo (no se filtra automáticamente a los
                tools — el LLM decide cuándo usarlo).
            race_event_id: id del evento activo (feature 010). Cuando se
                provee junto a ``event_scope``, las tools se restringen a
                ese evento y la sesión se siembra con la etiqueta del evento.
            event_scope: tupla ``(season, valida_num, event_label)`` ya
                resuelta por el router. Evita que el agente haga una DB
                lookup adicional. Sólo se usa cuando ``race_event_id`` es
                not None.
        """
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        # Determine effective tools: if an event scope is provided, build
        # scoped tool variants (closed over season + valida_num) so that the
        # LLM never needs to guess the event context. The default self._tools
        # are used when no scope is active (backward-compatible path).
        if race_event_id is not None and event_scope is not None:
            scope_season, scope_valida_num, event_label = event_scope
            scoped_tools = self._default_tools(
                self._db_factory,
                scope_season=scope_season,
                scope_valida_num=scope_valida_num,
                forbidden_names=self._forbidden_names,
                race_event_id=race_event_id,
            )
            effective_tools = scoped_tools
            effective_tools_by_name = {t.name: t for t in effective_tools}
        elif athlete_id is not None:
            # Feature 037 (T203): chat abierto desde el perfil de un atleta
            # (sin evento activo) — tools horneadas a ese athlete_id, más
            # `obtener_contexto_entrenamiento`. El coach no puede desviar el
            # chat a otro atleta desde este contexto.
            event_label = None
            athlete_scoped_tools = self._default_tools(
                self._db_factory,
                forbidden_names=self._forbidden_names,
                scope_athlete_id=athlete_id,
            )
            effective_tools = athlete_scoped_tools
            effective_tools_by_name = {t.name: t for t in effective_tools}
        else:
            event_label = None
            effective_tools = self._tools
            effective_tools_by_name = self._tools_by_name

        llm = self._llm or build_chat_llm(role="chat")

        # Bind tools si el LLM soporta — en tests con FakeLLM, asumimos
        # que ya viene bindeado o no necesita.
        bound_llm = llm.bind_tools(effective_tools) if hasattr(llm, "bind_tools") else llm

        history = await self._store.get(session_id)
        if not history:
            prompt_ctx: dict[str, Any] = {}
            if athlete_id:
                prompt_ctx["athlete_id"] = athlete_id
            if athlete_id is not None and race_event_id is None:
                prompt_ctx["athlete_scoped"] = True
            if event_label:
                prompt_ctx["event_label"] = event_label
            system_prompt = render_prompt(
                "race_chat_v1",
                prompt_ctx,
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
                if not name or name not in effective_tools_by_name:
                    tool_output = f"(tool desconocida: {name})"
                else:
                    tools_called.append(name)
                    try:
                        tool = effective_tools_by_name[name]
                        result = await tool.ainvoke(args or {})
                        tool_output = str(result)
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
