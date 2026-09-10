"""Router ``/api/race-analysis/*`` — capa HTTP del módulo agéntico race-results v2.

Endpoints (F5, design.md §9):
- ``POST /runs`` — iniciar análisis (returns run_id + status_url).
- ``GET /runs/{run_id}/status`` — polling cada 2s, slicing por seq.
- ``POST /runs/{run_id}/hitl/{step_id}`` — coach aprueba/rechaza/edita.
- ``GET /runs/{run_id}/result`` — output final (AnalysisOutput JSON).
- ``GET /runs/{run_id}/pdf`` — renderiza PDF con weasyprint.
- ``POST /chat`` — chat consultivo (sin streaming, JSON completo).
- ``GET /admin/ai-usage?days=30`` — métricas agregadas (coach o admin; ver
  nota RBAC abajo).

Convenciones:
- RBAC: coach + admin en TODOS los endpoints, incluido ``/admin/ai-usage``
  (feature 041, §7.2) — el prefijo ``admin/`` de la ruta es histórico y se
  conserva por contrato con el frontend, pero ya no implica admin-only. El
  desglose por entrenador (``by_coach``) SÍ está acotado: un coach sólo ve
  la identidad y el gasto individual del staff de SUS propios clubes; el
  gasto de staff de otros clubes se repliega en una fila agregada
  ``"Otros clubes"`` sin nombres (hallazgo H3). El admin sigue viendo a
  todo el mundo. Padres NO acceden a ningún endpoint de este router.
- Persistencia: SQL crudo via ``text()`` contra ``agent_runs`` /
  ``agent_run_events`` / ``athlete_ai_insights`` (modelos SQLAlchemy
  diferidos a F8B).
- Grafo: spawneado en background via :func:`runner.submit_run` con
  backpressure (10 concurrentes max). El handler HTTP retorna en <50ms.
- Reanudación HITL: :func:`runner.resume_run` con ``Command(resume=...)``
  y ``thread_id == external_run_id`` (estable durante el lifecycle del
  run).

Privacidad (CLAUDE.md §Privacidad):
- ``new_events`` en polling NUNCA contiene nombres reales — el grafo
  garantiza pseudónimos. El test
  ``tests/routers/test_race_analysis_privacy.py`` valida la invariante.
- El cliente sólo ve ``run_id`` (UUID), ``pseudonym``, fechas. NUNCA
  ``athlete_id`` en payloads de eventos.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.race_ai import (
    AIUsageByCoach,
    AIUsageByPromptVersion,
    AIUsageResponse,
    ChatRequest,
    GroupRunLaunchRequest,
    GroupRunLaunchResponse,
    GroupRunOutcome,
    HITLDecision,
    HITLDecisionRequest,
    HITLDecisionResponse,
    RaceEventRunsResponse,
    RunEvent,
    RunState,
    RunStatusResponse,
    StartRunRequest,
    StartRunResponse,
)
from app.services.race import observability
from app.services.race.ai.budget_guard import (
    BudgetExceededError,
    check_budget,
    spend_by_user_last_30d,
)
from app.services.race.ai.runner import (
    RunBackpressureError,
    resume_run,
    submit_run,
)
from app.services.race.schemas import ChatResponse
from app.schemas.season_panorama import (
    SeasonPanoramaAthleteItem,
    SeasonPanoramaResponse,
)
from app.services.permissions import (
    coach_club_ids,
    ensure_run_club_access,
    user_club_role,
)
from app.services.race.season_panorama import fetch_season_panorama
from app.services.race.run_staleness import mark_run_stale
from app.services.privacy import athlete_has_ai_processing_consent
from app.models.club import ClubMember, ClubRole
from app.services.audit import AuditAction, AuditDocumentKind, AuditEntityType, record_audit
from app.services.request_context import current_request_id, system_context
from pydantic import BaseModel as _BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Mapping status DB → estado expuesto al cliente
# ---------------------------------------------------------------------------

_DB_STATUS_TO_RUN_STATE: dict[str, RunState] = {
    "running": RunState.RUNNING,
    "awaiting_hitl": RunState.HITL_WAITING,
    "completed": RunState.DONE,
    "rejected": RunState.DONE,  # ver result para distinguir
    "failed": RunState.FAILED,
    "cancelled": RunState.CANCELLED,
}

# Estados terminales en DB. Un run en cualquiera de ellos ya no acepta
# decisiones HITL ni cancelación (ambos endpoints responden 409).
_TERMINAL_DB_STATUSES: frozenset[str] = frozenset(
    {"completed", "rejected", "failed", "cancelled"}
)

# Heurística de progreso: 13 nodos en el grafo (F4).
_GRAPH_NODE_COUNT = 13

# Cap defensivo de eventos por polling response — evita payloads enormes
# si un cliente llama con since=0 después de un run largo.
_EVENTS_PER_POLL_MAX = 200


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


_coach_or_admin = require_role([UserRole.coach, UserRole.admin])
# NOTA (hallazgo H6, feature 041): ningún endpoint de ESTE router usa ya
# ``_admin_only`` como ``Depends()`` — ``/admin/ai-usage`` pasó a
# ``_coach_or_admin`` con el desglose acotado por club (ver
# ``_coach_visible_staff_ids``). El símbolo se conserva porque
# ``tests/routers/conftest.py`` y ``tests/routers/test_race_event_runs.py``
# (fuera del alcance de este cambio) todavía lo importan para
# ``app.dependency_overrides[_admin_only] = ...`` — borrarlo rompe la
# colección de esos módulos con un ``ImportError``. Si una limpieza futura
# retira esos overrides, este símbolo puede eliminarse en el mismo cambio.
_admin_only = require_role([UserRole.admin])


def get_race_chat_agent():
    """Factory del :class:`RaceChatAgent` con db_factory inyectado.

    Cada request crea una instancia liviana (sin LLM aún — el LLM se
    construye lazy en ``chat()``). Las sesiones in-memory son singleton
    a nivel módulo (ver ``_DEFAULT_STORE``).
    """
    from app.database import AsyncSessionLocal
    from app.services.race.agents.chat import RaceChatAgent

    return RaceChatAgent(db_factory=lambda: AsyncSessionLocal())


# ---------------------------------------------------------------------------
# Helpers DB
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _load_run(db: AsyncSession, external_run_id: str) -> Optional[dict[str, Any]]:
    """Carga la fila de ``agent_runs`` por external_run_id.

    Las columnas nuevas se AGREGAN al final (contrato scope-ai-imports §4.1):
    ``_g`` cae a acceso posicional para filas tipo tupla, así que los índices
    0-10 deben quedar intactos.

    Los dos ``LEFT JOIN`` sobre ``users`` (PK de una tabla de pocas filas)
    resuelven en la MISMA ida y vuelta los nombres de quien lanzó y de quien
    decidió: el poll de 2 s no gana una query extra. Se traen ``first_name`` /
    ``last_name`` por separado en vez de concatenar en SQL para no depender de
    ``CONCAT`` en el motor SQLite del carril offline; el formato final es el
    mismo resolutor compartido de ``contracts/audit-log-api.md`` §6.2.
    """
    result = await db.execute(
        text(
            """
            SELECT r.id, r.external_run_id, r.status, r.started_at, r.finished_at,
                   r.input_json, r.final_output_json, r.error_message,
                   r.requested_by_user_id, r.explain_mode, r.athlete_id,
                   r.decided_by_user_id, r.decided_at,
                   u_req.first_name AS requested_by_first_name,
                   u_req.last_name AS requested_by_last_name,
                   u_dec.first_name AS decided_by_first_name,
                   u_dec.last_name AS decided_by_last_name
            FROM agent_runs r
            LEFT JOIN users u_req ON u_req.id = r.requested_by_user_id
            LEFT JOIN users u_dec ON u_dec.id = r.decided_by_user_id
            WHERE r.external_run_id = :rid
            LIMIT 1
            """
        ),
        {"rid": external_run_id},
    )
    row = result.fetchone() if hasattr(result, "fetchone") else None
    if row is None:
        # Compat con FakeResult: usa .first()
        first = getattr(result, "first", lambda: None)()
        if first is None:
            # último fallback: lista
            rows = result.fetchall() if hasattr(result, "fetchall") else []
            row = rows[0] if rows else None
        else:
            row = first
    if row is None:
        return None
    # Soporta tanto Row tuples como SimpleNamespace en tests.
    def _g(name: str, idx: int) -> Any:
        if hasattr(row, name):
            return getattr(row, name)
        if hasattr(row, "_mapping"):
            return row._mapping.get(name)
        try:
            return row[idx]
        except Exception:  # noqa: BLE001
            return None

    return {
        "id": _g("id", 0),
        "external_run_id": _g("external_run_id", 1),
        "status": _g("status", 2),
        "started_at": _g("started_at", 3),
        "finished_at": _g("finished_at", 4),
        "input_json": _g("input_json", 5),
        "final_output_json": _g("final_output_json", 6),
        "error_message": _g("error_message", 7),
        "requested_by_user_id": _g("requested_by_user_id", 8),
        "explain_mode": _g("explain_mode", 9),
        "athlete_id": _g("athlete_id", 10),
        "decided_by_user_id": _g("decided_by_user_id", 11),
        "decided_at": _g("decided_at", 12),
        "requested_by_display_name": _display_name(
            _g("requested_by_first_name", 13), _g("requested_by_last_name", 14)
        ),
        "decided_by_display_name": _display_name(
            _g("decided_by_first_name", 15), _g("decided_by_last_name", 16)
        ),
    }


def _display_name(first_name: Any, last_name: Any) -> str:
    """Nombre visible de un miembro del staff (``audit-log-api.md`` §6.2).

    Cuando la FK está puesta pero el JOIN no trae un nombre usable (fila
    borrada o editada a mano) se devuelve ``"Usuario no disponible"``: FR-013
    prohíbe que un identificador crudo tipo ``user#7`` llegue al lector. El
    caso "la FK es NULL" NO se distingue aquí — lo resuelve
    :func:`_actor_ref`, que devuelve ``None`` para el objeto entero.

    Privacidad (Ley 1581): esto siempre es un adulto (coach o admin); jamás
    viaja por acá el nombre de un menor.
    """
    parts = [str(p).strip() for p in (first_name, last_name) if p]
    joined = " ".join(p for p in parts if p).strip()
    return joined or "Usuario no disponible"


def _actor_fields(user_id: Any, display_name: Any) -> tuple[Optional[int], Optional[str]]:
    """Par plano ``(user_id, display_name)`` para las respuestas de §4.2/§4.3.

    ``(None, None)`` cuando la FK es NULL — "sin lanzar / sin decidir aún",
    y el frontend no pinta nada. Con la FK puesta siempre sale una cadena
    legible; ``user#7`` jamás es un valor legal (FR-013).
    """
    if user_id is None:
        return None, None
    return int(user_id), str(display_name or "Usuario no disponible")


async def _resolve_athlete_club(db: AsyncSession, athlete_id: Optional[int]) -> Optional[int]:
    """``club_id`` del atleta (escalera §1.6 paso 2 de audit-recording.md).

    ``agent_runs`` no tiene columna ``club_id`` propia — se resuelve siempre
    vía el club del atleta que el run analiza.
    """
    if athlete_id is None:
        return None
    result = await db.execute(select(Athlete.club_id).where(Athlete.id == athlete_id))
    return result.scalar_one_or_none()


def _launcher_club_ids(user: User) -> Optional[set[int]]:
    """Clubes por los que se acota una superficie de evento, o ``None``.

    ``None`` significa "sin filtro" y es exclusivo del administrador, que
    conserva el mismo bypass que en ``permissions.py``. Un entrenador queda
    acotado a sus clubes; si no tiene ninguno, el conjunto vacío no devuelve
    deportistas, que es lo correcto.
    """
    if user.role == UserRole.admin:
        return None
    return coach_club_ids(user)


async def _coach_visible_staff_ids(db: AsyncSession, user: User) -> set[int]:
    """Staff (coach/admin) visible para ``user`` en ``GET /admin/ai-usage``.

    Hallazgo H3 (feature 041): abrir ``/admin/ai-usage`` a coaches sin acotar
    ``spend_by_user_last_30d`` filtraba nombre y gasto de IA de TODO el staff
    de TODOS los clubes. El alcance correcto es: todo usuario con membresía
    ``coach`` o ``admin`` en ``club_members`` en cualquier club donde
    ``user`` mismo sea coach, más siempre el propio id de ``user`` (así un
    coach recién asignado a un club sin otro staff todavía se ve a sí
    mismo). Sólo se llama para un coach — el admin no lo necesita
    (``visible_user_ids=None`` en el router deja pasar a todos).
    """
    club_ids = coach_club_ids(user)
    visible: set[int] = {user.id}
    if not club_ids:
        return visible
    result = await db.execute(
        select(ClubMember.user_id).where(
            ClubMember.club_id.in_(club_ids),
            ClubMember.role_in_club.in_([ClubRole.coach, ClubRole.admin]),
        )
    )
    visible.update(int(uid) for uid in result.scalars().all() if uid is not None)
    return visible


async def _ensure_athlete_club_access(
    db: AsyncSession, athlete_id: Optional[int], user: User
) -> None:
    """Exige que el atleta a analizar sea del club de quien lanza.

    Hallazgos H1 y H2 de la revisión de seguridad de US6 (T080). La matriz de
    ``contracts/scope-ai-imports.md`` §1.4 cubre **operar** una corrida que ya
    existe, pero no **crearla**, y ese hueco dejaba que un entrenador de otro
    club lanzara un análisis sobre una menor ajena: el nombre de la menor
    entraba en ``forbidden_names`` y salía hacia el proveedor de IA, se
    persistía un insight en su ficha, y la fila de auditoría quedaba con el
    club de ella y un actor que no le pertenece. La corrida nacía además
    inalcanzable para quien la lanzó, porque el chequeo de club sí actúa al
    leerla.

    Las otras dos superficies de lanzamiento
    (``app/routers/athlete_race_analysis.py``) ya estaban acotadas por
    ``verify_athlete_access``; estas dos se quedaron sin equivalente. Esto es
    ese equivalente.

    El administrador mantiene su bypass, igual que en ``permissions.py``.
    """
    if athlete_id is None or user.role == UserRole.admin:
        return
    club_id = await _resolve_athlete_club(db, athlete_id)
    if club_id is None or club_id not in coach_club_ids(user):
        # Mismo texto que el 403 de las rutas de corrida, para no abrir un
        # oráculo por diferencia de mensaje.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este atleta",
        )


async def _load_events_since(
    db: AsyncSession,
    run_db_id: int,
    since: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Lee ``agent_run_events`` con ``seq > since`` ORDER BY seq."""
    result = await db.execute(
        text(
            """
            SELECT seq, event_type, node_name, payload_json, created_at
            FROM agent_run_events
            WHERE run_id = :rid AND seq > :since
            ORDER BY seq ASC
            LIMIT :lim
            """
        ),
        {"rid": run_db_id, "since": since, "lim": limit},
    )
    rows = (
        result.fetchall()
        if hasattr(result, "fetchall")
        else (result.all() if hasattr(result, "all") else [])
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "_mapping"):
            m = row._mapping
            seq, event_type, node_name, payload, created_at = (
                m["seq"], m["event_type"], m["node_name"], m["payload_json"], m["created_at"]
            )
        else:
            # tuple-like o SimpleNamespace
            seq = getattr(row, "seq", None) or row[0]
            event_type = getattr(row, "event_type", None) or row[1]
            node_name = getattr(row, "node_name", None) or row[2]
            payload = getattr(row, "payload_json", None) or row[3]
            created_at = getattr(row, "created_at", None) or row[4]
        # payload llega como JSON string en MySQL si la columna es JSON;
        # SQLite lo entrega como str. SQLAlchemy con sa.JSON puede
        # deserializar automáticamente — soportamos ambos.
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = {"_raw": payload}
        if not isinstance(payload, dict):
            payload = {"_value": payload}
        out.append(
            {
                "seq": int(seq),
                "ts": created_at,
                "type": str(event_type),
                "node": str(node_name) if node_name else None,
                "payload": payload,
            }
        )
    return out


