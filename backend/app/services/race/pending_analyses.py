"""Análisis IA pendientes del coach — fuente única para conteo y lista.

Feature 045 (US5, SC-005): cada fila de «Pendientes» del Home debe abrir una
lista con **exactamente** los ítems que contó. Para que eso valga por
construcción y no por disciplina de quien edite, el conteo del resumen
(``GET /api/dashboard/coach-summary``) y la lista
(``GET /api/race-analysis/pending-analyses``) salen de la MISMA especificación:
:func:`_membership_stmt`. ``count_pending_analyses`` envuelve ese SELECT en un
``COUNT(*)``; ``list_pending_analyses`` lo ejecuta y solo le agrega
presentación (nombre del evento, temporada). La presentación nunca cambia la
pertenencia.

Unidad de conteo: **un análisis = un run** (``agent_runs``), en ambos estados.
Es la unidad sobre la que actúa el coach (re-ejecutar o descartar el aviso, ver
``POST /runs/{run_id}/dismiss-stale``), así que descartar un ítem baja el conteo
exactamente en uno.

- ``awaiting_approval``: ``AgentRun.status == awaiting_hitl`` de atletas del
  club. Todavía no hay insight persistido → ``insight_id`` es ``None``.
- ``stale``: run con ``stale_since`` marcado que respalda al menos un insight
  activo (``is_active = 1``) de un atleta del club. Si el run respalda varios
  insights activos (varias válidas en un mismo run) se toma el más reciente.

``kind`` (``valida`` | ``season_summary`` | ``None``) dice qué respalda el ítem
para que la UI sepa cómo re-ejecutarlo: se deriva del insight activo (stale) o
de ``agent_runs.input_json`` (por aprobar). Es presentación pura: no afecta la
pertenencia, así que conteo y lista siguen siendo iguales (SC-005).

Privacidad (Ley 1581): ``athlete_ref`` es el nombre que la UI del coach ya
muestra; solo viaja en la respuesta (coach/admin, acotada por club) y **nunca**
se escribe en un log. Los logs de este módulo llevan ids/conteos únicamente.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, bindparam, func, null, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete import Athlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.race_event import RaceEvent
from app.schemas.race_pending_analyses import PendingAnalysisKind, PendingAnalysisState

logger = logging.getLogger(__name__)

_NO_EVENT_LABEL = "Sin competencia asignada"


@dataclass(frozen=True, slots=True)
class PendingAnalysis:
    """Un análisis pendiente, listo para serializar.

    ``run_id`` es el ``external_run_id`` (el mismo que usan los demás
    endpoints de ``/api/race-analysis/runs/{run_id}``), no la PK interna.
    ``season`` acota la lista y se expone para que «Re-ejecutar» lance la
    temporada exacta (no la deducida de la fecha del evento).
    """

    run_id: str
    insight_id: int | None
    athlete_id: int
    athlete_ref: str
    event_id: int | None
    event_label: str
    state: PendingAnalysisState
    updated_at: datetime
    season: int | None
    kind: PendingAnalysisKind | None = None


def _membership_stmt(
    state: PendingAnalysisState, club_ids: set[int] | None
) -> Select[Any]:
    """La especificación: qué runs están pendientes en ``state`` para el club.

    ``club_ids=None`` = sin acotar (admin sin ``club_id``). Un ``set`` vacío no
    devuelve nada. Ambos estados devuelven las mismas columnas, en el mismo
    orden, para que el conteo y la lista compartan la forma.
    """
    if state is PendingAnalysisState.awaiting_approval:
        stmt = (
            select(
                AgentRun.id.label("run_pk"),
                AgentRun.external_run_id.label("run_id"),
                null().label("insight_id"),
                Athlete.id.label("athlete_id"),
                Athlete.first_name.label("first_name"),
                Athlete.last_name.label("last_name"),
                null().label("event_id"),
                null().label("season"),
                null().label("valida_num"),
                null().label("use_case"),
                AgentRun.updated_at.label("updated_at"),
            )
            .select_from(AgentRun)
            .join(Athlete, Athlete.id == AgentRun.athlete_id)
            .where(
                AgentRun.status == AgentRunStatus.awaiting_hitl,
                Athlete.deleted_at.is_(None),
            )
        )
    else:
        latest_active_insight = (
            select(
                AthleteAiInsight.agent_run_id.label("run_pk"),
                func.max(AthleteAiInsight.id).label("insight_id"),
            )
            .where(
                AthleteAiInsight.is_active == 1,
                AthleteAiInsight.agent_run_id.is_not(None),
            )
            .group_by(AthleteAiInsight.agent_run_id)
            .subquery("latest_active_insight")
        )
        stmt = (
            select(
                AgentRun.id.label("run_pk"),
                AgentRun.external_run_id.label("run_id"),
                AthleteAiInsight.id.label("insight_id"),
                Athlete.id.label("athlete_id"),
                Athlete.first_name.label("first_name"),
                Athlete.last_name.label("last_name"),
                AthleteAiInsight.event_id.label("event_id"),
                AthleteAiInsight.season.label("season"),
                AthleteAiInsight.valida_num.label("valida_num"),
                AthleteAiInsight.use_case.label("use_case"),
                AgentRun.updated_at.label("updated_at"),
            )
            .select_from(AgentRun)
            .join(latest_active_insight, latest_active_insight.c.run_pk == AgentRun.id)
            .join(AthleteAiInsight, AthleteAiInsight.id == latest_active_insight.c.insight_id)
            .join(Athlete, Athlete.id == AthleteAiInsight.athlete_id)
            .where(
                AgentRun.stale_since.is_not(None),
                Athlete.deleted_at.is_(None),
            )
        )

    if club_ids is not None:
        stmt = stmt.where(Athlete.club_id.in_(club_ids))
    return stmt.order_by(AgentRun.updated_at.desc(), AgentRun.id.desc())


async def count_pending_analyses(
    db: AsyncSession,
    state: PendingAnalysisState,
    club_ids: set[int] | None,
) -> int:
    """Cuántos análisis hay en ``state`` — el número que muestra el Home."""
    members = _membership_stmt(state, club_ids).order_by(None).subquery("pending")
    return int((await db.execute(select(func.count()).select_from(members))).scalar_one())


def _parse_input_json(raw: Any) -> dict[str, Any]:
    """``agent_runs.input_json`` llega como ``str`` (MySQL JSON / SQLite) o ``dict``."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _kind_from_run_input(payload: dict[str, Any]) -> PendingAnalysisKind | None:
    """Tipo de un run por aprobar, leído de su ``input_json``.

    El resumen de temporada se lanza con ``analysis_kind="season"`` (y
    ``valida_nums=None``); el análisis por válida lleva ``event_id`` y/o
    ``valida_nums`` positivos. ``valida_nums == [0]`` es la convención de
    temporada de ``athlete_ai_insights`` (``valida_num=0``). Sin señal
    explícita devuelve ``None``: nunca se adivina.
    """
    if payload.get("analysis_kind") == "season":
        return PendingAnalysisKind.season_summary
    raw_nums = payload.get("valida_nums")
    nums = [_as_int(n) for n in raw_nums] if isinstance(raw_nums, list) else []
    if nums == [0]:
        return PendingAnalysisKind.season_summary
    if payload.get("analysis_kind") == "valida" or _as_int(payload.get("event_id")) is not None:
        return PendingAnalysisKind.valida
    if nums and all(n is not None and n > 0 for n in nums):
        return PendingAnalysisKind.valida
    return None


