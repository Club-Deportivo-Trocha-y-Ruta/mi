"""Servicio: generación del PDF del boletín mensual individual.

Wrapper sobre DocumentGenerator que orquesta:
  1. Construir el contexto completo del template.
  2. Generar el PDF via WeasyPrint.
  3. Calcular el hash SHA-256 para integridad.

Privacidad:
  - Nunca loguear nombre del atleta ni email del padre.
  - Solo loguear: template_ref, tamaño en bytes.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.notification import DocumentFormat, DocumentRequest, DocumentTemplate, GeneratedDocument
from app.services.notification.document_generator import DocumentGenerator

logger = logging.getLogger(__name__)


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"


async def generate_newsletter_pdf(
    generator: DocumentGenerator,
    *,
    athlete_first_name: str,
    athlete_last_name: str,
    athlete_id: int,
    year: int,
    month: int,
    email_blocks: dict[str, Any],
    pdf_only_blocks: dict[str, Any],
    ai_narrative: dict[str, Any] | None,
    coach_narrative_overrides: dict[str, Any] | None,
    club_name: str = "Trocha y Ruta",
    season_year: str | None = None,
) -> tuple[GeneratedDocument, str]:
    """Genera el PDF del boletín mensual individual.

    Returns:
        (GeneratedDocument con bytes PDF, sha256 hex del PDF)

    Raises:
        ValueError: si el contexto es inválido para el template.
    """
    month_label = _month_label(year, month)
    season_year_str = season_year or str(year)

    context: dict[str, Any] = {
        "athlete_first_name": athlete_first_name,
        "athlete_last_name": athlete_last_name,
        "club_name": club_name,
        "month_label": month_label,
        "season_year": season_year_str,
        "email_blocks": email_blocks,
        "pdf_only_blocks": pdf_only_blocks,
        "ai_narrative": ai_narrative,
        "coach_narrative_overrides": coach_narrative_overrides,
    }

    request = DocumentRequest(
        template=DocumentTemplate.ATHLETE_MONTHLY_NEWSLETTER,
        format=DocumentFormat.PDF,
        context=context,
        filename_hint=f"{athlete_id}_{year}_{month:02d}",
    )

    doc = await generator.generate(request)

    # Calcular SHA-256 para integridad
    sha256 = hashlib.sha256(doc.data).hexdigest()

    logger.info(
        "PDF boletín generado | template=%s athlete_id=%d period=%d-%02d bytes=%d",
        DocumentTemplate.ATHLETE_MONTHLY_NEWSLETTER.value,
        athlete_id,
        year,
        month,
        len(doc.data),
    )

    return doc, sha256
