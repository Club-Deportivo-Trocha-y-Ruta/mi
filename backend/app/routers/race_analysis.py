"""Router ``/api/race-analysis/*`` — capa HTTP del módulo agéntico race-results v2.

Endpoints (F5, design.md §9):
- ``POST /runs`` — iniciar análisis (returns run_id + status_url).
- ``GET /runs/{run_id}/status`` — polling cada 2s, slicing por seq.
- ``POST /runs/{run_id}/hitl/{step_id}`` — coach aprueba/rechaza/edita.
- ``GET /runs/{run_id}/result`` — output final (AnalysisOutput JSON).
- ``GET /runs/{run_id}/pdf`` — renderiza PDF con weasyprint.
- ``POST /chat`` — chat consultivo (sin streaming, JSON completo).
- ``GET /admin/ai-usage?days=30`` — métricas agregadas (admin).

Convenciones:
- RBAC: coach + admin (excepto admin/* → admin only). Padres NO acceden.
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
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, require_role
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.race_ai import (
    AIUsageByPromptVersion,
    AIUsageResponse,
    ChatRequest,
    HITLDecision,
    HITLDecisionRequest,
    HITLDecisionResponse,
    RunEvent,
    RunState,
    RunStatusResponse,
    StartRunRequest,
    StartRunResponse,
)
from app.services.race.ai.budget_guard import (
    BudgetExceededError,
    check_budget,
)
from app.services.race.agents.pricing import PROMPT_VERSION_ANALYST_V2
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
from app.services.permissions import user_club_role
from app.services.race.season_panorama import fetch_season_panorama
from app.services.race.run_staleness import mark_run_stale
from app.models.club import ClubMember
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

# Heurística de progreso: 13 nodos en el grafo (F4).
_GRAPH_NODE_COUNT = 13

# Cap defensivo de eventos por polling response — evita payloads enormes
# si un cliente llama con since=0 después de un run largo.
_EVENTS_PER_POLL_MAX = 200


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


_coach_or_admin = require_role([UserRole.coach, UserRole.admin])
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
    """Carga la fila de ``agent_runs`` por external_run_id."""
    result = await db.execute(
        text(
            """
            SELECT id, external_run_id, status, started_at, finished_at,
                   input_json, final_output_json, error_message,
                   requested_by_user_id, explain_mode
            FROM agent_runs
            WHERE external_run_id = :rid
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
    }


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

    events = list((result_state or {}).get("events") or [])

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