def _kind_from_insight(
    use_case: Any, valida_num: int | None, event_id: int | None
) -> PendingAnalysisKind | None:
    """Tipo de un ítem desactualizado, leído del insight activo que respalda el run.

    ``valida_num=0`` / ``use_case="season_summary*"`` = resumen de temporada;
    una válida concreta (``valida_num > 0`` o ``event_id``) = ``valida``;
    analíticas sin válida (``valida_num`` nulo y sin evento) = ``None``.
    """
    if valida_num == 0 or (isinstance(use_case, str) and use_case.startswith("season_summary")):
        return PendingAnalysisKind.season_summary
    if event_id is not None or (valida_num is not None and valida_num > 0):
        return PendingAnalysisKind.valida
    return None


@dataclass(frozen=True, slots=True)
class _RunInput:
    """Lo que se lee de ``agent_runs.input_json`` de un run por aprobar."""

    event_id: int | None
    season: int | None
    kind: PendingAnalysisKind | None


async def _run_inputs(db: AsyncSession, run_pks: list[int]) -> dict[int, _RunInput]:
    """``run_pk -> _RunInput`` leído de ``agent_runs.input_json``.

    El modelo ORM de ``agent_runs`` es un subconjunto a propósito (ver su
    docstring); ``input_json`` se lee por SQL con parámetros, en un solo
    viaje para todos los runs de la página.
    """
    if not run_pks:
        return {}
    result = await db.execute(
        text("SELECT id, input_json FROM agent_runs WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": run_pks},
    )
    inputs: dict[int, _RunInput] = {}
    for run_pk, raw in result.all():
        payload = _parse_input_json(raw)
        inputs[int(run_pk)] = _RunInput(
            event_id=_as_int(payload.get("event_id")),
            season=_as_int(payload.get("season")),
            kind=_kind_from_run_input(payload),
        )
    return inputs


