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
- Persistencia: ORM via :mod:`app.services.race.ai.runs` (refactor BE-A1
  eliminó el SQL crudo previo, manteniendo paridad funcional).
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
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, require_role
from app.models.agent_run import AgentRun, AgentRunStatus
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
from app.services.race.ai import runs as runs_service
from app.services.race.ai.budget_guard import (
    BudgetExceededError,
    check_budget,
)
from app.services.race.ai.runner import (
    RunBackpressureError,
    resume_run,
    submit_run,
)
from app.services.race.schemas import ChatResponse

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
# Helpers locales (sin SQL crudo)
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Any) -> datetime:
    """Asegura tz=UTC en datetimes que vienen de MySQL DATETIME (naive)."""
    if dt is None:
        return _utc_now()
    if not isinstance(dt, datetime):
        return _utc_now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _event_to_run_event(ev) -> RunEvent:
    """Adapta una fila ORM ``AgentRunEvent`` al schema HTTP ``RunEvent``."""
    payload = ev.payload_json
    # JSON nullable o serializado en algunos dialectos: tolerante a ambos.
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = {"_raw": payload}
    if not isinstance(payload, dict):
        payload = {"_value": payload} if payload is not None else {}

    event_type_val = ev.event_type
    if hasattr(event_type_val, "value"):
        event_type_val = event_type_val.value

    return RunEvent(
        seq=int(ev.seq),
        ts=_aware(ev.created_at),
        type=str(event_type_val),
        node=str(ev.node_name) if ev.node_name else None,
        payload=payload,
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
        new_status: str = "failed"
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

    run = await runs_service.load_run(db, external_run_id)
    if run is None:
        logger.error("_finalize_run: run %s no existe", external_run_id)
        return
    run_db_id = int(run.id)

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

    await runs_service.persist_events(db, run_db_id, events)
    await runs_service.update_run_status(
        db,
        run_db_id,
        status=new_status,
        error_message=err,
        final_output_json=final_payload,
    )


def _ensure_run_owner(run: AgentRun, user: User) -> None:
    """Solo el owner o admin pueden acceder al run."""
    if user.role == UserRole.admin:
        return
    if run.requested_by_user_id != user.id:
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

    input_payload = {
        "athlete_id": body.athlete_id,
        "season": body.season,
        "valida_nums": body.valida_nums,
        "explain_mode": body.explain_mode,
    }

    # Insert agent_runs (status=running). El run_id es el thread_id del
    # checkpointer LangGraph para reanudación post-HITL.
    try:
        await runs_service.create_run(
            db,
            external_run_id=run_id,
            graph_name="race-analyst",
            prompt_version="race_analyst_v1",
            requested_by_user_id=current_user.id,
            athlete_id=body.athlete_id,
            checkpoint_thread_id=run_id,
            input_json=input_payload,
            explain_mode=body.explain_mode,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("start_run: insert agent_runs falló")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear el run: {type(exc).__name__}",
        )

    initial_state = {
        "athlete_id": body.athlete_id,
        "season": body.season,
        "valida_nums": body.valida_nums,
        "coach_id": current_user.id,
        "explain_mode": body.explain_mode,
        "run_id": run_id,
    }

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
            await runs_service.update_run_status_by_external_id(
                db,
                run_id,
                status=AgentRunStatus.cancelled,
                error_message="backpressure: no slots",
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
    run = await runs_service.load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    _ensure_run_owner(run, current_user)

    last_seq_val = await runs_service.last_seq(db, int(run.id))
    db_status_str = (
        run.status.value if isinstance(run.status, AgentRunStatus) else str(run.status)
    )

    # ETag basado en last_seq + status → cambia con cualquier evento o
    # transición de estado. Más barato que hashear el response completo.
    etag = f'W/"{run_id}:{last_seq_val}:{db_status_str}"'
    if_none_match = request.headers.get("if-none-match")
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache"
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})

    state = _DB_STATUS_TO_RUN_STATE.get(db_status_str, RunState.RUNNING)
    current_node = (
        await runs_service.last_node(db, int(run.id))
        if state == RunState.RUNNING
        else None
    )

    raw_events = await runs_service.load_events_since(
        db, int(run.id), since_seq=since, limit=_EVENTS_PER_POLL_MAX
    )
    new_events = [_event_to_run_event(ev) for ev in raw_events]

    # Heurística de progreso: cuento distinct nodos completados.
    # Aproximación barata: progress = min(100, last_seq / (13*2) * 100)
    # porque cada nodo emite ~2 eventos (start + end).
    progress_pct = min(100, int(round((last_seq_val / (_GRAPH_NODE_COUNT * 2)) * 100)))
    if state in {RunState.DONE, RunState.FAILED, RunState.CANCELLED}:
        progress_pct = 100

    # Estimación tiempo restante: heurística simple.
    if state == RunState.RUNNING:
        eta = max(0, 30 - int((_utc_now() - _aware(run.started_at)).total_seconds()))
    else:
        eta = 0

    return RunStatusResponse(
        run_id=run_id,
        state=state,
        progress_pct=progress_pct,
        current_node=current_node,
        started_at=_aware(run.started_at),
        estimated_seconds_remaining=eta,
        new_events=new_events,
        last_seq=last_seq_val,
    )


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
    run = await runs_service.load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    _ensure_run_owner(run, current_user)

    # Validación de estado: debe estar awaiting_hitl o running (si el
    # status no se actualizó aún por el grafo). Mantenemos permisivo:
    # si está en estado terminal, 409.
    db_status_str = (
        run.status.value if isinstance(run.status, AgentRunStatus) else str(run.status)
    )
    if db_status_str in {"completed", "rejected", "failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run en estado terminal '{db_status_str}', no acepta HITL",
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
    try:
        await runs_service.insert_hitl_event(
            db,
            int(run.id),
            node_name="hitl_gate_review",
            payload={
                "decision": body.decision.value,
                "step_id": step_id,
                "has_edits": bool(body.edits),
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("submit_hitl_decision: insert evento hitl_response falló")

    # Reanudar grafo en background.
    async def _on_complete(
        rid: str,
        exc: Optional[BaseException],
        result_state: Optional[dict[str, Any]],
    ) -> None:
        from app.database import AsyncSessionLocal

        final_payload = _extract_final_output(result_state) if exc is None else None
        graph_status = (result_state or {}).get("status") if exc is None else None

        if exc is not None:
            new_status = "failed"
            err: Optional[str] = f"{type(exc).__name__}: {str(exc)[:500]}"
        elif body.decision == HITLDecision.REJECT:
            new_status = "rejected"
            err = None
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

        async with AsyncSessionLocal() as session:
            try:
                await runs_service.update_run_status_by_external_id(
                    session,
                    rid,
                    status=new_status,
                    error_message=err,
                    final_output_json=final_payload,
                )
                await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("_on_complete hitl: update falló para %s", rid)

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


def _decode_final_output(value: Any) -> dict[str, Any] | None:
    """Tolerante a ``final_output_json`` serializado o ya dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json

        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {"raw_markdown": value, "_warning": "final_output_json mal formado"}
    return None


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
    run = await runs_service.load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    _ensure_run_owner(run, current_user)

    db_status_str = (
        run.status.value if isinstance(run.status, AgentRunStatus) else str(run.status)
    )
    if db_status_str == "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run falló: {run.error_message or 'sin detalle'}",
        )
    if db_status_str not in {"completed", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run aún no terminado (status={db_status_str})",
        )

    final = _decode_final_output(run.final_output_json)
    if final is None:
        final = {
            "raw_markdown": "(sin output persistido)",
            "sections": {},
            "recommendations": [],
            "risk_flags": [],
        }

    return {
        "run_id": run_id,
        "status": db_status_str,
        "final": final,
        "finished_at": _aware(run.finished_at) if run.finished_at else None,
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
    run = await runs_service.load_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run no encontrado",
        )
    _ensure_run_owner(run, current_user)

    db_status_str = (
        run.status.value if isinstance(run.status, AgentRunStatus) else str(run.status)
    )
    if db_status_str not in {"completed", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run aún no completado",
        )

    final = _decode_final_output(run.final_output_json) or {}
    md = final.get("raw_markdown") or "_(sin contenido)_"

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

    # Markdown → HTML básico (sin parser markdown para evitar deps): el
    # md viene ya como markdown. Para MVP, lo envolvemos en <pre>
    # preservando estructura. TODO: integrar python-markdown si el coach
    # pide rendering rico.
    import html as html_mod

    safe_md = html_mod.escape(md)
    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Análisis race {run_id[:8]}</title>
<style>
  body {{ font-family: 'Helvetica', sans-serif; margin: 2cm; }}
  header {{ border-bottom: 2px solid #2c5282; padding-bottom: 1em; }}
  pre {{ white-space: pre-wrap; font-family: 'Helvetica', sans-serif; font-size: 11pt; }}
  footer {{ position: fixed; bottom: 0; left: 0; right: 0; text-align: center; font-size: 9pt; color: #666; }}
</style>
</head>
<body>
<header>{logo_html}<p><strong>Análisis de carrera</strong> · Run {run_id[:8]}</p></header>
<pre>{safe_md}</pre>
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

    metrics = await runs_service.admin_usage_metrics(db, since=cutoff)

    by_pv = [
        AIUsageByPromptVersion(
            prompt_version=row["prompt_version"],
            run_count=row["run_count"],
            cost_usd_total=row["cost_usd_total"],
        )
        for row in metrics["by_prompt_version"]
    ]

    return AIUsageResponse(
        window_days=days,
        run_count=metrics["run_count"],
        cost_usd_total=metrics["cost_usd_total"],
        latency_ms_p50=metrics["latency_ms_p50"],
        latency_ms_p95=metrics["latency_ms_p95"],
        fail_rate=metrics["fail_rate"],
        by_prompt_version=by_pv,
    )


__all__ = ["router"]
