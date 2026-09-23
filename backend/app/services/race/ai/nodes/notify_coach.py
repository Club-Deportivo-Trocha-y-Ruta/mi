"""Nodo 13: ``notify_coach`` — notifica tras un análisis exitoso.

Responsabilidades
=================
1. Log estructurado de finalización del grafo (siempre, no-PII).
2. Si el coach aprobó el draft (``insight_approved=True``) y hay
   ``persisted_insight_ids`` en el state, despacha la notificación
   in-app a padres vía :func:`dispatch_insight_notification`.

Decisión cerrada (2026-09-23, reestructura Competencias): aprobar un
insight NUNCA envía email a padres, sin importar la válida. La lógica de
publicación in-app vive en
:mod:`app.services.notification.race_insight_dispatcher` — este nodo es
solo el cableador.

Fallbacks
=========
- Si el dispatcher levanta cualquier excepción, log + ``notified=False``
  pero el grafo NO se rompe (último nodo, ya no hay flujo dependiente).
- Estado sin ``persisted_insight_ids`` (p.ej. tests viejos, fan-out
  fallido) ⇒ log y skip silencioso.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "notify_coach"


async def _dispatch_for_persisted_insights(state: dict) -> int:
    """Carga insights persistidos y llama al dispatcher por cada uno.

    Retorna número de insights procesados (todos publicados in-app — el
    detalle queda en logs estructurados del dispatcher).
    """
    insight_ids: list[int] = list(state.get("persisted_insight_ids") or [])
    if not insight_ids:
        return 0

    # Import diferido para no penalizar arranque del grafo en tests
    # que no tocan persistencia ni notificaciones.
    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.services.notification.race_insight_dispatcher import (
        dispatch_insight_notification,
    )
    from app.services.race.ai.db import get_session

    processed = 0
    async with get_session() as db:
        for insight_id in insight_ids:
            insight = await db.get(AthleteAiInsight, insight_id)
            if insight is None:
                logger.warning(
                    "notify_coach: persisted insight_id=%s no encontrado, skip",
                    insight_id,
                )
                continue
            try:
                result = await dispatch_insight_notification(insight, db)
                logger.info(
                    "notify_coach.dispatch | insight_id=%s decision=%s tier=%s "
                    "in_app_emitted=%d",
                    insight_id,
                    result.decision.value,
                    result.tier.value,
                    result.in_app_emitted,
                )
                processed += 1
            except Exception as exc:  # noqa: BLE001
                # Último nodo, no romper el grafo. La aprobación ya está
                # comitteada por persist_insight — el coach puede re-disparar
                # la notificación manualmente desde el endpoint de aprobación
                # cuando exista.
                logger.exception(
                    "notify_coach.dispatch_error | insight_id=%s error_type=%s",
                    insight_id,
                    type(exc).__name__,
                )
    return processed


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def notify_coach(state: dict) -> dict[str, Any]:
    coach_id = state.get("coach_id")
    athlete_id = state.get("athlete_id")
    run_id = state.get("run_id", "?")
    approved = bool(state.get("insight_approved"))
    persisted_count = len(state.get("persisted_insight_ids") or [])

    if not approved or persisted_count == 0:
        logger.info(
            "notify_coach: nada que dispatchear (coach_id=%s, athlete_id=%s, "
            "run_id=%s, approved=%s, persisted=%d)",
            coach_id,
            athlete_id,
            run_id,
            approved,
            persisted_count,
        )
        return {"notified": False, "insights_dispatched": 0}

    try:
        processed = await _dispatch_for_persisted_insights(state)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "notify_coach: dispatch_for_persisted_insights falló (run_id=%s, "
            "error_type=%s)",
            run_id,
            type(exc).__name__,
        )
        return {"notified": False, "insights_dispatched": 0}

    logger.info(
        "notify_coach: dispatch completado (run_id=%s, athlete_id=%s, "
        "approved=%s, persisted=%d, processed=%d)",
        run_id,
        athlete_id,
        approved,
        persisted_count,
        processed,
    )
    return {"notified": processed > 0, "insights_dispatched": processed}


__all__ = ["notify_coach", "NODE_NAME"]
