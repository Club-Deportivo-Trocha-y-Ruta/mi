"""Servicio: generación del PDF instructivo de una estructura de intervalos
por marca de ciclocomputador (Garmin / Magene / iGPSport) — feature 026, T028.

Wrapper sobre ``DocumentGenerator`` (mismo patrón que
``services/notification/athlete_newsletter_pdf.py``, US3/FR-010/FR-011):

  1. Armar el contexto que exige ``DocumentTemplate.SESSION_INSTRUCTIVO``
     (``templates/documents/pdf/session_instructivo.html``, T027) — la tabla
     de bloques se arma a partir de ``structure.blocks`` **sin aplanar**
     (bloques distintos, en orden de ``position``), porque así es como se
     configura realmente el dispositivo: un grupo de repetición se carga una
     sola vez y el ciclocomputador (o el atleta, con el botón de vuelta) lo
     repite. Se propaga ``repeat_group``/``repeat_count`` por bloque para que
     la plantilla anote "Se repite ×N" una sola vez por grupo, en vez de
     expandir cada iteración como fila (``flatten_blocks`` sigue existiendo
     en ``services/intervals/structures.py`` para el motor de matching, pero
     este wrapper ya no lo usa).
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
    """Arma las filas de la tabla a partir de los bloques SIN aplanar.

    A diferencia del motor de matching (que sí necesita la secuencia real de
    ejecución vía ``flatten_blocks``), el instructivo debe reflejar **cómo se
    configura el dispositivo**: los bloques de un grupo de repetición se
    cargan una sola vez, con su ``repeat_count`` como anotación aparte (ej.
    "Se repite ×2"), no como filas repetidas. Por eso acá se itera
    ``structure.blocks`` en orden de ``position`` (ya viene ordenado por el
    eager-load de ``_structure_select()``, pero se reordena de forma
    defensiva) sin pasar por ``flatten_blocks``.
    """
    ordered = sorted(structure.blocks, key=lambda b: b.position)

    rows: list[dict[str, Any]] = []
    for block in ordered:
        rows.append(
            {
                "order": block.position,
                "block_type": _as_str(block.block_type),
                "duration_s": block.duration_s,
                "target_zone": _as_str(block.target_zone),
                "target_cadence_rpm": block.target_cadence_rpm,
                "repeat_group": block.repeat_group,
                "repeat_count": block.repeat_count,
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
