"""Router ``/api/race-analysis/imports/*`` — wizard upload UI race PDFs (F-UP3).

Endpoints (docs/10-race-results/upload-design.md §4):

- ``POST /parse``              — multipart upload (RESULTADOS + GENERAL opcional).
                                   Valida magic bytes / tamaño / sanitiza filename,
                                   sube PDFs a SFTP path
                                   ``race-imports/pending/{uuid}/...``, parsea
                                   con pdfplumber (timeout ``RACE_PARSE_TIMEOUT_SECONDS``),
                                   crea ``RaceImport`` status=pending, retorna
                                   ``parse_id`` + header detectado + conteos.
- ``POST /{parse_id}/dry-run`` — ejecuta ``RaceIngestor.ingest_event(dry_run=True)``
                                   con los datos del parse persistido. Devuelve
                                   ``matches`` con resolución HITL pendiente.
- ``POST /{parse_id}/commit``  — ejecuta ``RaceIngestor.ingest_event(dry_run=False)``
                                   con ``resolved_matches`` del coach. Promueve
                                   pending → committed. Mueve PDFs SFTP a
                                   ``race-imports/committed/{uuid}/``.
- ``GET /``                    — histórico paginado. RBAC: coach + admin.

Feature 044 (US1, research R-05, ``contracts/reading-integrity.md``): además,
``POST /parse`` gana ``categories[]``/``unreadable_rows[]`` (lector por banda
de ``pdf_parser.parse_results_document``), y tres rutas nuevas:

- ``POST /{parse_id}/corrections``  — parcha una fila (add/edit/remove) de
                                        una categoría; se persiste en
                                        ``parse_meta_json.corrections`` y se
                                        reaplica en cada dry-run/commit.
- ``POST /{parse_id}/acknowledge``  — reconoce una categoría inconsistente
                                        con un motivo del catálogo cerrado.
- ``GET /acknowledge-reasons``      — catálogo cerrado del dropdown.

Convenciones:
- RBAC ``require_role([coach, admin])`` — padres bloqueados.
- Magic bytes obligatorios: ``%PDF-`` para PDF, primera línea con delimitador
  CSV-like para .csv.
- Cap tamaño desde ``settings.race_max_pdf_mb`` (default 8 MB).
- Path en storage: ``race-imports/{pending|committed}/{uuid}/{resultados|general}.{ext}``
  — UUID server-side evita path traversal en filename original.

Privacidad (CLAUDE.md):
- Logs nunca incluyen nombres de menores — usan ``bib`` + ``cat_code`` + sha256.
- ``MatchPreview.competitor_name`` contiene nombre del PDF público Federación
  (no datos privados).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from collections import OrderedDict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path as PathLib
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction
from app.models.club import ClubMember, ClubRole
from app.models.race_category import RaceCategory
from app.models.race_identity_candidate import (
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_event import RaceEvent
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.schemas.race import EventMeta
from app.schemas.race_imports import (
    AcknowledgeIn,
    AcknowledgeReasonOption,
    AcknowledgeReasonsResponse,
    CategoryCompletenessResponse,
    CompletenessRead,
    DryRunCounts,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportDryRunResponse,
    ImportListItem,
    ImportListResponse,
    ImportParseRequestFields,
    ImportParseResponse,
    MatchPreview,
    ParseWarning,
    RaceEventDiffResponse,
    REVISION_REASON_LABELS,
    RevisionReasonCode,
    RevisionReasonOption,
    RevisionReasonsResponse,
    RowCorrectionIn,
    TyrAthleteRef,
    UploadUserRef,
)
from app.services.audit import AuditEntityType, record_audit
from app.services.permissions import coach_club_ids, ensure_import_club_access
from app.services.race.completeness import (
    ACKNOWLEDGE_REASON_LABELS,
    AcknowledgeReasonCode,
    CompletenessReport,
    CorrectionError,
    apply_corrections,
    check_category,
)
from app.services.race import identity_review
from app.services.race.import_staging import (
    _category_headers_raw,
    _legacy_results_by_category,
    _parse_general_with_timeout,
    _parse_results_with_timeout,
    stage_results_file,
)
from app.services.race.ingestor import RaceIngestor
from app.services.race.matcher import match_athletes
from app.services.race.pdf_parser import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
)
from app.services.race.revision_diff_view import build_event_diff_view
from app.services.race.run_staleness import invalidate_runs_for_event
from app.services.request_context import AuditContext, get_request_context
from app.services.training import storage_sftp

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Constantes y helpers de validación
# ---------------------------------------------------------------------------

_PDF_MAGIC = b"%PDF-"

#: Sanitización filename: keep alnum, dash, underscore, dot. Strip path-traversal.
_FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.\-]")

#: Cabecera CSV Copa Valle. Heurística: cualquier línea con coma/punto-coma/tab
#: que contenga las palabras clave esperadas. Si no matchea, 415.
_CSV_DELIMITERS = (",", ";", "\t")

def _sanitize_filename(raw: Optional[str]) -> str:
    """Devuelve un filename seguro para preservar en BD. Cero path traversal."""
    if not raw:
        return "upload.pdf"
    # Nos quedamos solo con el basename (Windows + Unix)
    base = PathLib(raw.replace("\\", "/")).name
    safe = _FILENAME_SAFE_RE.sub("_", base)
    # Cap a 200 chars (columna filename) y prevenir empty
    safe = safe[:200] or "upload.pdf"
    return safe


def _is_pdf(content: bytes) -> bool:
    return len(content) >= 5 and content[:5] == _PDF_MAGIC


def _is_csv_like(content: bytes) -> bool:
    """Acepta CSV si decodifica UTF-8 y la primera línea contiene delimitador."""
    try:
        head = content[:4096].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    first_line = head.splitlines()[0] if head else ""
    return any(d in first_line for d in _CSV_DELIMITERS)


def _compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def _read_with_cap(file: UploadFile, max_mb: int) -> bytes:
    """Lee el archivo subido con cap defensivo (max_mb + 1 byte para detectar exceso)."""
    max_bytes = max_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Archivo '{file.filename}' supera el límite ({max_mb} MB). "
                f"PDFs Federación típicos = 250 KB."
            ),
        )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo '{file.filename}' está vacío.",
        )
    return raw


def _validate_results_magic(content: bytes, filename: str) -> str:
    """Valida que el RESULTADOS sea PDF o CSV reconocible. Retorna extensión normalizada."""
    fname_lower = (filename or "").lower()
    if fname_lower.endswith(".pdf"):
        if not _is_pdf(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo no es un PDF válido (magic bytes '%PDF-' ausentes).",
            )
        return "pdf"
    if fname_lower.endswith((".csv", ".tsv", ".txt")):
        if not _is_csv_like(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo no es un CSV válido (UTF-8 + delimitador requerido).",
            )
        return "csv"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Formato no soportado. RESULTADOS acepta .pdf, .csv, .tsv, .txt."
        ),
    )


def _validate_general_magic(content: bytes, filename: str) -> None:
    """GENERAL solo acepta PDF (Federación nunca publica GENERAL en CSV)."""
    if not (filename or "").lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GENERAL solo acepta .pdf.",
        )
    if not _is_pdf(content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GENERAL no es un PDF válido (magic bytes '%PDF-' ausentes).",
        )


# ---------------------------------------------------------------------------
# Helpers internos — series + parsing
#
# Feature 044 (US5, T059): ``_get_or_create_series``, ``_parse_results_with_
# timeout``, ``_parse_general_with_timeout``, ``_legacy_results_by_category``,
# ``_category_headers_raw``, ``_categories_read``, ``_categories_meta`` y
# ``_unreadable_rows_meta`` se extrajeron a
# ``app.services.race.import_staging`` (contracts/historical-load.md
# §"Staging service") y se re-importan arriba — el script de carga
# histórica los reutiliza sin pasar por FastAPI, y este router queda como
# llamador delgado. La re-exportación mantiene los tests existentes que
# hacen ``monkeypatch.setattr(router_mod, "_parse_..._with_timeout", ...)``
# funcionando para el camino dry-run/commit (que sigue viviendo aquí); los
# tests que ejercitan ``POST /parse`` parchan además
# ``app.services.race.import_staging`` (única copia que ``stage_results_
# file`` usa internamente).
# ---------------------------------------------------------------------------


def _update_category_cache(
    categories_meta: list[dict],
    header: str,
    *,
    rows: int,
    completeness: CompletenessReport,
) -> list[dict]:
    """Actualiza (o agrega) la entrada de ``header`` en la caché de solo
    lectura ``parse_meta_json["categories"]`` tras una corrección o un
    reconocimiento. No es la fuente de verdad — esa es el archivo almacenado
    más ``corrections``/``acknowledged`` — solo evita que la caché quede
    desactualizada frente a lo que un futuro listado mostraría.
    """
    updated = [dict(entry) for entry in categories_meta]
    completeness_dict = {
        "status": completeness.status,
        "missing": completeness.missing,
        "duplicated": completeness.duplicated,
    }
    for entry in updated:
        if entry.get("header_raw") == header:
            entry["rows"] = rows
            entry["completeness"] = completeness_dict
            return updated
    updated.append(
        {
            "header_raw": header,
            "code": None,
            "mapping_kind": "unknown",
            "rows": rows,
            "completeness": completeness_dict,
        }
    )
    return updated


# ---------------------------------------------------------------------------
# Endpoint 1: POST /parse
# ---------------------------------------------------------------------------


@router.post("/parse", response_model=ImportParseResponse)
async def parse_import(
    resultados_pdf: Annotated[
        UploadFile, File(description="PDF/CSV RESULTADOS (requerido)")
    ],
    series_name: Annotated[str, Form(min_length=1, max_length=100)],
    season: Annotated[int, Form(ge=2020, le=2100)],
    valida_num: Annotated[int, Form(ge=1, le=99)],
    event_name: Annotated[str, Form(min_length=1, max_length=200)],
    event_date: Annotated[str, Form(description="ISO date YYYY-MM-DD")],
    location: Annotated[str, Form(min_length=1, max_length=150)],
    general_pdf: Annotated[
        Optional[UploadFile], File(description="PDF GENERAL (opcional)")
    ] = None,
    kind: Annotated[Optional[str], Form()] = None,  # 'resultados'|'general'|'both'
    series_kind: Annotated[
        Optional[str],
        Form(description="Tipo de serie: 'cup' (default) o 'championship'. Retrocompatible."),
    ] = None,
    series_level: Annotated[
        Optional[str],
        Form(
            description="Ámbito del campeonato: 'departmental' (default) o 'national'. Retrocompatible."
        ),
    ] = None,
    # --- Condiciones de carrera (opcionales — no están en el PDF) ---
    climate: Annotated[
        Optional[str],
        Form(description="Descripción libre del clima (máx 60 chars)."),
    ] = None,
    temperature_c: Annotated[
        Optional[Decimal],
        Form(description="Temperatura en °C (0-50, un decimal)."),
    ] = None,
    surface_condition: Annotated[
        Optional[str],
        Form(description="seca | humeda | barro | lluvia | mixta"),
    ] = None,
    altitude_msnm: Annotated[
        Optional[int],
        Form(description="Altitud msnm (0-5000)."),
    ] = None,
    weather_notes: Annotated[
        Optional[str],
        Form(description="Notas climatológicas adicionales (máx 2000 chars)."),
    ] = None,
    # ---------------------------------------------------------------
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ctx: AuditContext = Depends(get_request_context),
) -> ImportParseResponse:
    """Endpoint 1 wizard (parse) — sube PDFs, valida, parsea, crea pending.

    Los campos de condiciones de carrera (climate, temperature_c, etc.) son
    opcionales y retrocompatibles: parse sin ellos funciona exactamente igual.
    Se validan vía ``ImportParseRequestFields`` antes de persistir en
    ``parse_meta_json`` para garantizar invariantes (rangos, longitudes).

    El campo ``series_kind`` (default 'cup') indica si los resultados corresponden
    a una copa con rondas o a un campeonato anual. Retrocompatible: clientes que
    no envían el campo reciben el comportamiento de copa (existente).

    El campo ``series_level`` (default 'departmental', spec 023) indica el
    ámbito territorial de un campeonato nuevo (departmental | national). Solo
    se consulta cuando ``_get_or_create_series`` crea una serie de tipo
    ``championship``; el organizer "Liga Vallecaucana de Ciclismo" NO se
    aplica a campeonatos nuevos (D5).

    Feature 044 (US5, T059): el cuerpo de este endpoint vive ahora en
    ``app.services.race.import_staging.stage_results_file`` — este handler
    solo valida el multipart/Form (magic bytes, tamaño, enums crudos, fecha
    ISO) y delega. ``contracts/historical-load.md`` §"Staging service".
    """
    # Validar y resolver series_kind
    resolved_series_kind: RaceSeriesKind = RaceSeriesKind.cup
    if series_kind is not None:
        try:
            resolved_series_kind = RaceSeriesKind(series_kind)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"series_kind inválido: '{series_kind}'. "
                    "Valores permitidos: cup, championship."
                ),
            )

    # Validar y resolver series_level (spec 023)
    resolved_series_level: RaceSeriesLevel = RaceSeriesLevel.departmental
    if series_level is not None:
        try:
            resolved_series_level = RaceSeriesLevel(series_level)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"series_level inválido: '{series_level}'. "
                    "Valores permitidos: departmental, national."
                ),
            )

    # Validar campos de condiciones mediante el schema Pydantic
    # (FastAPI no aplica validación Pydantic a Form() individuales)
    from pydantic import ValidationError as PydanticValidationError

    from app.models.race_event import SurfaceCondition as _SurfaceCondition

    surface_condition_enum: Optional[_SurfaceCondition] = None
    if surface_condition is not None:
        try:
            surface_condition_enum = _SurfaceCondition(surface_condition)
        except ValueError:
            values = [e.value for e in _SurfaceCondition]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"surface_condition inválido: '{surface_condition}'. Valores permitidos: {values}.",
            )

    try:
        conditions_fields = ImportParseRequestFields(
            climate=climate,
            temperature_c=temperature_c,
            surface_condition=surface_condition_enum,
            altitude_msnm=altitude_msnm,
            weather_notes=weather_notes,
        )
    except PydanticValidationError as exc:
        # `exc.errors()` puede contener `input=Decimal(...)` cuando el campo
        # inválido es `temperature_c`; Decimal NO es JSON-serializable y
        # rompería la respuesta 422 con HTTP 500. Pasamos por `jsonable_encoder`
        # para forzar conversión Decimal -> str antes de serializar el body.
        from fastapi.encoders import jsonable_encoder

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=jsonable_encoder(exc.errors(include_url=False)),
        )

    # Validar fecha ISO — antes solo se validaba al re-construir EventMeta en
    # dry-run (`_build_event_meta_from_parse_meta`); feature 044 la valida ya
    # en /parse porque ``stage_results_file`` la recibe tipada (``date``).
    try:
        event_date_obj = date.fromisoformat(event_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event_date inválido: '{event_date}'. Formato esperado YYYY-MM-DD.",
        )

    # Leer + validar magic bytes RESULTADOS
    resultados_bytes = await _read_with_cap(resultados_pdf, settings.race_max_pdf_mb)
    results_ext = _validate_results_magic(
        resultados_bytes, resultados_pdf.filename or "upload.pdf"
    )

    # (Opcional) GENERAL — solo PDF
    general_bytes: Optional[bytes] = None
    if general_pdf is not None and (general_pdf.filename or ""):
        general_bytes = await _read_with_cap(general_pdf, settings.race_max_pdf_mb)
        _validate_general_magic(general_bytes, general_pdf.filename or "general.pdf")

    # Determinar override de `kind` (auto-detección vive en el service)
    kind_override: Optional[RaceImportKind] = None
    if kind is not None:
        try:
            kind_override = RaceImportKind(kind)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"kind inválido: {kind}. Permitidos: resultados, general, both.",
            )

    return await stage_results_file(
        db,
        file_bytes=resultados_bytes,
        original_filename=resultados_pdf.filename or "upload.pdf",
        results_ext=results_ext,
        series_name=series_name,
        season=season,
        valida_num=valida_num,
        event_name=event_name,
        event_date=event_date_obj,
        location=location,
        series_kind=resolved_series_kind,
        series_level=resolved_series_level,
        conditions=conditions_fields,
        general_bytes=general_bytes,
        kind_override=kind_override,
        actor=current_user,
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: POST /{parse_id}/dry-run
# ---------------------------------------------------------------------------


async def _load_pending_import(
    db: AsyncSession,
    parse_id: int,
    current_user: User,
    *,
    for_update: bool = False,
) -> RaceImport:
    """Carga un RaceImport pending por id + verifica alcance por club.

    El chequeo de club (``ensure_import_club_access``, contrato
    scope-ai-imports §6.1) reemplazó al viejo creator-lock: cualquier coach
    del club puede continuar el cargue que empezó otro coach del mismo club.
    Las dos ramas 404 de arriba (id desconocido, estado ya no ``pending``) se
    evalúan primero y no cambian.
    """
    stmt = select(RaceImport).where(RaceImport.id == parse_id)
    if for_update:
        # Serializa commits concurrentes del mismo parse_id (MySQL InnoDB).
        # SQLite (tests) ignora FOR UPDATE — no-op inofensivo.
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    imp = result.scalar_one_or_none()
    if imp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"parse_id={parse_id} no existe.",
        )
    if imp.status != RaceImportStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"parse_id={parse_id} no está en estado pending "
                f"(actual: {imp.status.value}). No se puede dry-run/commit."
            ),
        )
    await ensure_import_club_access(db, imp, current_user)
    return imp


async def _load_committed_import_with_pending(
    db: AsyncSession,
    parse_id: int,
    current_user: User,
    *,
    for_update: bool = False,
) -> RaceImport:
    """Carga un RaceImport ``committed`` con categorías pendientes — soporte
    de ``POST /{parse_id}/commit-pending`` (contracts/historical-load.md
    §"Idempotence and resumption"). Un commit parcial deja el import
    ``committed`` (sin un enum nuevo, research R-05) con
    ``parse_meta_json["pending_categories"]`` no vacío; esta carga es su
    contraparte de ``_load_pending_import``.

    404 si el id no existe o el import nunca llegó a ``committed``; 409
    ``nothing_pending`` si ya no queda ninguna categoría pendiente en el
    caché de meta (chequeo barato antes de tocar SFTP — el commit-pending
    vuelve a verificarlo tras re-parsear, por si las correcciones dejaron
    todo consistente pero nadie limpió el contador).
    """
    stmt = select(RaceImport).where(RaceImport.id == parse_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    imp = result.scalar_one_or_none()
    if imp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"parse_id={parse_id} no existe.",
        )
    if imp.status != RaceImportStatus.committed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"parse_id={parse_id} no está en estado committed "
                f"(actual: {imp.status.value}). No se puede commit-pending."
            ),
        )
    await ensure_import_club_access(db, imp, current_user)
    pending = (imp.parse_meta_json or {}).get("pending_categories") or []
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "nothing_pending",
                "message": "No quedan categorías pendientes en este cargue.",
            },
        )
    return imp


def _matches_unresolved_error(missing: set[str]) -> HTTPException:
    """``409 matches_unresolved`` — el coach del `HistoricalLoadPage` commitea
    con ``resolved_matches: []`` siempre (no hay UI de resolución de matches
    en el tablero); si el acta trae competidores TyR sin decisión, el board
    debe poder distinguir esto de ``identity_review_pending``/
    ``nothing_pending`` y mandar al coach al Import Wizard en vez de
    commitear sin vincular en silencio. ``missing`` son slugs normalizados
    (``competitor_normalized_name``), nunca el nombre de pila — misma
    sensibilidad que el resto de la cola de identidad.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "matches_unresolved",
            "missing_count": len(missing),
            "examples": sorted(missing)[:3],
            "message": (
                f"Faltan resolved_matches para {len(missing)} atleta(s) TyR. "
                "Resuélvelos en el Import Wizard antes de confirmar la carga."
            ),
        },
    )


