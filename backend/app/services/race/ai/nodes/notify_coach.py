"""Nodo 13: ``notify_coach`` — envía email/notificación al coach.

MVP: log-only por defecto. Si :envvar:`NOTIFICATION_SEND_EMAILS` es
true, intenta despachar via :class:`NotificationService` (modulo
notification ya existe en el proyecto). En este F4 NO inyectamos el
service real (eso lo hará F5 al wirear el endpoint) — el nodo se
limita a marcar ``notified=True`` en el state y loggear.

Razón: este nodo es un wrapper trivial; lo importante en F4 es que el
grafo termine de forma observable. El envío real se cablea en F5 con
DI desde el endpoint.
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


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def notify_coach(state: dict) -> dict[str, Any]:
    coach_id = state.get("coach_id")
    athlete_id = state.get("athlete_id")
    run_id = state.get("run_id", "?")

    if not _send_emails_enabled():
        logger.info(
            "notify_coach: NOTIFICATION_SEND_EMAILS=false — log-only "
            "(coach_id=%s, athlete_id=%s, run_id=%s)",
            coach_id,
            athlete_id,
            run_id,
        )
        return {"notified": False}

    # En F5 se inyectará un dispatcher real. Por ahora, log de
    # "would notify" con metadata segura (sin PII).
    logger.info(
        "notify_coach: notificación pendiente de cablear en F5 "
        "(coach_id=%s, athlete_id=%s, run_id=%s)",
        coach_id,
        athlete_id,
        run_id,
    )
    return {"notified": True}


__all__ = ["notify_coach", "NODE_NAME"]
