"""Servicio de invalidación / re-trigger de análisis IA (PR5 unificación).

Implementa la lógica de "análisis desactualizado" (stale) sobre ``agent_runs``:

- :func:`mark_run_stale` — marca un run individual como stale (idempotente).
- :func:`invalidate_runs_for_event` — marca stale todos los runs cuyos insights
  pertenecen a un ``race_event`` (usado tras una re-ingesta que cambió los
  resultados). Además marca como ``outdated`` los boletines mensuales ya
  enviados que dependían de esos insights (D3) — SIN reenviar.

Decisiones honradas:
- D5: el re-trigger es SIEMPRE manual (endpoint dedicado). Este servicio NO
  dispara runs nuevos; solo marca staleness. La re-ejecución la decide el
  coach explícitamente.
- D3: boletines ``sent`` afectados → ``outdated`` (no reenvío).

Privacidad: los logs no incluyen nombres ni datos del menor, solo ids.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def mark_run_stale(
    db: AsyncSession,
    run_db_id: int,
    *,
    when: datetime | None = None,
) -> bool:
    """Marca un run (``agent_runs.id``) como stale. Idempotente.

    Returns:
        True si el run existe y quedó marcado (o ya lo estaba). False si no
        existe.
    """
    run = await db.get(AgentRun, run_db_id)
    if run is None:
        return False
    if run.stale_since is None:
        run.stale_since = when or _utcnow()
        run.updated_at = _utcnow()
        await db.flush()
    return True


async def mark_run_fresh(db: AsyncSession, run_db_id: int) -> bool:
    """Limpia la marca stale de un run (tras re-ejecución exitosa)."""
    run = await db.get(AgentRun, run_db_id)
    if run is None:
        return False
    run.stale_since = None
    run.updated_at = _utcnow()
    await db.flush()
    return True


async def invalidate_runs_for_event(
    db: AsyncSession,
    event_id: int,
    *,
    when: datetime | None = None,
) -> dict[str, int]:
    """Marca stale todos los runs con insights del evento + boletines outdated.

    Usado tras una re-ingesta que detectó cambios (SHA256 distinto) sobre el
    mismo ``race_event``. NO re-ejecuta nada (D5) ni reenvía boletines (D3).

    Returns:
        Dict con conteos: ``{"runs_marked": N, "newsletters_outdated": M}``.
    """
    ts = when or _utcnow()

    # 1. Runs cuyos insights pertenecen al evento.
    run_ids_q = await db.execute(
        select(AthleteAiInsight.agent_run_id)
        .where(
            AthleteAiInsight.event_id == event_id,
            AthleteAiInsight.agent_run_id.is_not(None),
        )
        .distinct()
    )
    run_ids = {int(r) for r in run_ids_q.scalars().all() if r is not None}

    runs_marked = 0
    for rid in run_ids:
        run = await db.get(AgentRun, rid)
        if run is None:
            continue
        if run.stale_since is None:
            run.stale_since = ts
            run.updated_at = ts
            runs_marked += 1

    # 2. Boletines mensuales ya enviados que referencian insights del evento.
    #    Marcamos outdated (D3) — el dispatcher NO reenvía outdated.
    #    Vínculo: insights del evento → athlete_id + (season, valida) → boletín.
    insights_q = await db.execute(
        select(AthleteAiInsight.athlete_id, AthleteAiInsight.season).where(
            AthleteAiInsight.event_id == event_id
        )
    )
    affected_athlete_seasons: set[tuple[int, int]] = {
        (int(aid), int(season))
        for aid, season in insights_q
        if aid is not None and season is not None
    }

    newsletters_outdated = 0
    for athlete_id, season in affected_athlete_seasons:
        nl_q = await db.execute(
            select(AthleteMonthlyNewsletter).where(
                AthleteMonthlyNewsletter.athlete_id == athlete_id,
                AthleteMonthlyNewsletter.year == season,
                AthleteMonthlyNewsletter.status == NewsletterStatus.sent,
            )
        )
        for nl in nl_q.scalars().all():
            nl.status = NewsletterStatus.outdated
            nl.updated_at = ts
            newsletters_outdated += 1

    await db.flush()

    logger.info(
        "race_runs_invalidated event_id=%s runs_marked=%d newsletters_outdated=%d",
        event_id,
        runs_marked,
        newsletters_outdated,
    )
    return {
        "runs_marked": runs_marked,
        "newsletters_outdated": newsletters_outdated,
    }


__all__ = [
    "mark_run_stale",
    "mark_run_fresh",
    "invalidate_runs_for_event",
]
