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
import tempfile
import uuid
from asyncio import wait_for
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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.club import ClubMember, ClubRole
from app.models.race_category import RaceCategory
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.schemas.race import EventMeta
from app.schemas.race_imports import (
    DryRunCounts,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportDryRunResponse,
    ImportListItem,
    ImportListResponse,
    ImportParseRequestFields,
    ImportParseResponse,
    MatchPreview,
    ParseHeaderInfo,
    ParseWarning,
    RaceEventDiffResponse,
    REVISION_REASON_LABELS,
    RevisionReasonCode,
    RevisionReasonOption,
    RevisionReasonsResponse,
    TyrAthleteRef,
    UploadUserRef,
)
from app.services.race.ingestor import RaceIngestor
from app.services.race.matcher import match_athletes
from app.services.race.revision import detect_revision
from app.services.race.revision_diff_view import build_event_diff_view
from app.services.race.run_staleness import invalidate_runs_for_event
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
# ---------------------------------------------------------------------------


async def _get_or_create_series(
    db: AsyncSession,
    series_name: str,
    season: int,
    kind: RaceSeriesKind,
    level: RaceSeriesLevel | str = RaceSeriesLevel.departmental,
) -> RaceSeries:
    """Resuelve o crea una serie por (name, season_year), honrando el kind del cliente.

    Bug fix (spec 014 / T017): la versión anterior ignoraba ``series_name`` y
    siempre usaba el hardcoded ``_SERIES_NAME`` ("Copa Valle de Ciclomontañismo").
    Esta versión usa el nombre real enviado por el cliente.

    Spec 023 (D5 / R5): el default de organizer ``"Liga Vallecaucana de
    Ciclismo"`` solo se aplica a series NUEVAS de tipo ``kind == cup``. Los
    campeonatos nuevos (departamentales o nacionales) quedan con
    ``organizer=None`` — el organizador real lo aporta el flujo de import
    ligado a la competencia (feature 015).

    Args:
        db: Sesión async.
        series_name: Nombre de la serie (enviado por el cliente en el Form).
        season: Año de temporada.
        kind: Tipo de serie (cup | championship).
        level: Ámbito territorial (departmental | national). Solo relevante
            para campeonatos nuevos; se acepta ``str`` para validar el valor
            crudo del Form field ``series_level`` (lanza ``ValueError`` si es
            inválido).

    Raises:
        ValueError: si ``level`` es una cadena que no corresponde a ningún
            valor de ``RaceSeriesLevel``.
    """
    resolved_level = (
        level if isinstance(level, RaceSeriesLevel) else RaceSeriesLevel(level)
    )
    result = await db.execute(
        select(RaceSeries).where(
            RaceSeries.name == series_name,
            RaceSeries.season_year == season,
        )
    )
    series = result.scalar_one_or_none()
    if series is not None:
        return series
    series = RaceSeries(
        name=series_name,
        season_year=season,
        organizer=(
            "Liga Vallecaucana de Ciclismo" if kind == RaceSeriesKind.cup else None
        ),
        points_scheme_code="copa_valle_2026",
        kind=kind,
        level=resolved_level,
    )
    db.add(series)
    await db.flush()
    return series


