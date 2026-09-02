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
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, require_role, verify_athlete_access
from app.models.athlete import Athlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.user import User, UserRole
from app.schemas.athlete_race_analysis import (
    AnswerInsightBody,
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
    RaceParticipationResponse,
    SeasonSummaryRequest,
    SeasonSummaryRunResponse,
)
from app.schemas.race_ai import (
    MetricsSnapshotV1,
    RunState,
    StartRunResponse,
)
from app.services.race.analytics_charts import (
    AthleteDidNotParticipate,
    build_distribution,
    build_evolution,
    list_athlete_races,
)
from app.services.race.ai.budget_guard import BudgetExceededError, check_budget
from app.services.race.ai.runner import RunBackpressureError, submit_run
from app.services.race.group_launch import find_active_run
from app.services.privacy import athlete_has_ai_processing_consent
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
    """Mapea ORM → schema público.  Filtra ``athlete_id`` / ``competitor_id``.

    ``event_date``/``series_kind`` (T030, feature 036) vienen del ``event``
    (y su ``series``) eager-cargados por ``insights_history`` — nunca
    disparan un lazy-load implícito, que rompería en contexto async con
    ``MissingGreenlet``.
    """
    event = row.event
    series = event.series if event is not None else None
    headline: Optional[str] = None
    structured_raw = getattr(row, "structured_json", None)
    if structured_raw is not None:
        structured_dict = _ensure_json_dict(structured_raw)
        headline_val = structured_dict.get("headline")
        if isinstance(headline_val, str) and headline_val.strip():
            headline = headline_val
    return AthleteInsightOut(
        id=row.id,
        season=row.season,
        valida_num=row.valida_num,
        event_id=row.event_id,
        event_date=event.event_date if event is not None else None,
        series_kind=series.kind.value if series is not None else None,
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
        is_fallback=bool(row.is_fallback),
        headline=headline,
        coach_rating=getattr(row, "coach_rating", None),
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


_PII_KEYS_TO_SCRUB = frozenset({"competitor_id", "athlete_id", "rider_id"})


def _scrub_pii_keys(obj: Any) -> Any:
    """Scrubber recursivo que elimina claves PII de dicts anidados.

    Cubre snapshots viejos (pre-Fix 4) que pueden contener ``competitor_id``,
    ``athlete_id`` o ``rider_id`` en cualquier nivel de anidamiento.
    """
    if isinstance(obj, dict):
        return {
            k: _scrub_pii_keys(v)
            for k, v in obj.items()
            if k not in _PII_KEYS_TO_SCRUB
        }
    if isinstance(obj, list):
        return [_scrub_pii_keys(item) for item in obj]
    return obj


def _maybe_metrics_snapshot(raw: Any) -> MetricsSnapshotV1 | dict[str, Any]:
    """Intenta tipar como :class:`MetricsSnapshotV1`, fallback a dict.

    Snapshots viejos (pre-schema_version) se entregan como dict crudo.
    Aplica scrub recursivo de claves PII (competitor_id, athlete_id,
    rider_id) antes de exponer al cliente — cobertura de snapshots
    pre-Fix4 que no fueron scrubados en compute_metrics.
    """
    data = _ensure_json_dict(raw)
    data = _scrub_pii_keys(data)
    if data.get("schema_version") == 1:
        try:
            return MetricsSnapshotV1(**data)
        except Exception:  # noqa: BLE001
            logger.debug("Snapshot con schema_version=1 no validó; entrego dict")
    return data


_TRAINING_DOMAIN = "training"


def _structured_for_response(raw: Any, *, for_parent: bool) -> Optional[dict[str, Any]]:
    """Normaliza ``structured_json`` y aplica la omisión server-side (037).

    En modo parent (data-model.md §API deltas) se omiten:
    - ``field_reading.expected_position`` / ``delta_vs_expected``.
    - ``coach_question``.
    - la evidencia (``evidence``) de las observaciones de dominio
      ``training`` (deja el resto de la observación intacta).
    """
    if raw is None:
        return None
    structured = _ensure_json_dict(raw)
    if not structured:
        return None
    if not for_parent:
        return structured

    structured = dict(structured)
    field_reading = structured.get("field_reading")
    if isinstance(field_reading, dict):
        field_reading = dict(field_reading)
        field_reading.pop("expected_position", None)
        field_reading.pop("delta_vs_expected", None)
        structured["field_reading"] = field_reading
    structured.pop("coach_question", None)

    observations = structured.get("observations")
    if isinstance(observations, list):
        scrubbed_observations = []
        for obs in observations:
            if isinstance(obs, dict) and obs.get("domain") == _TRAINING_DOMAIN:
                obs = dict(obs)
                obs.pop("evidence", None)
            scrubbed_observations.append(obs)
        structured["observations"] = scrubbed_observations

    return structured


def _insight_to_detail(
    row: AthleteAiInsight,
    *,
    supersedes: list[InsightLink],
    superseded_by: Optional[InsightLink],
    for_parent: bool = False,
) -> AthleteInsightDetailOut:
    base = _insight_to_out(row)
    snapshot = _ensure_json_dict(row.metrics_snapshot_json)

    aggregate = snapshot.get("aggregate", {}) if isinstance(snapshot, dict) else {}

    # is_first_in_season — campo nuevo (v2). None para insights v1.
    is_first_in_season_raw = aggregate.get("is_first_in_season")
    is_first_in_season: Optional[bool] = (
        bool(is_first_in_season_raw)
        if is_first_in_season_raw is not None
        else None
    )

    # season_validas_count — campo nuevo (v2). None para insights v1.
    season_validas_count_raw = aggregate.get("season_validas_count")
    try:
        season_validas_count: Optional[int] = (
            int(season_validas_count_raw)
            if season_validas_count_raw is not None
            else None
        )
    except (TypeError, ValueError):
        season_validas_count = None

    coach_answer_text = getattr(row, "coach_answer_text", None)
    coach_answer_at = getattr(row, "coach_answer_at", None)
    if for_parent:
        # Feature 037 (data-model.md §API deltas): coach_answer_* es
        # contenido coach-only (respuesta a coach_question, que también se
        # omite arriba).
        coach_answer_text = None
        coach_answer_at = None

    return AthleteInsightDetailOut(
        **base.model_dump(),
        recommendations=_ensure_json_list(row.recommendations_json),
        metrics_snapshot=_maybe_metrics_snapshot(row.metrics_snapshot_json),
        principles_cited=_ensure_json_list(row.principles_cited_json),
        supersedes=supersedes,
        superseded_by=superseded_by,
        is_first_in_season=is_first_in_season,
        season_validas_count=season_validas_count,
        structured=_structured_for_response(
            getattr(row, "structured_json", None), for_parent=for_parent
        ),
        coach_answer_text=coach_answer_text,
        coach_answer_at=coach_answer_at,
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
        row,
        supersedes=supersedes,
        superseded_by=superseded_by_link,
        for_parent=current_user.role == UserRole.parent,
    )


# ---------------------------------------------------------------------------
# POST /insights/{insight_id}/answer (feature 037, T104)
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/race-analysis/insights/{insight_id}/answer",
    response_model=AthleteInsightDetailOut,
)
async def answer_insight(
    insight_id: int,
    body: AnswerInsightBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
    athlete: Athlete = Depends(verify_athlete_access),
) -> AthleteInsightDetailOut:
    """Responde ``structured_json['coach_question']`` y/o califica el insight.

    Coach/admin only (``_coach_or_admin`` → 403 para parent, mismo patrón
    que ``POST /season-summary`` y ``GET /runs``). ``verify_athlete_access``
    ya filtra coach a atletas de sus propios clubes.

    El texto de la respuesta se escrubea con
    ``services/race/ai/grounding.load_forbidden_names`` (nombres reales del
    atleta y sus acudientes) ANTES de persistir — nunca guardamos el texto
    crudo del coach en ``coach_answer_text`` (feature 037, US4, AC-4.2).
    """
    if body.answer_text is None and body.rating is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debe enviar answer_text y/o rating.",
        )

    row = await get_athlete_insight(db, athlete_id=athlete.id, insight_id=insight_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight no encontrado",
        )

    if body.answer_text is not None:
        from app.services.race.ai.grounding import load_forbidden_names

        forbidden_names = await load_forbidden_names(
            db, athlete.id, nickname=getattr(athlete, "nickname", None)
        )
        answer_text = body.answer_text
        for name in forbidden_names:
            name = name.strip()
            if name:
                answer_text = answer_text.replace(name, "[nombre omitido]")
        row.coach_answer_text = answer_text
        row.coach_answer_at = _utc_now()

    if body.rating is not None:
        row.coach_rating = body.rating

    row.updated_at = _utc_now()
    await db.commit()

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
        row,
        supersedes=supersedes,
        superseded_by=superseded_by_link,
        for_parent=False,
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


