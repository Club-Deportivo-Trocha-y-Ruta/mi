"""Service ORM para gestión de ``agent_runs`` + ``agent_run_events``.

Antes del refactor BE-A1 el router ``routers/race_analysis.py`` accedía
estas tablas con SQL crudo (``sqlalchemy.text``) — patrón intencional
documentado en el modelo pero que arrastraba >300 LOC defensivos
(parse de Row tuples vs FakeResult vs mappings, JSON dump manual).

Este módulo expone una API ORM idiomática, equivalente y testeable con
SQLAlchemy real (SQLite in-memory o MySQL). Convenciones:

* Funciones libres ``async def`` que reciben ``AsyncSession``. No commit
  interno — el caller decide la unidad de trabajo (transacciones HTTP
  cierran con ``get_db`` dependency).
* Idempotencia explícita en :func:`persist_events` (filtra por
  ``seq > MAX(seq)``).
* Privacidad: no se loguea payload en ningún punto. El campo
  ``payload_json`` puede contener pseudónimos pero NO PII.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.agent_run_event import AgentRunEvent, AgentRunEventType
from app.models.athlete_ai_insight import AthleteAiInsight

logger = logging.getLogger(__name__)


# Mapeo nombres in-memory (``app.services.race.ai.events``) → ENUM físico
# de ``agent_run_events.event_type``. Cualquier nombre fuera de los
# valores del ENUM se persiste como ``error`` para evitar DataError.
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_event_type(raw: str) -> AgentRunEventType:
    """Mapea string in-memory al enum DB. Desconocidos → ``error``."""
    db_value = _EVENT_TYPE_TO_DB.get(raw, "error")
    return AgentRunEventType(db_value)


# ---------------------------------------------------------------------------
# CRUD básico
# ---------------------------------------------------------------------------


async def create_run(
    db: AsyncSession,
    *,
    external_run_id: str,
    graph_name: str,
    prompt_version: str,
    requested_by_user_id: int,
    athlete_id: int | None = None,
    checkpoint_thread_id: str | None = None,
    input_json: dict | None = None,
    explain_mode: bool = False,
    started_at: datetime | None = None,
) -> AgentRun:
    """Crea una nueva fila ``agent_runs`` con ``status=running``.

    No hace commit: el caller decide. Devuelve la instancia ORM con
    ``id`` poblado vía ``flush``.
    """
    now = started_at or _utc_now()
    run = AgentRun(
        external_run_id=external_run_id,
        graph_name=graph_name,
        prompt_version=prompt_version,
        started_at=now,
        status=AgentRunStatus.running,
        requested_by_user_id=requested_by_user_id,
        athlete_id=athlete_id,
        checkpoint_thread_id=checkpoint_thread_id or external_run_id,
        input_json=input_json or {},
        explain_mode=explain_mode,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    await db.flush()
    return run


async def load_run(db: AsyncSession, external_run_id: str) -> AgentRun | None:
    """Carga un run por ``external_run_id`` (None si no existe)."""
    stmt = select(AgentRun).where(AgentRun.external_run_id == external_run_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def load_events_since(
    db: AsyncSession,
    run_id: int,
    since_seq: int,
    limit: int = 200,
) -> list[AgentRunEvent]:
    """Devuelve eventos con ``seq > since_seq`` ordenados ascendentemente."""
    stmt = (
        select(AgentRunEvent)
        .where(AgentRunEvent.run_id == run_id, AgentRunEvent.seq > since_seq)
        .order_by(AgentRunEvent.seq.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def last_seq(db: AsyncSession, run_id: int) -> int:
    """Máximo ``seq`` emitido para el run. ``0`` si aún no hay eventos."""
    stmt = select(func.coalesce(func.max(AgentRunEvent.seq), 0)).where(
        AgentRunEvent.run_id == run_id
    )
    result = await db.execute(stmt)
    value = result.scalar_one()
    return int(value or 0)


async def last_node(db: AsyncSession, run_id: int) -> Optional[str]:
    """Último ``node_name`` emitido (cualquier tipo de evento)."""
    stmt = (
        select(AgentRunEvent.node_name)
        .where(AgentRunEvent.run_id == run_id)
        .order_by(AgentRunEvent.seq.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return row[0]


# ---------------------------------------------------------------------------
# Persistencia masiva de eventos (idempotente)
# ---------------------------------------------------------------------------


async def persist_events(
    db: AsyncSession,
    run_id: int,
    events: Iterable[dict[str, Any]],
) -> int:
    """Inserta eventos in-memory en ``agent_run_events``.

    Idempotente: ignora eventos con ``seq <= MAX(seq)`` actual. Devuelve
    el número de filas insertadas.

    El parámetro ``events`` acepta diccionarios con claves
    ``seq``, ``ts`` (str ISO8601 o datetime), ``type``, ``node`` (opt),
    ``payload`` (dict).
    """
    events_list = list(events)
    if not events_list:
        return 0

    existing = await last_seq(db, run_id)
    inserted = 0
    fallback_ts = _utc_now()

    for ev in events_list:
        try:
            seq = int(ev.get("seq") or 0)
        except (TypeError, ValueError):
            continue
        if seq <= existing:
            continue

        type_raw = str(ev.get("type") or "")
        event_type = _normalize_event_type(type_raw)
        node = ev.get("node")
        payload = ev.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"_value": payload}

        # Preservamos el ts original cuando viene parseable.
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

        db.add(
            AgentRunEvent(
                run_id=run_id,
                seq=seq,
                event_type=event_type,
                node_name=node,
                payload_json=payload,
                created_at=ts_value,
            )
        )
        inserted += 1

    if inserted:
        await db.flush()
    return inserted


# ---------------------------------------------------------------------------
# Update de estado (terminal o parcial)
# ---------------------------------------------------------------------------


_TERMINAL_STATUSES = {
    AgentRunStatus.completed,
    AgentRunStatus.rejected,
    AgentRunStatus.failed,
    AgentRunStatus.cancelled,
}


def _coerce_status(value: AgentRunStatus | str) -> AgentRunStatus:
    if isinstance(value, AgentRunStatus):
        return value
    return AgentRunStatus(value)


async def update_run_status(
    db: AsyncSession,
    run_id: int,
    *,
    status: AgentRunStatus | str,
    finished_at: datetime | None = None,
    error_message: str | None = None,
    final_output_json: dict | None = None,
    cost_usd: Decimal | float | None = None,
) -> None:
    """Actualiza columnas mutables de ``agent_runs``.

    Sigue la semántica COALESCE del SQL original: si un campo se pasa
    como ``None`` se preserva el valor actual de la fila.
    """
    new_status = _coerce_status(status)

    values: dict[str, Any] = {"status": new_status, "updated_at": _utc_now()}
    if finished_at is not None:
        values["finished_at"] = finished_at
    elif new_status in _TERMINAL_STATUSES:
        # Si entramos a estado terminal sin finished_at explícito, ponemos now().
        values["finished_at"] = _utc_now()
    if error_message is not None:
        values["error_message"] = error_message
    if final_output_json is not None:
        values["final_output_json"] = final_output_json
    if cost_usd is not None:
        values["cost_usd"] = (
            cost_usd if isinstance(cost_usd, Decimal) else Decimal(str(cost_usd))
        )

    stmt = update(AgentRun).where(AgentRun.id == run_id).values(**values)
    await db.execute(stmt)


async def update_run_status_by_external_id(
    db: AsyncSession,
    external_run_id: str,
    *,
    status: AgentRunStatus | str,
    finished_at: datetime | None = None,
    error_message: str | None = None,
    final_output_json: dict | None = None,
    cost_usd: Decimal | float | None = None,
) -> None:
    """Versión que resuelve el run por ``external_run_id`` antes de updatear."""
    run = await load_run(db, external_run_id)
    if run is None:
        logger.error("update_run_status_by_external_id: run %s no existe", external_run_id)
        return
    await update_run_status(
        db,
        run.id,
        status=status,
        finished_at=finished_at,
        error_message=error_message,
        final_output_json=final_output_json,
        cost_usd=cost_usd,
    )


async def finalize_run(
    db: AsyncSession,
    run_id: int,
    *,
    status: AgentRunStatus | str,
    final_output_json: dict | None = None,
    error_message: str | None = None,
    cost_usd: Decimal | float | None = None,
) -> AgentRun | None:
    """Cierra un run aplicando ``finished_at=utc_now()`` automático.

    Devuelve la instancia recargada o ``None`` si no existe.
    """
    await update_run_status(
        db,
        run_id,
        status=status,
        finished_at=_utc_now(),
        error_message=error_message,
        final_output_json=final_output_json,
        cost_usd=cost_usd,
    )
    stmt = select(AgentRun).where(AgentRun.id == run_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Insert de eventos HITL puntuales
# ---------------------------------------------------------------------------


async def insert_hitl_event(
    db: AsyncSession,
    run_id: int,
    *,
    node_name: str,
    payload: dict,
) -> AgentRunEvent:
    """Inserta un evento ``hitl_response`` con ``seq = last_seq + 1``."""
    next_seq = await last_seq(db, run_id) + 1
    ev = AgentRunEvent(
        run_id=run_id,
        seq=next_seq,
        event_type=AgentRunEventType.hitl_response,
        node_name=node_name,
        payload_json=payload or {},
        created_at=_utc_now(),
    )
    db.add(ev)
    await db.flush()
    return ev


# ---------------------------------------------------------------------------
# Admin: métricas agregadas para /admin/ai-usage
# ---------------------------------------------------------------------------


def _extract_aggregate_value(snapshot: Any, key: str) -> Any:
    """Lee ``aggregate.<key>`` de ``metrics_snapshot_json``.

    El campo puede llegar deserializado (dict) o como string crudo
    (depende del dialecto). Tolerante a ambos.
    """
    if snapshot is None:
        return None
    data = snapshot
    if isinstance(snapshot, str):
        import json as _json

        try:
            data = _json.loads(snapshot)
        except (ValueError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    aggregate = data.get("aggregate")
    if not isinstance(aggregate, dict):
        return None
    return aggregate.get(key)


async def admin_usage_metrics(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Métricas agregadas para el endpoint admin.

    Retorna un dict con la forma esperada por ``AIUsageResponse``:

    .. code-block:: python

        {
            "run_count": int,
            "cost_usd_total": float,
            "latency_ms_p50": int,
            "latency_ms_p95": int,
            "fail_rate": float,
            "by_prompt_version": [
                {"prompt_version": str, "run_count": int, "cost_usd_total": float},
                ...
            ],
        }
    """
    # 1) Insights → fuente de verdad para cost + latency.
    insights_stmt = select(AthleteAiInsight)
    if since is not None:
        insights_stmt = insights_stmt.where(AthleteAiInsight.generated_at >= since)
    if until is not None:
        insights_stmt = insights_stmt.where(AthleteAiInsight.generated_at <= until)

    result = await db.execute(insights_stmt)
    insights = list(result.scalars().all())

    run_count = len(insights)
    cost_total = 0.0
    latencies: list[int] = []
    by_pv: dict[str, dict[str, Any]] = {}

    for ins in insights:
        snap = ins.metrics_snapshot_json
        cost = _extract_aggregate_value(snap, "cost_usd_total")
        if cost is not None:
            try:
                cost_total += float(cost)
            except (TypeError, ValueError):
                pass

        lat = _extract_aggregate_value(snap, "latency_ms_total")
        if lat is not None:
            try:
                latencies.append(int(lat))
            except (TypeError, ValueError):
                pass

        pv = getattr(ins, "prompt_version", None) or "unknown"
        entry = by_pv.setdefault(
            pv, {"prompt_version": pv, "run_count": 0, "cost_usd_total": 0.0}
        )
        entry["run_count"] += 1
        if cost is not None:
            try:
                entry["cost_usd_total"] += float(cost)
            except (TypeError, ValueError):
                pass

    p50 = int(statistics.median(latencies)) if latencies else 0
    if len(latencies) >= 2:
        p95 = int(statistics.quantiles(latencies, n=20, method="inclusive")[-1])
    elif latencies:
        p95 = int(latencies[0])
    else:
        p95 = 0

    # 2) Fail rate → desde agent_runs por status.
    runs_stmt = select(AgentRun.status, func.count(AgentRun.id))
    if since is not None:
        runs_stmt = runs_stmt.where(AgentRun.started_at >= since)
    if until is not None:
        runs_stmt = runs_stmt.where(AgentRun.started_at <= until)
    runs_stmt = runs_stmt.group_by(AgentRun.status)

    runs_result = await db.execute(runs_stmt)
    counts: dict[str, int] = {}
    for status_val, c in runs_result.all():
        # ``status_val`` puede ser AgentRunStatus o str según el dialecto.
        key = status_val.value if isinstance(status_val, AgentRunStatus) else str(status_val)
        counts[key] = int(c or 0)

    failed = counts.get("failed", 0)
    terminal = (
        counts.get("completed", 0)
        + counts.get("rejected", 0)
        + counts.get("failed", 0)
        + counts.get("cancelled", 0)
    )
    fail_rate = (failed / terminal) if terminal > 0 else 0.0

    # Orden estable: by run_count desc (compat con SQL ORDER BY c DESC).
    by_pv_list = sorted(
        by_pv.values(), key=lambda d: d["run_count"], reverse=True
    )

    return {
        "run_count": run_count,
        "cost_usd_total": cost_total,
        "latency_ms_p50": p50,
        "latency_ms_p95": p95,
        "fail_rate": round(fail_rate, 4),
        "by_prompt_version": by_pv_list,
    }


__all__ = [
    "AgentRun",
    "AgentRunEvent",
    "AgentRunEventType",
    "create_run",
    "load_run",
    "load_events_since",
    "last_seq",
    "last_node",
    "persist_events",
    "update_run_status",
    "update_run_status_by_external_id",
    "finalize_run",
    "insert_hitl_event",
    "admin_usage_metrics",
]
