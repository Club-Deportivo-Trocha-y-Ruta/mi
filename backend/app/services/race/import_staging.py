"""Servicio de staging de un archivo RESULTADOS (feature 044, US5).

Extraído de ``routers/race_imports.py::parse_import`` (contracts/
historical-load.md §"Staging service"): el mismo cuerpo que hoy corre detrás
de ``POST /race-imports/parse`` para una válida 2026 sirve, sin cambio de
comportamiento, para las quince válidas históricas — el router queda como un
llamador delgado y ``backend/scripts/stage_race_history.py`` (T063) llama
esta función directamente, sin pasar por FastAPI.

``general_pdf`` nunca se usa en la carga histórica (contracts/historical-load
.md: "solo se sube el archivo de resultados por válida"), pero el parámetro
sigue existiendo — el wizard actual de temporada corriente lo sigue
soportando y el contrato pide "sin cambio de comportamiento" para 2026
(T056, comparación golden).

Season, válida, fecha y sede son **siempre** los que llegan en los
parámetros (form fields del wizard, campos del manifiesto del script) —
``parse_event_header`` en el parser solo pre-rellena el formulario; nada se
infiere en silencio aquí (FR-025).

Privacidad: igual que el router previo — los warnings usan ``bib``/
``category_code``, nunca nombres; ``MatchPreview``/``ParsedResultsRowRead``
(fuera de este módulo) sí muestran nombres porque vienen de un PDF ya
público de la Federación.
"""
from __future__ import annotations

import hashlib
import logging
import re
import tempfile
import uuid
from asyncio import wait_for
from datetime import date as date_type
from pathlib import Path as PathLib
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit_log import AuditAction
from app.models.race_category import RaceCategory
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User
from app.schemas.race_imports import (
    CompletenessRead,
    ImportParseRequestFields,
    ImportParseResponse,
    ParseHeaderInfo,
    ParsedCategoryRead,
    ParsedResultsRowRead,
    ParseWarning,
    UnreadableRowRead,
)
from app.services.audit import AuditEntityType, record_audit
from app.services.race.completeness import check_category
from app.services.race.normalizer import mapping_kind_for
from app.services.race.pdf_parser import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    parse_event_header,
    parse_results_document,
)
from app.services.race.revision import detect_revision
from app.services.request_context import AuditContext
from app.services.training import storage_sftp

logger = logging.getLogger(__name__)

#: Sanitización filename: keep alnum, dash, underscore, dot. Strip path-traversal.
_FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.\-]")


def _sanitize_filename(raw: Optional[str]) -> str:
    """Devuelve un filename seguro para preservar en BD. Cero path traversal."""
    if not raw:
        return "upload.pdf"
    base = PathLib(raw.replace("\\", "/")).name
    safe = _FILENAME_SAFE_RE.sub("_", base)
    safe = safe[:200] or "upload.pdf"
    return safe


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------