def _eligible_and_pending_categories(
    categories: list[ParsedCategory],
    parse_meta: dict,
    *,
    restrict_to_headers: Optional[set[str]] = None,
) -> tuple[set[str], list[str]]:
    """Separa las categorías re-parseadas (con correcciones ya aplicadas) en
    ``(eligible_codes, pending_categories)`` — contracts/historical-load.md
    §"Idempotence and resumption": elegible es ``status == "ok"`` o
    reconocida (``AcknowledgeIn``); todo lo demás (inconsistente sin
    reconocer, o header sin ``code`` resuelto) queda pendiente. ``pending_
    categories`` lleva el ``header_raw`` — el mismo identificador que usan
    ``/corrections`` y ``/acknowledge`` — nunca un ``code`` que podría ser
    ``None``.

    ``restrict_to_headers``, usado por ``/commit-pending``: limita la
    evaluación a estos headers (los que quedaron ``pending_categories`` del
    commit anterior) — sin esto, una categoría YA commiteada en una pasada
    previa (consistente desde el inicio) volvería a contarse como
    "elegible" en cada ``/commit-pending`` posterior, y el gate ``409
    nothing_pending`` nunca dispararía aunque nada nuevo se hubiera vuelto
    consistente. ``None`` (el caso de ``/commit``) evalúa todas las
    categorías, como siempre.
    """
    acknowledged_headers = {
        a.get("category_header") for a in (parse_meta.get("acknowledged") or [])
    }
    eligible_codes: set[str] = set()
    pending_categories: list[str] = []
    for cat in categories:
        if restrict_to_headers is not None and cat.header_raw not in restrict_to_headers:
            continue
        if cat.code is None:
            pending_categories.append(cat.header_raw)
            continue
        report = check_category(cat)
        if report.status == "ok" or cat.header_raw in acknowledged_headers:
            eligible_codes.add(cat.code)
        else:
            pending_categories.append(cat.header_raw)
    return eligible_codes, pending_categories