async def _last_seq(db: AsyncSession, run_db_id: int) -> int:
    """Máximo ``seq`` emitido para el run."""
    result = await db.execute(
        text("SELECT COALESCE(MAX(seq), 0) AS s FROM agent_run_events WHERE run_id = :rid"),
        {"rid": run_db_id},
    )
    first = getattr(result, "first", lambda: None)()
    if first is None:
        rows = result.fetchall() if hasattr(result, "fetchall") else []
        first = rows[0] if rows else None
    if first is None:
        return 0
    if hasattr(first, "_mapping"):
        return int(first._mapping.get("s") or 0)
    return int(getattr(first, "s", None) or first[0] or 0)


async def _last_node(db: AsyncSession, run_db_id: int) -> Optional[str]:
    """Último ``node_name`` con type=node_start sin node_end posterior."""
    result = await db.execute(
        text(
            """
            SELECT node_name FROM agent_run_events
            WHERE run_id = :rid
            ORDER BY seq DESC
            LIMIT 1
            """
        ),
        {"rid": run_db_id},
    )
    first = getattr(result, "first", lambda: None)()
    if first is None:
        return None
    if hasattr(first, "_mapping"):
        return first._mapping.get("node_name")
    return getattr(first, "node_name", None) or first[0]


# Mapeo de tipos in-memory (events.py) → ENUM DB (agentruneventtype).
# La tabla `agent_run_events.event_type` solo acepta los valores del ENUM,
# pero los wrappers emiten `node_error` y `run_failed` (sintético). Esto
# evita DataError al persistir y mantiene los nombres in-memory ricos.
_EVENT_TYPE_TO_DB: dict[str, str] = {
    "node_start": "node_start",
    "node_end": "node_end",
    "node_error": "error",
    "hitl_request": "hitl_request",
    "hitl_response": "hitl_response",
    "explain": "explain",
    "token": "token",
    "error": "error",
    "done": "done",
    "run_failed": "error",
}