async def _get_or_create_series(
    db: AsyncSession,
    series_name: str,
    season: int,
    kind: RaceSeriesKind,
    level: RaceSeriesLevel | str = RaceSeriesLevel.departmental,
) -> RaceSeries:
    """Resuelve o crea una serie por ``(name, season_year)``, honrando el
    ``kind`` del cliente.

    Historia previa a la extracción de este módulo (spec 014 / T017, spec 023
    D5): ver ``git log`` de ``routers/race_imports.py`` para el detalle de
    cada corrección — el comportamiento no cambió, solo la ubicación.
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


# ---------------------------------------------------------------------------
# Parsing helpers (compartidos con el reload de dry-run/commit — ver
# ``routers/race_imports.py::_reload_parsed_from_storage``, que los llama a
# través de este módulo para que exista una sola copia parcheable)
# ---------------------------------------------------------------------------


async def _parse_results_with_timeout(path: PathLib, ext: str) -> ParsedResults:
    """Parsea RESULTADOS con timeout; mapea TimeoutError/excepción a 422.

    Lector por banda (``parse_results_document``): devuelve categorías en
    orden de documento — incluidas las de encabezado no reconocido, con sus
    filas — y las bandas ilegibles (``unreadable_rows``). El CSV de la Liga
    no tiene el defecto de desborde de columna que motiva el lector por
    banda, así que sigue usando ``csv_parser.parse_results_csv``.
    """
    import asyncio

    from app.services.race.csv_parser import parse_results_csv

    async def _run() -> ParsedResults:
        if ext == "pdf":
            return await asyncio.to_thread(parse_results_document, path)
        legacy = await asyncio.to_thread(parse_results_csv, path)
        categories = [
            ParsedCategory(header_raw=code, code=code, rows=rows)
            for code, rows in legacy.items()
        ]
        return ParsedResults(categories=categories, unreadable_rows=[])

    try:
        return await wait_for(_run(), timeout=settings.race_parse_timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"PDF demasiado complejo (parse > "
                f"{settings.race_parse_timeout_seconds}s). Verifique formato oficial."
            ),
        )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        logger.exception("race_import_parse GENERAL failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo procesar el PDF GENERAL. Verifique que sea el formato oficial de la Federación.",
        )


def _legacy_results_by_category(parsed: ParsedResults) -> dict[str, list[ResultsRow]]:
    """Colapsa un ``ParsedResults`` a la forma legada ``{code: [rows]}`` que
    ``RaceIngestor.ingest_event`` sigue esperando. Categorías de encabezado no
    reconocido se excluyen — su commit queda bloqueado hasta que exista un
    mapeo (research R-03)."""
    out: dict[str, list[ResultsRow]] = {}
    for category in parsed.categories:
        if category.code is None:
            continue
        out.setdefault(category.code, []).extend(category.rows)
    return out


def _category_headers_raw(parsed: ParsedResults) -> dict[str, str]:
    """``{code: header_raw}`` — el encabezado tal como venía impreso, para que
    el ingestor congele ``category_label_raw`` con el header REAL del acta
    (research R-04)."""
    out: dict[str, str] = {}
    for category in parsed.categories:
        if category.code and category.code not in out:
            out[category.code] = category.header_raw
    return out


def _categories_read(
    parsed: ParsedResults, cat_by_code: dict[str, "RaceCategory"]
) -> list[ParsedCategoryRead]:
    """Construye el ``categories[]`` de la respuesta de ``/parse`` — header
    crudo, code resuelto, ``mapping_kind`` y completitud por categoría
    (contracts/reading-integrity.md)."""
    out: list[ParsedCategoryRead] = []
    for category in parsed.categories:
        cat_obj = cat_by_code.get(category.code) if category.code else None
        mapping_kind = mapping_kind_for(f"CAT: {category.header_raw}", cat_obj)
        report = check_category(category)
        out.append(
            ParsedCategoryRead(
                header_raw=category.header_raw,
                code=category.code,
                mapping_kind=mapping_kind,
                rows=[
                    ParsedResultsRowRead(
                        position=row.position,
                        bib=row.bib,
                        name=row.name,
                        city=row.city,
                        club=row.club,
                        time_raw=row.time_raw,
                        points=row.points,
                    )
                    for row in category.rows
                ],
                completeness=CompletenessRead(
                    status=report.status,
                    missing=report.missing,
                    duplicated=report.duplicated,
                ),
            )
        )
    return out


def _categories_meta(parsed: ParsedResults, categories_read: list[ParsedCategoryRead]) -> list[dict]:
    """Forma persistida en ``parse_meta_json["categories"]`` (data-model.md
    §7): ``rows`` es un CONTEO, nunca la lista — el archivo almacenado ya es
    la fuente de verdad de las filas."""
    return [
        {
            "header_raw": read.header_raw,
            "code": read.code,
            "mapping_kind": read.mapping_kind,
            "rows": len(read.rows),
            "completeness": {
                "status": read.completeness.status,
                "missing": read.completeness.missing,
                "duplicated": read.completeness.duplicated,
            },
        }
        for read in categories_read
    ]


def _unreadable_rows_meta(parsed: ParsedResults) -> list[dict]:
    return [{"page": r.page, "ordinal": r.ordinal} for r in parsed.unreadable_rows]


# ---------------------------------------------------------------------------
# Staging service
# ---------------------------------------------------------------------------


async def _response_for_already_staged(
    db: AsyncSession,
    imp: RaceImport,
    *,
    file_bytes: bytes,
    results_ext: str,
    series_name: str,
    season: int,
    valida_num: int,
    event_name: str,
) -> ImportParseResponse:
    """FR-027: respuesta para un archivo idéntico ya en staging.

    Re-parsea los ``file_bytes`` recién recibidos en memoria (sin tocar
    SFTP ni la base de datos) para que la respuesta conserve el mismo
    detalle por fila que un ``/parse`` normal — el import existente no se
    toca, así que esto es puramente de lectura. ``will_be_revision`` no
    aplica a un import que ya está en staging (no hay nada previo commiteado
    de otro modo se habría bloqueado arriba con el 409 de duplicado
    commiteado), así que queda en ``False``.
    """
    with tempfile.NamedTemporaryFile(
        suffix=f".{results_ext}", delete=False
    ) as tmp_results:
        tmp_results.write(file_bytes)
        tmp_results.flush()
        results_path = PathLib(tmp_results.name)
    try:
        parsed_doc = await _parse_results_with_timeout(results_path, results_ext)
    finally:
        try:
            results_path.unlink(missing_ok=True)
        except OSError:
            pass

    n_rows_resultados = sum(len(c.rows) for c in parsed_doc.categories)
    parsed_codes = {c.code for c in parsed_doc.categories if c.code}
    cat_by_code: dict[str, RaceCategory] = {}
    if parsed_codes:
        cat_stmt = select(RaceCategory).where(RaceCategory.code.in_(parsed_codes))
        cat_by_code = {
            c.code: c for c in (await db.execute(cat_stmt)).scalars().all()
        }
    categories_read = _categories_read(parsed_doc, cat_by_code)
    unreadable_rows_read = [
        UnreadableRowRead(page=r.page, ordinal=r.ordinal)
        for r in parsed_doc.unreadable_rows
    ]
    n_rows_general = (imp.parse_meta_json or {}).get("n_rows_general")

    return ImportParseResponse(
        parse_id=imp.id,
        sha256=imp.sha256,
        header=ParseHeaderInfo(
            series_name=series_name,
            season=season,
            valida_num=valida_num,
            event_name=event_name,
        ),
        n_rows_resultados=n_rows_resultados,
        n_rows_general=n_rows_general,
        warnings=[],
        categories=categories_read,
        unreadable_rows=unreadable_rows_read,
        will_be_revision=False,
        parent_event_id=None,
        parent_import_id=None,
        parent_committed_at=None,
        parent_n_results=None,
    )


async def stage_results_file(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    original_filename: str,
    results_ext: str,
    series_name: str,
    season: int,
    valida_num: int,
    event_name: str,
    event_date: date_type,
    location: str,
    series_kind: RaceSeriesKind = RaceSeriesKind.cup,
    series_level: RaceSeriesLevel = RaceSeriesLevel.departmental,
    conditions: Optional[ImportParseRequestFields] = None,
    general_bytes: Optional[bytes] = None,
    kind_override: Optional[RaceImportKind] = None,
    actor: User,
    ctx: AuditContext,
) -> ImportParseResponse:
    """Sube, parsea y crea el ``RaceImport`` ``pending`` de un archivo
    RESULTADOS — contracts/historical-load.md §"Staging service".

    Es el cuerpo de ``POST /race-imports/parse`` sin cambio de
    comportamiento (T056 lo verifica con una comparación golden); el router
    valida el multipart/Form (magic bytes, tamaño, enums crudos) y llama esta
    función con tipos ya resueltos. El script de carga histórica
    (``scripts/stage_race_history.py``, T063) la llama directamente sin
    pasar por FastAPI — nunca envía ``general_bytes`` (FR-024: el archivo
    acumulado de la Liga no se stagea para las temporadas históricas).

    Deviations frente al esbozo de firma del contrato: ``results_ext``,
    ``general_bytes`` y ``kind_override`` no aparecen en el esbozo de
    ``contracts/historical-load.md`` (que solo ilustra el caso
    RESULTADOS-only) pero son necesarios para que el wizard de temporada
    corriente — que sí sube GENERAL opcional y puede forzar ``kind`` —
    conserve exactamente su comportamiento actual.

    Raises:
        HTTPException: 409 si el sha256 de RESULTADOS ya está ``committed``;
            400 si GENERAL es idéntico a RESULTADOS; 422 si el parser no
            extrae ninguna fila.
    """
    conditions_fields = conditions or ImportParseRequestFields()

    results_sha = hashlib.sha256(file_bytes).hexdigest()

    general_sha: Optional[str] = None
    if general_bytes is not None:
        general_sha = hashlib.sha256(general_bytes).hexdigest()
        if general_sha == results_sha:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RESULTADOS y GENERAL no pueden ser el mismo archivo.",
            )

    # Detectar duplicado SHA committed (409) — FR-027: un archivo idéntico ya
    # confirmado no crea nada.
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

    # FR-027 (contracts/historical-load.md §"Idempotence and resumption"):
    # el mismo archivo ya en staging (pending o dry_run), aún no committed,
    # no crea un segundo ``RaceImport`` — se devuelve el existente. Sin esto
    # el script de carga histórica (T063), pensado para poder re-correrse
    # tras una interrupción, duplicaría cada import ya en cola en cada
    # reintento.
    already_staged = (
        await db.execute(
            select(RaceImport)
            .where(
                RaceImport.sha256 == results_sha,
                RaceImport.status.in_(
                    (RaceImportStatus.pending, RaceImportStatus.dry_run)
                ),
            )
            .order_by(RaceImport.id.desc())
        )
    ).scalars().first()
    if already_staged is not None:
        return await _response_for_already_staged(
            db,
            already_staged,
            file_bytes=file_bytes,
            results_ext=results_ext,
            series_name=series_name,
            season=season,
            valida_num=valida_num,
            event_name=event_name,
        )

    # Liberar conexión MySQL antes de SFTP upload + pdfplumber parse (pueden
    # tardar minutos). Hostinger cierra sockets ociosos por wait_timeout.
    await db.commit()

    if kind_override is not None:
        kind_value = kind_override
    else:
        kind_value = (
            RaceImportKind.both if general_bytes else RaceImportKind.resultados
        )

    parse_uuid = uuid.uuid4().hex
    results_rel = f"race-imports/pending/{parse_uuid}/resultados.{results_ext}"
    results_storage_path, results_storage_url = await storage_sftp.upload_bytes(
        file_bytes, results_rel
    )
    general_storage_path: Optional[str] = None
    general_storage_url: Optional[str] = None
    if general_bytes:
        general_rel = f"race-imports/pending/{parse_uuid}/general.pdf"
        general_storage_path, general_storage_url = await storage_sftp.upload_bytes(
            general_bytes, general_rel
        )

    with tempfile.NamedTemporaryFile(
        suffix=f".{results_ext}", delete=False
    ) as tmp_results:
        tmp_results.write(file_bytes)
        tmp_results.flush()
        results_path = PathLib(tmp_results.name)
    warnings_collected: list[ParseWarning] = []
    try:
        parsed_doc = await _parse_results_with_timeout(results_path, results_ext)
        # FR-025 (contracts/historical-load.md §"Staging service"):
        # season/válida/fecha/sede vienen SIEMPRE de los parámetros — nunca
        # se infieren del PDF. ``parse_event_header`` solo pre-rellena el
        # formulario del wizard; aquí se usa exclusivamente para detectar un
        # desacuerdo y avisarlo, nunca para sobreescribir los inputs. Solo
        # aplica a PDF (el CSV de la Liga no trae ese encabezado); un header
        # no detectado (``None``) no es un desacuerdo, es "no hay con qué
        # comparar".
        if results_ext == "pdf":
            try:
                detected_header = parse_event_header(results_path)
            except Exception:  # noqa: BLE001 — best-effort, nunca bloquea el parse
                detected_header = None
            if detected_header is not None:
                mismatched: list[str] = []
                if detected_header.valida_num != valida_num:
                    mismatched.append("valida_num")
                if detected_header.location.strip().upper() != location.strip().upper():
                    mismatched.append("location")
                if detected_header.event_date != event_date:
                    mismatched.append("event_date")
                if mismatched:
                    warnings_collected.append(
                        ParseWarning(
                            code="header_mismatch",
                            message=(
                                "El encabezado impreso del archivo no coincide con "
                                "los datos ingresados (" + ", ".join(mismatched) + "); "
                                "se usan los datos ingresados."
                            ),
                            context={"fields": mismatched},
                        )
                    )
    finally:
        try:
            results_path.unlink(missing_ok=True)
        except OSError:
            pass

    # Feature 044 (US1): el total cuenta TODAS las filas parseadas, incluidas
    # las de encabezado no reconocido — FR-002 las conserva.
    n_rows_resultados = sum(len(c.rows) for c in parsed_doc.categories)
    if n_rows_resultados == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parser no extrajo ninguna fila válida. PDF/CSV no oficial?",
        )

    parsed_codes = {c.code for c in parsed_doc.categories if c.code}
    cat_by_code: dict[str, RaceCategory] = {}
    if parsed_codes:
        cat_stmt = select(RaceCategory).where(RaceCategory.code.in_(parsed_codes))
        cat_by_code = {
            c.code: c for c in (await db.execute(cat_stmt)).scalars().all()
        }
    categories_read = _categories_read(parsed_doc, cat_by_code)
    unreadable_rows_read = [
        UnreadableRowRead(page=r.page, ordinal=r.ordinal)
        for r in parsed_doc.unreadable_rows
    ]

    parsed_results = _legacy_results_by_category(parsed_doc)

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

    series = await _get_or_create_series(db, series_name, season, series_kind, series_level)
    event_date_str = event_date.isoformat()
    parse_meta = {
        "header": {
            "series_name": series_name,
            "season": season,
            "valida_num": valida_num,
            "event_name": event_name,
            "event_date": event_date_str,
            "location": location,
        },
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
        "categories": _categories_meta(parsed_doc, categories_read),
        "unreadable_rows": _unreadable_rows_meta(parsed_doc),
    }
    race_import = RaceImport(
        filename=_sanitize_filename(original_filename),
        original_filename=original_filename,
        sha256=results_sha,
        series_id=series.id,
        status=RaceImportStatus.pending,
        stats_json={},
        imported_by_user_id=actor.id,
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

    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.race_import,
        entity_id=race_import.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        request_id=ctx.request_id,
    )

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
        actor.id,
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
        categories=categories_read,
        unreadable_rows=unreadable_rows_read,
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