async def _load_correctable_import(
    db: AsyncSession, parse_id: int, current_user: User
) -> RaceImport:
    """Carga un import sobre el que ``/corrections``/``/acknowledge`` pueden
    operar: ``pending`` (aún no commiteado, el caso de siempre) o
    ``committed`` con ``pending_categories`` (feature 044, US5) — un commit
    parcial deja categorías por resolver y el coach necesita poder
    corregirlas/reconocerlas antes de ``/commit-pending``, sin que el import
    haya vuelto a ``pending``. 404 en cualquier otro caso (id inexistente, o
    un import ya sin nada pendiente).
    """
    result = await db.execute(select(RaceImport).where(RaceImport.id == parse_id))
    imp = result.scalar_one_or_none()
    if imp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"parse_id={parse_id} no existe.",
        )
    has_pending_categories = bool(
        (imp.parse_meta_json or {}).get("pending_categories")
    )
    is_correctable = imp.status == RaceImportStatus.pending or (
        imp.status == RaceImportStatus.committed and has_pending_categories
    )
    if not is_correctable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"parse_id={parse_id} no admite corrección/reconocimiento "
                f"(estado: {imp.status.value})."
            ),
        )
    await ensure_import_club_access(db, imp, current_user)
    return imp


# ---------------------------------------------------------------------------
# G4 mitigation (plan.md Complexity Tracking, nota sobre T060/T061):
# ``load_identity_rows`` re-descarga y re-parsea cada import en staging en
# CADA ``/rebuild`` y en cada gate de commit (que hace un rebuild primero) —
# medido en 0.60 s/archivo de 229 filas, ≈9 s para las quince válidas
# históricas más latencia SFTP. Dos cachés LRU acotadas y locales al proceso
# (el filesystem de Render es efímero — no hay nada que persistir entre
# deploys, así que un dict en memoria basta):
#
# - ``_RAW_PARSE_CACHE`` — el parseo crudo (sin correcciones), por
#   ``sha256``. El archivo almacenado nunca cambia para un import ya creado
#   (una revisión sube un import NUEVO con su propio sha), así que esta
#   entrada nunca se invalida — solo se desaloja por LRU.
# - ``_CORRECTED_CATEGORIES_CACHE`` — categorías con correcciones ya
#   aplicadas, por ``(sha256, corrections_revision)``. ``corrections`` en
#   ``parse_meta_json`` solo crece por *append* (nunca se edita/borra una ya
#   guardada — ver ``add_correction``), así que ``len(corrections)`` es una
#   revisión válida y barata: una corrección nueva cambia la clave y la
#   entrada vieja simplemente deja de pedirse (invalidación implícita, sin
#   lógica extra).
#
# Ambas cachés son puramente de lectura para sus consumidores (el ingestor,
# ``_categories_read``, ``check_category`` no mutan lo que reciben;
# ``apply_corrections`` hace ``copy.deepcopy`` antes de tocar nada), así que
# reusar el mismo objeto entre llamadas es seguro.
# ---------------------------------------------------------------------------

_PARSED_CACHE_MAX_ENTRIES = 32

# PRIVACIDAD (auditoría T090, 2026-09-22): estas dos cachés guardan la
# parrilla COMPLETA sin filtrar — nombre, club y ciudad de cada fila, incluidos
# cientos de menores ajenos al club. Son seguras solo porque todos sus
# llamadores (dry-run, commit, commit-pending, corrections, acknowledge y el
# rebuild de identidad vía ``load_identity_rows``) exigen
# ``require_role([admin, coach])``. Un llamador nuevo DEBE tener el mismo
# guard; nunca sirvas su contenido a un padre, a un atleta ni a un log.
_RAW_PARSE_CACHE: "OrderedDict[str, ParsedResults]" = OrderedDict()
_CORRECTED_CATEGORIES_CACHE: "OrderedDict[tuple[str, int], list[ParsedCategory]]" = (
    OrderedDict()
)


def _lru_get(cache: "OrderedDict", key):
    value = cache.get(key)
    if value is not None:
        cache.move_to_end(key)
    return value


def _lru_put(cache: "OrderedDict", key, value) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _PARSED_CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


def clear_parsed_rows_caches() -> None:
    """Vacía ambas cachés — usado por tests para aislar casos entre sí."""
    _RAW_PARSE_CACHE.clear()
    _CORRECTED_CATEGORIES_CACHE.clear()


