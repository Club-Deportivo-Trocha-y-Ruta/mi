"""
Document Generator — genera PDF (WeasyPrint) y DOCX (docxtpl) desde templates Jinja2.

Paso 4 del workflow-notifications.

IMPORTANTE: _generate_pdf y _generate_docx son síncronos.
Se invocan via run_in_executor desde NotificationService para no bloquear el event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

_BOGOTA_TZ = ZoneInfo("America/Bogota")

if TYPE_CHECKING:
    from app.config import Settings

from app.schemas.notification import DocumentFormat, DocumentRequest, GeneratedDocument
from app.services.notification.template_registry import TemplateRegistry

logger = logging.getLogger(__name__)

_TEMPLATES_ROOT = Path(__file__).parents[3] / "templates"

# MIME types por formato
_CONTENT_TYPES: dict[DocumentFormat, str] = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


class DocumentGenerator:
    """Orquestador de generación de documentos PDF y DOCX.

    Uso:
        generator = DocumentGenerator(registry, settings)
        doc = await generator.generate(request)
    """

    def __init__(
        self,
        registry: TemplateRegistry,
        settings: "Settings | None" = None,
        templates_root: Path | None = None,
    ) -> None:
        self._registry = registry
        self._root = templates_root or _TEMPLATES_ROOT

        # Inicializar entorno Jinja2 con FileSystemLoader
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        self._jinja = Environment(
            loader=FileSystemLoader(str(self._root)),
            autoescape=select_autoescape(["html"]),
        )

        # Nombre del club para enriquecer contexto automáticamente
        self._club_name: str = getattr(settings, "club_name", "Trocha y Ruta") if settings else "Trocha y Ruta"

    # ------------------------------------------------------------------
    # API pública (async — despacha trabajo síncrono al executor)
    # ------------------------------------------------------------------

    async def generate(self, request: DocumentRequest) -> GeneratedDocument:
        """Genera el documento y retorna GeneratedDocument con bytes en memoria.

        Raises:
            ValueError: si el contexto es incompleto o el template no existe.
        """
        # Validar contexto vía registry antes de lanzar al executor
        self._registry.validate_document_context(request.template.value, request.context)

        spec = self._registry.get_document_spec(request.template.value)

        # Enriquecer contexto con campos automáticos
        enriched = self._enrich_context(request.context)

        loop = asyncio.get_running_loop()

        if request.format == DocumentFormat.PDF:
            doc = await loop.run_in_executor(
                None, self._generate_pdf, spec, enriched, request
            )
        else:
            doc = await loop.run_in_executor(
                None, self._generate_docx, spec, enriched, request
            )

        return doc

    # ------------------------------------------------------------------
    # Generadores síncronos (ejecutados en threadpool)
    # ------------------------------------------------------------------

    def _generate_pdf(self, spec, context: dict, request: DocumentRequest) -> GeneratedDocument:
        """Renderiza template HTML con Jinja2 y convierte a PDF con WeasyPrint."""
        from weasyprint import HTML

        # Render Jinja2
        template = self._jinja.get_template(spec.template_path)
        html_string = template.render(**context)

        # Convertir a PDF en memoria
        pdf_bytes = HTML(
            string=html_string,
            base_url=str(self._root),
        ).write_pdf(optimize_images=True)

        filename = self._build_filename(request, "pdf")
        # No loguear filename — contiene apellido del atleta (dato ALTO)
        logger.info(
            "PDF generado | template=%s bytes=%d",
            spec.template_id, len(pdf_bytes),
        )

        return GeneratedDocument(
            filename=filename,
            format=DocumentFormat.PDF,
            data=pdf_bytes,
            content_type=_CONTENT_TYPES[DocumentFormat.PDF],
        )

    def _generate_docx(self, spec, context: dict, request: DocumentRequest) -> GeneratedDocument:
        """Renderiza template DOCX con docxtpl (Jinja2 en Word) y retorna bytes."""
        from docxtpl import DocxTemplate

        template_path = self._root / spec.template_path
        doc = DocxTemplate(str(template_path))
        doc.render(context)

        buffer = BytesIO()
        doc.save(buffer)
        docx_bytes = buffer.getvalue()

        filename = self._build_filename(request, "docx")
        # No loguear filename — contiene apellido del atleta (dato ALTO)
        logger.info(
            "DOCX generado | template=%s bytes=%d",
            spec.template_id, len(docx_bytes),
        )

        return GeneratedDocument(
            filename=filename,
            format=DocumentFormat.DOCX,
            data=docx_bytes,
            content_type=_CONTENT_TYPES[DocumentFormat.DOCX],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _enrich_context(self, context: dict) -> dict:
        """Agrega campos automáticos: generated_at, club_name."""
        enriched = dict(context)
        enriched.setdefault("generated_at", datetime.now(_BOGOTA_TZ).strftime("%Y-%m-%d %H:%M COT"))
        enriched.setdefault("club_name", self._club_name)
        return enriched

    @staticmethod
    def _build_filename(request: DocumentRequest, ext: str) -> str:
        """Construye nombre de archivo con apellido del atleta y fecha actual.

        Formato: {template}_{apellido}_{fecha}.{ext}
        Ejemplo: anthropometry_report_garcia_2026-04-15.pdf
        """
        today = date.today().isoformat()
        # Usar filename_hint si está disponible (apellido del atleta)
        hint = request.filename_hint or "atleta"
        # Sanitizar: minúsculas, sin espacios
        hint_clean = hint.lower().replace(" ", "_")[:30]
        template_slug = request.template.value.replace("_", "-")
        return f"{template_slug}_{hint_clean}_{today}.{ext}"
