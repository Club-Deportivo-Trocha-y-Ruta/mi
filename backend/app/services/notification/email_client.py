"""
Email Client — transporte de email abstracto con implementaciones SMTP y Resend.

Paso 3 del workflow-notifications.

Reglas de privacidad en logging (NUNCA loguear):
  - to_email, to_name, html_body, subject
Solo loguear: template_ref y message_id opaco.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

from app.schemas.notification import NotificationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass de mensaje saliente (interno — no expuesto como schema HTTP)
# ---------------------------------------------------------------------------


@dataclass
class Attachment:
    """Adjunto que acompaña un email."""
    filename: str
    data: bytes
    content_type: str


@dataclass
class OutboundEmail:
    """Representación interna de un email listo para enviarse.

    Nunca aparece en logs completo. Solo `template_ref` es seguro para logging.
    """
    to_email: str          # PII — nunca loguear
    to_name: str           # PII — nunca loguear
    subject: str           # puede contener nombre del atleta — nunca loguear
    html_body: str         # PII — nunca loguear
    template_ref: str      # identificador del template — seguro para logging
    cc_emails: list[str] = field(default_factory=list)  # PII — nunca loguear
    attachments: list[Attachment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ABC BaseEmailClient
# ---------------------------------------------------------------------------


class BaseEmailClient(ABC):
    """Interfaz de transporte de email. Implementaciones: SMTP y Resend."""

    @abstractmethod
    async def send(self, message: OutboundEmail) -> NotificationResult:
        """Envía el email. Retorna NotificationResult con success/message_id/error."""
        ...


# ---------------------------------------------------------------------------
# SmtpEmailClient — aiosmtplib (async nativo)
# ---------------------------------------------------------------------------


class SmtpEmailClient(BaseEmailClient):
    """Cliente SMTP usando aiosmtplib (async nativo, ideal para dev con MailHog)."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        from_name: str,
        use_tls: bool = False,
        start_tls: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self._use_tls = use_tls
        self._start_tls = start_tls

    async def send(self, message: OutboundEmail) -> NotificationResult:
        try:
            import email as email_lib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders
            import aiosmtplib

            from email.utils import formataddr

            msg = MIMEMultipart("mixed")
            msg["Subject"] = message.subject
            msg["From"] = formataddr((self._from_name, self._from_email))
            # No loguear to_email — solo usarlo en el header.
            # formataddr() entrecomilla correctamente nombres con caracteres especiales.
            msg["To"] = formataddr((message.to_name, message.to_email))

            if message.cc_emails:
                msg["Cc"] = ", ".join(message.cc_emails)

            msg.attach(MIMEText(message.html_body, "html", "utf-8"))

            for attachment in message.attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{attachment.filename}"',
                )
                part.add_header("Content-Type", attachment.content_type)
                msg.attach(part)

            smtp_kwargs: dict = {
                "hostname": self._host,
                "port": self._port,
                "use_tls": self._use_tls,
                "start_tls": self._start_tls,
            }
            # Solo incluir credenciales si están configuradas.
            # Con username=None/vacío, aiosmtplib intenta AUTH y falla en
            # servidores sin autenticación (ej. MailHog).
            if self._username:
                smtp_kwargs["username"] = self._username
            if self._password:
                smtp_kwargs["password"] = self._password

            recipients = [message.to_email] + message.cc_emails
            await aiosmtplib.send(msg, recipients=recipients, **smtp_kwargs)

            # Solo loguear referencia segura del template, nunca PII
            # (subject excluido — puede contener nombre del atleta o datos del padre)
            template_ref = message.template_ref
            logger.info(
                "SMTP email enviado | template=%s",
                template_ref,
            )

            return NotificationResult(success=True, message_id=f"smtp-{template_ref}")

        except Exception as exc:
            # Loguear solo el tipo de error, nunca el contenido del mensaje
            logger.error(
                "SMTP error al enviar | template=%s error_type=%s",
                message.template_ref, type(exc).__name__,
            )
            return NotificationResult(
                success=False,
                error=f"SMTP error: {type(exc).__name__}",
            )


# ---------------------------------------------------------------------------
# ResendEmailClient — SDK síncrono, envuelto en run_in_executor
# ---------------------------------------------------------------------------


class ResendEmailClient(BaseEmailClient):
    """Cliente Resend para producción.

    El SDK `resend` es síncrono — se envuelve en run_in_executor para
    no bloquear el event loop de FastAPI.
    """

    def __init__(
        self,
        api_key: str,
        from_email: str,
        from_name: str,
    ) -> None:
        import resend as resend_sdk
        resend_sdk.api_key = api_key
        self._resend = resend_sdk
        self._from_email = from_email
        self._from_name = from_name

    async def send(self, message: OutboundEmail) -> NotificationResult:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, self._send_sync, message)
            return result
        except Exception as exc:
            logger.error(
                "Resend executor error | template=%s error_type=%s",
                message.template_ref, type(exc).__name__,
            )
            return NotificationResult(
                success=False,
                error=f"Resend executor error: {type(exc).__name__}",
            )

    def _send_sync(self, message: OutboundEmail) -> NotificationResult:
        """Lógica síncrona ejecutada en threadpool. No accede al event loop."""
        try:
            params: dict = {
                "from": f"{self._from_name} <{self._from_email}>",
                "to": [message.to_email],   # PII — no sale de este método
                "subject": message.subject,
                "html": message.html_body,
            }

            if message.cc_emails:
                params["cc"] = message.cc_emails

            if message.attachments:
                params["attachments"] = [
                    {
                        "filename": att.filename,
                        "content": list(att.data),  # Resend espera list[int]
                    }
                    for att in message.attachments
                ]

            response = self._resend.Emails.send(params)
            message_id: str = response.get("id", "unknown")

            # Solo loguear el message_id opaco (no PII)
            logger.info(
                "Resend email enviado | template=%s message_id=%s",
                message.template_ref, message_id,
            )
            return NotificationResult(success=True, message_id=message_id)

        except Exception as exc:
            logger.error(
                "Resend SDK error | template=%s error_type=%s",
                message.template_ref, type(exc).__name__,
            )
            return NotificationResult(
                success=False,
                error=f"Resend error: {type(exc).__name__}",
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_email_client(settings: "Settings") -> BaseEmailClient:
    """Retorna la implementación de email según EMAIL_PROVIDER en settings.

    - EMAIL_PROVIDER=smtp  → SmtpEmailClient (dev / MailHog)
    - EMAIL_PROVIDER=resend → ResendEmailClient (producción)
    """
    provider = getattr(settings, "email_provider", "smtp").lower()

    if provider == "resend":
        return ResendEmailClient(
            api_key=settings.resend_api_key,
            from_email=settings.email_from_address,
            from_name=settings.email_from_name,
        )

    # Default: SMTP
    return SmtpEmailClient(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=getattr(settings, "smtp_user", None),
        password=getattr(settings, "smtp_pass", None),
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        use_tls=getattr(settings, "smtp_use_tls", False),
        start_tls=getattr(settings, "smtp_start_tls", False),
    )