async def _persist_events(
    db: AsyncSession,
    run_db_id: int,
    events: list[dict[str, Any]],
) -> int:
    """Bulk INSERT de eventos in-memory a ``agent_run_events``.

    Idempotente: omite eventos con ``seq <= MAX(seq)`` actual para el run,
    de forma que reintentos no dupliquen. Retorna el conteo insertado.
    """
    if not events:
        return 0
    import json as _json

    existing = await _last_seq(db, run_db_id)
    inserted = 0
    fallback_ts = _utc_now()
    for ev in events:
        try:
            seq = int(ev.get("seq") or 0)
        except (TypeError, ValueError):
            continue
        if seq <= existing:
            continue
        type_raw = str(ev.get("type") or "")
        type_db = _EVENT_TYPE_TO_DB.get(type_raw, "error")
        node = ev.get("node")
        payload = ev.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"_value": payload}
        # Preservar el ts original del evento (emitido por with_events al
        # entrar/salir del nodo) para que la duración por nodo se calcule
        # correctamente en el cliente. Si el evento no trae ts parseable,
        # caemos al timestamp del bulk insert.
        ev_ts = ev.get("ts")
        ts_value = fallback_ts
        if isinstance(ev_ts, str) and ev_ts:
            try:
                parsed = datetime.fromisoformat(ev_ts)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                ts_value = parsed
            except ValueError:
                ts_value = fallback_ts
        elif isinstance(ev_ts, datetime):
            ts_value = (
                ev_ts if ev_ts.tzinfo is not None else ev_ts.replace(tzinfo=timezone.utc)
            )
        await db.execute(
            text(
                """
                INSERT INTO agent_run_events
                    (run_id, seq, event_type, node_name, payload_json, created_at)
                VALUES (:rid, :seq, :et, :nn, :pl, :ts)
                """
            ),
            {
                "rid": run_db_id,
                "seq": seq,
                "et": type_db,
                "nn": node,
                "pl": _json.dumps(payload, ensure_ascii=False, default=str),
                "ts": ts_value,
            },
        )
        inserted += 1
    return inserted


async def _update_run_status(
    db: AsyncSession,
    external_run_id: str,
    new_status: str,
    error_message: Optional[str] = None,
    final_output: Optional[dict[str, Any]] = None,
) -> None:
    import json

    params: dict[str, Any] = {
        "rid": external_run_id,
        "st": new_status,
        "fin": _utc_now() if new_status in {"completed", "rejected", "failed", "cancelled"} else None,
        "em": error_message,
        "fo": json.dumps(final_output, ensure_ascii=False, default=str) if final_output else None,
    }
    await db.execute(
        text(
            """
            UPDATE agent_runs
            SET status = :st,
                finished_at = COALESCE(:fin, finished_at),
                error_message = COALESCE(:em, error_message),
                final_output_json = COALESCE(:fo, final_output_json)
            WHERE external_run_id = :rid
            """
        ),
        params,
    )


def _extract_final_output(result_state: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not result_state:
        return None

    payload: dict[str, Any] = {}

    final_analysis = result_state.get("final_analysis")
    if final_analysis is not None:
        if hasattr(final_analysis, "model_dump"):
            try:
                payload.update(final_analysis.model_dump())
            except Exception:  # noqa: BLE001
                logger.exception("_extract_final_output: model_dump falló")
        elif isinstance(final_analysis, dict):
            payload.update(final_analysis)

    rendered = result_state.get("rendered_markdown")
    if isinstance(rendered, str) and rendered.strip():
        existing_md = payload.get("raw_markdown")
        if not isinstance(existing_md, str) or not existing_md.strip():
            payload["raw_markdown"] = rendered

    if "raw_markdown" not in payload or not str(payload.get("raw_markdown") or "").strip():
        return None

    return payload


async def _finalize_run(
    db: AsyncSession,
    external_run_id: str,
    exc: Optional[BaseException],
    result_state: Optional[dict[str, Any]],
    *,
    origin_request_id: Optional[str] = None,
) -> None:
    """Cierre atómico de un run: drena eventos + actualiza estado terminal.

    Se invoca desde ``_on_complete`` del runner (success / exception /
    cancel). Si el grafo falló antes de emitir cualquier evento de nodo,
    sintetiza un evento ``error`` para que la UI tenga al menos un dato
    explícito de la falla (invariante INV-3 del módulo de tests).

    Idempotente: si los eventos ya están persistidos no duplica (filtro
    por ``seq > MAX(seq)``).
    """
    final_payload = _extract_final_output(result_state) if exc is None else None
    graph_status = (result_state or {}).get("status") if exc is None else None

    # LangGraph marca pausa por interrupt() colocando `__interrupt__` en el
    # state retornado por `ainvoke`. La task del runner termina pero el run
    # NO es terminal — sigue en `awaiting_hitl` hasta que el coach reanude.
    interrupts: Any = None
    if isinstance(result_state, dict) and exc is None:
        interrupts = (
            result_state.get("__interrupt__")
            or result_state.get("interrupt")
        )

    if exc is not None:
        new_status = "failed"
        err: Optional[str] = f"{type(exc).__name__}: {str(exc)[:500]}"
    elif interrupts:
        new_status = "awaiting_hitl"
        err = None
        final_payload = None
    elif graph_status == "failed":
        new_status = "failed"
        errors_list = (result_state or {}).get("errors") or []
        first_err = errors_list[0] if errors_list else {}
        err = first_err.get("message") or "Grafo terminó con status=failed"
    elif not final_payload:
        new_status = "failed"
        err = "Grafo completó sin output"
    else:
        new_status = "completed"
        err = None

    run = await _load_run(db, external_run_id)
    if run is None:
        logger.error("_finalize_run: run %s no existe", external_run_id)
        return
    run_db_id = int(run["id"])

    trace_id = observability.trace_id_for(external_run_id)
    if trace_id is not None:
        await db.execute(
            text("UPDATE agent_runs SET langfuse_trace_id = :tid WHERE id = :id"),
            {"tid": trace_id, "id": run_db_id},
        )

    events = list((result_state or {}).get("events") or [])

    # El coach pudo descartar el run (POST /runs/{id}/cancel) mientras la
    # task del grafo seguía viva. `cancelled` es una decisión humana
    # explícita y terminal: drenamos los eventos que alcanzó a producir el
    # grafo (audit trail) pero NO reescribimos el estado — si no, un run
    # descartado "revivía" como completed/failed en el próximo poll.
    if str(run["status"]) == "cancelled":
        await _persist_events(db, run_db_id, events)
        logger.info(
            "_finalize_run: run %s ya estaba cancelado; no se reescribe estado",
            external_run_id,
        )
        return

    if new_status == "failed":
        has_err_event = any(
            str(e.get("type") or "") in {"error", "node_error", "run_failed"}
            for e in events
        )
        if not has_err_event:
            next_seq = max((int(e.get("seq") or 0) for e in events), default=0) + 1
            err_type = type(exc).__name__ if exc else "GraphFailure"
            err_msg = (str(exc) if exc else err or "Run failed")[:200]
            events.append(
                {
                    "seq": next_seq,
                    "ts": _utc_now().isoformat(),
                    "type": "error",
                    "node": None,
                    "payload": {"exc": err_type, "msg": err_msg},
                }
            )

    await _persist_events(db, run_db_id, events)
    await _update_run_status(
        db,
        external_run_id,
        new_status,
        error_message=err,
        final_output=final_payload,
    )

    # Cierre del run (§3.3, §4.9): actor_kind=system, sin request HTTP en
    # scope (esta sesión se abre después de que la respuesta ya volvió al
    # cliente) — el request_id viaja explícito, capturado en el closure de
    # quien lanzó/reanudó el run.
    ctx = system_context(job="agent_run_complete", request_id=origin_request_id)
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.agent_run,
        entity_id=run_db_id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=await _resolve_athlete_club(db, run.get("athlete_id")),
        athlete_id=run.get("athlete_id"),
        changed_fields=["status"],
        diff={"status": (str(run["status"]), new_status)},
        meta={"job": "agent_run_complete"},
        request_id=ctx.request_id,
    )


# ---------------------------------------------------------------------------
# Endpoint 1: POST /runs
# ---------------------------------------------------------------------------