async def _reload_results_document(imp: RaceImport) -> ParsedResults:
    """Descarga + parsea solo RESULTADOS desde storage, SIN aplicar las
    correcciones guardadas (research R-05). Building block de
    ``_reload_parsed_from_storage`` y de los endpoints de corrección /
    reconocimiento (T019), que necesitan un parseo fresco del acta tal como
    quedó impresa para validar una corrección nueva contra el estado real.

    En producción (SFTP configurado) el ``storage_path`` es un path remoto
    Hostinger que no existe en el disco del contenedor. Se descarga vía FTPS
    a un archivo temporal, se parsea y se borra en el finally.

    G4: cacheado por ``sha256`` (ver comentario arriba) — un import pending
    referencia siempre el mismo archivo, así que el segundo llamador en
    adelante (otra corrección, otro rebuild) no vuelve a tocar SFTP.
    """
    if imp.sha256:
        cached = _lru_get(_RAW_PARSE_CACHE, imp.sha256)
        if cached is not None:
            return cached

    meta = imp.parse_meta_json or {}
    results_ext = meta.get("results_ext", "pdf")

    try:
        results_tmp_path = await storage_sftp.download_to_tempfile(
            imp.storage_path or "", suffix=f".{results_ext}"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                f"PDF RESULTADOS no encontrado en storage "
                f"(path={imp.storage_path}). Re-suba el archivo."
            ),
        )

    # ¿Es el path un temporal nuevo (SFTP) o el mismo local ya existente?
    results_is_tmp = str(results_tmp_path) != str(imp.storage_path or "")
    try:
        parsed = await _parse_results_with_timeout(results_tmp_path, results_ext)
    finally:
        if results_is_tmp:
            try:
                os.unlink(results_tmp_path)
            except OSError:
                pass
    if imp.sha256:
        _lru_put(_RAW_PARSE_CACHE, imp.sha256, parsed)
    return parsed


async def _reload_parsed_from_storage(
    imp: RaceImport,
) -> tuple[
    dict[str, list], Optional[dict[str, list]], str, dict[str, str], list[ParsedCategory]
]:
    """Re-carga RESULTADOS (+ GENERAL opcional) desde el storage path persistido
    durante /parse. Retorna ``(results, general, results_ext,
    category_headers_raw, categories)``.

    Necesario para dry-run/commit: el bytes original ya está en SFTP/local; lo
    descargamos a tmp, parseamos, descartamos.

    Feature 044 (US1, research R-05): las correcciones manuales guardadas en
    ``parse_meta_json["corrections"]`` se reaplican aquí, ANTES de que el
    resultado llegue al ingestor — las filas parseadas se re-derivan del
    archivo almacenado en cada dry-run/commit, así que una corrección que no
    se reaplicara en este punto se perdería en silencio.

    Feature 044 (US5, T060/T061): también se retorna ``categories`` (la lista
    completa, incluidas las de encabezado no reconocido) — el commit la usa
    para decidir qué categorías son elegibles y cuáles quedan en
    ``pending_categories``, algo que ``parsed_results`` (que ya excluye las de
    ``code=None``) no puede responder por sí solo.

    G4: cacheado por ``(sha256, corrections_revision)`` — ver comentario
    sobre ``_CORRECTED_CATEGORIES_CACHE`` más arriba.
    """
    meta = imp.parse_meta_json or {}
    results_ext = meta.get("results_ext", "pdf")
    corrections = meta.get("corrections") or []

    categories: Optional[list[ParsedCategory]] = None
    cache_key = (imp.sha256, len(corrections)) if imp.sha256 else None
    if cache_key is not None:
        categories = _lru_get(_CORRECTED_CATEGORIES_CACHE, cache_key)
    if categories is None:
        parsed_doc = await _reload_results_document(imp)
        if corrections:
            parsed_doc = apply_corrections(parsed_doc, corrections)
        categories = parsed_doc.categories
        if cache_key is not None:
            _lru_put(_CORRECTED_CATEGORIES_CACHE, cache_key, categories)

    categories_doc = ParsedResults(categories=categories, unreadable_rows=[])
    category_headers_raw = _category_headers_raw(categories_doc)
    parsed_results = _legacy_results_by_category(categories_doc)

    # --- GENERAL (opcional) ---
    parsed_general: Optional[dict[str, list]] = None
    if imp.general_storage_path:
        try:
            general_tmp_path = await storage_sftp.download_to_tempfile(
                imp.general_storage_path, suffix=".pdf"
            )
            general_is_tmp = str(general_tmp_path) != str(imp.general_storage_path)
            try:
                parsed_general = await _parse_general_with_timeout(general_tmp_path)
            finally:
                if general_is_tmp:
                    try:
                        os.unlink(general_tmp_path)
                    except OSError:
                        pass
        except FileNotFoundError:
            # GENERAL es opcional; si no está en storage, continuamos sin él.
            logger.warning(
                "_reload_parsed_from_storage: GENERAL no encontrado en storage "
                "(parse_id implícito). Continuando sin GENERAL."
            )
            parsed_general = None

    return parsed_results, parsed_general, results_ext, category_headers_raw, categories


#: Presupuesto del contrato (``identity-review-api.md`` §Rebuild): trabajo
#: real ≤ 10 s, este timeout deja margen bajo carga sin bloquear la petición
#: indefinidamente. Compartido por el gate de este router y por
#: ``POST /api/race-identity/rebuild`` (T049), que importa esta constante en
#: vez de repetir el número.
IDENTITY_REBUILD_TIMEOUT_S = 30.0


async def _identity_rebuild_needed(db: AsyncSession) -> bool:
    """¿Hace falta recalcular la cola antes de este commit?

    El rebuild reparsea TODOS los imports en staging: con las quince válidas
    históricas cargadas eso son minutos en Render y la conexión MySQL ociosa
    se cae a mitad (visto en producción, 2026-09-22). Solo es necesario si
    algún import en staging es más nuevo que el último candidato calculado
    — si nada se subió desde entonces, la cola ya está al día y basta con
    leer el contador de `pending`.
    """
    last_candidate = (
        await db.execute(select(func.max(RaceIdentityCandidate.created_at)))
    ).scalar()
    if last_candidate is None:
        return True
    newest_staged = (
        await db.execute(
            select(func.max(RaceImport.imported_at)).where(
                RaceImport.status.in_(
                    (RaceImportStatus.pending, RaceImportStatus.dry_run)
                )
            )
        )
    ).scalar()
    return newest_staged is not None and newest_staged > last_candidate


async def _identity_pending_count(db: AsyncSession) -> int:
    """Candidatos `pending` de la cola, sin recalcular."""
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(RaceIdentityCandidate)
                .where(RaceIdentityCandidate.state == IdentityCandidateState.pending)
            )
        ).scalar()
        or 0
    )


async def load_identity_rows(imp: RaceImport) -> dict[str, list[ResultsRow]]:
    """``RowsLoader`` de ``identity_review.rebuild`` (feature 044, T050/T049).

    Adapta ``_reload_parsed_from_storage`` — descarta ``GENERAL`` y los
    metadatos que el universo de identidad no usa, y conserva solo RESULTADOS
    con las correcciones ya reaplicadas. Vive en este router, no en el
    servicio, porque reutiliza su descarga SFTP + reparseo; el servicio de
    identidad no debe importar el router (contrato §Resolver, docstring de
    ``identity_review.load_universe``).
    """
    parsed_results, _general, _ext, _headers, cats = await _reload_parsed_from_storage(imp)
    if imp.status == RaceImportStatus.committed:
        # Import confirmado a medias: solo sus categorías pendientes siguen
        # en el universo de identidad; las ya ingestadas son resultados.
        pending = set((imp.parse_meta_json or {}).get("pending_categories") or [])
        pending_codes = {c.code for c in cats if c.header_raw in pending and c.code}
        return {code: rows for code, rows in parsed_results.items() if code in pending_codes}
    return parsed_results


