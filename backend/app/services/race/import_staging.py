"""Servicio de staging de resultados de carrera (feature 044, US5).

Amendment 2026-09-26 (contracts/staged-import.md, FR-044): el único camino
de entrada es ``stage_extracted_results`` — recibe un ``ParsedResults`` YA
extraído (por ``app.services.race.results_skill.apply_profile``, corrido por
el CLI/skill fuera de FastAPI) y deja un ``RaceImport`` pending con su
documento persistido en ``race_import_staged_documents`` (T137). No hay
parseo ni upload aquí: ``stage_results_file`` (el cuerpo legado de
``POST /parse``, que sí parseaba un PDF/CSV recién subido) se retiró en
T152 junto con el endpoint.

Season, válida, fecha y sede son **siempre** los que llegan explícitos en
``StageHeader`` — nada se infiere en silencio (FR-025).

Privacidad: los warnings usan ``bib``/``category_code``, nunca nombres;
``MatchPreview``/``ParsedResultsRowRead`` (fuera de este módulo) sí muestran
nombres porque vienen de un PDF ya público de la Federación.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path as PathLib
from typing import Literal, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction
from app.models.race_category import RaceCategory
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User
from app.schemas.race_imports import (
    CompletenessRead,
    ParsedCategoryRead,
    ParsedResultsRowRead,
    ParseWarning,
    UnreadableRowRead,
)
from app.services.audit import AuditEntityType, record_audit
from app.services.race import staged_document as staged_document_module
from app.services.race.completeness import check_category
from app.services.race.normalizer import mapping_kind_for
from app.services.race.revision import detect_revision
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    StagedProfileMeta,
)
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
# Staging service (amendment 2026-09-26, contracts/staged-import.md) — el
# documento ya viene extraído (``results_skill.apply_profile``); no hay
# parseo aquí. ``stage_results_file`` (el cuerpo de ``POST /parse``, que sí
# parseaba) se retiró en T152 junto con el endpoint.
# ---------------------------------------------------------------------------


@dataclass
class StageHeader:
    """Header de la carga — siempre explícito, nunca inferido del archivo
    (FR-025, igual que ``stage_results_file``)."""

    series_name: str
    series_kind: RaceSeriesKind
    series_level: RaceSeriesLevel
    season: int
    valida_num: int
    event_name: str
    event_date: date_type
    location: str


@dataclass
class StageResult:
    """Resultado de ``stage_extracted_results`` — contracts/staged-import.md.

    ``status`` es ``"pending"`` para una carga nueva (o el mismo pending ya
    en staging, dedupe FR-027) y ``"already_committed"`` cuando el sha256 ya
    fue confirmado (no se crea nada).
    """

    import_id: Optional[int]
    status: str
    is_revision: bool = False
    parent_import_id: Optional[int] = None
    already_committed: bool = False
    n_rows: int = 0
    n_categories: int = 0
    warnings: list[str] = field(default_factory=list)


#: Claves "públicas" del meta cacheado — mismas que
#: ``routers.race_imports._PUBLIC_PARSE_META_KEYS`` (duplicadas aquí porque
#: ese router importa de este módulo, no al revés).
_STAGE_PUBLIC_META_KEYS = (
    "header",
    "conditions",
    "categories_found",
    "n_rows_resultados",
    "n_rows_general",
    "categories",
    "unreadable_rows",
)


def _stage_header_dict(header: StageHeader) -> dict:
    return {
        "series_name": header.series_name,
        "season": header.season,
        "valida_num": header.valida_num,
        "event_name": header.event_name,
        "event_date": header.event_date.isoformat(),
        "location": header.location,
    }


async def stage_extracted_results(
    db: AsyncSession,
    *,
    document: ParsedResults,
    profile: StagedProfileMeta,
    file_bytes: bytes,
    original_filename: str,
    results_ext: Literal["pdf", "csv"],
    header: StageHeader,
    actor: User,
    ctx: AuditContext,
    dry: bool = False,
) -> StageResult:
    """Sucesor de ``stage_results_file`` — sin parseo: el documento ya viene
    extraído (``results_skill.apply_profile``). contracts/staged-import.md.

    A diferencia de ``stage_results_file``: no soporta GENERAL (GENERAL
    retirement, R-25) y persiste el documento en
    ``race_import_staged_documents`` (T137) en vez de solo referenciar el
    archivo en storage — las rutas de revisión ya no vuelven a tocar el
    archivo (FR-048, FR-049).

    ``dry=True``: valida (dedupe, documento no vacío) y calcula conteos sin
    subir el archivo ni escribir nada en la base de datos — usado por el CLI
    para una previsualización sin efectos (``contracts/results-skill-cli.md``).
    """
    n_rows = sum(len(c.rows) for c in document.categories)
    n_categories = len(document.categories)
    sha256_hex = hashlib.sha256(file_bytes).hexdigest()

    # 1. Dedupe — mismo orden que ``stage_results_file``: committed primero.
    committed = (
        await db.execute(
            select(RaceImport).where(
                RaceImport.sha256 == sha256_hex,
                RaceImport.status == RaceImportStatus.committed,
            )
        )
    ).scalar_one_or_none()
    if committed is not None:
        return StageResult(
            import_id=committed.id,
            status="already_committed",
            already_committed=True,
            n_rows=n_rows,
            n_categories=n_categories,
        )

    already_pending = (
        await db.execute(
            select(RaceImport)
            .where(
                RaceImport.sha256 == sha256_hex,
                RaceImport.status.in_(
                    (RaceImportStatus.pending, RaceImportStatus.dry_run)
                ),
            )
            .order_by(RaceImport.id.desc())
        )
    ).scalars().first()
    if already_pending is not None:
        return StageResult(
            import_id=already_pending.id,
            status=already_pending.status.value,
            is_revision=bool(already_pending.parent_import_id),
            parent_import_id=already_pending.parent_import_id,
            n_rows=n_rows,
            n_categories=n_categories,
        )

    # 2. Documento vacío — nada que stagear.
    if n_rows == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "empty_document",
                "message": "El documento no tiene ninguna fila. Verifique el perfil de lectura.",
            },
        )

    # 3. Serie + categorías leídas + filas ilegibles.
    series = await _get_or_create_series(
        db, header.series_name, header.season, header.series_kind, header.series_level
    )
    parsed_codes = {c.code for c in document.categories if c.code}
    cat_by_code: dict[str, RaceCategory] = {}
    if parsed_codes:
        cat_stmt = select(RaceCategory).where(RaceCategory.code.in_(parsed_codes))
        cat_by_code = {
            c.code: c for c in (await db.execute(cat_stmt)).scalars().all()
        }
    categories_read = _categories_read(document, cat_by_code)
    unreadable_meta = _unreadable_rows_meta(document)

    revision_ctx = await detect_revision(
        db,
        series_name=header.series_name,
        season=header.season,
        valida_num=header.valida_num,
        series_id=series.id,
    )
    is_revision = revision_ctx is not None

    if dry:
        return StageResult(
            import_id=None,
            status="dry",
            is_revision=is_revision,
            parent_import_id=revision_ctx.parent_import_id if revision_ctx else None,
            n_rows=n_rows,
            n_categories=n_categories,
        )

    # 4. Subir la evidencia — nunca se re-sube ni se re-lee (FR-048/049).
    parse_uuid = uuid.uuid4().hex
    results_rel = f"race-imports/pending/{parse_uuid}/resultados.{results_ext}"
    results_storage_path, results_storage_url = await storage_sftp.upload_bytes(
        file_bytes, results_rel
    )

    # 5. Una transacción: RaceImport + documento + auditoría. Si algo falla,
    # se borra el objeto subido (best effort) y se relanza — nunca queda un
    # import huérfano ni un documento sin import (o viceversa).
    parse_meta = {
        "header": _stage_header_dict(header),
        # No hay condiciones de carrera en este flujo (contrato): siempre null.
        "conditions": {
            "climate": None,
            "temperature_c": None,
            "surface_condition": None,
            "altitude_msnm": None,
            "weather_notes": None,
        },
        "categories_found": sorted(c.code for c in document.categories if c.code),
        "n_rows_resultados": n_rows,
        "n_rows_general": 0,
        "categories": _categories_meta(document, categories_read),
        "unreadable_rows": unreadable_meta,
        "results_ext": results_ext,
        "results_storage_path": results_storage_path,
        "parse_uuid": parse_uuid,
        "source": "results_skill",
        "profile_id": profile.profile_id,
    }
    try:
        race_import = RaceImport(
            filename=_sanitize_filename(original_filename),
            original_filename=original_filename,
            sha256=sha256_hex,
            series_id=series.id,
            status=RaceImportStatus.pending,
            stats_json={},
            imported_by_user_id=actor.id,
            kind=RaceImportKind.resultados,
            storage_path=results_storage_path,
            storage_url=results_storage_url,
            parse_meta_json=parse_meta,
            imported_at=func.now(),
        )
        db.add(race_import)
        await db.flush()

        await staged_document_module.save(db, race_import.id, document, profile)

        await record_audit(
            db,
            action=AuditAction.create,
            entity_type=AuditEntityType.race_import,
            entity_id=race_import.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=None,
            request_id=ctx.request_id,
            meta={"via": "results_skill"},
        )
        await db.flush()
    except Exception:
        await db.rollback()
        try:
            await storage_sftp.delete_object(results_storage_path)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            logger.warning(
                "stage_extracted_results: no se pudo borrar el objeto huérfano "
                "storage_path=%s tras fallo de transacción",
                results_storage_path,
            )
        raise

    logger.info(
        "race_import_stage parse_id=%s sha=%s user_id=%s rows=%d categories=%d "
        "is_revision=%s via=results_skill",
        race_import.id,
        sha256_hex[:12],
        actor.id,
        n_rows,
        n_categories,
        is_revision,
    )

    return StageResult(
        import_id=race_import.id,
        status=RaceImportStatus.pending.value,
        is_revision=is_revision,
        parent_import_id=revision_ctx.parent_import_id if revision_ctx else None,
        n_rows=n_rows,
        n_categories=n_categories,
    )