@router.post(
    "/runs",
    response_model=StartRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"model": StartRunResponse},
        400: {"description": "Input inválido."},
        403: {"description": "Rol no permitido."},
        429: {"description": "Demasiados runs activos (cap=10)."},
        451: {"description": "Sin consentimiento parental vigente para procesamiento con IA."},
        503: {"description": "AI deshabilitada (AI_ENABLED=false)."},
    },
)
async def start_run(
    body: StartRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> StartRunResponse:
    """Inicia un análisis agéntico. Retorna inmediatamente con ``run_id``."""
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible (AI_ENABLED=false)",
        )

    if body.valida_nums and len(body.valida_nums) > 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cap v2: máximo 4 válidas por lanzamiento. Usa resumen temporada para visión global.",
        )

    # El atleta tiene que ser del club de quien lanza (hallazgo H1 de T080).
    # Va **antes** del chequeo de archivado a propósito: si no, la diferencia
    # entre 404 y 403 le confirma a un entrenador de otro club que ese id
    # existe y está archivado.
    await _ensure_athlete_club_access(db, body.athlete_id, current_user)

    # No se puede lanzar un análisis IA para un atleta archivado
    # (contracts/athlete-archive.md §5.2).
    if body.athlete_id is not None:
        _archived_check = await db.execute(
            select(Athlete.deleted_at).where(Athlete.id == body.athlete_id)
        )
        _deleted_at = _archived_check.scalar_one_or_none()
        if _deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Atleta no encontrado",
            )

    # Consentimiento parental para procesamiento con IA (Ley 1581 art. 9).
    # Mismo contrato que ``routers/ai.py::_ensure_ai_consent`` (feature 037,
    # T203) — sin autorización de terceros vigente, 451.
    if not await athlete_has_ai_processing_consent(body.athlete_id, db):
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "Falta consentimiento parental vigente con autorización para "
                "compartir datos con terceros (procesamiento con IA). "
                "Solicita a la familia renovar el consentimiento."
            ),
        )

    # F8A: Budget guard — chequea ANTES de insertar agent_runs y adquirir
    # el semáforo. Si el gasto de los últimos 30d excede el presupuesto,
    # respondemos 503 con mensaje claro. Runs en curso completan.
    try:
        await check_budget(db)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        )

    run_id = uuid.uuid4().hex
    started_at = _utc_now()

    import json

    input_payload = {
        "athlete_id": body.athlete_id,
        "season": body.season,
        "valida_nums": body.valida_nums,
        "explain_mode": body.explain_mode,
    }

    # Insert agent_runs (status=running). El run_id es el thread_id del
    # checkpointer LangGraph para reanudación post-HITL.
    try:
        await db.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, requested_by_user_id,
                    checkpoint_thread_id, explain_mode, athlete_id
                ) VALUES (
                    :rid, :gn, :pv, :sa, 'running', :inp, :uid, :tid, :em, :aid
                )
                """
            ),
            {
                "rid": run_id,
                "gn": "race-analyst",
                "pv": settings.race_ai_prompt_version,
                "sa": started_at,
                "inp": json.dumps(input_payload, ensure_ascii=False, default=str),
                "uid": current_user.id,
                "tid": run_id,  # estable durante el lifecycle.
                "em": 1 if body.explain_mode else 0,
                # §1.3: sin esta columna el club del run sólo se podía
                # resolver leyendo ``input_json``. Se persiste igual en el
                # JSON, que sigue siendo el respaldo de las filas históricas.
                "aid": body.athlete_id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("start_run: insert agent_runs falló")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear el run: {type(exc).__name__}",
        )

    # Fila de auditoría del lanzamiento (§4.9 audit-recording.md): un run
    # NUEVO es siempre ``create``, sea cual sea el punto de entrada (club,
    # atleta o resumen de temporada, o el re-lanzamiento vía /re-execute).
    _new_run_row = await _load_run(db, run_id)
    if _new_run_row is not None:
        await record_audit(
            db,
            action=AuditAction.create,
            entity_type=AuditEntityType.agent_run,
            entity_id=int(_new_run_row["id"]),
            actor=current_user,
            club_id=await _resolve_athlete_club(db, body.athlete_id),
            athlete_id=body.athlete_id,
        )

    # Calcular edad del atleta para inyectarla en el state del grafo.
    # Si el atleta no existe (body.athlete_id inválido), continuamos sin edad
    # y el nodo analyst_agent emitirá un warning explícito.
    athlete_age: Optional[int] = None
    ltad_group_val: Optional[str] = None
    maturation_status: Optional[str] = None
    forbidden_names: list[str] = []
    athlete_sex_val: Optional[str] = None
    if body.athlete_id is not None:
        _athlete_result = await db.execute(
            select(Athlete).where(Athlete.id == body.athlete_id)
        )
        _athlete = _athlete_result.scalar_one_or_none()
        # Feature 037 (T101): sexo real del atleta → athlete_ref del prompt
        # ("el deportista"/"la deportista"). No depende de birth_date, así
        # que se resuelve fuera del bloque siguiente (que sí lo requiere).
        if _athlete is not None and getattr(_athlete, "sex", None) is not None:
            athlete_sex_val = getattr(_athlete.sex, "value", None) or str(_athlete.sex)
        if _athlete is not None and _athlete.birth_date is not None:
            # Feature 011: inyectar grupo LTAD + fase madurativa reales (igual
            # que el path per-atleta) para no caer en defaults Pre-PHV/Bambino.
            from app.services.race.ai.grounding import (
                latest_maturation_status,
                load_forbidden_names,
                ltad_group_from_age,
            )

            _age_decimal = (date.today() - _athlete.birth_date).days / 365.25
            athlete_age = int(_age_decimal)
            ltad_group_val = ltad_group_from_age(_age_decimal).value
            maturation_status = await latest_maturation_status(db, body.athlete_id)
            forbidden_names = await load_forbidden_names(
                db, body.athlete_id, nickname=getattr(_athlete, "nickname", None)
            )
        else:
            logger.warning(
                "start_run: athlete_id=%s no encontrado o sin birth_date; "
                "athlete_age no inyectado al state",
                body.athlete_id,
            )

    initial_state: dict[str, Any] = {
        "athlete_id": body.athlete_id,
        "season": body.season,
        "valida_nums": body.valida_nums,
        "coach_id": current_user.id,
        "explain_mode": body.explain_mode,
        "run_id": run_id,
        "prompt_version": settings.race_ai_prompt_version,
        "forbidden_names": forbidden_names,
        # Feature 037 (T101/T204): athlete_sex/analysis_kind viajan al state
        # para que analyst.py resuelva athlete_ref y active la rama v3 del
        # nodo analyst_agent. El prompt_version por defecto es
        # ``settings.race_ai_prompt_version`` (v3), con rollback a v2 vía
        # RACE_AI_PROMPT_VERSION sin deploy de código.
        "athlete_sex": athlete_sex_val,
        "analysis_kind": body.analysis_kind,
    }
    if athlete_age is not None:
        initial_state["athlete_age"] = athlete_age
    if ltad_group_val is not None:
        initial_state["ltad_group"] = ltad_group_val
    # maturation_status puede ser None legítimamente (sin registros) — se
    # inyecta siempre que se haya resuelto el atleta.
    if body.athlete_id is not None and _athlete is not None:
        initial_state["maturation_status"] = maturation_status

    # Capturado ANTES de spawnear el background task: la sesión de
    # ``_on_complete`` corre fuera del scope HTTP (§3.3), así que el
    # request_id del lanzamiento viaja explícito por closure.
    _launch_request_id = current_request_id()

    async def _on_complete(
        rid: str,
        exc: Optional[BaseException],
        result_state: Optional[dict[str, Any]],
    ) -> None:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                await _finalize_run(
                    session, rid, exc, result_state, origin_request_id=_launch_request_id
                )
                await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("_on_complete: finalize_run falló para %s", rid)

    try:
        await submit_run(run_id, initial_state, on_complete=_on_complete)
    except RunBackpressureError as exc:
        # Marcar el run como cancelado y propagar 429.
        try:
            await _update_run_status(
                db, run_id, "cancelled", error_message="backpressure: no slots"
            )
        except Exception:  # noqa: BLE001
            logger.exception("start_run: falló cancelar tras backpressure")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )

    estimated = 15 + 5 * len(body.valida_nums or [])

    return StartRunResponse(
        run_id=run_id,
        status=RunState.RUNNING,
        started_at=started_at,
        status_url=f"/api/race-analysis/runs/{run_id}/status",
        estimated_seconds=estimated,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: GET /runs/{run_id}/status
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/status",
    response_model=RunStatusResponse,
    responses={
        200: {"model": RunStatusResponse},
        304: {"description": "Sin cambios desde el último poll (ETag match)."},
        403: {"description": "Coach de otro club."},
        404: {"description": "Run no existe."},
    },
)
async def get_run_status(
    run_id: str,
    request: Request,
    response: Response,
    since: int = Query(default=0, ge=0, description="Sólo retorna eventos con seq > since."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> Any:
    """Polling endpoint. Cliente envía ``?since=<last_seq>`` cada 2s.

    Si ``last_seq == since`` (sin cambios) → 304. Esto reduce ancho de
    banda en runs largos esperando HITL.
    """
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    await ensure_run_club_access(db, run, current_user)

    last_seq = await _last_seq(db, int(run["id"]))

    # ETag basado en last_seq + status → cambia con cualquier evento o
    # transición de estado. Más barato que hashear el response completo.
    etag = f'W/"{run_id}:{last_seq}:{run["status"]}"'
    if_none_match = request.headers.get("if-none-match")
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache"
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    state = _DB_STATUS_TO_RUN_STATE.get(str(run["status"]), RunState.RUNNING)
    current_node = await _last_node(db, int(run["id"])) if state == RunState.RUNNING else None

    new_events_raw = await _load_events_since(
        db, int(run["id"]), since=since, limit=_EVENTS_PER_POLL_MAX
    )
    new_events = [RunEvent(**e) for e in new_events_raw]

    # Heurística de progreso: cuento distinct nodos completados.
    # Aproximación barata: progress = min(100, last_seq / (13*2) * 100)
    # porque cada nodo emite ~2 eventos (start + end).
    progress_pct = min(100, int(round((last_seq / (_GRAPH_NODE_COUNT * 2)) * 100)))
    if state in {RunState.DONE, RunState.FAILED, RunState.CANCELLED}:
        progress_pct = 100

    # Estimación tiempo restante: heurística simple.
    if state == RunState.RUNNING:
        eta = max(0, 30 - int((_utc_now() - _aware(run["started_at"])).total_seconds()))
    else:
        eta = 0

    requested_by_user_id, requested_by_display_name = _actor_fields(
        run.get("requested_by_user_id"), run.get("requested_by_display_name")
    )
    decided_by_user_id, decided_by_display_name = _actor_fields(
        run.get("decided_by_user_id"), run.get("decided_by_display_name")
    )

    return RunStatusResponse(
        run_id=run_id,
        state=state,
        progress_pct=progress_pct,
        current_node=current_node,
        started_at=_aware(run["started_at"]),
        estimated_seconds_remaining=eta,
        new_events=new_events,
        last_seq=last_seq,
        requested_by_user_id=requested_by_user_id,
        requested_by_display_name=requested_by_display_name,
        decided_by_user_id=decided_by_user_id,
        decided_by_display_name=decided_by_display_name,
    )


def _aware(dt: Any) -> datetime:
    """Asegura tz=UTC en datetimes que vienen de MySQL DATETIME (naive)."""
    if dt is None:
        return _utc_now()
    if not isinstance(dt, datetime):
        return _utc_now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Endpoint 3: POST /runs/{run_id}/hitl/{step_id}
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/hitl/{step_id}",
    response_model=HITLDecisionResponse,
    responses={
        200: {"model": HITLDecisionResponse},
        403: {"description": "Coach de otro club."},
        404: {"description": "Run no existe."},
        409: {"description": "Run no está en estado awaiting_hitl."},
        429: {"description": "Backpressure: reintenta en breve."},
    },
)
async def submit_hitl_decision(
    run_id: str,
    step_id: str,
    body: HITLDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> HITLDecisionResponse:
    """Coach aprueba/edita/rechaza un draft pendiente en HITL.

    Reanuda el grafo con ``Command(resume=...)``. La reanudación es
    asíncrona — el endpoint retorna ``accepted=True`` apenas se spawn la
    task. El cliente sigue pollngueando ``/status`` para ver el avance.
    """
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    await ensure_run_club_access(db, run, current_user)

    # Validación de estado: debe estar awaiting_hitl o running (si el
    # status no se actualizó aún por el grafo). Mantenemos permisivo:
    # si está en estado terminal, 409.
    db_status = str(run["status"])
    if db_status in _TERMINAL_DB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run en estado terminal '{db_status}', no acepta HITL",
        )

    # Validación edits: si decision=edit, edits es obligatorio.
    if body.decision == HITLDecision.EDIT and not body.edits:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision=edit requiere campo 'edits'",
        )

    resume_value = {
        "decision": body.decision.value,
        "edits": body.edits,
        "notes": body.notes,
        "step_id": step_id,
        "by_user_id": current_user.id,
    }

    # Persistir evento hitl_response — visible en próximo poll.
    last_seq_val = await _last_seq(db, int(run["id"]))
    import json

    try:
        await db.execute(
            text(
                """
                INSERT INTO agent_run_events (
                    run_id, seq, event_type, node_name, payload_json
                ) VALUES (
                    :rid, :seq, 'hitl_response', 'hitl_gate_review', :pl
                )
                """
            ),
            {
                "rid": int(run["id"]),
                "seq": last_seq_val + 1,
                "pl": json.dumps(
                    {
                        "decision": body.decision.value,
                        "step_id": step_id,
                        "has_edits": bool(body.edits),
                    },
                    ensure_ascii=False,
                ),
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("submit_hitl_decision: insert evento hitl_response falló")

    # FR-028: quién resolvió el gate queda en ``agent_runs`` (no solo en el
    # payload del evento) y en la fila de auditoría — accept/edit=approve,
    # reject=unapprove (audit-recording.md §4.9; los tres verbos NO son
    # intercambiables, ver la nota de esa sección).
    decided_at = _utc_now()
    await db.execute(
        text(
            "UPDATE agent_runs SET decided_by_user_id = :uid, decided_at = :dat "
            "WHERE id = :rid"
        ),
        {"uid": current_user.id, "dat": decided_at, "rid": int(run["id"])},
    )
    _hitl_is_reject = body.decision == HITLDecision.REJECT
    _hitl_audit_meta: dict[str, Any] = {
        "step_id": step_id,
        "previous_status": db_status,
    }
    if not _hitl_is_reject:
        _hitl_audit_meta["has_edits"] = bool(body.edits)
    await record_audit(
        db,
        action=AuditAction.unapprove if _hitl_is_reject else AuditAction.approve,
        entity_type=AuditEntityType.agent_run,
        entity_id=int(run["id"]),
        actor=current_user,
        club_id=await _resolve_athlete_club(db, run.get("athlete_id")),
        athlete_id=run.get("athlete_id"),
        changed_fields=["decided_by_user_id", "decided_at"],
        meta=_hitl_audit_meta,
    )

    # Reanudar grafo en background.
    #
    # Fix BUG-002: la reanudación tras HITL ejecuta nodos post-gate
    # (rehydrate_names, persist_insight, render_outputs, notify_coach)
    # que emiten ``node_start`` / ``node_end`` en ``result_state.events``.
    # Antes drenábamos solo ``status`` con ``_update_run_status`` y los
    # eventos quedaban en memoria, sin persistirse a ``agent_run_events``.
    # El polling del frontend nunca veía los ``node_end`` y el timeline
    # mostraba ``hitl_gate_review`` "en curso" indefinidamente.
    #
    # Reutilizamos ``_finalize_run`` (mismo helper que el flujo inicial)
    # para garantizar que los eventos generados durante la reanudación
    # se persisten antes de marcar el estado terminal. Para el caso
    # ``reject``, sobrescribimos el status final a ``rejected`` después
    # del finalize (que por sí solo lo marcaría ``completed``).
    is_reject = body.decision == HITLDecision.REJECT

    # Capturado ANTES de spawnear el background task — ver la misma nota en
    # ``start_run``.
    _resume_request_id = current_request_id()

    async def _on_complete(
        rid: str,
        exc: Optional[BaseException],
        result_state: Optional[dict[str, Any]],
    ) -> None:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                await _finalize_run(
                    session, rid, exc, result_state, origin_request_id=_resume_request_id
                )
                # Tras reject, el grafo igual completa los nodos post-HITL
                # (persist con archived_at, etc.). El status correcto es
                # ``rejected`` — _finalize_run lo dejaría como ``completed``.
                if is_reject and exc is None:
                    await _update_run_status(
                        session,
                        rid,
                        "rejected",
                        error_message=None,
                        final_output=None,
                    )
                await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("_on_complete hitl: finalize falló para %s", rid)

    try:
        await resume_run(run_id, resume_value, on_complete=_on_complete)
    except RunBackpressureError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )

    return HITLDecisionResponse(
        accepted=True,
        run_id=run_id,
        step_id=step_id,
        next_state=RunState.RUNNING,
        # Quien decide es el usuario de esta petición: la fila se acaba de
        # actualizar arriba, así que no hace falta releer ``agent_runs``.
        decided_by_user_id=current_user.id,
        decided_by_display_name=_display_name(
            getattr(current_user, "first_name", None),
            getattr(current_user, "last_name", None),
        ),
    )


# ---------------------------------------------------------------------------
# Endpoint 4: GET /runs/{run_id}/result
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/result",
    responses={
        200: {"description": "AnalysisOutput JSON."},
        403: {"description": "Coach de otro club."},
        404: {"description": "Run aún no terminado o no existe."},
        409: {"description": "Run en estado failed."},
    },
)
async def get_run_result(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> dict[str, Any]:
    """Retorna el ``AnalysisOutput`` final (markdown + sections + ...)."""
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    await ensure_run_club_access(db, run, current_user)

    db_status = str(run["status"])
    if db_status == "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run falló: {run.get('error_message') or 'sin detalle'}",
        )
    if db_status not in {"completed", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run aún no terminado (status={db_status})",
        )

    final = run.get("final_output_json")
    if isinstance(final, str):
        import json

        try:
            final = json.loads(final)
        except (ValueError, TypeError):
            final = {"raw_markdown": final, "_warning": "final_output_json mal formado"}
    if final is None:
        final = {"raw_markdown": "(sin output persistido)", "sections": {}, "recommendations": [], "risk_flags": []}

    return {
        "run_id": run_id,
        "status": db_status,
        "final": final,
        "finished_at": _aware(run.get("finished_at")) if run.get("finished_at") else None,
    }


# ---------------------------------------------------------------------------
# Endpoint 5: GET /runs/{run_id}/pdf
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/pdf",
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Run no encontrado o sin output."},
        501: {"description": "weasyprint no disponible en este entorno."},
    },
)
async def get_run_pdf(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> Any:
    """Renderiza el markdown final a PDF con weasyprint + branding TyR."""
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    await ensure_run_club_access(db, run, current_user)

    if str(run["status"]) not in {"completed", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run aún no completado",
        )

    final = run.get("final_output_json")
    if isinstance(final, str):
        import json

        try:
            final = json.loads(final)
        except (ValueError, TypeError):
            final = {"raw_markdown": final}
    md = (final or {}).get("raw_markdown") or "_(sin contenido)_"

    # weasyprint import lazy: requiere libs nativas (cairo, pango). Si
    # falta en este entorno, devolvemos 501 claro.
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except (ImportError, OSError) as exc:
        # OSError cubre el caso "libgobject not found" en macOS sin brew.
        logger.warning("weasyprint no disponible: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "PDF rendering no disponible en este entorno: weasyprint "
                "requiere libs nativas (cairo, pango, gobject). "
                "TODO: instalar deps o devolver markdown crudo."
            ),
        )

    # Render mínimo HTML + branding TyR (logo si existe).
    from pathlib import Path

    logo_path = Path("static/logo.png").resolve()
    logo_html = (
        f'<img src="file://{logo_path}" alt="TyR" style="height:50px"/>'
        if logo_path.exists()
        else "<h2>Club Deportivo Trocha y Ruta</h2>"
    )

    import markdown as _md_lib

    body_html = _md_lib.markdown(
        md,
        extensions=["extra", "sane_lists"],
        output_format="html",
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Análisis race {run_id[:8]}</title>
<style>
  body {{ font-family: 'Helvetica', sans-serif; margin: 2cm; font-size: 11pt; line-height: 1.5; }}
  header {{ border-bottom: 2px solid #2c5282; padding-bottom: 1em; margin-bottom: 1.5em; }}
  h2 {{ font-size: 14pt; color: #1a365d; margin-top: 1.4em; margin-bottom: 0.4em; }}
  h3 {{ font-size: 12pt; color: #2c5282; margin-top: 1em; margin-bottom: 0.3em; }}
  ul, ol {{ padding-left: 1.4em; }}
  li {{ margin-bottom: 0.3em; }}
  p {{ margin-top: 0; margin-bottom: 0.7em; }}
  footer {{ position: fixed; bottom: 0; left: 0; right: 0; text-align: center; font-size: 9pt; color: #666; }}
</style>
</head>
<body>
<header>{logo_html}<p><strong>Análisis de carrera</strong> · Run {run_id[:8]}</p></header>
{body_html}
<footer>Club Deportivo Trocha y Ruta — Generado {_utc_now().strftime('%Y-%m-%d')}</footer>
</body>
</html>"""

    try:
        pdf_bytes = HTML(string=html_doc).write_pdf()
    except Exception as exc:  # noqa: BLE001
        logger.exception("weasyprint.write_pdf falló")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renderizando PDF: {type(exc).__name__}",
        )

    # Fila de exportación (§4.13 audit-recording.md): SOLO el tipo de
    # documento, nunca su contenido.
    await record_audit(
        db,
        action=AuditAction.export,
        entity_type=AuditEntityType.agent_run,
        entity_id=int(run["id"]),
        actor=current_user,
        club_id=await _resolve_athlete_club(db, run.get("athlete_id")),
        athlete_id=run.get("athlete_id"),
        meta={"document_kind": AuditDocumentKind.race_analysis_pdf.value},
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="analisis-{run_id[:12]}.pdf"',
        },
    )


