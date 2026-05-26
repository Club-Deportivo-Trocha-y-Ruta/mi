"""Nodo 13: ``notify_coach`` — notifica tras un análisis exitoso.

Responsabilidades
=================
1. Log estructurado de finalización del grafo (siempre, no-PII).
2. Si el coach aprobó el draft (``insight_approved=True``) y hay
   ``persisted_insight_ids`` en el state, despacha la notificación a
   padres/in-app vía :func:`dispatch_insight_notification`.

Decisión cerrada (Family Relations track, 2026-05-25): no toda válida
genera email a padres. La lógica de tier (A/CD ⇒ email, B/C ⇒ solo in-app)
vive en :mod:`app.services.notification.race_insight_dispatcher` —
este nodo es solo el cableador.

Fallbacks
=========
- ``NOTIFICATION_SEND_EMAILS=false`` ⇒ in-app igual se emite (logs),
  solo se omite el email Resend. El dispatcher respeta el flag a nivel
  ``NotificationService.send``.
- Si el dispatcher levanta cualquier excepción, log + ``notified=False``
  pero el grafo NO se rompe (último nodo, ya no hay flujo dependiente).
- Estado sin ``persisted_insight_ids`` (p.ej. tests viejos, fan-out
  fallido) ⇒ log y skip silencioso.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "notify_coach"


def _send_emails_enabled() -> bool:
    raw = os.environ.get("NOTIFICATION_SEND_EMAILS", "true").strip().lower()
    return raw not in {"false", "0", "no", "off"}


async def _dispatch_for_persisted_insights(state: dict) -> int:
    """Carga insights persistidos y llama al dispatcher por cada uno.

    Retorna número de insights procesados (no de emails enviados — eso
    queda en logs estructurados del dispatcher).
    """
    insight_ids: list[int] = list(state.get("persisted_insight_ids") or [])
    if not insight_ids:
        return 0

    # Import diferido para no penalizar arranque del grafo en tests
    # que no tocan persistencia ni notificaciones.
    from app.config import settings
    from app.dependencies import get_email_settings, get_template_registry
    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.services.notification import (
        NotificationService,
        create_email_client,
    )
    from app.services.notification.document_generator import DocumentGenerator
    from app.services.notification.race_insight_dispatcher import (
        dispatch_insight_notification,
    )
    from app.services.race.ai.db import get_session

    # Construir NotificationService manualmente (estamos fuera del request
    # cycle de FastAPI, los Depends no aplican). get_email_settings es
    # @lru_cache, así que es estable y barato.
    email_settings = get_email_settings()
    registry = get_template_registry()
    generator = DocumentGenerator(registry=registry, settings=email_settings)
    email_client = create_email_client(email_settings)
    notification_service = NotificationService(
        email_client=email_client,
        registry=registry,
        document_generator=generator,
        settings=email_settings,
    )

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
                result = await dispatch_insight_notification(
                    insight,
                    db,
                    notification_service=notification_service,
                    dispatcher=None,  # sync inline — estamos en background ya
                    settings=settings,
                )
                logger.info(
                    "notify_coach.dispatch | insight_id=%s decision=%s tier=%s "
                    "emails_sent=%d in_app_emitted=%d",
                    insight_id,
                    result.decision.value,
                    result.tier.value,
                    result.emails_sent,
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

    base_log_extra = (coach_id, athlete_id, run_id, approved, persisted_count)

    if not _send_emails_enabled():
        logger.info(
            "notify_coach: NOTIFICATION_SEND_EMAILS=false — emails desactivados "
            "(coach_id=%s, athlete_id=%s, run_id=%s, approved=%s, persisted=%d)",
            *base_log_extra,
        )
        # Aún así, queremos que el dispatcher procese in-app (es solo log).
        # Pero como el flag corta el envío en NotificationService.send, los
        # emails se cortocircuitan y los logs reflejan el bypass.

    if not approved or persisted_count == 0:
        logger.info(
            "notify_coach: nada que dispatchear (coach_id=%s, athlete_id=%s, "
            "run_id=%s, approved=%s, persisted=%d)",
            *base_log_extra,
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
