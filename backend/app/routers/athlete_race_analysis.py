"""Router ``/api/athletes/{athlete_id}/race-analysis/*`` (BE-2).

Fachada legible (perfil del atleta) sobre el módulo race-results v2.
Reaprovecha el runner agéntico de :mod:`app.routers.race_analysis` para
POST /runs y la persistencia con versionado de
:mod:`app.services.race.insights_history` para los endpoints de lectura.

RBAC
====
- ``GET /insights``         — admin + coach + parent (parent fuerza ``include_deprecated=false``).
- ``GET /insights/{id}``    — admin + coach + parent. Padre recibe ``404`` si la fila no es activa+aprobada.
- ``GET /runs``             — admin + coach (parent ⇒ 403).
- ``POST /runs``            — admin + coach.
- ``GET /distribution``     — admin + coach + parent.
- ``GET /evolution``        — admin + coach + parent.

Privacidad (CLAUDE.md §Privacidad)
==================================
Todos los responses pasan por schemas con ``extra="forbid"`` que NO
contienen ``athlete_id``, ``competitor_id``, IDs de coach/usuario ni la
PK BigInt interna de ``agent_runs``.  Los pseudónimos en
``/distribution`` son determinísticos por temporada.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, require_role, verify_athlete_access
from app.models.athlete import Athlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.user import User, UserRole
from app.schemas.athlete_race_analysis import (
    AthleteInsightDetailOut,
    AthleteInsightListResponse,
    AthleteInsightOut,
    AthleteRunListResponse,
    AthleteRunOut,
    AthleteRunStatus,
    AthleteStartRunBody,
    DistributionResponse,
    EvolutionMetric,
    EvolutionResponse,
    InsightLink,
)
from app.schemas.race_ai import (
    MetricsSnapshotV1,
    RunState,
    StartRunResponse,
)
from app.services.race.analytics_charts import build_distribution, build_evolution
from app.services.race.ai.budget_guard import BudgetExceededError, check_budget
from app.services.race.ai.runner import RunBackpressureError, submit_run
from app.services.race.insights_history import (
    get_athlete_insight,
    get_insight_supersedes_chain,
    list_athlete_insights,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_coach_or_admin = require_role([UserRole.coach, UserRole.admin])


# ---------------------------------------------------------------------------
# Helpers de mapping ORM → schema
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _link_from_row(row: AthleteAiInsight) -> InsightLink:
    return InsightLink(
        id=row.id,
        generated_at=row.generated_at,
        coach_approved=bool(row.coach_approved),
    )


def _insight_to_out(row: AthleteAiInsight) -> AthleteInsightOut:
    """Mapea ORM → schema público.  Filtra ``athlete_id`` / ``competitor_id``."""
    return AthleteInsightOut(
        id=row.id,
        season=row.season,
        valida_num=row.valida_num,
        event_id=row.event_id,
        use_case=row.use_case,
        summary_text=row.summary_text,
        confidence=row.confidence,
        model=row.model,
        prompt_version=row.prompt_version,
        coach_approved=bool(row.coach_approved),
        generated_at=row.generated_at,
        approved_at=row.approved_at,
        is_active=bool(row.is_active == 1) if row.is_active is not None else False,
        deprecated_at=row.deprecated_at,
    )


def _ensure_json_dict(raw: Any) -> dict[str, Any]:
    """Si la columna JSON viene como str (MySQL en ciertos drivers), parsea."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    if isinstance(raw, dict):
        return raw
    return {"_value": raw} if raw is not None else {}