def _build_event_meta_from_parse_meta(
    parse_meta: dict,
    filename: Optional[str],
) -> "EventMeta":
    """Construye un ``EventMeta`` desde el ``parse_meta_json`` persistido en ``RaceImport``.

    Centraliza la lógica de dry-run y commit para mantener un único punto de
    conversión del JSON almacenado → schema Pydantic.

    Las condiciones de carrera se leen desde ``parse_meta["conditions"]`` (clave
    introducida en B2). Si la clave no existe (imports previos al cambio), los
    campos quedan en ``None`` — compatibilidad total hacia atrás.
    """
    from datetime import date as _date
    from decimal import Decimal as _Decimal

    from app.models.race_event import SurfaceCondition as _SurfaceCondition

    header = parse_meta.get("header", {})
    conditions = parse_meta.get("conditions", {}) or {}

    event_date_str = header.get("event_date", "")
    event_date_obj = (
        _date.fromisoformat(event_date_str) if event_date_str else _date.today()
    )

    # Convertir temperatura de string (guardada como str para preservar Decimal)
    temp_raw = conditions.get("temperature_c")
    temperature_c: Optional[_Decimal] = (
        _Decimal(str(temp_raw)) if temp_raw is not None else None
    )

    # Convertir surface_condition de string a enum
    sc_raw = conditions.get("surface_condition")
    surface_condition: Optional[_SurfaceCondition] = None
    if sc_raw is not None:
        try:
            surface_condition = _SurfaceCondition(sc_raw)
        except ValueError:
            pass  # valor obsoleto o corrupto — ignorar silenciosamente

    return EventMeta(
        season=int(header.get("season", 2026)),
        copa_code="copa_valle",
        valida_num=int(header.get("valida_num", 1)),
        name=str(header.get("event_name", "Sin nombre")),
        event_date=event_date_obj,
        location=str(header.get("location", "Sin ubicación")),
        climate=conditions.get("climate"),
        temperature_c=temperature_c,
        surface_condition=surface_condition,
        altitude_msnm=conditions.get("altitude_msnm"),
        weather_notes=conditions.get("weather_notes"),
        pdf_results_filename=filename,
        pdf_general_filename=None,
    )