async def _resolve_events_by_valida(
    db: AsyncSession,
    athlete_id: int,
    season: int,
    valida_nums: list[int],
) -> dict[int, list[int]]:
    """Mapea cada ``valida_num`` (sequence_number) a los ``event_id`` en los que
    el atleta participó esa temporada.

    Necesario por la colisión cup vs championship (feature 014): desde
    ``feature 014`` un campeonato es su propia serie con ``sequence_number=1``,
    igual que la válida 1 de copa. Con ``valida_num`` solo NO se puede saber a
    qué evento se refiere el lanzamiento. Este helper detecta ambigüedad para
    que ``start_athlete_run`` pueda exigir desambiguación (HTTP 409) y, cuando
    resuelve a un único evento, anclar el insight por ``event_id``.

    Returns:
        dict ``{sequence_number: [event_id, ...]}``. Solo incluye válidas con
        al menos un resultado del atleta en la temporada.
    """
    if not valida_nums:
        return {}

    from sqlalchemy import bindparam

    stmt = (
        text(
            """
            SELECT re.sequence_number AS seq, re.id AS event_id
            FROM race_results rr
            JOIN race_events re ON re.id = rr.event_id
            JOIN race_series rs ON rs.id = re.series_id
            WHERE rr.athlete_id = :aid
              AND rr.deleted_at IS NULL
              AND rs.season_year = :season
              AND re.sequence_number IN :seqs
            GROUP BY re.sequence_number, re.id
            """
        ).bindparams(bindparam("seqs", expanding=True))
    )
    rows = await db.execute(
        stmt, {"aid": athlete_id, "season": season, "seqs": list(set(valida_nums))}
    )
    mapping: dict[int, list[int]] = {}
    for seq, event_id in rows.all():
        mapping.setdefault(int(seq), []).append(int(event_id))
    return mapping