# ---------------------------------------------------------------------------
# Endpoint 6: POST /chat
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        200: {"model": ChatResponse},
        403: {"description": "Rol no permitido."},
        404: {"description": "Competencia no encontrada."},
        503: {"description": "AI deshabilitada."},
    },
)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(_coach_or_admin),
    chat_agent=Depends(get_race_chat_agent),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Chat consultivo con tools (RAG + insights + resultados).

    Sin streaming — respuesta completa JSON. Sesiones in-memory con TTL
    de 1h (ver :mod:`app.services.race.agents.chat`).

    Cuando ``race_event_id`` se incluye en el body, el router valida que
    el evento exista (404 si no) y pasa el scope ``(season, valida_num,
    event_label)`` al agente para que los tools queden restringidos a ese
    evento y la sesión se siembre con la etiqueta del evento.
    """
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible (AI_ENABLED=false)",
        )

    import asyncio as _asyncio

    # Resolve event scope when race_event_id is provided.
    event_scope = None
    if body.race_event_id is not None:
        from app.services.race.group_launch import (
            EventNotAnalyzableError,
            RaceEventNotFoundError,
            resolve_event_scope,
        )
        from app.models.race_event import RaceEvent

        try:
            scope_season, scope_valida_num = await resolve_event_scope(db, body.race_event_id)
        except RaceEventNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Competencia no encontrada.",
            )
        except EventNotAnalyzableError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La competencia no tiene número de válida asignado.",
            )

        # Build a human-readable event label for the system prompt.
        # Best-effort: load the event name/date; fall back to generic label.
        event_label = f"Válida {scope_valida_num} ({scope_season})"
        try:
            _ev_result = await db.execute(
                select(RaceEvent).where(RaceEvent.id == body.race_event_id)
            )
            _ev = _ev_result.scalar_one_or_none()
            if _ev is not None:
                loc = getattr(_ev, "location", None) or ""
                ev_date = getattr(_ev, "event_date", None)
                date_str = ev_date.strftime("%d/%m/%Y") if ev_date else ""
                parts = [f"Válida {scope_valida_num} {scope_season}"]
                if loc:
                    parts.append(loc)
                if date_str:
                    parts.append(date_str)
                event_label = " — ".join(parts)
        except Exception:  # noqa: BLE001 — label is informational only
            pass

        event_scope = (scope_season, scope_valida_num, event_label)

    try:
        response = await chat_agent.chat(
            session_id=body.session_id,
            query=body.query,
            athlete_id=body.athlete_id,
            race_event_id=body.race_event_id,
            event_scope=event_scope,
        )
    except (TimeoutError, _asyncio.TimeoutError):
        logger.exception("chat endpoint failed (timeout) for session=%s", body.session_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM timeout: el agente tardó demasiado en responder.",
        )
    except ValueError as exc:
        logger.exception("chat endpoint failed (value error) for session=%s", body.session_id)
        msg = str(exc).lower()
        if "ai_api_key" in msg or "api_key" in msg or "config" in msg:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI provider no configurado.",
            )
        first_line = str(exc).splitlines()[0] if str(exc) else ""
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error en agente de chat ({type(exc).__name__}): {first_line[:200]}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat endpoint failed for session=%s", body.session_id)
        first_line = str(exc).splitlines()[0] if str(exc) else ""
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error en agente de chat ({type(exc).__name__}): {first_line[:200]}",
        )
    return response


# ---------------------------------------------------------------------------
# Endpoint 7: GET /admin/ai-usage
# ---------------------------------------------------------------------------


@router.get(
    "/admin/ai-usage",
    response_model=AIUsageResponse,
    responses={
        200: {"model": AIUsageResponse},
        403: {"description": "Solo coach/admin."},
    },
)
async def admin_ai_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> AIUsageResponse:
    """Métricas agregadas de uso de IA en ventana ``days``.

    Lee desde ``athlete_ai_insights`` — fuente de verdad para
    cost/latency. Langfuse es solo un observador local opcional
    (``services/race/observability.py``), no fuente de estas métricas.

    RBAC ampliado a coach (§7.2, US6 AC4): a diferencia de
    ``GET /api/ai/status``, acá el entrenador SÍ ve montos en dólares —
    necesita saber quién está consumiendo el presupuesto compartido del
    club. No hay datos de menores en esta superficie: sólo nombres de staff
    adulto y dinero.
    """
    cutoff = _utc_now() - timedelta(days=days)

    # Total runs y costo desde athlete_ai_insights (1 fila por run
    # exitoso). Para fail rate sumamos agent_runs con status=failed.
    result = await db.execute(
        text(
            """
            SELECT
              COUNT(*) AS n,
              COALESCE(SUM(JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.cost_usd_total')), 0) AS cost
            FROM athlete_ai_insights
            WHERE generated_at >= :cutoff
            """
        ),
        {"cutoff": cutoff},
    )
    first = getattr(result, "first", lambda: None)()
    if first is None:
        rows = result.fetchall() if hasattr(result, "fetchall") else []
        first = rows[0] if rows else None

    if first is not None and hasattr(first, "_mapping"):
        n_insights = int(first._mapping.get("n") or 0)
        cost_total = float(first._mapping.get("cost") or 0.0)
    elif first is not None:
        n_insights = int(getattr(first, "n", None) or first[0] or 0)
        cost_total = float(getattr(first, "cost", None) or first[1] or 0.0)
    else:
        n_insights = 0
        cost_total = 0.0

    # Latencias: lectura puntual desde aggregate.
    result2 = await db.execute(
        text(
            """
            SELECT
              CAST(JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.latency_ms_total') AS UNSIGNED) AS lat
            FROM athlete_ai_insights
            WHERE generated_at >= :cutoff
              AND JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.latency_ms_total') IS NOT NULL
            """
        ),
        {"cutoff": cutoff},
    )
    rows2 = (
        result2.fetchall()
        if hasattr(result2, "fetchall")
        else (result2.all() if hasattr(result2, "all") else [])
    )
    latencies: list[int] = []
    for r in rows2:
        try:
            if hasattr(r, "_mapping"):
                v = r._mapping.get("lat")
            else:
                v = getattr(r, "lat", None) or r[0]
            if v is not None:
                latencies.append(int(v))
        except (TypeError, ValueError):
            continue

    p50 = int(statistics.median(latencies)) if latencies else 0
    p95 = (
        int(statistics.quantiles(latencies, n=20, method="inclusive")[-1])
        if len(latencies) >= 2
        else (latencies[0] if latencies else 0)
    )

    # Fail rate: failed / (completed + rejected + failed)
    result3 = await db.execute(
        text(
            """
            SELECT status, COUNT(*) AS c
            FROM agent_runs
            WHERE started_at >= :cutoff
            GROUP BY status
            """
        ),
        {"cutoff": cutoff},
    )
    rows3 = (
        result3.fetchall()
        if hasattr(result3, "fetchall")
        else (result3.all() if hasattr(result3, "all") else [])
    )
    counts: dict[str, int] = {}
    for r in rows3:
        if hasattr(r, "_mapping"):
            counts[str(r._mapping.get("status"))] = int(r._mapping.get("c") or 0)
        else:
            st = getattr(r, "status", None) or r[0]
            c = getattr(r, "c", None) or r[1]
            counts[str(st)] = int(c)

    failed = counts.get("failed", 0)
    terminal = (
        counts.get("completed", 0)
        + counts.get("rejected", 0)
        + counts.get("failed", 0)
        + counts.get("cancelled", 0)
    )
    fail_rate = (failed / terminal) if terminal > 0 else 0.0

    # By prompt_version.
    result4 = await db.execute(
        text(
            """
            SELECT prompt_version,
                   COUNT(*) AS c,
                   COALESCE(SUM(JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.cost_usd_total')), 0) AS cost
            FROM athlete_ai_insights
            WHERE generated_at >= :cutoff
            GROUP BY prompt_version
            ORDER BY c DESC
            """
        ),
        {"cutoff": cutoff},
    )
    rows4 = (
        result4.fetchall()
        if hasattr(result4, "fetchall")
        else (result4.all() if hasattr(result4, "all") else [])
    )
    by_pv: list[AIUsageByPromptVersion] = []
    for r in rows4:
        if hasattr(r, "_mapping"):
            pv = r._mapping.get("prompt_version")
            c = int(r._mapping.get("c") or 0)
            cost = float(r._mapping.get("cost") or 0.0)
        else:
            pv = getattr(r, "prompt_version", None) or r[0]
            c = int(getattr(r, "c", None) or r[1] or 0)
            cost = float(getattr(r, "cost", None) or r[2] or 0.0)
        by_pv.append(
            AIUsageByPromptVersion(
                prompt_version=str(pv or "unknown"),
                run_count=c,
                cost_usd_total=cost,
            )
        )

    # Gasto por entrenador (§7.2) — aditivo; el servicio ya resuelve nombres
    # por lote, así que son dos queries más, nunca N+1.
    #
    # Hallazgo H3: el admin ve a todo el staff (visible_user_ids=None,
    # comportamiento histórico); un coach sólo ve identidad + gasto
    # individual del staff de SUS propios clubes — el resto se repliega en
    # una fila agregada "Otros clubes" sin nombres (ver
    # ``spend_by_user_last_30d``/``_coach_visible_staff_ids``).
    visible_user_ids = (
        None
        if current_user.role == UserRole.admin
        else await _coach_visible_staff_ids(db, current_user)
    )
    by_coach = [
        AIUsageByCoach(
            user_id=s.user_id,
            display_name=s.display_name,
            run_count=s.run_count,
            cost_usd_total=s.cost_usd_total,
        )
        for s in await spend_by_user_last_30d(
            db, days=days, visible_user_ids=visible_user_ids
        )
    ]

    return AIUsageResponse(
        window_days=days,
        run_count=n_insights,
        cost_usd_total=cost_total,
        latency_ms_p50=p50,
        latency_ms_p95=p95,
        fail_rate=round(fail_rate, 4),
        by_prompt_version=by_pv,
        by_coach=by_coach,
    )


# ---------------------------------------------------------------------------
# Panorama de temporada (PR3 unificación /competitions)
# ---------------------------------------------------------------------------


async def _resolve_panorama_club_id(
    db: AsyncSession,
    current_user: User,
    club_id_param: Optional[int],
) -> Optional[int]:
    """Resuelve el club para el panorama de temporada.

    - admin: usa ``club_id`` si se pasa (verificado a nivel existencia por la
      query); si se omite ⇒ ``None`` = panorama global (todos los clubes).
    - coach: ignora ``club_id`` ajeno y SIEMPRE usa su propio club (defensa:
      un coach no puede inspeccionar otro club). Si pasa un ``club_id`` del
      que no es miembro ⇒ 403.
    """
    if current_user.role == UserRole.admin:
        return club_id_param  # None ⇒ global

    # coach: resolver su club. Si pasa club_id, debe ser uno suyo.
    if club_id_param is not None:
        role = await user_club_role(db, current_user.id, club_id_param)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No eres miembro del club indicado",
            )
        return club_id_param

    stmt = (
        select(ClubMember.club_id)
        .where(ClubMember.user_id == current_user.id)
        .order_by(ClubMember.club_id)
        .limit(1)
    )
    res = await db.execute(stmt)
    first_club_id = res.scalar_one_or_none()
    if first_club_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No perteneces a ningún club.",
        )
    return int(first_club_id)


@router.get(
    "/insights/season/{year}",
    response_model=SeasonPanoramaResponse,
    summary="Panorama agregado de una temporada",
    description=(
        "Vista agregada por deportista a lo largo de todas las válidas de una "
        "temporada (válidas + podios + puntos + mejor posición). "
        "RBAC: coach/admin. Parents → 403. Una sola query agregada (sin N+1)."
    ),
    responses={
        200: {"model": SeasonPanoramaResponse},
        403: {"description": "Solo coach/admin."},
    },
)
async def season_panorama(
    year: int,
    club_id: Optional[int] = Query(
        default=None,
        ge=1,
        description=(
            "Club a consultar. Coach: opcional, se fuerza su club. "
            "Admin: opcional, si se omite es panorama global (todos los clubes)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> SeasonPanoramaResponse:
    """``GET /api/race-analysis/insights/season/{year}`` (coach/admin)."""
    resolved_club_id = await _resolve_panorama_club_id(db, current_user, club_id)

    rows = await fetch_season_panorama(db, season=year, club_id=resolved_club_id)

    items = [
        SeasonPanoramaAthleteItem(
            athlete_id=row.athlete_id,
            athlete_display_name=f"{row.first_name} {row.last_name}",
            races_count=row.races_count,
            wins=row.wins,
            podiums=row.podiums,
            best_position=row.best_position,
            total_points=row.total_points,
        )
        for row in rows
    ]

    return SeasonPanoramaResponse(
        season=year,
        total_athletes=len(items),
        items=items,
    )


# ---------------------------------------------------------------------------
# Re-trigger IA + flag stale (PR5 unificación /competitions)
# ---------------------------------------------------------------------------


class RunInvalidateResponse(_BaseModel):
    run_id: str
    stale: bool


class RunCancelResponse(_BaseModel):
    run_id: str
    state: RunState


@router.post(
    "/runs/{run_id}/invalidate",
    response_model=RunInvalidateResponse,
    summary="Marca un run de análisis como desactualizado (stale)",
    description=(
        "Marca el run como 'análisis desactualizado'. Idempotente. "
        "Usado tras una re-ingesta que cambió los resultados. NO re-ejecuta "
        "nada (D5: el re-trigger es manual). RBAC coach/admin del club."
    ),
    responses={
        200: {"model": RunInvalidateResponse},
        403: {"description": "Coach de otro club."},
        404: {"description": "Run no existe."},
    },
)
async def invalidate_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> RunInvalidateResponse:
    """``POST /api/race-analysis/runs/{run_id}/invalidate`` (coach/admin)."""
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run no encontrado")
    await ensure_run_club_access(db, run, current_user)
    await mark_run_stale(db, int(run["id"]))
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.agent_run,
        entity_id=int(run["id"]),
        actor=current_user,
        club_id=await _resolve_athlete_club(db, run.get("athlete_id")),
        athlete_id=run.get("athlete_id"),
        changed_fields=["stale_since"],
        meta={"stale": True},
    )
    return RunInvalidateResponse(run_id=run_id, stale=True)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunCancelResponse,
    summary="Descarta un análisis en curso o pendiente de revisión",
    description=(
        "Lleva un run vivo (``running`` / ``awaiting_hitl``) al estado "
        "terminal ``cancelled`` sin guardar ningún resultado. Es la única "
        "salida operativa para un run atascado en un gate HITL: la "
        "reconciliación de huérfanos sólo corre al arrancar el proceso, así "
        "que en una instancia viva un run pendiente no expira nunca. Tras "
        "cancelar, ``find_active_run`` deja de verlo y el coach puede volver "
        "a lanzar el análisis (desaparece el 409 de 'ya hay un run activo'). "
        "RBAC coach/admin del club."
    ),
    responses={
        200: {"model": RunCancelResponse},
        403: {"description": "Coach de otro club."},
        404: {"description": "Run no existe."},
        409: {"description": "Run ya está en estado terminal."},
    },
)
async def cancel_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> RunCancelResponse:
    """``POST /api/race-analysis/runs/{run_id}/cancel`` (coach/admin)."""
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run no encontrado")
    await ensure_run_club_access(db, run, current_user)

    db_status = str(run["status"])
    if db_status in _TERMINAL_DB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run en estado terminal '{db_status}', no se puede descartar",
        )

    # Evento de auditoría — el polling del frontend lo ve en el siguiente
    # ciclo. Va SIN ``node_name``: el timeline sólo reduce eventos con nodo,
    # y marcar el gate HITL como "done" daría a entender que el paso se
    # completó, cuando en realidad el coach lo descartó. El tipo es ``done``
    # porque el ENUM ``agentruneventtype`` no tiene un valor ``cancelled``
    # (ver migración 7a8b9c0d1e2f) y el run sí queda cerrado aquí.
    last_seq_val = await _last_seq(db, int(run["id"]))
    import json

    try:
        await db.execute(
            text(
                """
                INSERT INTO agent_run_events (
                    run_id, seq, event_type, node_name, payload_json, created_at
                ) VALUES (
                    :rid, :seq, 'done', NULL, :pl, :ts
                )
                """
            ),
            {
                "rid": int(run["id"]),
                "seq": last_seq_val + 1,
                "pl": json.dumps(
                    {
                        "reason": "cancelled_by_coach",
                        "previous_status": db_status,
                        "by_user_id": current_user.id,
                    },
                    ensure_ascii=False,
                ),
                "ts": _utc_now(),
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("cancel_run: insert del evento de cancelación falló")

    await _update_run_status(
        db,
        run_id,
        "cancelled",
        error_message="Análisis descartado por el coach.",
    )
    await record_audit(
        db,
        action=AuditAction.cancel,
        entity_type=AuditEntityType.agent_run,
        entity_id=int(run["id"]),
        actor=current_user,
        club_id=await _resolve_athlete_club(db, run.get("athlete_id")),
        athlete_id=run.get("athlete_id"),
        meta={"previous_status": db_status},
    )
    logger.info("cancel_run: run %s descartado (estado previo %s)", run_id, db_status)

    return RunCancelResponse(run_id=run_id, state=RunState.CANCELLED)


@router.post(
    "/runs/{run_id}/re-execute",
    response_model=StartRunResponse,
    summary="Re-ejecuta un análisis desactualizado (manual, D5)",
    description=(
        "Lanza un NUEVO run agéntico reutilizando los parámetros del run "
        "original (athlete, temporada, válidas). Acción MANUAL del coach con "
        "confirmación — NO hay cron ni auto-trigger (D5). RBAC coach/admin del club."
    ),
    responses={
        200: {"model": StartRunResponse},
        403: {"description": "Coach de otro club."},
        404: {"description": "Run no existe."},
        503: {"description": "AI deshabilitada o presupuesto excedido."},
    },
)
async def re_execute_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> StartRunResponse:
    """``POST /api/race-analysis/runs/{run_id}/re-execute`` (coach/admin)."""
    run = await _load_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run no encontrado")
    await ensure_run_club_access(db, run, current_user)

    # Reconstruir los parámetros originales desde input_json.
    import json as _json

    raw = run.get("input_json")
    if isinstance(raw, str):
        try:
            params = _json.loads(raw)
        except (ValueError, TypeError):
            params = {}
    elif isinstance(raw, dict):
        params = raw
    else:
        params = {}

    athlete_id = params.get("athlete_id")
    season = params.get("season")
    if athlete_id is None or season is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El run original no tiene parámetros suficientes para re-ejecutar.",
        )

    valida_nums = params.get("valida_nums") or None  # [] inválido → None = todas

    try:
        body = StartRunRequest(
            athlete_id=athlete_id,
            season=season,
            valida_nums=valida_nums,
            explain_mode=bool(params.get("explain_mode", False)),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Parámetros del run original inválidos: {exc}",
        )

    # Delegar al launcher canónico (valida AI_ENABLED, budget, backpressure).
    # El run viejo conserva su marca stale; el nuevo run lo supersede.
    # ``start_run`` ya deja su propia fila ``create`` para el run nuevo; esta
    # fila adicional ``execute`` es la que documenta la relación de
    # supersesión (§4.9: los tres verbos no son intercambiables).
    response = await start_run(body=body, db=db, current_user=current_user)
    _new_run = await _load_run(db, response.run_id)
    if _new_run is not None:
        await record_audit(
            db,
            action=AuditAction.execute,
            entity_type=AuditEntityType.agent_run,
            entity_id=int(_new_run["id"]),
            actor=current_user,
            club_id=await _resolve_athlete_club(db, athlete_id),
            athlete_id=athlete_id,
            meta={"supersedes_run_id": int(run["id"])},
        )
    return response


# ---------------------------------------------------------------------------
# T005: POST /race-events/{race_event_id}/runs — group analysis launch
# ---------------------------------------------------------------------------


@router.post(
    "/race-events/{race_event_id}/runs",
    response_model=GroupRunLaunchResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": GroupRunLaunchResponse},
        403: {"description": "Rol no permitido."},
        404: {"description": "Evento no encontrado."},
        422: {"description": "Evento sin resultados importados o sin válida asignada."},
        429: {"description": "Todos los análisis bloqueados por backpressure."},
        503: {"description": "AI deshabilitada o presupuesto excedido."},
    },
)
async def launch_race_event_group(
    race_event_id: int,
    body: GroupRunLaunchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> Any:
    """Lanza análisis agéntico para todos (o un subset) de los atletas de un evento.

    Retorna inmediatamente con el estado de cada intento de lanzamiento.
    HTTP 200 incluso con starts parciales; 429 sólo cuando CERO pudieron iniciar
    por backpressure; 503 cuando el presupuesto mensual está agotado.
    """
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible (AI_ENABLED=false)",
        )

    # Budget guard — single up-front check (the service never calls it).
    try:
        await check_budget(db)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.user_message,
        )

    from app.services.race.group_launch import (
        EventHasNoResultsError,
        EventNotAnalyzableError,
        RaceEventNotFoundError,
        launch_group,
    )

    try:
        response = await launch_group(
            db=db,
            race_event_id=race_event_id,
            athlete_ids=body.athlete_ids,
            # Hallazgo H1 (T080): una válida la corren menores de varios
            # clubes. Sin este filtro el lanzamiento grupal abría una corrida
            # por cada menor del evento, incluidas las de otros clubes, y
            # mandaba sus nombres al proveedor de IA. El administrador manda
            # `None` y sigue viendo todo.
            club_ids=_launcher_club_ids(current_user),
            explain_mode=body.explain_mode,
            requested_by_user_id=current_user.id,
        )
    except RaceEventNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento de carrera no encontrado.",
        )
    except EventNotAnalyzableError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La competencia no tiene número de válida asignado.",
        )
    except EventHasNoResultsError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La competencia no tiene resultados importados.",
        )

    # All-backpressure → 429.
    if (
        response.started_count == 0
        and response.items
        and all(i.outcome == GroupRunOutcome.backpressure for i in response.items)
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos.",
        )

    return response


# ---------------------------------------------------------------------------
# T006: GET /race-events/{race_event_id}/runs — list runs for refresh recovery
# ---------------------------------------------------------------------------


@router.get(
    "/race-events/{race_event_id}/runs",
    response_model=RaceEventRunsResponse,
    responses={
        200: {"model": RaceEventRunsResponse},
        403: {"description": "Rol no permitido."},
        404: {"description": "Evento no encontrado."},
    },
)
async def list_race_event_runs(
    race_event_id: int,
    active_only: bool = Query(
        default=True,
        description=(
            "Si True (default), sólo retorna runs activos (running/awaiting_hitl). "
            "Si False, incluye también runs terminales de los últimos 7 días."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
) -> RaceEventRunsResponse:
    """Lista los runs de análisis asociados a un evento de carrera.

    Útil para recuperar el estado tras recargar la UI (refresh recovery).
    """
    from app.services.race.group_launch import (
        EventNotAnalyzableError,
        RaceEventNotFoundError,
        list_event_runs,
    )

    try:
        # Hallazgo H2 (T080): este listado resuelve nombres de deportistas
        # a partir de los resultados del evento. Sin acotarlo por club le
        # entregaba a un entrenador de otro club el nombre completo de una
        # menor ajena junto con un `run_id` válido — que es, además, la única
        # forma práctica de conseguir ids de corrida ajenos, porque son uuid4.
        return await list_event_runs(
            db=db,
            race_event_id=race_event_id,
            active_only=active_only,
            club_ids=_launcher_club_ids(current_user),
        )
    except RaceEventNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento de carrera no encontrado.",
        )
    except EventNotAnalyzableError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento de carrera no encontrado.",
        )


__all__ = ["router"]