@router.post("/{parse_id}/dry-run", response_model=ImportDryRunResponse)
async def dry_run_import(
    parse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ImportDryRunResponse:
    """Endpoint 2 wizard (dry-run) — ejecuta ingest sin commit + retorna matches."""
    imp = await _load_pending_import(db, parse_id, current_user)
    parse_meta = imp.parse_meta_json or {}

    # Liberar conexión MySQL antes de SFTP download + pdfplumber parse.
    # expire_on_commit=False mantiene los atributos de `imp` accesibles tras commit.
    await db.commit()

    parsed_results, parsed_general, _, category_headers_raw, _categories = (
        await _reload_parsed_from_storage(imp)
    )

    # Construir EventMeta desde parse_meta (incluye condiciones de carrera si las hay)
    try:
        meta_obj = _build_event_meta_from_parse_meta(parse_meta, imp.filename)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"parse_meta inválido: {exc}",
        )

    # Snapshot attrs antes del ingest: el ingestor hace rollback/commit sobre la
    # misma session, lo que expira el ORM `imp` (MissingGreenlet en lazy-load).
    imp_id = imp.id
    imp_sha256 = imp.sha256
    imp_general_sha256 = imp.general_sha256
    imp_uploader_user_id = imp.imported_by_user_id
    imp_series_id = imp.series_id  # BUG-1 fix: honor series resolved at /parse

    # Ejecutar dry-run real
    ingestor = RaceIngestor(db)
    try:
        report = await ingestor.ingest_event(
            meta=meta_obj,
            results_by_category=parsed_results,
            general_by_category=parsed_general,
            pdf_results_sha256=imp_sha256,
            pdf_general_sha256=imp_general_sha256,
            ingested_by_user_id=current_user.id,
            dry_run=True,
            series_id=imp_series_id,
            category_headers_raw=category_headers_raw,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Construir matches preview desde RESULTADOS — basado en is_trocha_y_ruta
    from app.services.race.normalizer import is_trocha_y_ruta, normalize_name

    # Cargar atletas del/los club(s) del uploader (admin: cae al mismo set para
    # consistencia con lo que vería el coach). Vacío → matcher devuelve top-3
    # vacío → todas las filas quedan ambiguas sin sugerencia (comportamiento
    # legacy preservado cuando no hay roster cargado).
    club_ids_stmt = select(ClubMember.club_id).where(
        ClubMember.user_id == imp_uploader_user_id,
        ClubMember.role_in_club == ClubRole.coach,
    )
    coach_club_ids = list(
        (await db.execute(club_ids_stmt)).scalars().all()
    )
    athletes: list[Athlete] = []
    if coach_club_ids:
        athletes_stmt = select(Athlete).where(
            Athlete.club_id.in_(coach_club_ids),
            Athlete.deleted_at.is_(None),
        )
        athletes = list((await db.execute(athletes_stmt)).scalars().all())

    # Pre-cargar RaceCategory por code para el boost por edad del matcher.
    cat_codes = [c for c in parsed_results.keys() if c]
    cat_by_code: dict[str, RaceCategory] = {}
    if cat_codes:
        cat_stmt = select(RaceCategory).where(RaceCategory.code.in_(cat_codes))
        cat_by_code = {
            c.code: c for c in (await db.execute(cat_stmt)).scalars().all()
        }

    matches: list[MatchPreview] = []
    confirmed = 0
    ambiguous = 0
    for code, rows in parsed_results.items():
        category = cat_by_code.get(code)
        for row in rows:
            if not is_trocha_y_ruta(getattr(row, "club", None)):
                continue
            normalized = normalize_name(row.name) or ""

            candidates = match_athletes(
                competitor_name=row.name,
                competitor_club=getattr(row, "club", "") or "",
                competitor_category=category,
                athletes=athletes,
                threshold=70.0,
                reference_date=meta_obj.event_date,
            )

            tyr_ref: Optional[TyrAthleteRef] = None
            confidence = 0.0
            is_ambiguous = True
            if candidates:
                top = candidates[0]
                confidence = round(top.score / 100.0, 4)
                second_score = candidates[1].score if len(candidates) > 1 else 0.0
                # Auto-confirma cuando el top es alto y claramente único.
                if top.score >= 95.0 and (top.score - second_score) >= 5.0:
                    tyr_ref = TyrAthleteRef(id=top.athlete_id, full_name=top.full_name)
                    is_ambiguous = False
                else:
                    # Sugerencia presente pero coach debe confirmar (homónimos o score medio).
                    tyr_ref = TyrAthleteRef(id=top.athlete_id, full_name=top.full_name)

            if is_ambiguous:
                ambiguous += 1
            else:
                confirmed += 1

            matches.append(
                MatchPreview(
                    competitor_name=row.name,
                    competitor_normalized_name=normalized,
                    tyr_athlete=tyr_ref,
                    confidence=confidence,
                    is_ambiguous=is_ambiguous,
                )
            )

    counts = DryRunCounts(
        confirmed=confirmed,
        ambiguous=ambiguous,
        no_match=0,
        total=len(matches),
    )
    warnings = [
        ParseWarning(code="ingestor_warning", message=w)
        for w in report.warnings
    ]

    return ImportDryRunResponse(
        parse_id=imp_id,
        matches=matches,
        counts=counts,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Endpoint 3: POST /{parse_id}/commit
# ---------------------------------------------------------------------------


@router.post("/{parse_id}/commit", response_model=ImportCommitResponse)
async def commit_import(
    parse_id: int,
    body: ImportCommitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ctx: AuditContext = Depends(get_request_context),
) -> ImportCommitResponse:
    """Endpoint 3 wizard (commit) — promueve pending → committed con resolved matches."""
    imp = await _load_pending_import(db, parse_id, current_user, for_update=True)
    parse_meta = imp.parse_meta_json or {}

    # Liberar conexión MySQL antes de SFTP download + pdfplumber parse.
    # expire_on_commit=False mantiene los atributos de `imp` accesibles tras commit.
    await db.commit()

    parsed_results, parsed_general, _, category_headers_raw, categories = (
        await _reload_parsed_from_storage(imp)
    )

    # Feature 044 (US5, T060/T061): categorías elegibles para ESTE commit
    # (consistentes o reconocidas) vs. las que quedan `pending_categories`
    # (inconsistentes sin reconocer, o de encabezado no reconocido) —
    # contracts/historical-load.md §"Idempotence and resumption". Un commit
    # de temporada corriente con todo en orden tiene `pending_categories=[]`
    # y `eligible_codes` cubre todos los codes presentes — cero cambio de
    # comportamiento frente a antes de esta feature.
    eligible_codes, pending_categories = _eligible_and_pending_categories(
        categories, parse_meta
    )

    # Feature 044 (US4, T050) — candado de revisión de identidad. Mientras
    # exista al menos un candidato `pending`, el resolver del ingestor podría
    # fusionar homónimos en silencio (o partir a una misma persona) sin que
    # el coach haya decidido. `identity_review.rebuild` es idempotente
    # (nunca pisa una decisión tomada, `pair_hash` no cambia), así que
    # llamarlo aquí — incluso si el coach nunca pulsó "recalcular" en la
    # pantalla de revisión — es barato y cierra estructuralmente el hueco:
    # sin este rebuild, `pending` podría leer 0 solo porque nadie reconstruyó
    # la cola desde que se subió el import, y el commit avanzaría igual.
    try:
        if await _identity_rebuild_needed(db):
            identity_pending = (
                await identity_review.rebuild(
                    db,
                    rows_loader=load_identity_rows,
                    timeout_s=IDENTITY_REBUILD_TIMEOUT_S,
                )
            ).pending
        else:
            identity_pending = await _identity_pending_count(db)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "identity_rebuild_timeout",
                "message": (
                    "El recálculo de identidad tardó demasiado antes del "
                    "commit. Intenta de nuevo en unos minutos."
                ),
            },
        )
    await db.commit()
    if identity_pending > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "identity_review_pending",
                "pending": identity_pending,
                "message": (
                    "Hay candidatos de identidad sin decidir. Resuélvelos en "
                    "la revisión de identidad antes de confirmar la carga."
                ),
            },
        )

    # Construir EventMeta (incluye condiciones de carrera si fueron capturadas en /parse)
    try:
        meta_obj = _build_event_meta_from_parse_meta(parse_meta, imp.filename)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"parse_meta inválido: {exc}",
        )

    # Validar que resolved_matches cubra todos los matches ambiguos (TyR detectados)
    from app.services.race.normalizer import is_trocha_y_ruta, normalize_name

    # Feature 044 (US5): la validación de resolved_matches solo exige
    # decisión del coach para las categorías que SÍ se van a ingestar en este
    # commit — una categoría pendiente no le ha sido mostrada todavía en un
    # dry-run útil, y su turno de pedir resolved_matches es el futuro
    # `commit-pending`.
    tyr_normalized: set[str] = set()
    bib_by_normalized: dict[str, str] = {}
    for code, rows in parsed_results.items():
        if code not in eligible_codes:
            continue
        for row in rows:
            if is_trocha_y_ruta(getattr(row, "club", None)):
                norm = normalize_name(row.name) or ""
                if norm:
                    tyr_normalized.add(norm)
                    bib_by_normalized.setdefault(norm, str(row.bib))

    resolved_normalized = {rm.competitor_normalized_name for rm in body.resolved_matches}
    missing = tyr_normalized - resolved_normalized
    if missing:
        raise _matches_unresolved_error(missing)

    # Construir match_decisions {bib: athlete_id|None} para el ingestor
    match_decisions: dict[str, Optional[int]] = {}
    for rm in body.resolved_matches:
        bib = bib_by_normalized.get(rm.competitor_normalized_name)
        if bib is not None:
            match_decisions[bib] = rm.athlete_id

    # Re-adquirir el lock y re-verificar status justo antes de mutar:
    # el commit temprano (liberar conexión durante SFTP+parse) soltó el lock
    # de la carga inicial. Si otro commit ganó la carrera durante el parse,
    # esta re-verificación lanza 404 (ya no está pending).
    imp = await _load_pending_import(db, parse_id, current_user, for_update=True)

    # Snapshot attrs antes del ingest: el ingestor hace commit/rollback sobre la
    # misma session, lo que expira el ORM `imp` (MissingGreenlet en lazy-load).
    imp_sha256 = imp.sha256
    imp_general_sha256 = imp.general_sha256
    imp_series_id = imp.series_id  # BUG-1 fix: honor series resolved at /parse

    # Ejecutar commit (dry_run=False) — promueve pending → committed
    ingestor = RaceIngestor(db)
    try:
        report = await ingestor.ingest_event(
            meta=meta_obj,
            results_by_category=parsed_results,
            general_by_category=parsed_general,
            match_decisions=match_decisions,
            pdf_results_sha256=imp_sha256,
            pdf_general_sha256=imp_general_sha256,
            ingested_by_user_id=current_user.id,
            dry_run=False,
            series_id=imp_series_id,
            category_headers_raw=category_headers_raw,
            only_categories=eligible_codes,
        )
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "race_import_commit integrity_conflict parse_id=%s", parse_id
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Los resultados de este evento ya fueron registrados por otra "
                "operación. Refresca la página para ver el estado actual."
            ),
        )
    except ValueError as exc:
        # Categoría desconocida u otro error transactional
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Re-cargar imp tras commit interno del ingestor (atributos quedaron expirados)
    await db.refresh(imp)

    # Mover PDFs en SFTP: pending/{uuid}/ → committed/{uuid}/
    parse_uuid = parse_meta.get("parse_uuid", "unknown")
    new_path: Optional[str] = None
    new_url: Optional[str] = None
    if imp.storage_path:
        ext = parse_meta.get("results_ext", "pdf")
        dst_rel = f"race-imports/committed/{parse_uuid}/resultados.{ext}"
        try:
            new_path, new_url = await storage_sftp.move_object(
                imp.storage_path, dst_rel
            )
            imp.storage_path = new_path
            imp.storage_url = new_url
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "race_import_commit move_object failed parse_id=%s err=%s",
                parse_id,
                exc,
            )

    new_g_path: Optional[str] = None
    new_g_url: Optional[str] = None
    if imp.general_storage_path:
        dst_g_rel = f"race-imports/committed/{parse_uuid}/general.pdf"
        try:
            new_g_path, new_g_url = await storage_sftp.move_object(
                imp.general_storage_path, dst_g_rel
            )
            imp.general_storage_path = new_g_path
            imp.general_storage_url = new_g_url
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "race_import_commit move_object_general failed parse_id=%s err=%s",
                parse_id,
                exc,
            )

    # Limpiar parse_meta_json y enlazar event_id en RaceImport — feature 044
    # (US5): si quedaron categorías pendientes, el meta se PRESERVA (header,
    # corrections, acknowledged, caché de categorías) para que un futuro
    # `commit-pending` pueda re-parsear y decidir sin volver a pedirle nada
    # al coach; solo se anota `pending_categories` para que el listado y el
    # gate 404/409 de `commit-pending` lo lean en O(1). Un import totalmente
    # consistente (el caso común, sin cambio de comportamiento) sigue
    # limpiando el meta como antes.
    imp.event_id = report.event_id
    if pending_categories:
        new_meta = dict(parse_meta)
        new_meta["pending_categories"] = pending_categories
        imp.parse_meta_json = new_meta
    else:
        imp.parse_meta_json = None
    # PR4: persistir el motivo de revisión (catálogo cerrado) si se envió.
    # Pydantic ya validó que sea un RevisionReasonCode válido. Guardamos el
    # code (string) — nunca texto libre.
    is_revision = body.revision_reason is not None
    if is_revision:
        imp.revision_reason = body.revision_reason.value
    await db.flush()

    # El ingestor ya hizo su propio commit interno (comentario arriba: "el
    # ingestor hace commit/rollback sobre la misma session"), así que esta
    # fila de auditoría viaja en la transacción siguiente que abre `get_db`
    # al hacer flush/commit al final del request — no en la transacción de
    # negocio original, que ya cerró.
    await record_audit(
        db,
        action=AuditAction.execute,
        entity_type=AuditEntityType.race_import,
        entity_id=imp.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        changed_fields=["status"],
        diff={"status": (RaceImportStatus.pending.value, RaceImportStatus.committed.value)},
        meta={
            "race_event_id": int(report.event_id) if report.event_id is not None else None,
            "is_revision": is_revision,
            "results_count": report.results_inserted,
            "competitors_count": report.competitors_created,
        },
        request_id=ctx.request_id,
    )

    # PR5 (D5): si fue una re-ingesta (revisión), marcamos como stale los
    # análisis IA basados en los resultados ahora corregidos + boletines
    # enviados como outdated (D3). NO se re-ejecuta nada automáticamente —
    # el coach decide el re-trigger manualmente.
    if is_revision and report.event_id is not None:
        try:
            await invalidate_runs_for_event(db, int(report.event_id))
            await db.flush()
        except Exception as exc:  # noqa: BLE001
            # No bloquea el commit: la invalidación es best-effort.
            logger.warning(
                "race_import_commit invalidate_runs failed parse_id=%s err=%s",
                parse_id,
                exc,
            )

    logger.info(
        "race_import_commit parse_id=%s event_id=%s results_inserted=%d "
        "competitors_created=%d tyr_count=%d",
        parse_id,
        report.event_id,
        report.results_inserted,
        report.competitors_created,
        report.tyr_count,
    )

    return ImportCommitResponse(
        parse_id=parse_id,
        race_event_id=report.event_id,
        n_results_inserted=report.results_inserted,
        n_competitors_created=report.competitors_created,
        n_competitors_linked=report.tyr_count,
        pending_categories=pending_categories,
    )


# ---------------------------------------------------------------------------
# Endpoint 3b: POST /{parse_id}/commit-pending (feature 044, US5, T061)
# ---------------------------------------------------------------------------


