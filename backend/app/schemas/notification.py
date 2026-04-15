"""
Schemas Pydantic para el módulo de notificaciones y generación de documentos.

Paso 1 del workflow-notifications — entregable: app/schemas/notification.py
"""

from enum import Enum

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NotificationTemplate(str, Enum):
    """Identificadores de templates de email registrados en TemplateRegistry."""

    WELCOME_ATHLETE = "welcome_athlete"
    ANTHROPOMETRY_ALERT = "anthropometry_alert"
    MONTHLY_REPORT = "monthly_report"
    PARENT_INVITE = "parent_invite"


class DocumentTemplate(str, Enum):
    """Identificadores de templates de documentos registrados en TemplateRegistry."""

    ANTHROPOMETRY_REPORT = "anthropometry_report"
    MONTHLY_PROGRESS = "monthly_progress"
    MEDICAL_CLEARANCE = "medical_clearance"


class DocumentFormat(str, Enum):
    """Formato de salida del documento generado."""

    PDF = "pdf"
    DOCX = "docx"


# ---------------------------------------------------------------------------
# Modelos de dominio
# ---------------------------------------------------------------------------


class NotificationRecipient(BaseModel):
    """Destinatario de una notificación por email."""

    email: EmailStr
    name: str = Field(..., min_length=1, description="Nombre para saludo (ej. 'Carlos')")


class GeneratedDocument(BaseModel):
    """Documento generado en memoria listo para adjuntar o descargar.

    `data` contiene los bytes crudos del archivo (PDF o DOCX).
    Nunca se serializa como base64: se transmite directamente vía Response o adjunto.
    """

    filename: str = Field(..., description="Nombre sugerido para descarga (ej. 'reporte_garcia_2026-04.pdf')")
    format: DocumentFormat
    data: bytes
    content_type: str = Field(..., description="MIME type (application/pdf o application/vnd.openxmlformats-...)")

    model_config = {"arbitrary_types_allowed": True}


class DocumentRequest(BaseModel):
    """Solicitud de generación de un documento (PDF o DOCX)."""

    template: DocumentTemplate
    format: DocumentFormat
    context: dict = Field(
        ...,
        description="Variables de contexto para el template (validadas por TemplateRegistry)",
    )
    filename_hint: str | None = Field(
        default=None,
        description="Sufijo sugerido para el nombre de archivo (ej. apellido del atleta)",
    )


class NotificationRequest(BaseModel):
    """Solicitud de envío de email de notificación."""

    recipient: NotificationRecipient
    template: NotificationTemplate
    context: dict = Field(
        default_factory=dict,
        description="Variables de contexto Jinja2 para el template (validadas por TemplateRegistry)",
    )
    attachments: list[DocumentRequest] = Field(
        default_factory=list,
        description="Documentos a generar y adjuntar al email",
    )
    send_async: bool = Field(
        default=True,
        description="True: despacha en BackgroundTask y retorna inmediatamente. False: espera resultado.",
    )


class NotificationResult(BaseModel):
    """Resultado de un intento de envío de email."""

    success: bool
    message_id: str | None = Field(
        default=None,
        description="ID de mensaje devuelto por el proveedor (opaco). 'queued' si fue async.",
    )
    error: str | None = Field(
        default=None,
        description="Mensaje de error si success=False. Nunca contiene PII.",
    )

