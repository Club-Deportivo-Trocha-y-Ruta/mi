"""Router ``/api/race-analysis/imports/*`` — el coach revisa y comitea (F-UP3).

Amendment 2026-09-26 (contracts/staged-import.md, FR-044): la web app YA NO
sube archivos de resultados — ``POST /parse`` se retiró (T152). El único
camino de entrada es ahora ``app.services.race.results_skill`` (motor de
lectura offline del CLI/skill) → ``stage_extracted_results`` (ver
``import_staging.py``), que deja el ``RaceImport`` pending listo. Este router
solo revisa y comitea lo que ya está staged.

Endpoints (docs/10-race-results/upload-design.md §4):

- ``POST /{parse_id}/dry-run`` — ejecuta ``RaceIngestor.ingest_event(dry_run=True)``
                                   con los datos del parse persistido. Devuelve
                                   ``matches`` con resolución HITL pendiente.
- ``POST /{parse_id}/commit``  — ejecuta ``RaceIngestor.ingest_event(dry_run=False)``
                                   con ``resolved_matches`` del coach. Promueve
                                   pending → committed. Mueve PDFs SFTP a
                                   ``race-imports/committed/{uuid}/``.
- ``GET /``                    — histórico paginado. RBAC: coach + admin.

Feature 044 (US1, research R-05, ``contracts/reading-integrity.md``): la
respuesta trae ``categories[]``/``unreadable_rows[]`` (lector por banda,
ahora vía ``results_skill``), y tres rutas nuevas:

- ``POST /{parse_id}/corrections``  — parcha una fila (add/edit/remove) de
                                        una categoría; se persiste en
                                        ``parse_meta_json.corrections`` y se
                                        reaplica en cada dry-run/commit.
- ``POST /{parse_id}/acknowledge``  — reconoce una categoría inconsistente
                                        con un motivo del catálogo cerrado.
- ``GET /acknowledge-reasons``      — catálogo cerrado del dropdown.

Convenciones:
- RBAC ``require_role([coach, admin])`` — padres bloqueados.
- Path en storage: ``race-imports/{pending|committed}/{uuid}/{resultados|general}.{ext}``
  — UUID server-side evita path traversal en filename original.

Privacidad (CLAUDE.md):
- Logs nunca incluyen nombres de menores — usan ``bib`` + ``cat_code`` + sha256.
- ``MatchPreview.competitor_name`` contiene nombre del PDF público Federación
  (no datos privados).
"""
from __future__ import annotations

import functools
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction
from app.models.club import ClubMember, ClubRole
from app.models.race_category import RaceCategory
from app.models.race_event import RaceEvent
from app.models.race_identity_candidate import RaceIdentityCandidate
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_import_staged_document import RaceImportStagedDocument
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.schemas.race import EventMeta
from app.schemas.race_imports import (
    REVISION_REASON_LABELS,
    AcknowledgeIn,
    AcknowledgeReasonOption,
    AcknowledgeReasonsResponse,
    CategoryCompletenessResponse,
    CompletenessRead,
    DiffRowRead,
    DiffSummaryRead,
    DryRunCounts,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportDetailRead,
    ImportDryRunResponse,
    ImportDryRunRevisionResponse,
    ImportListItem,
    ImportListResponse,
    MatchPreview,
    ParseWarning,
    RaceEventDiffResponse,
    RevisionReasonCode,
    RevisionReasonOption,
    RevisionReasonsResponse,
    RowCorrectionIn,
    TyrAthleteRef,
    UploadUserRef,
)
from app.services.audit import AuditEntityType, record_audit
from app.services.permissions import coach_club_ids, ensure_import_club_access
from app.services.race import identity_review, staged_document
from app.services.race.completeness import (
    ACKNOWLEDGE_REASON_LABELS,
    AcknowledgeReasonCode,
    CompletenessReport,
    CorrectionError,
    apply_corrections,
    check_category,
)
from app.services.race.import_staging import (
    _category_headers_raw,
    _legacy_results_by_category,
)
from app.services.race.ingestor import RaceIngestor
from app.services.race.matcher import match_athletes
from app.services.race.revision import (
    DiffRow,
    RevisionContext,
    commit_revision,
    compute_diff,
    detect_revision,
)
from app.services.race.revision_diff_view import build_event_diff_view
from app.services.race.run_staleness import invalidate_runs_for_event
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    StagedDocumentMissing,
)
from app.services.request_context import AuditContext, get_request_context
from app.services.training import storage_sftp

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers internos — series + lectura de categorías
#
# Feature 044 (US5, T059): ``_get_or_create_series``, ``_legacy_results_by_
# category``, ``_category_headers_raw``, ``_categories_read``,
# ``_categories_meta`` y ``_unreadable_rows_meta`` viven en
# ``app.services.race.import_staging`` (contracts/historical-load.md
# §"Staging service") y se re-importan arriba — este router queda como
# llamador delgado del camino dry-run/commit.
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
    debe poder distinguir esto de ``identity_pending``/
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
# Documento stageado (amendment 2026-09-26, T138, contracts/staged-import.md)
#
# Las rutas de revisión ya no vuelven a tocar SFTP ni a reparsear: leen la
# fila ``race_import_staged_documents`` (``staged_document.load``) y
# reaplican las correcciones guardadas en ``parse_meta_json["corrections"]``
# — exactamente lo que antes hacían ``_reload_results_document``/
# ``_reload_parsed_from_storage`` sobre el archivo redescargado, con las
# mismas dos cachés LRU (retiradas: ya no hace falta cachear una lectura de
# storage que no vuelve a ocurrir). Un import legado (staged por el flujo de
# subida anterior a esta amendment, sin fila de documento) responde ``409
# restage_required`` — el coach debe volver a subir el archivo por el CLI/
# skill de lectura.
# ---------------------------------------------------------------------------