async def _event_names(db: AsyncSession, event_ids: set[int]) -> dict[int, str]:
    if not event_ids:
        return {}
    result = await db.execute(
        select(RaceEvent.id, RaceEvent.name).where(RaceEvent.id.in_(event_ids))
    )
    return {int(event_id): str(name) for event_id, name in result.all()}


async def list_pending_analyses(
    db: AsyncSession,
    state: PendingAnalysisState,
    club_ids: set[int] | None,
    *,
    season: int | None = None,
) -> list[PendingAnalysis]:
    """Los análisis en ``state``, del más reciente al más antiguo.

    Sin ``season`` la lista es exactamente lo que cuenta
    :func:`count_pending_analyses` (SC-005). Con ``season`` es un subconjunto
    pedido explícitamente por quien llama (la página «Temporada»).
    """
    rows = (await db.execute(_membership_stmt(state, club_ids))).all()
    if not rows:
        return []

    # Los runs "por aprobar" no tienen insight: evento y temporada salen del
    # input del run. Los "desactualizados" ya traen ambos del insight.
    inputs: dict[int, _RunInput] = {}
    if state is PendingAnalysisState.awaiting_approval:
        inputs = await _run_inputs(db, [int(r.run_pk) for r in rows])

    resolved: list[tuple[Any, int | None, int | None, PendingAnalysisKind | None]] = []
    for row in rows:
        if state is PendingAnalysisState.awaiting_approval:
            run_input = inputs.get(int(row.run_pk), _RunInput(None, None, None))
            event_id, row_season, kind = run_input.event_id, run_input.season, run_input.kind
        else:
            event_id, row_season = _as_int(row.event_id), _as_int(row.season)
            kind = _kind_from_insight(row.use_case, _as_int(row.valida_num), event_id)
        resolved.append((row, event_id, row_season, kind))

    names = await _event_names(db, {e for _, e, _, _ in resolved if e is not None})

    items: list[PendingAnalysis] = []
    for row, event_id, row_season, kind in resolved:
        if season is not None and row_season != season:
            continue
        event_name = names.get(event_id) if event_id is not None else None
        if event_name is not None:
            label = event_name
        elif row_season is not None:
            label = f"Temporada {row_season}"
        else:
            label = _NO_EVENT_LABEL
        items.append(
            PendingAnalysis(
                run_id=str(row.run_id),
                insight_id=_as_int(row.insight_id),
                athlete_id=int(row.athlete_id),
                athlete_ref=f"{row.first_name} {row.last_name}".strip(),
                event_id=event_id if event_name is not None else None,
                event_label=label,
                state=state,
                updated_at=row.updated_at,
                season=row_season,
                kind=kind,
            )
        )

    logger.debug(
        "pending_analyses.list state=%s club_scoped=%s season=%s returned=%d",
        state.value,
        club_ids is not None,
        season,
        len(items),
    )
    return items


__all__ = [
    "PendingAnalysis",
    "PendingAnalysisKind",
    "PendingAnalysisState",
    "count_pending_analyses",
    "list_pending_analyses",
]
