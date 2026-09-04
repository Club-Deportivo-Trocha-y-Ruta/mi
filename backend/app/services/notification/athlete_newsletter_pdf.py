"""Servicio: generación del PDF de la bitácora de etapa (feature 038).

Wrapper sobre DocumentGenerator que orquesta:
  1. Construir el contexto completo del template.
  2. Generar el PDF via WeasyPrint.
  3. Calcular el hash SHA-256 para integridad.

Privacidad:
  - Nunca loguear nombre del atleta ni email del padre.
  - Solo loguear: template_ref, tamaño en bytes.
"""

from __future__ import annotations

import calendar
import hashlib
import io
import logging
from datetime import date
from typing import Any

import pdfplumber

from app.schemas.notification import DocumentFormat, DocumentRequest, DocumentTemplate, GeneratedDocument
from app.services.notification.document_generator import DocumentGenerator

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> date | None:
    """Parsea una fecha ISO (``date`` o ``str``); tolera ``None`` y ruido.

    Copiado a propósito de ``stage_log_builder._parse_date`` (mismo criterio
    ya establecido en la feature 038): evita importar ese módulo desde el
    servicio de notificaciones solo por un parser de fechas.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text in ("None", "NaT", "nan"):
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"


#: Tope de páginas de la bitácora (AC-5.2, feature 038): cuerpo en 2 páginas
#: + anexo de crecimiento en la tercera.
_MAX_STAGE_LOG_PAGES = 3


def _pdf_page_count(data: bytes) -> int:
    """Cuenta las páginas de un PDF ya renderizado.

    Se usa solo para decidir la recomposición de la bitácora; ante cualquier
    problema de lectura devuelve 0 para que el llamador se quede con el primer
    render (nunca se aborta la generación por no poder contar páginas).
    """
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages)
    except Exception:  # pragma: no cover - defensivo, pdfplumber ya validó bytes
        logger.warning("No se pudo contar páginas del PDF de bitácora", exc_info=True)
        return 0


def _build_stage_log_pdf_context(
    *,
    athlete_first_name: str,
    athlete_last_name: str,
    year: int,
    month: int,
    stage_log: dict[str, Any],
    anthropometry: dict[str, Any] | None,
    charts_context: dict[str, Any] | None,
    percentile_curves: dict[str, Any] | None,
    race_results: dict[str, Any] | None,
    club_name: str,
    season_year: str | None,
    annex_page_break: bool = True,
) -> dict[str, Any]:
    """Arma el ``context`` Jinja del PDF de bitácora — función pura (F-9).

    Extraída de :func:`generate_stage_log_pdf` para poder probar los gates
    de las secciones de temporada (``charts_annex``/``race_results``) sin
    pasar por WeasyPrint, que no carga en todos los entornos locales (ver
    ``tests/services/notification/test_stage_log_pdf.py``).
    """
    month_label = _month_label(year, month)
    season_year_str = season_year or str(year)

    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    anthro_annex: dict[str, Any] | None = None
    if anthropometry and anthropometry.get("has_records"):
        month_records = [
            record
            for record in (anthropometry.get("records") or [])
            if (lambda d: d is not None and month_start <= d <= month_end)(
                _parse_date(record.get("evaluation_date"))
            )
        ]
        if month_records:
            anthro_annex = {
                **anthropometry,
                "records": month_records,
                "latest": month_records[-1],
            }

    # Los gráficos de temporada solo acompañan al anexo cuando la cima del
    # mes vino de una carrera — build_stage_log()/summit() solo produce
    # kind="race" cuando hubo resultados de carrera dentro de este mes en el
    # snapshot (ver stage_log_builder.py), así que es la misma señal
    # determinista de "hubo carrera en el mes" sin necesitar un flag aparte.
    has_race_this_month = bool((stage_log.get("summit") or {}).get("kind") == "race")
    charts_annex = (
        charts_context
        if has_race_this_month and charts_context and charts_context.get("has_data")
        else None
    )
    percentile_annex = percentile_curves if anthro_annex is not None else None

    # F-9: la sección "Campeonatos" comparte el mismo gate que charts_annex
    # (decisión feature 038 — las secciones de temporada solo aparecen en
    # meses con carrera). Sin carrera este mes, no se envía race_results al
    # template en absoluto.
    race_results_annex = race_results if has_race_this_month else None

    return {
        "athlete_first_name": athlete_first_name,
        "athlete_last_name": athlete_last_name,
        "club_name": club_name,
        "month_label": month_label,
        "season_year": season_year_str,
        "stage_log": stage_log,
        "anthro_annex": anthro_annex,
        "charts_annex": charts_annex,
        "percentile_annex": percentile_annex,
        "race_results": race_results_annex,
        "annex_page_break": annex_page_break,
    }


async def generate_stage_log_pdf(
    generator: DocumentGenerator,
    *,
    athlete_first_name: str,
    athlete_last_name: str,
    athlete_id: int,
    year: int,
    month: int,
    stage_log: dict[str, Any],
    anthropometry: dict[str, Any] | None = None,
    charts_context: dict[str, Any] | None = None,
    percentile_curves: dict[str, Any] | None = None,
    race_results: dict[str, Any] | None = None,
    club_name: str = "Trocha y Ruta",
    season_year: str | None = None,
) -> tuple[GeneratedDocument, str]:
    """Genera el PDF de la bitácora de etapa (feature 038).

    Recibe un ``StageLog`` ya proyectado hacia la familia en vez de
    ``metrics_snapshot``/``ai_narrative`` sueltos — este PDF viaja al padre
    (descarga del portal), así que respeta la misma restricción que
    :func:`app.services.training.stage_log.to_parent_dto`.

    Args:
        stage_log: dict YA proyectado con ``to_parent_dto()`` (allow-list) —
            el llamador (router) es responsable de esa proyección. Nunca debe
            traer ``block_states``, ``grounding_violations`` ni
            ``analyst_reading.source_insight_id`` (uso exclusivo del coach).
        anthropometry: bloque ``pdf_only_blocks["anthropometry"]`` del
            snapshot v1 (mismas claves: ``has_records``, ``records``,
            ``latest``), o ``None``. Se filtra acá a solo los registros
            fechados en el mes — regla del "Anexo de crecimiento" (AC-5.2):
            la página 3 solo aparece cuando existe una medición del mes.
        charts_context: bloque ``pdf_only_blocks["charts_context"]`` (mismas
            3 curvas de temporada del v1), o ``None``. Solo se incluye cuando
            hubo una carrera en el mes — señal tomada de
            ``stage_log["summit"]["kind"] == "race"`` (ver
            ``stage_log_builder.summit()``: la cima solo es de tipo "race"
            cuando hay resultados de carrera del mes en el snapshot).
        percentile_curves: bloque ``pdf_only_blocks["percentile_curves"]``,
            acompaña al anexo de antropometría cuando este aplica.
        race_results: bloque ``email_blocks["race_results"]`` completo
            (feature 039) — el template solo lee ``race_results.championships``
            para la sección "Campeonatos" (contracts/newsletter-context.md).
            F-9: mismo gate ``has_race_this_month`` que ``charts_annex`` —
            decisión de la feature 038 de que las secciones de temporada
            solo aparecen en meses con carrera. Sin carrera en el mes,
            ``race_results`` se descarta antes de llegar al template
            (sección "Campeonatos" ausente). Ausente/``None`` → sin sección
            "Campeonatos", sin error (mismo criterio del resto del
            template: claves ausentes se tratan como vacías).

    No recibe ``db``: las fotos de ``StageLog.photos`` no traen ``media_id``
    (por diseño del modelo, ver
    ``app/services/training/stage_log.py::PhotoView``), así que este PDF las
    referencia directo por ``thumbnail_url`` en vez de embeberlas como
    data-URI.

    Returns:
        (GeneratedDocument con bytes PDF, sha256 hex del PDF)
    """
    context = _build_stage_log_pdf_context(
        athlete_first_name=athlete_first_name,
        athlete_last_name=athlete_last_name,
        year=year,
        month=month,
        stage_log=stage_log,
        anthropometry=anthropometry,
        charts_context=charts_context,
        percentile_curves=percentile_curves,
        race_results=race_results,
        club_name=club_name,
        season_year=season_year,
    )
    anthro_annex = context["anthro_annex"]

    request = DocumentRequest(
        template=DocumentTemplate.ATHLETE_STAGE_LOG,
        format=DocumentFormat.PDF,
        context=context,
        filename_hint=f"{athlete_id}_{year}_{month:02d}_bitacora",
    )

    doc = await generator.generate(request)

    # Válvula de escape de paginación (AC-5.2: la bitácora cabe en 3 páginas).
    # El anexo abre página propia, así que el cuerpo tiene que caber en dos; un
    # mes muy cargado (tres observaciones largas, varias fotos, nota extensa) se
    # pasa por unas decenas de puntos y empuja el último bloque a una tercera
    # página casi vacía, con el anexo abriendo una cuarta. Cuando eso ocurre se
    # vuelve a componer sin el salto forzado: el anexo arranca pegado al cuerpo
    # y el documento vuelve a 3 páginas. Segunda pasada solo en ese caso — el
    # mes típico se resuelve en el primer render.
    if anthro_annex is not None and _pdf_page_count(doc.data) > _MAX_STAGE_LOG_PAGES:
        compact_request = DocumentRequest(
            template=DocumentTemplate.ATHLETE_STAGE_LOG,
            format=DocumentFormat.PDF,
            context={**context, "annex_page_break": False},
            filename_hint=request.filename_hint,
        )
        compact_doc = await generator.generate(compact_request)
        if _pdf_page_count(compact_doc.data) < _pdf_page_count(doc.data):
            logger.info(
                "PDF bitácora recompuesto sin salto de anexo | athlete_id=%d period=%d-%02d",
                athlete_id,
                year,
                month,
            )
            doc = compact_doc

    sha256 = hashlib.sha256(doc.data).hexdigest()

    logger.info(
        "PDF bitácora generado | template=%s athlete_id=%d period=%d-%02d bytes=%d has_annex=%s",
        DocumentTemplate.ATHLETE_STAGE_LOG.value,
        athlete_id,
        year,
        month,
        len(doc.data),
        anthro_annex is not None,
    )

    return doc, sha256