async def _resolve_valida_for_event(
    db: AsyncSession,
    athlete_id: int,
    season: int,
    event_id: int,
) -> Optional[int]:
    """Devuelve el ``sequence_number`` del evento si pertenece a la temporada y
    el atleta participó en él; ``None`` en caso contrario.

    Usado por el camino anclado-por-evento de ``start_athlete_run``: el frontend
    pasa ``event_id`` explícito (lanzamiento desde una competición) y el grafo
    sigue consumiendo ``valida_nums``, así que necesitamos el sequence_number.
    """
    row = await db.execute(
        text(
            """
            SELECT re.sequence_number AS seq
            FROM race_results rr
            JOIN race_events re ON re.id = rr.event_id
            JOIN race_series rs ON rs.id = re.series_id
            WHERE rr.athlete_id = :aid
              AND rr.deleted_at IS NULL
              AND rs.season_year = :season
              AND re.id = :eid
            LIMIT 1
            """
        ),
        {"aid": athlete_id, "season": season, "eid": event_id},
    )
    found = row.first()
    return int(found[0]) if found else None


@router.post(
    "/{athlete_id}/race-analysis/runs",
    response_model=StartRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        451: {"description": "Sin consentimiento parental vigente para procesamiento con IA."},
    },
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

    # Consentimiento parental para procesamiento con IA (Ley 1581 art. 9).
    # Mismo contrato que ``routers/ai.py::_ensure_ai_consent``,
    # ``routers/race_analysis.py::start_run`` y
    # ``create_season_summary`` de este mismo router (feature 037, T405).
    if not await athlete_has_ai_processing_consent(athlete.id, db):
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "Falta consentimiento parental vigente con autorización para "
                "compartir datos con terceros (procesamiento con IA). "
                "Solicita a la familia renovar el consentimiento."
            ),
        )

    if body.valida_nums and len(body.valida_nums) > 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cap v2: máximo 4 válidas por lanzamiento. Usa resumen temporada para visión global.",
        )

    # Guard cup vs championship (feature 014): un valida_num (sequence_number)
    # puede mapear a >1 evento en la misma temporada (válida 1 de copa y un
    # campeonato comparten sequence_number=1). En ese caso el lanzamiento por
    # valida_num es ambiguo.
    #
    # Camino A — el frontend ancla por event_id (lanzamiento desde una
    # competición): usamos ese evento directamente, derivamos su valida_num y
    # NO aplicamos el guard (no hay ambigüedad: el evento es explícito).
    #
    # Camino B — lanzamiento solo por valida_num (vista de temporada): si algún
    # valida_num mapea a >1 evento exigimos desambiguación (409). Cuando una
    # única válida resuelve a un único evento, anclamos el insight por event_id.
    resolved_event_id: Optional[int] = None
    valida_nums = body.valida_nums

    if body.event_id is not None:
        seq = await _resolve_valida_for_event(
            db, athlete.id, body.season, body.event_id
        )
        if seq is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "El evento no existe en esta temporada o el deportista no "
                    "participó en él."
                ),
            )
        resolved_event_id = body.event_id
        valida_nums = [seq]
    elif body.valida_nums:
        events_by_valida = await _resolve_events_by_valida(
            db, athlete.id, body.season, body.valida_nums
        )
        ambiguous = {
            seq: eids for seq, eids in events_by_valida.items() if len(eids) > 1
        }
        if ambiguous:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Válida ambigua: "
                    + ", ".join(
                        f"#{seq} → eventos {eids}" for seq, eids in ambiguous.items()
                    )
                    + ". Hay copa y campeonato con el mismo número en esta "
                    "temporada; lanza el análisis desde la competición específica."
                ),
            )
        # Anclar por event_id solo cuando el lanzamiento es de una única válida
        # con un único evento (el caso común de los botones por deportista).
        if len(body.valida_nums) == 1:
            eids = events_by_valida.get(int(body.valida_nums[0]), [])
            if len(eids) == 1:
                resolved_event_id = eids[0]

    # T043 (feature 036): rechazar el lanzamiento si YA hay un run activo
    # (running/awaiting_hitl) para este mismo atleta + válida. Reusa
    # ``group_launch.find_active_run`` — el mismo mecanismo que el
    # lanzamiento grupal ya usa para detectar este caso (``already_running``)
    # — en vez de duplicar la lógica de matching sobre ``input_json``. Solo
    # cubre válidas concretas: un lanzamiento sin ``valida_nums`` (temporada
    # completa, sin filtro) no tiene una "misma válida" contra la cual
    # comparar y queda fuera del alcance de este guard.
    for vn in valida_nums or []:
        existing_run_id = await find_active_run(db, athlete.id, body.season, int(vn))
        if existing_run_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Ya hay un análisis en curso para este deportista en la "
                    f"válida {vn} de la temporada {body.season}. Espera a que "
                    "termine antes de lanzar uno nuevo."
                ),
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
        "valida_nums": valida_nums,
        "event_id": resolved_event_id,
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
                "pv": settings.race_ai_prompt_version,
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

    age_decimal = (date.today() - athlete.birth_date).days / 365.25
    athlete_age = int(age_decimal)

    # Feature 011: grupo LTAD y fase madurativa reales → al grafo. Sin estos,
    # el analista trataba a todas como Pre-PHV/Bambino por default.
    from app.services.race.ai.grounding import (
        latest_maturation_status,
        load_forbidden_names,
        ltad_group_from_age,
    )

    ltad_group_val = ltad_group_from_age(age_decimal)
    maturation_status = await latest_maturation_status(db, athlete.id)
    # Privacidad (feature 011): nombres reales para scrubear weather_notes y
    # blindar guardrails. NUNCA van al prompt.
    forbidden_names = await load_forbidden_names(
        db, athlete.id, nickname=getattr(athlete, "nickname", None)
    )
    # Feature 037 (T204): athlete_sex → athlete_ref del prompt v3
    # ("el deportista"/"la deportista"), igual que en race_analysis.py.
    athlete_sex_val: Optional[str] = None
    if getattr(athlete, "sex", None) is not None:
        athlete_sex_val = getattr(athlete.sex, "value", None) or str(athlete.sex)

    initial_state = {
        "athlete_id": athlete.id,
        "season": body.season,
        "valida_nums": valida_nums,
        "event_id": resolved_event_id,
        "coach_id": current_user.id,
        "explain_mode": body.explain_mode,
        "run_id": run_id,
        "prompt_version": settings.race_ai_prompt_version,
        "athlete_age": athlete_age,
        "ltad_group": ltad_group_val.value,
        "maturation_status": maturation_status,
        "forbidden_names": forbidden_names,
        "athlete_sex": athlete_sex_val,
        "analysis_kind": "valida",
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

    estimated = 15 + 5 * len(valida_nums or [])

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
    event_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> DistributionResponse:
    # display_name es dato público (fuente: PDFs federativos). Solo se expone
    # a coach/admin; parent ve únicamente pseudónimo para no ver datos de
    # otros menores que no son sus hijos.
    include_display_name = current_user.role in (UserRole.coach, UserRole.admin)
    try:
        return await build_distribution(
            db,
            athlete_id=athlete.id,
            season=season,
            event_id=event_id,
            include_display_name=include_display_name,
        )
    except AthleteDidNotParticipate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El deportista no compitió en esta carrera.",
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


# ---------------------------------------------------------------------------
# GET /races
# ---------------------------------------------------------------------------


@router.get(
    "/{athlete_id}/race-analysis/races",
    response_model=RaceParticipationResponse,
)
async def list_races(
    season: int = Query(..., ge=2020, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    athlete: Athlete = Depends(verify_athlete_access),
) -> RaceParticipationResponse:
    """Lista de carreras en las que el atleta compitió en la temporada.

    Solo eventos con al menos un result del atleta (incluyendo DNF).
    Ordenados por event_date ASC. Fuente de verdad para el picker de
    distribución en el frontend.

    RBAC via ``verify_athlete_access``: admin/coach/padre-de-este-atleta →
    200; padre de un atleta distinto → 403; atleta no visible → 404.

    Privacidad: el schema ``RaceParticipationResponse`` (extra="forbid") no
    contiene ``athlete_id`` ni ``competitor_id`` — solo datos públicos de
    eventos federativos.
    """
    return await list_athlete_races(db, athlete_id=athlete.id, season=season)


# ---------------------------------------------------------------------------
# POST /race-analysis/season-summary (v2, coach/admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/{athlete_id}/race-analysis/season-summary",
    response_model=SeasonSummaryRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_season_summary(
    body: SeasonSummaryRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_coach_or_admin),
    athlete: Athlete = Depends(verify_athlete_access),
) -> SeasonSummaryRunResponse:
    """Lanza el resumen de temporada v3 como un run agéntico (US5, T203).

    A diferencia del v2 (invocación síncrona del LLM dentro del request),
    v3 reusa el mismo grafo LangGraph que ``POST /runs`` — con crítico y
    HITL — anclado con ``analysis_kind="season"``. Requiere ≥3 válidas con
    insights activos aprobados para la temporada resuelta (mismo guard de
    v2). Devuelve ``202 {run_id, status}``; el cliente hace polling de
    ``GET /api/race-analysis/runs/{run_id}/status`` igual que un análisis
    por válida. Persistencia final (``valida_num=0``,
    ``use_case="season_summary_v3"``) queda a cargo de los nodos del grafo
    (``persist_insight``), no de este endpoint.
    """
    if body is None:
        body = SeasonSummaryRequest()
    if body.season is None:
        body.season = datetime.now(timezone.utc).year

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible (AI_ENABLED=false)",
        )

    # Consentimiento parental para procesamiento con IA (Ley 1581 art. 9).
    # Mismo contrato que ``routers/ai.py::_ensure_ai_consent`` y
    # ``routers/race_analysis.py::start_run`` (feature 037, T203).
    if not await athlete_has_ai_processing_consent(athlete.id, db):
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "Falta consentimiento parental vigente con autorización para "
                "compartir datos con terceros (procesamiento con IA). "
                "Solicita a la familia renovar el consentimiento."
            ),
        )

    # Verificar budget.
    try:
        await check_budget(db)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Presupuesto mensual de IA excedido: ${exc.current_usd:.4f} "
                f"de ${exc.budget_usd:.2f}. Reintenta más tarde."
            ),
        )

    # Verificar que existan ≥3 válidas analizadas (insights activos aprobados).
    count_sql = text(
        """
        SELECT COUNT(DISTINCT valida_num) AS c
        FROM athlete_ai_insights
        WHERE athlete_id = :aid
          AND season = :season
          AND valida_num > 0
          AND is_active = 1
          AND coach_approved = 1
          AND deprecated_at IS NULL
          AND archived_at IS NULL
        """
    )
    count_res = await db.execute(count_sql, {"aid": athlete.id, "season": body.season})
    count_row = count_res.first()
    validas_count = int(
        (count_row._mapping.get("c") if count_row and hasattr(count_row, "_mapping") else 0)
        or 0
    )

    if validas_count < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Se requieren ≥3 válidas con análisis aprobados para generar el resumen "
                f"de temporada. Válidas encontradas: {validas_count}."
            ),
        )

    run_id = uuid.uuid4().hex
    started_at = _utc_now()
    prompt_version = "race_season_summary_v3"

    input_payload = {
        "athlete_id": athlete.id,
        "season": body.season,
        "valida_nums": None,
        "explain_mode": body.explain_mode,
        "analysis_kind": "season",
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
                "pv": prompt_version,
                "sa": started_at,
                "inp": json.dumps(input_payload, ensure_ascii=False, default=str),
                "uid": current_user.id,
                "tid": run_id,
                "em": 1 if body.explain_mode else 0,
                "aid": athlete.id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_season_summary: insert agent_runs falló")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo crear el run: {type(exc).__name__}",
        )

    # Contexto del atleta (mismo patrón que start_athlete_run / start_run):
    # edad, sexo, grupo LTAD, fase madurativa y forbidden_names reales.
    from app.services.race.ai.grounding import (
        latest_maturation_status,
        load_forbidden_names,
        ltad_group_from_age,
    )

    athlete_sex_val: Optional[str] = None
    if getattr(athlete, "sex", None) is not None:
        athlete_sex_val = getattr(athlete.sex, "value", None) or str(athlete.sex)

    athlete_age: Optional[int] = None
    ltad_group_val: Optional[str] = None
    maturation_status: Optional[str] = None
    forbidden_names: list[str] = []
    if getattr(athlete, "birth_date", None) is not None:
        age_decimal = (date.today() - athlete.birth_date).days / 365.25
        athlete_age = int(age_decimal)
        ltad_group_val = ltad_group_from_age(age_decimal).value
        maturation_status = await latest_maturation_status(db, athlete.id)
        forbidden_names = await load_forbidden_names(
            db, athlete.id, nickname=getattr(athlete, "nickname", None)
        )
    else:
        logger.warning(
            "create_season_summary: athlete_id=%s sin birth_date; "
            "athlete_age no inyectado al state",
            athlete.id,
        )

    initial_state: dict[str, Any] = {
        "athlete_id": athlete.id,
        "season": body.season,
        "valida_nums": None,
        "coach_id": current_user.id,
        "explain_mode": body.explain_mode,
        "run_id": run_id,
        "prompt_version": prompt_version,
        "forbidden_names": forbidden_names,
        "athlete_sex": athlete_sex_val,
        "analysis_kind": "season",
    }
    if athlete_age is not None:
        initial_state["athlete_age"] = athlete_age
    if ltad_group_val is not None:
        initial_state["ltad_group"] = ltad_group_val
    initial_state["maturation_status"] = maturation_status

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
        try:
            await db.execute(
                text(
                    "UPDATE agent_runs SET status='cancelled', error_message=:em, finished_at=:fa "
                    "WHERE external_run_id=:rid"
                ),
                {"em": f"backpressure: {exc}", "fa": _utc_now(), "rid": run_id},
            )
        except Exception:  # noqa: BLE001
            logger.exception("create_season_summary: falló cancelar tras backpressure")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )

    return SeasonSummaryRunResponse(run_id=run_id, status=RunState.RUNNING.value)


__all__ = ["router"]
