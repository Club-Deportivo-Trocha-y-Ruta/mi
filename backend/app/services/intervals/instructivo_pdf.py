"""Servicio: generación del PDF instructivo de una estructura de intervalos
por marca de ciclocomputador (Garmin / Magene / iGPSport) — feature 026, T028.

Wrapper sobre ``DocumentGenerator`` (mismo patrón que
``services/notification/athlete_newsletter_pdf.py``, US3/FR-010/FR-011):

  1. Armar el contexto que exige ``DocumentTemplate.SESSION_INSTRUCTIVO``
     (``templates/documents/pdf/session_instructivo.html``, T027) — reusa
     ``flatten_blocks`` (``services/intervals/structures.py``) para expandir
     los grupos de repetición en la tabla de pasos, con el mismo orden de
     ejecución que ve el motor de matching (D5, research.md).
  2. Delegar el render PDF (Jinja2 + WeasyPrint, despachado a un executor) en
     ``DocumentGenerator.generate``.

Privacidad (Ley 1581, menores):
  - El instructivo NO contiene PII de menores: sin nombre de atleta, sin DOB,
    sin datos médicos — es un documento de apoyo genérico de la sesión.
  - No hay columna ni campo de potencia (watts) en ningún punto del contexto
    (FR-005) — los únicos targets propagados son zona de FC y cadencia.
  - Solo se loguea: template_ref, structure_id, session_id, marca, tamaño en
    bytes. Nunca el contenido del PDF ni datos de la sesión.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.models.interval_structure import IntervalStructure
from app.models.training_session import TrainingSession
from app.schemas.notification import (
    DocumentFormat,
    DocumentRequest,
    DocumentTemplate,
    GeneratedDocument,
)
from app.services.intervals.structures import flatten_blocks
from app.services.notification.document_generator import DocumentGenerator
from app.services.utils.dates_es import format_date_es

logger = logging.getLogger(__name__)

# Misma zona horaria y mismo formato que ``DocumentGenerator._enrich_context``
# (``document_generator.py``) — ``generated_at`` es una required_context_key
# del template (T027/template_registry.py) y por lo tanto debe viajar en el
# contexto ANTES de que ``DocumentGenerator.generate`` valide (el enrich con
# ``setdefault`` corre después de la validación, no la puede satisfacer).
_BOGOTA_TZ = ZoneInfo("America/Bogota")

#: Marcas soportadas por el instructivo (contracts/api.md). El endpoint
#: (router, fuera de este archivo) ya restringe el query param `brand` a este
#: mismo conjunto vía tipo Literal — este chequeo es defensa en profundidad
#: (mismo criterio que ``structures.py::validate_structure_blocks`` revalida
#: guardarraíles que el schema ya cubre en otras rutas de entrada).
SUPPORTED_BRANDS: frozenset[str] = frozenset({"garmin", "magene", "igpsport"})


def _as_str(value: Any) -> str:
    """Devuelve ``.value`` si es un enum, o el string tal cual.

    Duplicado deliberado del helper homónimo de ``structures.py`` — este
    módulo no depende de los internos privados de ese servicio, solo de su
    función pública ``flatten_blocks``.
    """
    return value.value if hasattr(value, "value") else str(value)


def _build_session_context(
    training_session: TrainingSession, structure: IntervalStructure
) -> dict[str, Any]:
    """Arma el dict ``session`` que consume ``session_instructivo.html``.

    ``target_age_band`` viene de la estructura (no de la sesión — una sesión
    no tiene banda de edad propia, es la estructura la que la declara, D3).
    """
    return {
        "technical_focus": training_session.technical_focus,
        "scheduled_date": format_date_es(training_session.scheduled_date),
        "duration_min": training_session.duration_min,
        "location": training_session.location,
        "session_kind": _as_str(training_session.session_kind),
        "objectives": training_session.objectives,
        "target_age_band": _as_str(structure.target_age_band),
    }


def _build_blocks_context(structure: IntervalStructure) -> list[dict[str, Any]]:
    """Aplana los bloques (``flatten_blocks``) y arma las filas de la tabla.

    ``repeat_label`` (ej. "Rep 2 de 4") se deriva de ``repeat_iteration`` del
    ``FlattenedStep`` más el ``repeat_count`` del bloque de origen — el paso
    aplanado no retiene ``repeat_count`` porque es un detalle de autoría, no
    de ejecución (ver docstring de ``FlattenedStep`` en ``structures.py``).
    """
    repeat_counts_by_block_id: dict[int | None, int | None] = {
        block.id: block.repeat_count for block in structure.blocks
    }
    steps = flatten_blocks(structure.blocks)

    rows: list[dict[str, Any]] = []
    for order, step in enumerate(steps, start=1):
        repeat_label: str | None = None
        if step.repeat_iteration is not None:
            total = repeat_counts_by_block_id.get(step.block_id)
            repeat_label = (
                f"Rep {step.repeat_iteration} de {total}"
                if total
                else f"Rep {step.repeat_iteration}"
            )
        rows.append(
            {
                "order": order,
                "block_type": step.block_type,
                "duration_s": step.planned_duration_s,
                "target_zone": step.target_zone,
                "target_cadence_rpm": step.target_cadence_rpm,
                "repeat_label": repeat_label,
            }
        )
    return rows


async def generate_instructivo_pdf(
    generator: DocumentGenerator,
    *,
    structure: IntervalStructure,
    training_session: TrainingSession,
    brand: str,
    club_name: str = "Trocha y Ruta",
) -> GeneratedDocument:
    """Genera el PDF instructivo de una estructura de intervalos (US3).

    Args:
        generator: instancia compartida de ``DocumentGenerator`` (DI — mismo
            patrón que el resto de wrappers de ``services/notification``).
        structure: ``IntervalStructure`` con ``blocks`` eager-loaded — está
            garantizado por todo read-path de ``services/intervals/
            structures.py`` (pasa por ``_structure_select()``).
        training_session: la ``TrainingSession`` dueña de la estructura
            (relación 1:1); el caller (router) ya la resolvió con
            club-scoping antes de llegar acá — este wrapper no vuelve a
            tocar la base de datos.
        brand: ``"garmin" | "magene" | "igpsport"`` (case-insensitive).
        club_name: nombre del club para el encabezado del documento.

    Returns:
        ``GeneratedDocument`` con los bytes del PDF en memoria
        (``content_type="application/pdf"``).

    Raises:
        HTTPException 422: marca no soportada (``unsupported_brand``) —
            defensa en profundidad; el router ya debería rechazarla antes.
        ValueError: si el contexto resultante quedara incompleto (no debería
            ocurrir con los tipos declarados aquí — defensa en profundidad de
            ``TemplateRegistry.validate_document_context``).

    Side-effects: ninguno propio de este wrapper — delega el render
    (síncrono, WeasyPrint) en ``DocumentGenerator.generate``, que lo despacha
    a un executor (no bloquea el event loop).
    """
    brand_normalized = brand.strip().lower()
    if brand_normalized not in SUPPORTED_BRANDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_brand",
                "message": (
                    "Marca de ciclocomputador no soportada. Usá garmin, "
                    "magene o igpsport."
                ),
            },
        )

    context: dict[str, Any] = {
        "brand": brand_normalized,
        "session": _build_session_context(training_session, structure),
        "blocks": _build_blocks_context(structure),
        "club_name": club_name,
        "generated_at": datetime.now(_BOGOTA_TZ).strftime("%Y-%m-%d %H:%M COT"),
    }

    request = DocumentRequest(
        template=DocumentTemplate.SESSION_INSTRUCTIVO,
        format=DocumentFormat.PDF,
        context=context,
        filename_hint=f"{brand_normalized}-{training_session.id}",
    )

    doc = await generator.generate(request)

    logger.info(
        "PDF instructivo generado | template=%s structure_id=%d session_id=%d "
        "brand=%s bytes=%d",
        DocumentTemplate.SESSION_INSTRUCTIVO.value,
        structure.id,
        training_session.id,
        brand_normalized,
        len(doc.data),
    )

    return doc