def _ensure_run_owner(run: dict[str, Any], user: User) -> None:
    """Solo el owner o admin pueden acceder al run."""
    if user.role == UserRole.admin:
        return
    if run.get("requested_by_user_id") != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este run",
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

    # F8A: Budget guard — chequea ANTES de insertar agent_runs y adquirir
    # el semáforo. Si el gasto de los últimos 30d excede el presupuesto,
    # respondemos 503 con mensaje claro. Runs en curso completan.
    try:
        await check_budget(db)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Presupuesto mensual de IA excedido: "
                f"${exc.current_usd:.4f} de ${exc.budget_usd:.2f}. "
                "Reintenta más tarde o contacta al administrador."
            ),
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
                    checkpoint_thread_id, explain_mode
                ) VALUES (
                    :rid, :gn, :pv, :sa, 'running', :inp, :uid, :tid, :em
                )
                """
            ),
            {
                "rid": run_id,
                "gn": "race-analyst",
                "pv": PROMPT_VERSION_ANALYST_V2,
                "sa": started_at,
                "inp": json.dumps(input_payload, ensure_ascii=False, default=str),
                "uid": current_user.id,
                "tid": run_id,  # estable durante el lifecycle.
                "em": 1 if body.explain_mode else 0,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("start_run: insert agent_runs falló")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear el run: {type(exc).__name__}",
        )

    # Calcular edad del atleta para inyectarla en el state del grafo.
    # Si el atleta no existe (body.athlete_id inválido), continuamos sin edad
    # y el nodo analyst_agent emitirá un warning explícito.
    athlete_age: Optional[int] = None
    if body.athlete_id is not None:
        _athlete_result = await db.execute(
            select(Athlete).where(Athlete.id == body.athlete_id)
        )
        _athlete = _athlete_result.scalar_one_or_none()
        if _athlete is not None and _athlete.birth_date is not None:
            athlete_age = int((date.today() - _athlete.birth_date).days / 365.25)
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
        "prompt_version": PROMPT_VERSION_ANALYST_V2,
    }
    if athlete_age is not None:
        initial_state["athlete_age"] = athlete_age

    async def _on_complete(
        rid: str,
        exc: Optional[BaseException],
        result_state: Optional[dict[str, Any]],
    ) -> None:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                await _finalize_run(session, rid, exc, result_state)
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
        403: {"description": "No eres el owner del run."},
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
    _ensure_run_owner(run, current_user)

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

    return RunStatusResponse(
        run_id=run_id,
        state=state,
        progress_pct=progress_pct,
        current_node=current_node,
        started_at=_aware(run["started_at"]),
        estimated_seconds_remaining=eta,
        new_events=new_events,
        last_seq=last_seq,
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
        403: {"description": "No eres el owner del run."},
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
    _ensure_run_owner(run, current_user)

    # Validación de estado: debe estar awaiting_hitl o running (si el
    # status no se actualizó aún por el grafo). Mantenemos permisivo:
    # si está en estado terminal, 409.
    db_status = str(run["status"])
    if db_status in {"completed", "rejected", "failed", "cancelled"}:
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

    async def _on_complete(
        rid: str,
        exc: Optional[BaseException],
        result_state: Optional[dict[str, Any]],
    ) -> None:
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                await _finalize_run(session, rid, exc, result_state)
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
    )


# ---------------------------------------------------------------------------
# Endpoint 4: GET /runs/{run_id}/result
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/result",
    responses={
        200: {"description": "AnalysisOutput JSON."},
        403: {"description": "No eres el owner."},
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
    _ensure_run_owner(run, current_user)

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
    _ensure_run_owner(run, current_user)

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
        503: {"description": "AI deshabilitada."},
    },
)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(_coach_or_admin),
    chat_agent=Depends(get_race_chat_agent),
) -> ChatResponse:
    """Chat consultivo con tools (RAG + insights + resultados).

    Sin streaming — respuesta completa JSON. Sesiones in-memory con TTL
    de 1h (ver :mod:`app.services.race.agents.chat`).
    """
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible (AI_ENABLED=false)",
        )

    import asyncio as _asyncio

    try:
        response = await chat_agent.chat(
            session_id=body.session_id,
            query=body.query,
            athlete_id=body.athlete_id,
        )
    except (TimeoutError, _asyncio.TimeoutError) as exc:
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
        403: {"description": "Solo admin."},
    },
)
async def admin_ai_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_admin_only),
) -> AIUsageResponse:
    """Métricas agregadas de uso de IA en ventana ``days``.

    Lee desde ``athlete_ai_insights`` — fuente de verdad para
    cost/latency en MVP (Langfuse diferido a F8B).
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

    return AIUsageResponse(
        window_days=days,
        run_count=n_insights,
        cost_usd_total=cost_total,
        latency_ms_p50=p50,
        latency_ms_p95=p95,
        fail_rate=round(fail_rate, 4),
        by_prompt_version=by_pv,
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


@router.post(
    "/runs/{run_id}/invalidate",
    response_model=RunInvalidateResponse,
    summary="Marca un run de análisis como desactualizado (stale)",
    description=(
        "Marca el run como 'análisis desactualizado'. Idempotente. "
        "Usado tras una re-ingesta que cambió los resultados. NO re-ejecuta "
        "nada (D5: el re-trigger es manual). RBAC coach/admin + owner."
    ),
    responses={
        200: {"model": RunInvalidateResponse},
        403: {"description": "No eres owner del run."},
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
    _ensure_run_owner(run, current_user)
    await mark_run_stale(db, int(run["id"]))
    return RunInvalidateResponse(run_id=run_id, stale=True)


@router.post(
    "/runs/{run_id}/re-execute",
    response_model=StartRunResponse,
    summary="Re-ejecuta un análisis desactualizado (manual, D5)",
    description=(
        "Lanza un NUEVO run agéntico reutilizando los parámetros del run "
        "original (athlete, temporada, válidas). Acción MANUAL del coach con "
        "confirmación — NO hay cron ni auto-trigger (D5). RBAC coach/admin + owner."
    ),
    responses={
        200: {"model": StartRunResponse},
        403: {"description": "No eres owner del run."},
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
    _ensure_run_owner(run, current_user)

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
    return await start_run(body=body, db=db, current_user=current_user)


__all__ = ["router"]