def _restage_required_response(import_id: int) -> JSONResponse:
    """``409 restage_required`` (contracts/staged-import.md §"API deltas").
    Cuerpo plano — igual patrón que ``_identity_pending_response``."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "restage_required", "import_id": import_id},
    )


async def _load_staged_categories(
    db: AsyncSession, imp: RaceImport
) -> list[ParsedCategory] | JSONResponse:
    """Categorías del documento stageado, con las correcciones guardadas ya
    reaplicadas (research R-05) — sucesor de ``_reload_parsed_from_storage``.
    Devuelve el 409 ``restage_required`` en vez de lanzar cuando el import es
    legado; el caller debe comprobar ``isinstance(..., JSONResponse)`` y
    devolverlo tal cual.
    """
    try:
        parsed_doc = await staged_document.load(db, imp)
    except StagedDocumentMissing:
        return _restage_required_response(imp.id)
    corrections = (imp.parse_meta_json or {}).get("corrections") or []
    if corrections:
        parsed_doc = apply_corrections(parsed_doc, corrections)
    return parsed_doc.categories


async def _load_fresh_document(
    db: AsyncSession, imp: RaceImport
) -> ParsedResults | JSONResponse:
    """Documento stageado SIN reaplicar correcciones (research R-05) —
    building block de ``add_correction``/``acknowledge_category``, que
    necesitan el acta tal como quedó impresa/extraída para validar una
    corrección nueva contra el estado real."""
    try:
        return await staged_document.load(db, imp)
    except StagedDocumentMissing:
        return _restage_required_response(imp.id)


#: Presupuesto del contrato (``identity-review-api.md`` §Rebuild): trabajo
#: real ≤ 10 s, este timeout deja margen bajo carga sin bloquear la petición
#: indefinidamente. Compartido por el gate de este router y por
#: ``POST /api/race-identity/rebuild`` (T049), que importa esta constante en
#: vez de repetir el número.
IDENTITY_REBUILD_TIMEOUT_S = 30.0


def _latest_correction_at(imp: RaceImport) -> Optional[datetime]:
    """Instante de la corrección manual más reciente de la carga (UTC sin
    zona, como las columnas ``DateTime``), o ``None`` si no tiene ninguna.

    ``add_correction`` guarda ``at`` (ISO, UTC) en cada entrada de
    ``parse_meta_json["corrections"]``; una entrada sin ``at`` legible se
    ignora.
    """
    latest: Optional[datetime] = None
    for correction in (imp.parse_meta_json or {}).get("corrections") or []:
        try:
            at = datetime.fromisoformat(correction["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if at.tzinfo is not None:
            at = at.astimezone(timezone.utc).replace(tzinfo=None)
        if latest is None or at > latest:
            latest = at
    return latest


async def _identity_rebuild_needed(
    db: AsyncSession, *, latest_correction_at: Optional[datetime] = None
) -> bool:
    """¿Hace falta recalcular la cola antes de este commit?

    El rebuild reparsea TODOS los imports en staging: con las quince válidas
    históricas cargadas eso son minutos en Render y la conexión MySQL ociosa
    se cae a mitad (visto en producción, 2026-09-22). Solo es necesario si
    algún import en staging es más nuevo que el último candidato calculado
    — si nada se subió desde entonces, la cola ya está al día y basta con
    leer el contador de `pending`.

    ``latest_correction_at``: la última corrección manual de ESTA carga
    (``POST /corrections`` agrega/edita filas pero no toca ``imported_at``). Si
    es posterior al último candidato, la cola no vio esas filas (research R-08,
    nota 2 del G2). Las correcciones de otras cargas no cuentan: el candado
    solo mira las filas de la que se confirma.
    """
    last_candidate = (
        await db.execute(select(func.max(RaceIdentityCandidate.created_at)))
    ).scalar()
    if last_candidate is None:
        return True
    if latest_correction_at is not None and latest_correction_at > last_candidate:
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


def _identity_pending_response(parse_id: int, pending_for_import: int) -> JSONResponse:
    """``409 identity_pending`` (feature 045, contracts/api.md §"Changed
    behaviour"). Cuerpo plano, no ``{"detail": {...}}``: ``HTTPException`` no
    admite claves hermanas de ``detail``, por eso se devuelve la respuesta
    directamente. ``review_path`` lleva al coach a las identidades de ESTA
    carga en «Cargas e identidades». Solo ids y conteos, nunca nombres.
    """
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "identity_pending",
            "pending_for_import": pending_for_import,
            "review_path": (
                f"/competitions/imports?seccion=identidades&import={parse_id}"
            ),
        },
    )


async def _identity_gate(
    db: AsyncSession,
    imp: RaceImport,
    rows_by_category: Mapping[str, Sequence[ResultsRow]],
    *,
    operation: str,
) -> Optional[JSONResponse]:
    """Candado de identidad POR CARGA de ``/commit`` y ``/commit-pending``
    (feature 045, research R-08; antes de 045 miraba la cola entera).

    Recalcula la cola solo si hace falta (``_identity_rebuild_needed``, que
    también mira las correcciones de esta carga; ``identity_review.rebuild``
    es idempotente y nunca pisa una decisión) y bloquea únicamente con los
    candidatos ``pending`` cuyas claves pertenecen a las filas que ESTE
    commit va a ingestar (``rows_by_category``, RESULTADOS de las categorías
    elegibles — GENERAL retirement, amendment 2026-09-26: ya no hay GENERAL
    que preguntar). Devuelve ``None`` si puede seguir, o la respuesta ``409
    identity_pending``. ``503`` si el recálculo excede
    ``IDENTITY_REBUILD_TIMEOUT_S``.

    Cierra la transacción (``commit``) antes de volver: el llamador sigue con
    SFTP/parseo/ingesta y no debe conservar la conexión MySQL abierta.
    """
    parse_id = imp.id
    try:
        if await _identity_rebuild_needed(
            db, latest_correction_at=_latest_correction_at(imp)
        ):
            await identity_review.rebuild(
                db,
                rows_loader=functools.partial(load_identity_rows, db),
                timeout_s=IDENTITY_REBUILD_TIMEOUT_S,
            )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "identity_rebuild_timeout",
                "message": (
                    "El recálculo de identidad tardó demasiado antes del "
                    f"{operation}. Intenta de nuevo en unos minutos."
                ),
            },
        )
    blocking = await identity_review.pending_candidates_for_import(
        db, identity_review.import_record_keys(rows_by_category)
    )
    await db.commit()
    if not blocking:
        return None
    logger.info(
        "race_import_%s identity_pending parse_id=%s pending_for_import=%d",
        operation.replace("-", "_"),
        parse_id,
        len(blocking),
    )
    return _identity_pending_response(parse_id, len(blocking))


async def load_identity_rows(
    db: AsyncSession, imp: RaceImport
) -> identity_review.ImportRows:
    """``RowsLoader`` de ``identity_review.rebuild`` (feature 044, T050/T049).

    Amendment 2026-09-26 (T139, contracts/staged-import.md): lee el
    documento stageado (``staged_document.load``) en vez de redescargar y
    reparsear desde storage. Un import legado (``StagedDocumentMissing``, sin
    fila de documento) se propaga tal cual — ``load_universe`` ya captura
    cualquier excepción de un ``rows_loader`` y lo reporta en
    ``imports_unreadable``, igual que un archivo ilegible antes de esta
    amendment. GENERAL ya no se carga (GENERAL retirement, R-25): el
    ingestor no lo ingesta más, así que tampoco entra al universo de
    identidad. Vive en este router, no en el servicio, porque el servicio de
    identidad no debe importar el router (contrato §Resolver, docstring de
    ``identity_review.load_universe``).
    """
    parsed_doc = await staged_document.load(db, imp)
    corrections = (imp.parse_meta_json or {}).get("corrections") or []
    if corrections:
        parsed_doc = apply_corrections(parsed_doc, corrections)
    if imp.status == RaceImportStatus.committed:
        # Import confirmado a medias: solo sus categorías pendientes siguen
        # en el universo de identidad; las ya ingestadas son resultados.
        pending = set((imp.parse_meta_json or {}).get("pending_categories") or [])
        pending_codes = {
            c.code for c in parsed_doc.categories if c.header_raw in pending and c.code
        }
        results = _legacy_results_by_category(
            ParsedResults(categories=parsed_doc.categories, unreadable_rows=[])
        )
        return identity_review.ImportRows(
            results={code: rows for code, rows in results.items() if code in pending_codes}
        )
    return identity_review.ImportRows(results=_legacy_results_by_category(parsed_doc))


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


async def _detect_import_revision(
    db: AsyncSession, imp: RaceImport, parse_meta: dict
) -> Optional[RevisionContext]:
    """¿Esta carga stageada es una revisión de una válida ya commiteada?

    Amendment 2026-09-26 (T174, contracts/revision-via-skill.md): a
    diferencia de ``stage_extracted_results`` (que solo la detecta para
    reportarla en el CLI), dry-run y commit necesitan el ``RevisionContext``
    completo (parent_event_id) para recomputar el diff. Se re-detecta con el
    mismo header persistido en ``parse_meta_json`` — ``series_id`` ya
    resuelto por el stage evita divergencia de nombre (BUG-1 fix, igual que
    ``detect_revision`` documenta).
    """
    header = parse_meta.get("header") or {}
    if not header:
        return None
    return await detect_revision(
        db,
        series_name=str(header.get("series_name", "")),
        season=int(header.get("season", 0)),
        valida_num=int(header.get("valida_num", 0)),
        series_id=imp.series_id,
    )


def _diff_row_to_read(row: DiffRow) -> DiffRowRead:
    return DiffRowRead(
        action=row.action,
        competitor_normalized_name=row.competitor_normalized_name,
        competitor_display_name=row.competitor_display_name,
        category_code=row.category_code,
        result_id=row.result_id,
        before=row.before,
        after=row.after,
        fuzzy_matched=row.fuzzy_matched,
    )


async def _build_revision_dry_run_response(
    db: AsyncSession,
    imp_id: int,
    revision_ctx: RevisionContext,
    parsed_results: dict[str, list[ResultsRow]],
    season: int,
) -> ImportDryRunRevisionResponse:
    """Rama de revisión del dry-run — contrato §"Dry-run, revision branch"."""
    diff_report = await compute_diff(
        db, parsed_results, revision_ctx.parent_event_id, season
    )
    return ImportDryRunRevisionResponse(
        parse_id=imp_id,
        is_revision=True,
        parent_event_id=revision_ctx.parent_event_id,
        diff_summary=DiffSummaryRead(
            n_create=diff_report.summary.n_create,
            n_update=diff_report.summary.n_update,
            n_delete=diff_report.summary.n_delete,
            n_unchanged=diff_report.summary.n_unchanged,
            n_total=diff_report.summary.n_total,
        ),
        diff_rows=[
            _diff_row_to_read(row)
            for row in diff_report.rows
            if row.action != "unchanged"
        ],
        warnings=[],
    )


@router.post(
    "/{parse_id}/dry-run",
    response_model=ImportDryRunResponse | ImportDryRunRevisionResponse,
)
async def dry_run_import(
    parse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ImportDryRunResponse | ImportDryRunRevisionResponse | JSONResponse:
    """Endpoint 2 wizard (dry-run) — ejecuta ingest sin commit + retorna matches.

    Amendment 2026-09-26 (T174): si la carga es una revisión de una válida ya
    commiteada, la rama entera cambia — se devuelve el diff identity-aware
    (``ImportDryRunRevisionResponse``) en vez de correr
    ``RaceIngestor.ingest_event`` (que no sabe de revisiones).
    """
    imp = await _load_pending_import(db, parse_id, current_user)
    parse_meta = imp.parse_meta_json or {}

    categories = await _load_staged_categories(db, imp)
    if isinstance(categories, JSONResponse):
        return categories
    categories_doc = ParsedResults(categories=categories, unreadable_rows=[])
    category_headers_raw = _category_headers_raw(categories_doc)
    parsed_results = _legacy_results_by_category(categories_doc)

    revision_ctx = await _detect_import_revision(db, imp, parse_meta)
    if revision_ctx is not None:
        season = int((parse_meta.get("header") or {}).get("season", 0))
        return await _build_revision_dry_run_response(
            db, imp.id, revision_ctx, parsed_results, season
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
    imp_uploader_user_id = imp.imported_by_user_id
    imp_series_id = imp.series_id  # BUG-1 fix: honor series resolved at /parse

    # Ejecutar dry-run real
    ingestor = RaceIngestor(db)
    try:
        report = await ingestor.ingest_event(
            meta=meta_obj,
            results_by_category=parsed_results,
            pdf_results_sha256=imp_sha256,
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
# Endpoint 3: POST /{parse_id}/commit — rama de revisión (T174)
# ---------------------------------------------------------------------------


async def _commit_revision_branch(
    db: AsyncSession,
    imp: RaceImport,
    categories: list[ParsedCategory],
    parsed_results: dict[str, list[ResultsRow]],
    revision_ctx: RevisionContext,
    body: ImportCommitRequest,
    parse_id: int,
    current_user: User,
    ctx: AuditContext,
) -> ImportCommitResponse | JSONResponse:
    """``POST /{parse_id}/commit`` cuando la carga es una revisión —
    ``contracts/revision-via-skill.md`` §"Commit, revision branch". Orden
    fijado por el contrato: motivo → candado de identidad → completitud (sin
    revisión parcial) → diff recomputado server-side → aplicar.
    """
    # 1. revision_reason obligatorio en TODA revisión (T174 punto 1).
    if body.revision_reason is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "revision_reason es obligatorio para confirmar una revisión "
                "(catálogo cerrado, ver GET /revision-reasons)."
            ),
        )
    revision_reason = body.revision_reason.value

    # 2. Candado de identidad por carga (feature 045) — sobre TODAS las
    #    filas de la carga: una revisión no tiene "categorías elegibles"
    #    parciales todavía (eso lo decide el punto 3).
    blocked = await _identity_gate(db, imp, parsed_results, operation="commit")
    if blocked is not None:
        return blocked

    # `_identity_gate` hace su propio `commit()` (para persistir un rebuild
    # si hizo falta), lo que suelta el lock FOR UPDATE y expira `imp` — se
    # re-verifica que sigue pending, igual que el camino normal.
    imp = await _load_pending_import(db, parse_id, current_user, for_update=True)
    parse_meta = imp.parse_meta_json or {}

    # 3. Sin revisión parcial (contrato): cualquier categoría inconsistente
    #    sin reconocer bloquea la revisión completa.
    _eligible_codes, pending_categories = _eligible_and_pending_categories(
        categories, parse_meta
    )
    if pending_categories:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "revision_incomplete",
                "pending_categories": pending_categories,
            },
        )

    season = int((parse_meta.get("header") or {}).get("season", 0))

    # 4. Diff recomputado server-side — el del dry-run NUNCA se toma del
    #    cliente (contrato punto 4).
    diff_report = await compute_diff(
        db, parsed_results, revision_ctx.parent_event_id, season
    )

    # 5. Aplicar transaccional (lock pesimista sobre el RaceEvent adentro).
    try:
        report = await commit_revision(
            db, imp, revision_ctx, diff_report, revision_reason, current_user.id
        )
    except OperationalError:
        await db.rollback()
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "event_locked"},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    await db.flush()

    # 6. Evidencia movida a committed/ + documento stageado borrado
    #    (FR-048/049 — nunca vuelve a leerse).
    parse_uuid = parse_meta.get("parse_uuid", "unknown")
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
                "race_import_commit_revision move_object failed parse_id=%s err=%s",
                parse_id,
                exc,
            )
    imp.parse_meta_json = None
    await staged_document.delete(db, imp.id)
    await db.flush()

    # 7. Invalidación de runs IA — best effort, nunca bloquea el commit.
    try:
        await invalidate_runs_for_event(db, report.event_id)
        await db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "race_import_commit_revision invalidate_runs failed parse_id=%s err=%s",
            parse_id,
            exc,
        )

    # 8. Auditoría — solo conteos, nunca nombres (privacidad menores).
    await record_audit(
        db,
        action=AuditAction.execute,
        entity_type=AuditEntityType.race_import,
        entity_id=imp.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        changed_fields=["status"],
        diff={
            "status": (
                RaceImportStatus.pending.value,
                RaceImportStatus.committed.value,
            )
        },
        meta={
            "race_event_id": report.event_id,
            "is_revision": True,
            "n_create": report.n_create,
            "n_update": report.n_update,
            "n_delete": report.n_delete,
        },
        request_id=ctx.request_id,
    )

    logger.info(
        "race_import_commit_revision parse_id=%s parent_import_id=%s event_id=%s "
        "creates=%d updates=%d deletes=%d revisions=%d",
        parse_id,
        report.parent_import_id,
        report.event_id,
        report.n_create,
        report.n_update,
        report.n_delete,
        report.revisions_created,
    )

    return ImportCommitResponse(
        parse_id=parse_id,
        race_event_id=report.event_id,
        n_results_inserted=report.n_create,
        n_competitors_created=0,
        n_competitors_linked=0,
        pending_categories=[],
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
) -> ImportCommitResponse | JSONResponse:
    """Endpoint 3 wizard (commit) — promueve pending → committed con resolved matches.

    ``409 identity_pending`` (feature 045, R-08) si algún candidato de identidad
    ``pending`` involucra a las filas de ESTA carga; ``JSONResponse`` porque su
    cuerpo plano (``detail`` + ``pending_for_import`` + ``review_path``) no cabe
    en ``HTTPException``.

    Amendment 2026-09-26 (T174): si es una revisión de una válida ya
    commiteada, toda la rama cambia — ver ``_commit_revision_branch``.
    """
    imp = await _load_pending_import(db, parse_id, current_user, for_update=True)
    parse_meta = imp.parse_meta_json or {}

    categories = await _load_staged_categories(db, imp)
    if isinstance(categories, JSONResponse):
        return categories
    categories_doc = ParsedResults(categories=categories, unreadable_rows=[])
    category_headers_raw = _category_headers_raw(categories_doc)
    parsed_results = _legacy_results_by_category(categories_doc)

    revision_ctx = await _detect_import_revision(db, imp, parse_meta)
    if revision_ctx is not None:
        return await _commit_revision_branch(
            db,
            imp,
            categories,
            parsed_results,
            revision_ctx,
            body,
            parse_id,
            current_user,
            ctx,
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

    # Feature 044 (US4, T050) — candado de revisión de identidad: el resolver
    # del ingestor podría fusionar homónimos en silencio (o partir a una misma
    # persona) sin que el coach haya decidido. Feature 045 (US3, R-08): solo
    # frena un candidato `pending` que involucre a las filas que ESTE commit
    # ingesta (`eligible_codes`) — uno que habla de otra carga ya no bloquea.
    # `_identity_gate` recalcula la cola si hace falta (idempotente), así que
    # el candado sigue cerrado aunque nadie pulsara "recalcular".
    blocked = await _identity_gate(
        db,
        imp,
        {code: rows for code, rows in parsed_results.items() if code in eligible_codes},
        operation="commit",
    )
    if blocked is not None:
        return blocked

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

    # Re-adquirir el lock justo antes de mutar: ``_identity_gate`` hace su
    # propio ``commit()`` internamente (para persistir un rebuild antes de
    # decidir), lo que suelta el lock tomado arriba. Si otro commit ganó la
    # carrera mientras tanto, esta re-verificación lanza 404 (ya no está
    # pending). Amendment 2026-09-26 (T138): ya no hay SFTP de por medio —
    # solo la lectura del documento stageado, que no toca storage.
    imp = await _load_pending_import(db, parse_id, current_user, for_update=True)

    # Snapshot attrs antes del ingest: el ingestor hace commit/rollback sobre la
    # misma session, lo que expira el ORM `imp` (MissingGreenlet en lazy-load).
    imp_sha256 = imp.sha256
    imp_series_id = imp.series_id  # BUG-1 fix: honor series resolved at /parse

    # Ejecutar commit (dry_run=False) — promueve pending → committed
    ingestor = RaceIngestor(db)
    try:
        report = await ingestor.ingest_event(
            meta=meta_obj,
            results_by_category=parsed_results,
            match_decisions=match_decisions,
            pdf_results_sha256=imp_sha256,
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
        # Amendment 2026-09-26 (T138, contracts/staged-import.md): commit
        # completo (sin categorías pendientes) — el documento stageado ya
        # no hace falta, se borra igual que el meta.
        await staged_document.delete(db, imp.id)
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
) -> ImportCommitResponse | JSONResponse:
    """Termina de ingestar un import ``committed`` cuyas categorías
    pendientes se corrigieron o reconocieron después del primer ``/commit``
    (contracts/historical-load.md §"Idempotence and resumption", FR-027).

    Mismo candado de identidad por carga que ``/commit`` (FR-018, 045 R-08):
    recalcula la cola antes de decidir, ``409 identity_pending`` si algún
    candidato pendiente involucra a las filas que va a ingestar.
    ``409 nothing_pending`` si no queda ninguna categoría pendiente
    (ni en el caché de meta, ni tras re-verificar contra el acta corregida).
    """
    imp = await _load_committed_import_with_pending(
        db, parse_id, current_user, for_update=True
    )
    parse_meta = imp.parse_meta_json or {}

    categories = await _load_staged_categories(db, imp)
    if isinstance(categories, JSONResponse):
        return categories
    categories_doc = ParsedResults(categories=categories, unreadable_rows=[])
    category_headers_raw = _category_headers_raw(categories_doc)
    parsed_results = _legacy_results_by_category(categories_doc)

    # Categorías que este commit-pending ingesta ahora: las pendientes que ya
    # son consistentes o reconocidas. Su conjunto de filas es el alcance del
    # candado de identidad — mismo `_identity_gate` que /commit (FR-018, 045 R-08).
    eligible_codes, pending_categories = _eligible_and_pending_categories(
        categories,
        parse_meta,
        restrict_to_headers=set(parse_meta.get("pending_categories") or []),
    )
    blocked = await _identity_gate(
        db,
        imp,
        {code: rows for code, rows in parsed_results.items() if code in eligible_codes},
        operation="commit-pending",
    )
    if blocked is not None:
        return blocked

    try:
        meta_obj = _build_event_meta_from_parse_meta(parse_meta, imp.filename)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"parse_meta inválido: {exc}",
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
    imp_series_id = imp.series_id

    ingestor = RaceIngestor(db)
    try:
        report = await ingestor.ingest_event(
            meta=meta_obj,
            results_by_category=parsed_results,
            match_decisions=match_decisions,
            pdf_results_sha256=imp_sha256,
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
        # Amendment 2026-09-26 (T138): ya no queda nada pendiente — el
        # documento stageado se borra, igual que en un commit completo.
        await staged_document.delete(db, imp.id)
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
) -> CategoryCompletenessResponse | JSONResponse:
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

    fresh = await _load_fresh_document(db, imp)
    if isinstance(fresh, JSONResponse):
        return fresh
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
) -> CategoryCompletenessResponse | JSONResponse:
    """``POST /{parse_id}/acknowledge`` (research R-05).

    El gate de commit que consume este reconocimiento (bloquear solo la
    categoría, no todo el cargue) es de T060/T061 — esta tarea (T019) solo
    persiste la decisión y la audita.
    """
    imp = await _load_correctable_import(db, parse_id, current_user)
    meta = dict(imp.parse_meta_json or {})

    corrections = meta.get("corrections") or []
    fresh = await _load_fresh_document(db, imp)
    if isinstance(fresh, JSONResponse):
        return fresh
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

    Sin ``status`` no lista las cargas ``discarded`` (feature 045, US3).
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
    else:
        # Feature 045 (US3): una carga descartada ya no es trabajo en curso;
        # solo se lista si se pide explícitamente con ``?status=discarded``.
        stmt = stmt.where(RaceImport.status != RaceImportStatus.discarded)
        count_stmt = count_stmt.where(RaceImport.status != RaceImportStatus.discarded)

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

    # Amendment 2026-09-26 (T140): un solo SELECT batched para toda la
    # página — nunca N+1, nunca carga el documento.
    restage_map = await _restage_required_map(db, imports)

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
                restage_required=restage_map.get(imp.id, False),
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


# ---------------------------------------------------------------------------
# Feature 045 (US3, research R-09): retomar y descartar una carga
#
# Se registran al FINAL del módulo: ``GET /{import_id}`` no debe quedar antes
# de las rutas estáticas ``/revision-reasons`` y ``/acknowledge-reasons``.
# ---------------------------------------------------------------------------

#: Claves de ``parse_meta_json`` que el wizard necesita para retomar la carga.
#: Lista permitida, no denegada: una clave nueva del meta no sale al cliente
#: hasta que alguien decida que es seguro. Quedan fuera las rutas de storage,
#: ``parse_uuid``/``results_ext`` (detalles internos) y ``corrections`` (filas
#: con nombre/club/ciudad de un menor).
_PUBLIC_PARSE_META_KEYS = (
    "header",
    "conditions",
    "categories_found",
    "n_rows_resultados",
    "n_rows_general",
    "categories",
    "unreadable_rows",
    "acknowledged",
    "pending_categories",
)

#: Estados desde los que se puede descartar una carga.
_DISCARDABLE_STATUSES = (RaceImportStatus.pending, RaceImportStatus.dry_run)


async def _load_import_in_scope(
    db: AsyncSession,
    import_id: int,
    current_user: User,
    *,
    for_update: bool = False,
) -> RaceImport:
    """Carga un ``RaceImport`` de cualquier estado dentro del alcance por club.

    ``404`` tanto si no existe como si es de otro club: a diferencia de
    ``_load_pending_import`` (``403`` por club), estos dos endpoints no revelan
    que la carga existe. El admin ve todo.
    """
    stmt = select(RaceImport).where(RaceImport.id == import_id)
    if for_update:
        stmt = stmt.with_for_update()
    imp = (await db.execute(stmt)).scalar_one_or_none()
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"import_id={import_id} no existe.",
    )
    if imp is None:
        raise not_found
    try:
        await ensure_import_club_access(db, imp, current_user)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_403_FORBIDDEN:
            raise
        raise not_found from None
    return imp


async def _import_season(db: AsyncSession, imp: RaceImport) -> Optional[int]:
    """Temporada de la carga: la del encabezado del meta mientras lo conserva;
    si no (confirmada por completo), la de la serie de su evento."""
    season = ((imp.parse_meta_json or {}).get("header") or {}).get("season")
    if season is not None:
        return int(season)
    if imp.event_id is None:
        return None
    return (
        await db.execute(
            select(RaceSeries.season_year)
            .join(RaceEvent, RaceEvent.series_id == RaceSeries.id)
            .where(RaceEvent.id == imp.event_id)
        )
    ).scalar_one_or_none()


async def _import_parent_committed_at(
    db: AsyncSession, imp: RaceImport
) -> Optional[datetime]:
    """Cuándo se confirmó la versión previa de la válida de una carga en
    staging — el mismo dato que ``POST /parse`` devuelve como
    ``parent_committed_at`` (``detect_revision``).

    Solo para ``pending``/``dry_run`` con encabezado: una carga ``committed``
    (incluida la confirmada a medias, que conserva su ``header`` y su evento)
    se encontraría a sí misma como «previa».
    """
    if imp.status not in _DISCARDABLE_STATUSES:
        return None
    header = (imp.parse_meta_json or {}).get("header") or {}
    try:
        season = int(header["season"])
        valida_num = int(header["valida_num"])
    except (KeyError, TypeError, ValueError):
        return None
    revision = await detect_revision(
        db,
        series_name=header.get("series_name") or "",
        season=season,
        valida_num=valida_num,
        series_id=imp.series_id,
    )
    return revision.parent_committed_at if revision is not None else None


def _restage_required_candidate_ids(imports: Sequence[RaceImport]) -> list[int]:
    """IDs de ``imports`` que necesitan un documento stageado para no
    requerir restage (T140, contracts/staged-import.md): ``pending``, o
    ``committed`` con ``pending_categories``. Un import en cualquier otro
    estado (``dry_run``, ``failed``, ``discarded``, o ``committed`` sin nada
    pendiente) nunca lo requiere — no hace falta ni preguntar por su
    documento."""
    out: list[int] = []
    for imp in imports:
        if imp.status == RaceImportStatus.pending:
            out.append(imp.id)
        elif imp.status == RaceImportStatus.committed and (
            imp.parse_meta_json or {}
        ).get("pending_categories"):
            out.append(imp.id)
    return out


async def _restage_required_map(
    db: AsyncSession, imports: Sequence[RaceImport]
) -> dict[int, bool]:
    """``{import_id: restage_required}`` para ``imports``, con un solo
    ``SELECT`` batched (nunca N+1, nunca carga el documento) — T140."""
    candidate_ids = _restage_required_candidate_ids(imports)
    if not candidate_ids:
        return {}
    has_document_ids = set(
        (
            await db.execute(
                select(RaceImportStagedDocument.import_id).where(
                    RaceImportStagedDocument.import_id.in_(candidate_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        import_id: import_id not in has_document_ids for import_id in candidate_ids
    }


async def _import_detail(db: AsyncSession, imp: RaceImport) -> ImportDetailRead:
    meta = imp.parse_meta_json
    restage_map = await _restage_required_map(db, [imp])
    return ImportDetailRead(
        id=imp.id,
        status=imp.status.value,
        source_filename=imp.original_filename or imp.filename,
        parse_meta=(
            {k: meta[k] for k in _PUBLIC_PARSE_META_KEYS if k in meta}
            if meta is not None
            else None
        ),
        created_at=imp.imported_at,
        event_id=imp.event_id,
        season=await _import_season(db, imp),
        parent_committed_at=await _import_parent_committed_at(db, imp),
        restage_required=restage_map.get(imp.id, False),
    )


@router.get(
    "/{import_id}",
    response_model=ImportDetailRead,
    summary="Una carga, para retomar el wizard",
    description=(
        "Devuelve el estado y el meta público de una carga (pending, dry_run, "
        "committed, failed o discarded) para que el wizard la retome desde "
        "`?import=<id>`. RBAC coach/admin, alcance por club: otro club o un id "
        "desconocido responden 404."
    ),
)
async def get_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ImportDetailRead:
    """``GET /api/race-analysis/imports/{import_id}`` (coach/admin)."""
    imp = await _load_import_in_scope(db, import_id, current_user)
    return await _import_detail(db, imp)


@router.post(
    "/{import_id}/discard",
    response_model=ImportDetailRead,
    summary="Descarta una carga en curso",
    description=(
        "`pending`/`dry_run` → `discarded` (200). Ya `discarded` → 200 sin "
        "cambios (idempotente). `committed` o `failed` → 409 "
        "`import_not_discardable`. RBAC coach/admin, alcance por club (404 si "
        "es de otro club). Los archivos de storage no se tocan."
    ),
)
async def discard_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ctx: AuditContext = Depends(get_request_context),
) -> ImportDetailRead:
    """``POST /api/race-analysis/imports/{import_id}/discard`` (coach/admin).

    Máquina de estados (data-model §5): ``pending | dry_run → discarded``;
    un ``committed`` nunca se descarta. Solo cambia ``status``: el PDF y el
    meta quedan como estaban, así una carga descartada por error se puede
    reconstruir a mano, y el mismo archivo se puede volver a subir (el staging
    solo reusa ``pending``/``dry_run``).
    """
    imp = await _load_import_in_scope(db, import_id, current_user, for_update=True)

    if imp.status == RaceImportStatus.discarded:
        return await _import_detail(db, imp)
    if imp.status not in _DISCARDABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "import_not_discardable",
                "message": (
                    f"Una carga en estado {imp.status.value} no se puede "
                    "descartar. Solo las cargas pendientes o en simulación."
                ),
            },
        )

    previous = imp.status
    imp.status = RaceImportStatus.discarded
    # Amendment 2026-09-26 (T138, contracts/staged-import.md): un discard
    # también borra el documento stageado — no hay vuelta atrás desde
    # ``discarded`` (el mismo archivo se re-stagea desde cero si se necesita).
    await staged_document.delete(db, imp.id)
    await db.flush()
    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.race_import,
        entity_id=imp.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=None,
        changed_fields=["status"],
        diff={"status": (previous.value, RaceImportStatus.discarded.value)},
        request_id=ctx.request_id,
    )
    logger.info(
        "race_import_discard import_id=%s from=%s", import_id, previous.value
    )
    return await _import_detail(db, imp)
