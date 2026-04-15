"""
NotificationService — orquestador central del módulo de notificaciones.

Paso 6 del workflow-notifications.

Coordina: TemplateRegistry → DocumentGenerator → EmailClient → TaskDispatcher.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

from app.schemas.notification import (
    DocumentRequest,
    GeneratedDocument,
    NotificationRequest,
    NotificationResult,
)
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.email_client import Attachment, BaseEmailClient, OutboundEmail
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.notification.template_registry import TemplateRegistry

logger = logging.getLogger(__name__)


class NotificationService:
    """Orquestador del módulo de notificaciones.

    Responsabilidades:
      - Validar contexto vía TemplateRegistry
      - Renderizar subject + body HTML con Jinja2
      - Aplicar CSS inlining con premailer
      - Generar adjuntos si se solicitan (via executor)
      - Enviar vía email_client (sync o async según send_async)

    Constructor pensado para inyección de dependencias (DI en Paso 7).
    """

    def __init__(
        self,
        email_client: BaseEmailClient,
        registry: TemplateRegistry,
        document_generator: DocumentGenerator,
        settings: "Settings",
    ) -> None:
        self._client = email_client
        self._registry = registry
        self._generator = document_generator
        self._settings = settings

        # Entorno Jinja2 para renderizar subject (string) y body (archivo)
        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        templates_root = Path(__file__).parents[3] / "templates"
        self._jinja = Environment(
            loader=FileSystemLoader(str(templates_root)),
            autoescape=select_autoescape(["html"]),
        )

    # ------------------------------------------------------------------
    # send() — envio de email (con o sin adjuntos)
    # ------------------------------------------------------------------

    async def send(
        self,
        request: NotificationRequest,
        dispatcher: TaskDispatcher | None = None,
    ) -> NotificationResult:
        """Envía un email de notificación.

        Args:
            request: Datos del destinatario, template y contexto.
            dispatcher: Si se provee, el envío se despacha en background.
                        Si es None, se ejecuta de forma síncrona (espera resultado).

        Returns:
            NotificationResult con success=True/False y message_id.
            Si send_async=True retorna inmediatamente con message_id="queued".

        Respeta el flag NOTIFICATION_SEND_EMAILS=false para cortocircuitar sin enviar.
        """
        # Flag de cortocircuito para entornos de test/CI
        send_emails: bool = getattr(self._settings, "notification_send_emails", True)
        if not send_emails:
            logger.info(
                "NOTIFICATION_SEND_EMAILS=false — email cortocircuitado | template=%s",
                request.template.value,
            )
            return NotificationResult(success=True, message_id="disabled")

        # Validar contexto antes de hacer cualquier trabajo
        self._registry.validate_email_context(request.template.value, request.context)

        if request.send_async and dispatcher is not None:
            # Despachar en background — retornar inmediatamente
            dispatcher.dispatch(self._send_now, request)
            return NotificationResult(success=True, message_id="queued")

        return await self._send_now(request)

    async def _send_now(self, request: NotificationRequest) -> NotificationResult:
        """Realiza el envío real (puede ejecutarse en background o de forma directa)."""
        spec = self._registry.get_email_spec(request.template.value)

        # 1. Renderizar subject (template string Jinja2)
        subject = self._jinja.from_string(spec.subject_template).render(**request.context)

        # 2. Renderizar body HTML (archivo de template)
        html_body = self._jinja.get_template(spec.body_path).render(**request.context)

        # 3. CSS inlining con premailer (mejora compatibilidad email clients)
        html_body = self._inline_css(html_body)

        # 4. Generar adjuntos si se solicitaron
        attachments: list[Attachment] = []
        for doc_request in request.attachments:
            try:
                generated: GeneratedDocument = await self._generator.generate(doc_request)
                attachments.append(
                    Attachment(
                        filename=generated.filename,
                        data=generated.data,
                        content_type=generated.content_type,
                    )
                )
            except Exception as exc:
                # Un adjunto fallido no cancela el email — se loguea el error
                logger.error(
                    "Error generando adjunto | template=%s error_type=%s",
                    doc_request.template.value, type(exc).__name__,
                )

        # 5. Construir OutboundEmail y enviar
        outbound = OutboundEmail(
            to_email=request.recipient.email,
            to_name=request.recipient.name,
            subject=subject,
            html_body=html_body,
            template_ref=request.template.value,
            attachments=attachments,
        )
        return await self._client.send(outbound)

    # ------------------------------------------------------------------
    # generate_document_only() — descarga directa sin email
    # ------------------------------------------------------------------

    async def generate_document_only(
        self, request: DocumentRequest
    ) -> GeneratedDocument:
        """Genera un documento sin enviarlo por email.

        Útil para los endpoints GET /report/pdf y GET /clearance/docx.

        Raises:
            ValueError: si el contexto es incompleto o el template no existe.
        """
        return await self._generator.generate(request)

    # ------------------------------------------------------------------
    # Helper: CSS inlining
    # ------------------------------------------------------------------

    @staticmethod
    def _inline_css(html: str) -> str:
        """Aplica premailer para inlinear CSS y mejorar compatibilidad.

        Si premailer no está instalado (Paso 0 pendiente), retorna el HTML sin cambios.
        """
        try:
            import premailer
            return premailer.transform(html)
        except ImportError:
            logger.warning("premailer no instalado — CSS inlining omitido")
            return html
        except Exception as exc:
            logger.warning(
                "premailer error — CSS inlining omitido | error_type=%s",
                type(exc).__name__,
            )
            return html