@router.post("/{parse_id}/commit-pending", response_model=ImportCommitResponse)
async def commit_pending_import(
    parse_id: int,
    body: ImportCommitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ctx: AuditContext = Depends(get_request_context),
) -> ImportCommitResponse:
    """Termina de ingestar un import ``committed`` cuyas categorías
    pendientes se corrigieron o reconocieron después del primer ``/commit``
    (contracts/historical-load.md §"Idempotence and resumption", FR-027).

    Mismo candado de identidad que ``/commit`` (FR-018): recalcula la cola
    antes de decidir, ``409 identity_review_pending`` si algo sigue sin
    decidir. ``409 nothing_pending`` si no queda ninguna categoría pendiente
    (ni en el caché de meta, ni tras re-verificar contra el acta corregida).
    """
    imp = await _load_committed_import_with_pending(
        db, parse_id, current_user, for_update=True
    )
    parse_meta = imp.parse_meta_json or {}

    # Liberar conexión MySQL antes de SFTP download + pdfplumber parse.
    await db.commit()

    parsed_results, parsed_general, _, category_headers_raw, categories = (
        await _reload_parsed_from_storage(imp)
    )

    # Mismo candado de identidad que /commit — reutiliza el patrón
    # rebuild-then-check (FR-018).
    try:
        if await _identity_rebuild_needed(db):
            identity_pending = (
                await identity_review.rebuild(
                    db,
                    rows_loader=load_identity_rows,
                    timeout_s=IDENTITY_REBUILD_TIMEOUT_S,
                )
            ).pending
        else:
            identity_pending = await _identity_pending_count(db)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "identity_rebuild_timeout",
                "message": (
                    "El recálculo de identidad tardó demasiado antes del "
                    "commit-pending. Intenta de nuevo en unos minutos."
                ),
            },
        )
    await db.commit()
    if identity_pending > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "identity_review_pending",
                "pending": identity_pending,
                "message": (
                    "Hay candidatos de identidad sin decidir. Resuélvelos en "
                    "la revisión de identidad antes de confirmar la carga."
                ),
            },
        )

    try:
        meta_obj = _build_event_meta_from_parse_meta(parse_meta, imp.filename)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"parse_meta inválido: {exc}",
        )

    eligible_codes, pending_categories = _eligible_and_pending_categories(
        categories,
        parse_meta,
        restrict_to_headers=set(parse_meta.get("pending_categories") or []),
    )
    if not eligible_codes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "nothing_pending",
                "message": (
                    "Ninguna categoría pendiente pasó a ser consistente o "
                    "reconocida todavía."
                ),
            },
        )

    from app.services.race.normalizer import is_trocha_y_ruta, normalize_name

    tyr_normalized: set[str] = set()
    bib_by_normalized: dict[str, str] = {}
    for code, rows in parsed_results.items():
        if code not in eligible_codes:
            continue
        for row in rows:
            if is_trocha_y_ruta(getattr(row, "club", None)):
                norm = normalize_name(row.name) or ""
                if norm:
                    tyr_normalized.add(norm)
                    bib_by_normalized.setdefault(norm, str(row.bib))

    resolved_normalized = {rm.competitor_normalized_name for rm in body.resolved_matches}
    missing = tyr_normalized - resolved_normalized
    if missing:
        raise _matches_unresolved_error(missing)

    match_decisions: dict[str, Optional[int]] = {}
    for rm in body.resolved_matches:
        bib = bib_by_normalized.get(rm.competitor_normalized_name)
        if bib is not None:
            match_decisions[bib] = rm.athlete_id

    # Re-adquirir el lock justo antes de mutar (mismo patrón que /commit).
    imp = await _load_committed_import_with_pending(
        db, parse_id, current_user, for_update=True
    )
    imp_sha256 = imp.sha256
    imp_general_sha256 = imp.general_sha256
    imp_series_id = imp.series_id

    ingestor = RaceIngestor(db)
    try:
        report = await ingestor.ingest_event(
            meta=meta_obj,
            results_by_category=parsed_results,
            general_by_category=parsed_general,
            match_decisions=match_decisions,
            pdf_results_sha256=imp_sha256,
            pdf_general_sha256=imp_general_sha256,
            ingested_by_user_id=current_user.id,
            dry_run=False,
            series_id=imp_series_id,
            category_headers_raw=category_headers_raw,
            only_categories=eligible_codes,
        )
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "race_import_commit_pending integrity_conflict parse_id=%s", parse_id
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Los resultados de este evento ya fueron registrados por otra "
                "operación. Refresca la página para ver el estado actual."
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    await db.refresh(imp)
    if pending_categories:
        new_meta = dict(parse_meta)
        new_meta["pending_categories"] = pending_categories
        imp.parse_meta_json = new_meta
    else:
        imp.parse_meta_json = None
    await db.flush()

    await record_audit(
        db,
        action=AuditAction.execute,
        entity_type=AuditEntityType.race_import,
        entity_id=imp.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        changed_fields=["parse_meta_json"],
        meta={
            "race_event_id": int(report.event_id) if report.event_id is not None else None,
            "commit_pending": True,
            "results_count": report.results_inserted,
            "competitors_count": report.competitors_created,
            "pending_categories_remaining": len(pending_categories),
        },
        request_id=ctx.request_id,
    )

    logger.info(
        "race_import_commit_pending parse_id=%s event_id=%s results_inserted=%d "
        "competitors_created=%d tyr_count=%d pending_remaining=%d",
        parse_id,
        report.event_id,
        report.results_inserted,
        report.competitors_created,
        report.tyr_count,
        len(pending_categories),
    )

    return ImportCommitResponse(
        parse_id=parse_id,
        race_event_id=report.event_id,
        n_results_inserted=report.results_inserted,
        n_competitors_created=report.competitors_created,
        n_competitors_linked=report.tyr_count,
        pending_categories=pending_categories,
    )


# ---------------------------------------------------------------------------
# Endpoints US1: correcciones manuales + reconocimiento de completitud
# (feature 044, research R-05, contracts/reading-integrity.md §"API deltas")
# ---------------------------------------------------------------------------


@router.post(
    "/{parse_id}/corrections",
    response_model=CategoryCompletenessResponse,
    summary="Corrige una fila de una categoría parseada",
    description=(
        "Agrega/edita/elimina una fila de una categoría (add|edit|remove) "
        "sobre el acta parseada de un cargue pending. El parche se persiste "
        "en `parse_meta_json.corrections` y se reaplica en cada dry-run/"
        "commit posterior (el archivo se re-parsea desde storage cada vez). "
        "422 si la categoría no existe o la fila es inválida. RBAC coach/admin."
    ),
)
async def add_correction(
    parse_id: int,
    body: RowCorrectionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ctx: AuditContext = Depends(get_request_context),
) -> CategoryCompletenessResponse:
    """``POST /{parse_id}/corrections`` (research R-05).

    Privacidad: ``body.row`` trae nombre/ciudad/club de un menor — nunca se
    loggea ni entra al ``meta_json`` de auditoría (solo se guarda en
    ``parse_meta_json.corrections``, misma clase de sensibilidad que
    ``race_competitors`` per data-model.md §7).
    """
    imp = await _load_correctable_import(db, parse_id, current_user)
    meta = dict(imp.parse_meta_json or {})

    existing_corrections = list(meta.get("corrections") or [])
    new_correction = {
        "op": body.op,
        "category_header": body.category_header,
        "ordinal": body.ordinal,
        "row": body.row.model_dump() if body.row is not None else None,
    }

    fresh = await _reload_results_document(imp)
    try:
        corrected = apply_corrections(fresh, [*existing_corrections, new_correction])
    except CorrectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    category = next(
        c for c in corrected.categories if c.header_raw == body.category_header
    )
    report = check_category(category)

    meta["corrections"] = [
        *existing_corrections,
        {
            **new_correction,
            "by": current_user.id,
            "at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    meta["categories"] = _update_category_cache(
        meta.get("categories") or [],
        body.category_header,
        rows=len(category.rows),
        completeness=report,
    )
    imp.parse_meta_json = meta

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.race_import,
        entity_id=imp.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        changed_fields=["parse_meta_json"],
        request_id=ctx.request_id,
    )
    await db.flush()

    return CategoryCompletenessResponse(
        category_header=body.category_header,
        completeness=CompletenessRead(
            status=report.status,
            missing=report.missing,
            duplicated=report.duplicated,
        ),
    )