def _ensure_json_list(raw: Any) -> list[dict[str, Any]]:
    """Como _ensure_json_dict pero para campos JSON list."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return []
        raw = parsed
    if isinstance(raw, list):
        return [x if isinstance(x, dict) else {"_value": x} for x in raw]
    return []


def _maybe_metrics_snapshot(raw: Any) -> MetricsSnapshotV1 | dict[str, Any]:
    """Intenta tipar como :class:`MetricsSnapshotV1`, fallback a dict.

    Snapshots viejos (pre-schema_version) se entregan como dict crudo.
    """
    data = _ensure_json_dict(raw)
    if data.get("schema_version") == 1:
        try:
            return MetricsSnapshotV1(**data)
        except Exception:  # noqa: BLE001
            logger.debug("Snapshot con schema_version=1 no validó; entrego dict")
    return data


def _insight_to_detail(
    row: AthleteAiInsight,
    *,
    supersedes: list[InsightLink],
    superseded_by: Optional[InsightLink],
) -> AthleteInsightDetailOut:
    base = _insight_to_out(row)
    return AthleteInsightDetailOut(
        **base.model_dump(),
        recommendations=_ensure_json_list(row.recommendations_json),
        metrics_snapshot=_maybe_metrics_snapshot(row.metrics_snapshot_json),
        principles_cited=_ensure_json_list(row.principles_cited_json),
        supersedes=supersedes,
        superseded_by=superseded_by,
    )


# ---------------------------------------------------------------------------
# GET /insights
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/race-analysis/insights",
    response_model=AthleteInsightListResponse,
)
async def list_insights(
    season: Optional[int] = Query(default=None, ge=2020, le=2100),
    use_case: Optional[str] = Query(default=None, max_length=32),
    valida_num: Optional[int] = Query(default=None, ge=0, le=99),
    include_deprecated: bool = Query(default=False),
    latest_only: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> AthleteInsightListResponse:
    """Lista insights del atleta. Default: ``latest_only=True``."""
    # Privacidad: padre NO puede ver versiones deprecadas.
    if current_user.role == UserRole.parent:
        include_deprecated = False

    items, total = await list_athlete_insights(
        db,
        athlete_id=athlete.id,
        season=season,
        use_case=use_case,
        valida_num=valida_num,
        include_deprecated=include_deprecated,
        latest_only=latest_only,
        limit=limit,
        offset=offset,
    )
    return AthleteInsightListResponse(
        items=[_insight_to_out(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /insights/{insight_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/race-analysis/insights/{insight_id}",
    response_model=AthleteInsightDetailOut,
)
async def get_insight_detail(
    insight_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> AthleteInsightDetailOut:
    row = await get_athlete_insight(db, athlete_id=athlete.id, insight_id=insight_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight no encontrado",
        )

    # Padre: solo ve insights activos aprobados.  404 (no 403) para no filtrar
    # existencia.
    if current_user.role == UserRole.parent:
        is_visible_to_parent = (
            bool(row.coach_approved)
            and row.is_active == 1
            and row.deprecated_at is None
            and row.archived_at is None
        )
        if not is_visible_to_parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Insight no encontrado",
            )

    chain_rows = await get_insight_supersedes_chain(db, insight_id=row.id)
    supersedes = [_link_from_row(r) for r in chain_rows]

    superseded_by_link: Optional[InsightLink] = None
    if row.superseded_by_insight_id is not None:
        next_row = await get_athlete_insight(
            db, athlete_id=athlete.id, insight_id=int(row.superseded_by_insight_id)
        )
        if next_row is not None:
            superseded_by_link = _link_from_row(next_row)

    return _insight_to_detail(
        row, supersedes=supersedes, superseded_by=superseded_by_link
    )


# ---------------------------------------------------------------------------
# GET /runs
# ---------------------------------------------------------------------------


def _parse_input_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except (ValueError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _agent_status_to_schema(s: str | None) -> AthleteRunStatus:
    try:
        return AthleteRunStatus(str(s))
    except ValueError:
        return AthleteRunStatus.FAILED


@router.get(
    "/{athlete_id}/race-analysis/runs",
    response_model=AthleteRunListResponse,
)
async def list_athlete_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
    athlete: Athlete = Depends(verify_athlete_access),
) -> AthleteRunListResponse:
    """Histórico de runs del agente sobre este atleta (coach/admin only)."""
    # Total
    total_sql = text(
        "SELECT COUNT(*) AS c FROM agent_runs WHERE athlete_id = :aid"
    )
    total_res = await db.execute(total_sql, {"aid": athlete.id})
    total_row = total_res.first() if hasattr(total_res, "first") else None
    total = int(
        (total_row._mapping.get("c") if total_row and hasattr(total_row, "_mapping") else 0)
        or 0
    )

    items_sql = text(
        """
        SELECT external_run_id, status, started_at, finished_at,
               input_json, explain_mode, final_output_json
        FROM agent_runs
        WHERE athlete_id = :aid
        ORDER BY started_at DESC, id DESC
        LIMIT :lim OFFSET :off
        """
    )
    items_res = await db.execute(
        items_sql,
        {"aid": athlete.id, "lim": limit, "off": offset},
    )
    rows = items_res.fetchall() if hasattr(items_res, "fetchall") else list(items_res)

    items: list[AthleteRunOut] = []
    for row in rows:
        m = row._mapping if hasattr(row, "_mapping") else {}

        def _g(name: str, idx: int):
            if m:
                return m.get(name)
            try:
                return row[idx]
            except Exception:  # noqa: BLE001
                return None

        external_run_id = _g("external_run_id", 0)
        if external_run_id is None:
            continue
        st_value = _g("status", 1)
        input_payload = _parse_input_json(_g("input_json", 4))
        valida_nums = input_payload.get("valida_nums")
        if valida_nums is not None and not isinstance(valida_nums, list):
            valida_nums = None
        season_value = input_payload.get("season")
        try:
            season_int = int(season_value) if season_value is not None else None
        except (TypeError, ValueError):
            season_int = None

        items.append(
            AthleteRunOut(
                run_id=str(external_run_id),
                status=_agent_status_to_schema(st_value),
                season=season_int,
                valida_nums=valida_nums,
                started_at=_g("started_at", 2) or _utc_now(),
                finished_at=_g("finished_at", 3),
                explain_mode=bool(_g("explain_mode", 5) or 0),
                has_output=_g("final_output_json", 6) is not None,
            )
        )

    return AthleteRunListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


# ---------------------------------------------------------------------------
# POST /runs
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/race-analysis/runs",
    response_model=StartRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_athlete_run(
    body: AthleteStartRunBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
    athlete: Athlete = Depends(verify_athlete_access),
) -> StartRunResponse:
    """Inicia un run agéntico anclado a este atleta.

    Reaprovecha el ``submit_run`` del runner LangGraph y persiste la fila
    ``agent_runs`` con ``athlete_id`` poblado (gracias a la columna nueva
    de BE-1 + índice ``ix_agent_runs_athlete_started``).
    """
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible (AI_ENABLED=false)",
        )

    try:
        await check_budget(db)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Presupuesto mensual de IA excedido: ${exc.current_usd:.4f} "
                f"de ${exc.budget_usd:.2f}. Reintenta más tarde o contacta al administrador."
            ),
        )

    run_id = uuid.uuid4().hex
    started_at = _utc_now()

    input_payload = {
        "athlete_id": athlete.id,
        "season": body.season,
        "valida_nums": body.valida_nums,
        "explain_mode": body.explain_mode,
    }

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
                "pv": "race_analyst_v1",
                "sa": started_at,
                "inp": json.dumps(input_payload, ensure_ascii=False, default=str),
                "uid": current_user.id,
                "tid": run_id,
                "em": 1 if body.explain_mode else 0,
                "aid": athlete.id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("start_athlete_run: insert agent_runs falló")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear el run: {type(exc).__name__}",
        )

    initial_state = {
        "athlete_id": athlete.id,
        "season": body.season,
        "valida_nums": body.valida_nums,
        "coach_id": current_user.id,
        "explain_mode": body.explain_mode,
        "run_id": run_id,
    }

    # Reusar el closure de finalize del router race_analysis (idéntica lógica
    # de drenado de eventos + actualización de estado).
    from app.routers.race_analysis import _finalize_run  # import diferido

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
            await db.execute(
                text(
                    "UPDATE agent_runs SET status='cancelled', error_message=:em, finished_at=:fa "
                    "WHERE external_run_id=:rid"
                ),
                {"em": f"backpressure: {exc}", "fa": _utc_now(), "rid": run_id},
            )
        except Exception:  # noqa: BLE001
            logger.exception("start_athlete_run: falló cancelar tras backpressure")
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
# GET /distribution
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/race-analysis/distribution",
    response_model=DistributionResponse,
)
async def get_distribution(
    season: int = Query(..., ge=2020, le=2100),
    valida_num: int = Query(..., ge=0, le=99),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> DistributionResponse:
    return await build_distribution(
        db,
        athlete_id=athlete.id,
        season=season,
        valida_num=valida_num,
    )


# ---------------------------------------------------------------------------
# GET /evolution
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/race-analysis/evolution",
    response_model=EvolutionResponse,
)
async def get_evolution(
    season: int = Query(..., ge=2020, le=2100),
    metric: EvolutionMetric = Query(default=EvolutionMetric.PODIUM_GAP_MS),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> EvolutionResponse:
    return await build_evolution(
        db,
        athlete_id=athlete.id,
        season=season,
        metric=metric,
    )


__all__ = ["router"]