async def _parse_results_with_timeout(
    path: PathLib, ext: str
) -> dict[str, list]:
    """Parsea con asyncio.wait_for + asyncio.to_thread; mapea TimeoutError a 422."""
    import asyncio

    from app.services.race.csv_parser import parse_results_csv
    from app.services.race.pdf_parser import parse_results_pdf

    parser = parse_results_pdf if ext == "pdf" else parse_results_csv
    try:
        return await wait_for(
            asyncio.to_thread(parser, path),
            timeout=settings.race_parse_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"PDF demasiado complejo (parse > "
                f"{settings.race_parse_timeout_seconds}s). Verifique formato oficial."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("race_import_parse RESULTADOS failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo procesar el PDF RESULTADOS. Verifique que sea el formato oficial de la Federación.",
        )


async def _parse_general_with_timeout(path: PathLib) -> dict[str, list]:
    import asyncio

    from app.services.race.pdf_parser import parse_general_pdf

    try:
        return await wait_for(
            asyncio.to_thread(parse_general_pdf, path),
            timeout=settings.race_parse_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="GENERAL demasiado complejo (parse > timeout).",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("race_import_parse GENERAL failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo procesar el PDF GENERAL. Verifique que sea el formato oficial de la Federación.",
        )


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
    # 1. Leer + validar magic bytes RESULTADOS
    resultados_bytes = await _read_with_cap(resultados_pdf, settings.race_max_pdf_mb)
    results_ext = _validate_results_magic(
        resultados_bytes, resultados_pdf.filename or "upload.pdf"
    )
    results_sha = _compute_sha256(resultados_bytes)

    # 2. (Opcional) GENERAL — solo PDF
    general_bytes: Optional[bytes] = None
    general_sha: Optional[str] = None
    if general_pdf is not None and (general_pdf.filename or ""):
        general_bytes = await _read_with_cap(general_pdf, settings.race_max_pdf_mb)
        _validate_general_magic(general_bytes, general_pdf.filename or "general.pdf")
        general_sha = _compute_sha256(general_bytes)
        if general_sha == results_sha:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RESULTADOS y GENERAL no pueden ser el mismo archivo.",
            )

    # 3. Detectar duplicado SHA committed (409)
    duplicate = await db.execute(
        select(RaceImport).where(
            RaceImport.sha256 == results_sha,
            RaceImport.status == RaceImportStatus.committed,
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"PDF RESULTADOS con sha256={results_sha[:8]}... ya fue commiteado. "
                "Use force_reingest=True (admin only) si necesita re-procesar."
            ),
        )

    # Liberar conexión MySQL antes de SFTP upload + pdfplumber parse (pueden
    # tardar minutos). Hostinger cierra sockets ociosos por wait_timeout y
    # NullPool no detecta la conexión muerta dentro de una transacción abierta.
    # SQLAlchemy autobegin abrirá una conexión fresca en el próximo execute.
    await db.commit()

    # 4. Determinar kind (override del cliente sobre auto-detection)
    if kind is None:
        kind_value = (
            RaceImportKind.both if general_bytes else RaceImportKind.resultados
        )
    else:
        try:
            kind_value = RaceImportKind(kind)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"kind inválido: {kind}. Permitidos: resultados, general, both.",
            )

    # 5. Subir PDFs a storage pending/{uuid}/...
    parse_uuid = uuid.uuid4().hex
    safe_results_name = _sanitize_filename(resultados_pdf.filename)
    results_rel = (
        f"race-imports/pending/{parse_uuid}/resultados.{results_ext}"
    )
    results_storage_path, results_storage_url = await storage_sftp.upload_bytes(
        resultados_bytes, results_rel
    )
    general_storage_path: Optional[str] = None
    general_storage_url: Optional[str] = None
    if general_bytes:
        _sanitize_filename(general_pdf.filename)  # type: ignore[union-attr]  # sanitized name preserved for future use
        general_rel = f"race-imports/pending/{parse_uuid}/general.pdf"
        general_storage_path, general_storage_url = await storage_sftp.upload_bytes(
            general_bytes, general_rel
        )

    # 6. Parsear con timeout — escribimos a tmp para Path-only API
    warnings_collected: list[ParseWarning] = []
    with tempfile.NamedTemporaryFile(
        suffix=f".{results_ext}", delete=False
    ) as tmp_results:
        tmp_results.write(resultados_bytes)
        tmp_results.flush()
        results_path = PathLib(tmp_results.name)
    try:
        parsed_results = await _parse_results_with_timeout(results_path, results_ext)
    finally:
        try:
            results_path.unlink(missing_ok=True)
        except OSError:
            pass

    n_rows_resultados = sum(len(v) for v in parsed_results.values())
    if n_rows_resultados == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parser no extrajo ninguna fila válida. PDF/CSV no oficial?",
        )

    n_rows_general: Optional[int] = None
    if general_bytes:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_g:
            tmp_g.write(general_bytes)
            tmp_g.flush()
            general_path = PathLib(tmp_g.name)
        try:
            parsed_general = await _parse_general_with_timeout(general_path)
            n_rows_general = sum(len(v) for v in parsed_general.values())
        finally:
            try:
                general_path.unlink(missing_ok=True)
            except OSError:
                pass

    # 7. Crear RaceImport status=pending con parse_meta_json
    series = await _get_or_create_series(
        db, series_name, season, resolved_series_kind, resolved_series_level
    )
    parse_meta = {
        "header": {
            "series_name": series_name,
            "season": season,
            "valida_num": valida_num,
            "event_name": event_name,
            "event_date": event_date,
            "location": location,
        },
        # Condiciones de carrera — None si el coach no las capturó aún;
        # el commit las propagará a EventMeta → RaceIngestor → race_events.
        "conditions": {
            "climate": conditions_fields.climate,
            "temperature_c": (
                str(conditions_fields.temperature_c)
                if conditions_fields.temperature_c is not None
                else None
            ),
            "surface_condition": (
                conditions_fields.surface_condition.value
                if conditions_fields.surface_condition is not None
                else None
            ),
            "altitude_msnm": conditions_fields.altitude_msnm,
            "weather_notes": conditions_fields.weather_notes,
        },
        "results_ext": results_ext,
        "results_storage_path": results_storage_path,
        "general_storage_path": general_storage_path,
        "categories_found": sorted(parsed_results.keys()),
        "n_rows_resultados": n_rows_resultados,
        "n_rows_general": n_rows_general,
        "parse_uuid": parse_uuid,
    }
    race_import = RaceImport(
        filename=safe_results_name,
        original_filename=resultados_pdf.filename,
        sha256=results_sha,
        series_id=series.id,
        status=RaceImportStatus.pending,
        stats_json={},
        imported_by_user_id=current_user.id,
        kind=kind_value,
        storage_path=results_storage_path,
        storage_url=results_storage_url,
        general_storage_path=general_storage_path,
        general_storage_url=general_storage_url,
        general_sha256=general_sha,
        parse_meta_json=parse_meta,
    )
    db.add(race_import)
    await db.flush()

    # F-UP-REV2: detección de revisión post-parse
    # Si existe `(series, valida_num)` con committed previo y SHA distinto,
    # marcamos `will_be_revision=true`. SHA byte-exacto ya fue bloqueado arriba
    # con 409, no llegamos aquí.
    # BUG-1 fix: usamos series.id (ya resuelto arriba) para que detect_revision
    # opere sobre la misma serie que el ingestor usará en dry-run/commit.
    # Esto evita la divergencia cuando series_name del cliente no coincide
    # exactamente con el name persisted (ej. "Copa Valle" vs "Copa Valle...").
    revision_ctx = await detect_revision(
        db,
        series_name=series_name,
        season=season,
        valida_num=valida_num,
        series_id=series.id,
    )
    will_be_revision = revision_ctx is not None

    logger.info(
        "race_import_parse parse_id=%s sha=%s user_id=%s kind=%s rows=%d "
        "will_be_revision=%s",
        race_import.id,
        results_sha[:12],
        current_user.id,
        kind_value.value,
        n_rows_resultados,
        will_be_revision,
    )

    return ImportParseResponse(
        parse_id=race_import.id,
        sha256=results_sha,
        header=ParseHeaderInfo(
            series_name=series_name,
            season=season,
            valida_num=valida_num,
            event_name=event_name,
        ),
        n_rows_resultados=n_rows_resultados,
        n_rows_general=n_rows_general,
        warnings=warnings_collected,
        will_be_revision=will_be_revision,
        parent_event_id=revision_ctx.parent_event_id if revision_ctx else None,
        parent_import_id=revision_ctx.parent_import_id if revision_ctx else None,
        parent_committed_at=(
            revision_ctx.parent_committed_at if revision_ctx else None
        ),
        parent_n_results=(
            revision_ctx.n_results_persisted if revision_ctx else None
        ),
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
    """Carga un RaceImport pending por id + verifica ownership (admin bypass)."""
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
    # Ownership: admin bypass; coach solo sobre sus propios parses.
    if (
        current_user.role != UserRole.admin
        and imp.imported_by_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este parse_id (ownership cross-coach).",
        )
    return imp


async def _reload_parsed_from_storage(
    imp: RaceImport,
) -> tuple[dict[str, list], Optional[dict[str, list]], str]:
    """Re-carga RESULTADOS (+ GENERAL opcional) desde el storage path persistido
    durante /parse. Retorna ``(results, general, results_ext)``.

    Necesario para dry-run/commit: el bytes original ya está en SFTP/local; lo
    descargamos a tmp, parseamos, descartamos.

    En producción (SFTP configurado) el ``storage_path`` es un path remoto
    Hostinger que no existe en el disco del contenedor. Se descarga vía FTPS
    a un archivo temporal, se parsea y se borra en el finally.
    """
    meta = imp.parse_meta_json or {}
    results_ext = meta.get("results_ext", "pdf")

    # --- RESULTADOS (obligatorio) ---
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
        parsed_results = await _parse_results_with_timeout(results_tmp_path, results_ext)
    finally:
        if results_is_tmp:
            try:
                os.unlink(results_tmp_path)
            except OSError:
                pass

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

    return parsed_results, parsed_general, results_ext


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

    parsed_results, parsed_general, _ = await _reload_parsed_from_storage(imp)

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
        athletes_stmt = select(Athlete).where(Athlete.club_id.in_(coach_club_ids))
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
) -> ImportCommitResponse:
    """Endpoint 3 wizard (commit) — promueve pending → committed con resolved matches."""
    imp = await _load_pending_import(db, parse_id, current_user, for_update=True)
    parse_meta = imp.parse_meta_json or {}

    # Liberar conexión MySQL antes de SFTP download + pdfplumber parse.
    # expire_on_commit=False mantiene los atributos de `imp` accesibles tras commit.
    await db.commit()

    parsed_results, parsed_general, _ = await _reload_parsed_from_storage(imp)

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

    tyr_normalized: set[str] = set()
    bib_by_normalized: dict[str, str] = {}
    for code, rows in parsed_results.items():
        for row in rows:
            if is_trocha_y_ruta(getattr(row, "club", None)):
                norm = normalize_name(row.name) or ""
                if norm:
                    tyr_normalized.add(norm)
                    bib_by_normalized.setdefault(norm, str(row.bib))

    resolved_normalized = {rm.competitor_normalized_name for rm in body.resolved_matches}
    missing = tyr_normalized - resolved_normalized
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Faltan resolved_matches para {len(missing)} atleta(s) TyR. "
                f"Ejemplos: {sorted(missing)[:3]}"
            ),
        )

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

    # Limpiar parse_meta_json y enlazar event_id en RaceImport
    imp.event_id = report.event_id
    imp.parse_meta_json = None
    # PR4: persistir el motivo de revisión (catálogo cerrado) si se envió.
    # Pydantic ya validó que sea un RevisionReasonCode válido. Guardamos el
    # code (string) — nunca texto libre.
    is_revision = body.revision_reason is not None
    if is_revision:
        imp.revision_reason = body.revision_reason.value
    await db.flush()

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
    """Endpoint 4 wizard (histórico) — lista paginada de imports."""
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

    items: list[ImportListItem] = []
    for imp in imports:
        u = users_by_id.get(imp.imported_by_user_id)
        uploader = UploadUserRef(
            id=imp.imported_by_user_id,
            full_name=(
                f"{u.first_name} {u.last_name}".strip() if u else f"user#{imp.imported_by_user_id}"
            ),
        )
        n_results = (imp.stats_json or {}).get("results_inserted", 0)
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