@router.post(
    "/{parse_id}/acknowledge",
    response_model=CategoryCompletenessResponse,
    summary="Reconoce una categoría con completitud inconsistente",
    description=(
        "Da por buena una categoría con un motivo del catálogo cerrado "
        "(`AcknowledgeReasonCode`) — sin texto libre (privacidad menores). "
        "`completeness.status` pasa a `acknowledged`. RBAC coach/admin, "
        "auditado (`record_audit`)."
    ),
)
async def acknowledge_category(
    parse_id: int,
    body: AcknowledgeIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ctx: AuditContext = Depends(get_request_context),
) -> CategoryCompletenessResponse:
    """``POST /{parse_id}/acknowledge`` (research R-05).

    El gate de commit que consume este reconocimiento (bloquear solo la
    categoría, no todo el cargue) es de T060/T061 — esta tarea (T019) solo
    persiste la decisión y la audita.
    """
    imp = await _load_correctable_import(db, parse_id, current_user)
    meta = dict(imp.parse_meta_json or {})

    corrections = meta.get("corrections") or []
    fresh = await _reload_results_document(imp)
    corrected = apply_corrections(fresh, corrections) if corrections else fresh
    category = next(
        (c for c in corrected.categories if c.header_raw == body.category_header),
        None,
    )
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown_category",
        )

    report = check_category(category)
    acknowledged_report = CompletenessReport(
        status="acknowledged", missing=report.missing, duplicated=report.duplicated
    )

    existing_acks = [
        a
        for a in (meta.get("acknowledged") or [])
        if a.get("category_header") != body.category_header
    ]
    meta["acknowledged"] = [
        *existing_acks,
        {
            "category_header": body.category_header,
            "reason": body.reason.value,
            "by": current_user.id,
            "at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    meta["categories"] = _update_category_cache(
        meta.get("categories") or [],
        body.category_header,
        rows=len(category.rows),
        completeness=acknowledged_report,
    )
    imp.parse_meta_json = meta

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.race_import,
        entity_id=imp.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        changed_fields=["parse_meta_json"],
        request_id=ctx.request_id,
    )
    await db.flush()

    return CategoryCompletenessResponse(
        category_header=body.category_header,
        completeness=CompletenessRead(
            status=acknowledged_report.status,
            missing=acknowledged_report.missing,
            duplicated=acknowledged_report.duplicated,
        ),
    )


@router.get(
    "/acknowledge-reasons",
    response_model=AcknowledgeReasonsResponse,
    summary="Catálogo cerrado de motivos de reconocimiento de completitud",
    description=(
        "Devuelve los motivos permitidos para reconocer una categoría con "
        "completitud inconsistente (research R-05). El frontend usa este "
        "catálogo para poblar el dropdown — sin texto libre (privacidad "
        "menores). RBAC coach/admin."
    ),
)
async def list_acknowledge_reasons(
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AcknowledgeReasonsResponse:
    """``GET /api/race-analysis/imports/acknowledge-reasons`` (coach/admin)."""
    return AcknowledgeReasonsResponse(
        options=[
            AcknowledgeReasonOption(code=code.value, label=ACKNOWLEDGE_REASON_LABELS[code])
            for code in AcknowledgeReasonCode
        ]
    )


# ---------------------------------------------------------------------------
# Endpoint 4: GET / — histórico
# ---------------------------------------------------------------------------


@router.get("/", response_model=ImportListResponse)
async def list_imports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ImportListResponse:
    """Endpoint 4 wizard (histórico) — lista paginada de imports.

    Alcance por club (H4, contracts/scope-ai-imports.md §1/§6): el admin ve
    todo; un coach solo ve los cargues cuyo club (resuelto vía
    ``import_club_ids`` — membresía del uploader) coincide con alguno de los
    suyos, más — respaldo de autoría, igual que ``_has_club_access`` — sus
    propios cargues cuando el club no resuelve. Filtrado en SQL para que
    ``limit``/``offset`` y ``total`` sigan siendo correctos.
    """
    stmt = select(RaceImport)
    count_stmt = select(RaceImport)
    if status_filter:
        try:
            status_enum = RaceImportStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"status inválido: {status_filter}",
            )
        stmt = stmt.where(RaceImport.status == status_enum)
        count_stmt = count_stmt.where(RaceImport.status == status_enum)

    if current_user.role != UserRole.admin:
        # Usuarios coach-o-admin de los clubes del solicitante: cualquier
        # cargue subido por alguno de ellos resuelve al club del solicitante
        # (misma regla que ``import_club_ids``/``_has_club_access``).
        requester_club_ids = coach_club_ids(current_user)
        same_club_user_ids: set[int] = set()
        if requester_club_ids:
            members_result = await db.execute(
                select(ClubMember.user_id).where(
                    ClubMember.club_id.in_(requester_club_ids),
                    ClubMember.role_in_club.in_([ClubRole.coach, ClubRole.admin]),
                )
            )
            same_club_user_ids = {int(uid) for uid in members_result.scalars().all()}

        # Respaldo por autoría: un cargue cuyo club no resuelve solo queda
        # alcanzable por quien lo subió (nunca ensancha el acceso).
        scope_filter = RaceImport.imported_by_user_id == current_user.id
        if same_club_user_ids:
            scope_filter = or_(
                RaceImport.imported_by_user_id.in_(same_club_user_ids),
                scope_filter,
            )
        stmt = stmt.where(scope_filter)
        count_stmt = count_stmt.where(scope_filter)

    # Total para paginación
    total_result = await db.execute(count_stmt)
    total = len(list(total_result.scalars().all()))

    # Página solicitada
    page_result = await db.execute(
        stmt.order_by(RaceImport.imported_at.desc())
        .offset(offset)
        .limit(limit)
    )
    imports = list(page_result.scalars().all())

    # Cargar uploaders de manera batched
    user_ids = list({i.imported_by_user_id for i in imports})
    users_by_id: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    # Feature 044 (US5): season/valida_num/series_name para agrupar el
    # tablero histórico por temporada (contracts/historical-load.md). Un
    # import con meta viva (pending, o committed con `pending_categories`)
    # los trae en `parse_meta_json["header"]`; uno ya committed sin nada
    # pendiente (meta en `None`) los resuelve vía `RaceEvent` → `RaceSeries`
    # — batched, un solo query para toda la página.
    event_ids_needing_lookup = {
        i.event_id for i in imports
        if i.parse_meta_json is None and i.event_id is not None
    }
    event_header_by_id: dict[int, tuple[int, int, str]] = {}
    if event_ids_needing_lookup:
        rows = await db.execute(
            select(
                RaceEvent.id,
                RaceEvent.sequence_number,
                RaceSeries.season_year,
                RaceSeries.name,
            )
            .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
            .where(RaceEvent.id.in_(event_ids_needing_lookup))
        )
        for event_id, seq, season_year, series_name in rows.all():
            event_header_by_id[event_id] = (season_year, seq, series_name)

    items: list[ImportListItem] = []
    for imp in imports:
        u = users_by_id.get(imp.imported_by_user_id)
        # FR-013 / contracts/scope-ai-imports.md §4.1: nunca un identificador
        # crudo (`user#{id}`) llega al lector — el join sin resolver (FK
        # borrada o editada a mano, o nombre vacío) cae en el mismo texto
        # humano que usan run_status/audit ("Usuario no disponible").
        joined_name = f"{u.first_name} {u.last_name}".strip() if u else ""
        uploader = UploadUserRef(
            id=imp.imported_by_user_id,
            full_name=joined_name or "Usuario no disponible",
        )
        n_results = (imp.stats_json or {}).get("results_inserted", 0)
        pending_categories_count = len(
            (imp.parse_meta_json or {}).get("pending_categories") or []
        )

        season: Optional[int] = None
        valida_num: Optional[int] = None
        series_name: Optional[str] = None
        header = (imp.parse_meta_json or {}).get("header")
        if header:
            season = header.get("season")
            valida_num = header.get("valida_num")
            series_name = header.get("series_name")
        elif imp.event_id is not None and imp.event_id in event_header_by_id:
            season, valida_num, series_name = event_header_by_id[imp.event_id]

        items.append(
            ImportListItem(
                id=imp.id,
                kind=imp.kind.value,
                status=imp.status.value,
                created_at=imp.imported_at,
                event_id=imp.event_id,
                original_filename=imp.original_filename or imp.filename,
                uploaded_by=uploader,
                n_results=n_results,
                pending_categories_count=pending_categories_count,
                season=season,
                valida_num=valida_num,
                series_name=series_name,
            )
        )

    return ImportListResponse(items=items, total=total)


@router.get(
    "/revision-reasons",
    response_model=RevisionReasonsResponse,
    summary="Catálogo cerrado de motivos de revisión",
    description=(
        "Devuelve los motivos permitidos para una re-ingesta (revisión). "
        "El frontend usa este catálogo para poblar el dropdown — sin texto "
        "libre (privacidad menores). RBAC coach/admin."
    ),
)
async def list_revision_reasons(
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RevisionReasonsResponse:
    """``GET /api/race-analysis/imports/revision-reasons`` (coach/admin)."""
    return RevisionReasonsResponse(
        options=[
            RevisionReasonOption(code=code.value, label=REVISION_REASON_LABELS[code])
            for code in RevisionReasonCode
        ]
    )


@router.get(
    "/{race_event_id}/diff",
    response_model=RaceEventDiffResponse,
    summary="Diff de la última revisión de una válida (read-only)",
    description=(
        "Devuelve los cambios aplicados en la última re-ingesta (revisión) de "
        "la válida, agrupados por: posición, tiempo, gap GC, recategorización y "
        "nuevos/eliminados. Read-only: NO recomputa contra un PDF. "
        "RBAC coach/admin. Si la válida no tiene revisiones → has_revision=false."
    ),
)
async def get_event_revision_diff(
    race_event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RaceEventDiffResponse:
    """``GET /api/race-analysis/imports/{race_event_id}/diff`` (coach/admin)."""
    return await build_event_diff_view(db, race_event_id)
