"""Router: webhook de Resend para señales de entrega (feature 038, T401, P3).

  POST /api/webhooks/resend

Apagado por defecto: si ``settings.resend_webhook_secret`` está vacío, el
endpoint responde ``404`` a cualquier llamada (no revela ni siquiera que la
ruta existe).

Cuando está configurado, verifica la firma Svix que envía Resend
(headers ``svix-id`` / ``svix-timestamp`` / ``svix-signature``) sin depender
de la librería ``svix`` (no está en requirements.txt) — HMAC-SHA256 estándar
sobre ``"{svix-id}.{svix-timestamp}.{body}"`` con el secreto decodificado de
base64 (formato `whsec_<base64>` de Svix; si no trae el prefijo se usa tal
cual). Firma inválida o timestamp fuera de tolerancia (5 minutos) -> 400.

Body esperado: ``{type, created_at, data: {email_id, ...}}``. Mapea
``type`` -> ``DeliveryEventType`` y ``data.email_id`` -> ``provider_message_id``
para insertar una fila en ``newsletter_delivery_events``. Si no hay match
(email_id desconocido) o el tipo no es uno de los mapeados, responde 200
igual (evento ignorado) — Resend reintenta en cualquier respuesta != 2xx.

Idempotencia: ``svix-id`` se persiste como ``provider_event_id`` (UNIQUE en
el modelo, T102) — un replay del mismo evento se ignora vía manejo
defensivo de ``IntegrityError``.

Privacidad (Ley 1581, CLAUDE.md): NUNCA se loguea el email del destinatario
ni el subject — el body del webhook de Resend no los incluye para eventos
de entrega, pero por si acaso solo se loguean campos opacos (event_type,
newsletter_id, svix-id).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.athlete_newsletter import AthleteMonthlyNewsletter
from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# Tolerancia de reloj para el timestamp de Svix (segundos).
_TOLERANCE_SECONDS = 5 * 60

# Mapeo de `type` del webhook de Resend -> evento persistido.
_EVENT_TYPE_MAP: dict[str, DeliveryEventType] = {
    "email.delivered": DeliveryEventType.delivered,
    "email.opened": DeliveryEventType.opened,
    "email.clicked": DeliveryEventType.clicked,
    "email.bounced": DeliveryEventType.bounced,
}


def _decode_secret(secret: str) -> bytes:
    """Decodifica el secreto de firma Svix (formato `whsec_<base64>`)."""
    raw = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    # Padding defensivo — base64 estándar de Svix a veces omite el '='.
    padded = raw + "=" * (-len(raw) % 4)
    return base64.b64decode(padded)


def _verify_svix_signature(
    *,
    secret: str,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
    body: bytes,
) -> bool:
    """Verifica la firma HMAC-SHA256 estilo Svix. Ver docstring del módulo."""
    try:
        timestamp = int(svix_timestamp)
    except (TypeError, ValueError):
        return False

    now = int(time.time())
    if abs(now - timestamp) > _TOLERANCE_SECONDS:
        return False

    try:
        secret_bytes = _decode_secret(secret)
    except Exception:
        return False

    signed_content = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + body
    expected = hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode("utf-8")

    # svix-signature trae uno o más esquemas separados por espacio, cada uno
    # "v1,<base64>". Basta con que uno coincida.
    for scheme in svix_signature.split():
        parts = scheme.split(",", 1)
        candidate = parts[1] if len(parts) == 2 else parts[0]
        if hmac.compare_digest(candidate, expected_b64):
            return True
    return False


@router.post("/resend", status_code=status.HTTP_200_OK)
async def resend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if not settings.resend_webhook_secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faltan headers de firma Svix.",
        )

    raw_body = await request.body()

    if not _verify_svix_signature(
        secret=settings.resend_webhook_secret,
        svix_id=svix_id,
        svix_timestamp=svix_timestamp,
        svix_signature=svix_signature,
        body=raw_body,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firma inválida.",
        )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body inválido.",
        )

    event_type_raw = payload.get("type")
    data = payload.get("data") or {}
    email_id = data.get("email_id")

    mapped_type = _EVENT_TYPE_MAP.get(event_type_raw) if isinstance(event_type_raw, str) else None

    if mapped_type is None or not email_id:
        logger.info("Webhook Resend ignorado | type=%s", event_type_raw)
        return {"status": "ignored"}

    result = await db.execute(
        select(NewsletterDeliveryEvent.newsletter_id)
        .join(
            AthleteMonthlyNewsletter,
            AthleteMonthlyNewsletter.id == NewsletterDeliveryEvent.newsletter_id,
        )
        .where(NewsletterDeliveryEvent.provider_message_id == email_id)
        .limit(1)
    )
    newsletter_id = result.scalar_one_or_none()

    if newsletter_id is None:
        logger.info("Webhook Resend | email_id sin match | type=%s", mapped_type.value)
        return {"status": "ignored"}

    occurred_at = _parse_created_at(payload.get("created_at"))

    event = NewsletterDeliveryEvent(
        newsletter_id=newsletter_id,
        parent_user_id=None,
        event_type=mapped_type,
        provider_message_id=email_id,
        provider_event_id=svix_id,
        occurred_at=occurred_at,
    )
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        # Replay del mismo svix-id (provider_event_id es UNIQUE) — idempotente.
        await db.rollback()
        logger.info(
            "Webhook Resend | evento duplicado ignorado | type=%s",
            mapped_type.value,
        )
        return {"status": "duplicate"}

    logger.info(
        "Webhook Resend procesado | type=%s newsletter_id=%d",
        mapped_type.value, newsletter_id,
    )
    return {"status": "processed"}


def _parse_created_at(raw: Any) -> datetime:
    if isinstance(raw, str):
        try:
            value = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
