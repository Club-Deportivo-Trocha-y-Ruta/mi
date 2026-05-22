"""Servicio de revisión integral de resultados Copa Valle (F-UP-REV).

Implementa el flujo descrito en ``docs/10-race-results/revision-design.md``:

- ``detect_revision``: dada una serie+valida, retorna ``RevisionContext`` si ya
  existe un ``RaceImport.status=committed`` previo apuntando al mismo evento
  ``(series_id, sequence_number)``. None si es primer import o legacy F1.7
  (``event_id`` NULL).

- ``compute_diff``: dado un PDF nuevo parseado + el ``parent_event_id``, calcula
  el diff completo (create / update / delete / unchanged) vs los ``RaceResult``
  persistidos (filtra ``deleted_at IS NULL``). Match primario por
  ``(category.code, normalized_name)``; fallback fuzzy ``partial_ratio >= 92``
  intra-categoría para tolerar correcciones de typos (ej. acento agregado).

- ``commit_revision``: aplica el diff transaccional con audit trail completo en
  ``race_result_revisions`` (una fila por cambio). Soft-delete via ``deleted_at``
  SIN tocar ``status`` (preserva semántica oficial federación). Lock pesimista
  ``SELECT ... FOR UPDATE`` sobre ``RaceEvent`` (nowait 5s) para evitar race
  conditions entre coaches. Promueve ``RaceImport`` a ``committed`` con
  ``parent_import_id`` y ``revision_reason``.

Convenciones:
- ``athlete_id`` linkage TyR NO se sobrescribe (preserva matching previo del coach).
- ``status`` del ``RaceResult`` jamás cambia en revisión: solo se soft-deletea.
- Privacidad menores (CLAUDE.md): logs nunca incluyen ``revision_reason`` text,
  solo ``len(reason)``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_result_revision import (
    RaceResultRevision,
    RaceResultRevisionAction,
)
from app.services.race.normalizer import normalize_name, parse_time

if TYPE_CHECKING:
    from app.services.race.pdf_parser import ResultsRow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_SERIES_NAME = "Copa Valle de Ciclomontañismo"

#: Threshold rapidfuzz para fuzzy match intra-categoría. 92 es el cierre del
#: design (revision-design.md §3.1) — captura typos leves ("MEJIA" → "MEJÍA")
#: sin tolerar matches espurios (test específico de tied names valida).
_FUZZY_THRESHOLD: int = 92

#: Campos del RaceResult comparados en el diff (revision-design.md §3.2).
#: ``athlete_id`` y ``bib_number`` NO se comparan (el primero es decisión del
#: coach, el segundo puede cambiar entre versiones de PDF si la fed corrige).
_DIFF_FIELDS: tuple[str, ...] = (
    "position",
    "status",
    "race_time_ms",
    "laps_behind",
    "points_awarded",
)


# ---------------------------------------------------------------------------
# Dataclasses de respuesta
# ---------------------------------------------------------------------------


@dataclass
class RevisionContext:
    """Contexto retornado por ``detect_revision`` cuando una ingesta es revisión.

    Campos:
    - ``parent_event_id``: id del ``RaceEvent`` ya persistido con la misma
      ``(series_id, sequence_number)``.
    - ``parent_import_id``: id del ``RaceImport`` committed inmediato anterior
      (último por ``imported_at DESC``).
    - ``parent_committed_at``: timestamp del commit previo (display UI banner).
    - ``parent_committed_by_user_id``: user id del coach que commiteó la versión
      anterior.
    - ``n_results_persisted``: conteo de ``RaceResult`` activos (deleted_at IS NULL)
      del parent_event para contexto del banner.
    """

    parent_event_id: int
    parent_import_id: int
    parent_committed_at: datetime
    parent_committed_by_user_id: int
    n_results_persisted: int


@dataclass
class DiffRow:
    """Una fila del diff: representa una acción a aplicar a un ``RaceResult``.

    Estructura JSON-serializable para uso en API responses + persistencia en
    ``RaceResultRevision.diff_json``.

    Campos:
    - ``action``: "create" | "update" | "delete" | "unchanged".
    - ``competitor_normalized_name``: clave de match (normalize_name).
    - ``competitor_display_name``: nombre display (del PDF nuevo o persistido).
    - ``category_code``: code de la categoría (ej. "INF_A_M").
    - ``result_id``: id del ``RaceResult`` persistido (None solo para create).
    - ``before``: snapshot del estado actual (para update/delete; None en create).
    - ``after``: snapshot del estado nuevo (para create/update; None en delete).
    - ``fields_changed``: lista de campos modificados (solo update).
    - ``fuzzy_matched``: True si el match se hizo via fuzzy fallback (warning UI).
    """

    action: str
    competitor_normalized_name: str
    competitor_display_name: str
    category_code: str
    result_id: Optional[int] = None
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    fields_changed: list[str] = field(default_factory=list)
    fuzzy_matched: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialización JSON-friendly (enums.value, datetimes ISO, etc.)."""
        return asdict(self)


@dataclass
class DiffSummary:
    """Conteos agregados del diff."""

    n_create: int
    n_update: int
    n_delete: int
    n_unchanged: int

    @property
    def n_total(self) -> int:
        return self.n_create + self.n_update + self.n_delete + self.n_unchanged


@dataclass
class DiffReport:
    """Reporte completo del diff: summary + rows ordenados.

    Las rows están ordenadas: deletes → updates → creates → unchanged
    (revision-design.md DTR-5: atención visual primero a removidos).
    """

    summary: DiffSummary
    rows: list[DiffRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": asdict(self.summary),
            "n_total": self.summary.n_total,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass
class CommitRevisionReport:
    """Resultado de ``commit_revision`` — counts aplicados + revisions creadas."""

    parse_import_id: int
    parent_import_id: int
    event_id: int
    n_create: int
    n_update: int
    n_delete: int
    n_unchanged: int
    revisions_created: int
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. detect_revision
# ---------------------------------------------------------------------------


async def detect_revision(
    db: AsyncSession,
    series_name: str,
    season: int,
    valida_num: int,
) -> Optional[RevisionContext]:
    """Detecta si una ingesta de `(series, season, valida_num)` es revisión.

    Algoritmo (revision-design.md §1.2):

    1. Buscar ``RaceSeries`` por ``(name, season_year)``.
    2. Si no existe → ``None`` (primera vez para esta serie).
    3. Buscar ``RaceEvent`` por ``(series_id, sequence_number=valida_num)``.
    4. Si no existe → ``None`` (primera vez para esta válida).
    5. Buscar el último ``RaceImport.status=committed`` con ``event_id=event.id``.
       Encadenamiento lineal — el "parent" de la próxima revisión es el último.
    6. Si no hay committed previo → ``None`` (puede ser legacy F1.7 con event_id
       NULL — esos imports nunca matchean el `WHERE event_id = X`).
    7. Contar ``RaceResult`` activos (``deleted_at IS NULL``) del parent_event.

    Args:
        db: AsyncSession activa.
        series_name: Nombre canónico de la serie (typically Copa Valle).
        season: Año de la temporada.
        valida_num: Número de válida (1..7, 99 = CD).

    Returns:
        ``RevisionContext`` si es revisión; ``None`` si es primer import.
    """
    # 1. Buscar serie
    from app.models.race_series import RaceSeries

    series_result = await db.execute(
        select(RaceSeries).where(
            RaceSeries.name == series_name,
            RaceSeries.season_year == season,
        )
    )
    series = series_result.scalar_one_or_none()
    if series is None:
        return None

    # 2. Buscar evento por (series_id, sequence_number=valida_num)
    event_result = await db.execute(
        select(RaceEvent).where(
            RaceEvent.series_id == series.id,
            RaceEvent.sequence_number == valida_num,
        )
    )
    event = event_result.scalar_one_or_none()
    if event is None:
        return None

    # 3. Buscar último import committed apuntando a este event
    prior_result = await db.execute(
        select(RaceImport)
        .where(
            RaceImport.event_id == event.id,
            RaceImport.status == RaceImportStatus.committed,
        )
        .order_by(RaceImport.imported_at.desc())
        .limit(1)
    )
    prior_import = prior_result.scalar_one_or_none()
    if prior_import is None:
        # Edge case D-1: event existe pero sin imports committed (F1.7 legacy
        # con event_id NULL no matchearía nunca esta query; este caso solo
        # ocurre si el event se creó manualmente vía CLI sin RaceImport linked).
        return None

    # 4. Contar resultados activos del parent event para contexto del banner
    count_result = await db.execute(
        select(RaceResult.id).where(
            RaceResult.event_id == event.id,
            RaceResult.deleted_at.is_(None),
        )
    )
    n_results = len(list(count_result.scalars().all()))

    return RevisionContext(
        parent_event_id=event.id,
        parent_import_id=prior_import.id,
        parent_committed_at=prior_import.imported_at,
        parent_committed_by_user_id=prior_import.imported_by_user_id,
        n_results_persisted=n_results,
    )


# ---------------------------------------------------------------------------
# 2. compute_diff
# ---------------------------------------------------------------------------


def _serialize_result_snapshot(result: RaceResult) -> dict[str, Any]:
    """Serializa ``RaceResult`` a dict JSON-friendly para ``diff_json``.

    Enum → .value, datetimes → ISO format, None preserva None.
    """
    return {
        "result_id": result.id,
        "event_id": result.event_id,
        "category_id": result.category_id,
        "competitor_id": result.competitor_id,
        "athlete_id": result.athlete_id,
        "bib_number": result.bib_number,
        "position": result.position,
        "status": result.status.value if result.status else None,
        "race_time_ms": result.race_time_ms,
        "laps_behind": result.laps_behind,
        "points_awarded": result.points_awarded,
    }


def _parsed_row_snapshot(
    parsed: "ResultsRow",
    status: ResultStatus,
    race_time_ms: Optional[int],
    laps_behind: Optional[int],
    category_id: int,
) -> dict[str, Any]:
    """Serializa una fila parseada (post parse_time) a dict snapshot."""
    return {
        "category_id": category_id,
        "bib_number": _parse_bib_int(parsed.bib),
        "position": parsed.position,
        "status": status.value,
        "race_time_ms": race_time_ms,
        "laps_behind": laps_behind,
        "points_awarded": parsed.points,
    }


def _parse_bib_int(bib_raw: str) -> Optional[int]:
    """Parse defensivo bib → int o None."""
    if bib_raw is None:
        return None
    s = str(bib_raw).strip()
    if not s.isdigit():
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _fuzzy_match_in_category(
    target_normalized: str,
    candidates_keys: list[str],
) -> Optional[str]:
    """Busca el mejor match fuzzy >= 92 dentro de una lista de claves (mismo cat).

    Args:
        target_normalized: nombre normalizado del PDF nuevo.
        candidates_keys: lista de normalized_names persistidos en la misma cat.

    Returns:
        El candidate matched (con score >= _FUZZY_THRESHOLD), o None si ninguno.
        Si hay tie (2+ con mismo score >= threshold), retorna el primero por
        orden de iteración (estable).
    """
    if not target_normalized or not candidates_keys:
        return None
    best_score = 0
    best_key: Optional[str] = None
    for candidate in candidates_keys:
        score = fuzz.partial_ratio(target_normalized, candidate)
        if score > best_score:
            best_score = score
            best_key = candidate
    if best_score >= _FUZZY_THRESHOLD:
        return best_key
    return None


async def _load_persisted_results(
    db: AsyncSession, event_id: int
) -> dict[tuple[str, str], tuple[RaceResult, RaceCompetitor, RaceCategory]]:
    """Carga ``RaceResult`` activos del event + joinea competitor + category.

    Retorna dict ``{(cat_code, normalized_name): (result, competitor, category)}``.
    Filtra ``deleted_at IS NULL`` (soft-deleted no participan en el diff).
    """
    # Cargar competitors index
    comp_result = await db.execute(select(RaceCompetitor))
    competitors_by_id = {c.id: c for c in comp_result.scalars().all()}

    # Cargar categories index
    cat_result = await db.execute(select(RaceCategory))
    categories_by_id = {c.id: c for c in cat_result.scalars().all()}

    # Cargar results del event, no soft-deleted
    result = await db.execute(
        select(RaceResult).where(
            RaceResult.event_id == event_id,
            RaceResult.deleted_at.is_(None),
        )
    )
    rows = list(result.scalars().all())

    out: dict[tuple[str, str], tuple[RaceResult, RaceCompetitor, RaceCategory]] = {}
    for r in rows:
        comp = competitors_by_id.get(r.competitor_id)
        cat = categories_by_id.get(r.category_id)
        if comp is None or cat is None:
            continue
        key = (cat.code, comp.normalized_name)
        # Tie-break: si dos persistidos comparten la key (raro pero posible si
        # hubo duplicados), preservamos el primero (orden ID asc).
        if key not in out:
            out[key] = (r, comp, cat)
    return out


def _compute_field_diffs(
    persisted: RaceResult,
    parsed_status: ResultStatus,
    parsed_race_time_ms: Optional[int],
    parsed_laps_behind: Optional[int],
    parsed_position: Optional[int],
    parsed_points: int,
) -> dict[str, dict[str, Any]]:
    """Compara los 5 campos del diff y retorna solo los modificados.

    Estructura: ``{field_name: {"before": ..., "after": ...}}``. Si nada cambió,
    retorna ``{}``.
    """
    diffs: dict[str, dict[str, Any]] = {}
    # position
    if persisted.position != parsed_position:
        diffs["position"] = {
            "before": persisted.position,
            "after": parsed_position,
        }
    # status (enum vs enum)
    persisted_status_val = persisted.status.value if persisted.status else None
    parsed_status_val = parsed_status.value
    if persisted_status_val != parsed_status_val:
        diffs["status"] = {
            "before": persisted_status_val,
            "after": parsed_status_val,
        }
    # race_time_ms
    if persisted.race_time_ms != parsed_race_time_ms:
        diffs["race_time_ms"] = {
            "before": persisted.race_time_ms,
            "after": parsed_race_time_ms,
        }
    # laps_behind: normalizar 0 → None para evitar diff espurios
    persisted_laps = persisted.laps_behind
    parsed_laps = parsed_laps_behind if parsed_laps_behind and parsed_laps_behind > 0 else None
    if persisted_laps != parsed_laps:
        diffs["laps_behind"] = {
            "before": persisted_laps,
            "after": parsed_laps,
        }
    # points_awarded
    if persisted.points_awarded != parsed_points:
        diffs["points_awarded"] = {
            "before": persisted.points_awarded,
            "after": parsed_points,
        }
    return diffs


async def compute_diff(
    db: AsyncSession,
    parsed_results: dict[str, list["ResultsRow"]],
    parent_event_id: int,
) -> DiffReport:
    """Computa el diff completo entre PDF nuevo y RaceResult persistidos.

    Args:
        db: AsyncSession activa.
        parsed_results: output de ``parse_results_pdf``: ``{cat_code: [ResultsRow]}``.
        parent_event_id: id del ``RaceEvent`` ya commiteado (de ``RevisionContext``).

    Returns:
        ``DiffReport`` con summary + rows ordenados (delete → update → create →
        unchanged).
    """
    persisted_index = await _load_persisted_results(db, parent_event_id)

    # Index de categorías por code (para resolver category_id en creates)
    cat_result = await db.execute(select(RaceCategory))
    categories_by_code = {c.code: c for c in cat_result.scalars().all()}

    # Pre-agrupar persisted keys por categoría (para fuzzy fallback intra-cat)
    persisted_keys_by_cat: dict[str, list[str]] = {}
    for (cat_code, norm_name) in persisted_index.keys():
        persisted_keys_by_cat.setdefault(cat_code, []).append(norm_name)

    matched_persisted_keys: set[tuple[str, str]] = set()
    rows_create: list[DiffRow] = []
    rows_update: list[DiffRow] = []
    rows_unchanged: list[DiffRow] = []

    # Iteramos las filas del PDF nuevo
    for cat_code, parsed_rows in parsed_results.items():
        cat_obj = categories_by_code.get(cat_code)
        if cat_obj is None:
            # Categoría desconocida — la dejamos como create skip silencioso
            # (ingest_event lo bloquearía con ValueError; aquí preferimos
            # incluirla en el diff con warning implícito).
            continue
        for parsed in parsed_rows:
            norm_name = normalize_name(parsed.name)
            if not norm_name:
                continue
            key = (cat_code, norm_name)
            fuzzy_used = False

            persisted_entry = persisted_index.get(key)
            if persisted_entry is None:
                # Fallback fuzzy intra-cat
                fuzzy_key = _fuzzy_match_in_category(
                    norm_name, persisted_keys_by_cat.get(cat_code, [])
                )
                if fuzzy_key is not None:
                    fkey = (cat_code, fuzzy_key)
                    if fkey not in matched_persisted_keys:
                        persisted_entry = persisted_index.get(fkey)
                        fuzzy_used = True
                        key = fkey  # tratamos al fuzzy match como match real

            # Parseo defensivo del tiempo del PDF nuevo
            try:
                p_status, p_time_ms, p_laps_behind = parse_time(parsed.time_raw)
            except ValueError:
                # Tiempo no parseable: skip (warning lo emite el ingestor real;
                # acá lo tratamos como unchanged si existe persisted, ó skip).
                if persisted_entry is not None:
                    matched_persisted_keys.add(key)
                    r, comp, cat = persisted_entry
                    rows_unchanged.append(
                        DiffRow(
                            action="unchanged",
                            competitor_normalized_name=norm_name,
                            competitor_display_name=comp.display_name,
                            category_code=cat.code,
                            result_id=r.id,
                            fuzzy_matched=fuzzy_used,
                        )
                    )
                continue

            laps_behind_val = (
                p_laps_behind if p_laps_behind and p_laps_behind > 0 else None
            )

            if persisted_entry is None:
                # CREATE — competitor nuevo en revisión
                rows_create.append(
                    DiffRow(
                        action="create",
                        competitor_normalized_name=norm_name,
                        competitor_display_name=parsed.name.strip(),
                        category_code=cat_code,
                        result_id=None,
                        before=None,
                        after=_parsed_row_snapshot(
                            parsed, p_status, p_time_ms, laps_behind_val, cat_obj.id
                        ),
                        fuzzy_matched=False,
                    )
                )
                continue

            # Match exact o fuzzy — clasificar update vs unchanged
            matched_persisted_keys.add(key)
            r, comp, cat = persisted_entry
            field_diffs = _compute_field_diffs(
                r,
                p_status,
                p_time_ms,
                p_laps_behind,
                parsed.position,
                parsed.points,
            )
            if field_diffs:
                before_snapshot = _serialize_result_snapshot(r)
                after_snapshot = dict(before_snapshot)
                for fname, change in field_diffs.items():
                    after_snapshot[fname] = change["after"]
                rows_update.append(
                    DiffRow(
                        action="update",
                        competitor_normalized_name=norm_name,
                        competitor_display_name=comp.display_name,
                        category_code=cat.code,
                        result_id=r.id,
                        before=before_snapshot,
                        after=after_snapshot,
                        fields_changed=sorted(field_diffs.keys()),
                        fuzzy_matched=fuzzy_used,
                    )
                )
            else:
                rows_unchanged.append(
                    DiffRow(
                        action="unchanged",
                        competitor_normalized_name=norm_name,
                        competitor_display_name=comp.display_name,
                        category_code=cat.code,
                        result_id=r.id,
                        fuzzy_matched=fuzzy_used,
                    )
                )

    # Calcular DELETES: persisted no matched
    rows_delete: list[DiffRow] = []
    for key, (r, comp, cat) in persisted_index.items():
        if key in matched_persisted_keys:
            continue
        rows_delete.append(
            DiffRow(
                action="delete",
                competitor_normalized_name=comp.normalized_name,
                competitor_display_name=comp.display_name,
                category_code=cat.code,
                result_id=r.id,
                before=_serialize_result_snapshot(r),
                after=None,
                fuzzy_matched=False,
            )
        )

    # Orden DTR-5: deletes → updates → creates → unchanged
    ordered_rows = rows_delete + rows_update + rows_create + rows_unchanged
    summary = DiffSummary(
        n_create=len(rows_create),
        n_update=len(rows_update),
        n_delete=len(rows_delete),
        n_unchanged=len(rows_unchanged),
    )
    return DiffReport(summary=summary, rows=ordered_rows)


# ---------------------------------------------------------------------------
# 3. commit_revision
# ---------------------------------------------------------------------------


async def _acquire_event_lock(db: AsyncSession, event_id: int) -> RaceEvent:
    """Adquiere lock pesimista ``SELECT ... FOR UPDATE`` sobre RaceEvent.

    En MySQL usamos NOWAIT (timeout efectivo inmediato si otro tx tiene lock).
    SQLite no soporta FOR UPDATE — el statement compila pero es no-op
    (aceptable en tests; en prod MySQL aplica).

    Si lock falla → propagamos OperationalError (caller convierte a 423 Locked).
    """
    # Detección dialecto: SQLite no soporta FOR UPDATE, evitamos compile error.
    dialect = db.bind.dialect.name if db.bind is not None else "unknown"
    stmt = select(RaceEvent).where(RaceEvent.id == event_id)
    if dialect != "sqlite":
        stmt = stmt.with_for_update(nowait=True)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if event is None:
        raise ValueError(f"RaceEvent id={event_id} no existe (lock failed)")
    return event


async def commit_revision(
    db: AsyncSession,
    parse_import: RaceImport,
    revision_context: RevisionContext,
    diff_report: DiffReport,
    revision_reason: Optional[str],
    changed_by_user_id: int,
) -> CommitRevisionReport:
    """Aplica una revisión transaccional con audit trail completo.

    Args:
        db: AsyncSession activa (caller maneja la transaction outer).
        parse_import: ``RaceImport`` en status ``pending`` (creado por /parse).
        revision_context: contexto de la revisión (del ``detect_revision``).
        diff_report: diff ya computado (del ``compute_diff``). Server reusa para
            consistencia — el cliente NO puede alterar el diff entre dry-run y
            commit (siempre se recomputa server-side antes de llamar a esta fn).
        revision_reason: motivo del coach. Obligatorio si ``n_delete > 0``.
        changed_by_user_id: user id que hace commit (para audit).

    Returns:
        ``CommitRevisionReport`` con counts aplicados.

    Raises:
        ValueError: si ``revision_reason`` requerido pero faltante.
    """
    # Validación app-level (Q4 design): obligatorio si hay deletes
    if diff_report.summary.n_delete > 0 and not revision_reason:
        raise ValueError(
            "revision_reason obligatorio cuando el diff incluye deletes"
        )

    # Lock pesimista sobre RaceEvent (NOWAIT timeout 5s en MySQL)
    event = await _acquire_event_lock(db, revision_context.parent_event_id)

    warnings: list[str] = []
    revisions_created = 0

    # Aplicar cada diff_row
    for row in diff_report.rows:
        if row.action == "create":
            new_result = await _apply_create(
                db, row, event.id, parse_import.id, changed_by_user_id
            )
            if new_result is not None:
                db.add(
                    RaceResultRevision(
                        result_id=new_result.id,
                        action=RaceResultRevisionAction.create,
                        changed_by_user_id=changed_by_user_id,
                        changed_at=datetime.now(timezone.utc),
                        diff_json={"after": row.after or {}},
                        reason=revision_reason,
                    )
                )
                revisions_created += 1

        elif row.action == "update":
            updated = await _apply_update(db, row, changed_by_user_id)
            if updated:
                db.add(
                    RaceResultRevision(
                        result_id=row.result_id,
                        action=RaceResultRevisionAction.update,
                        changed_by_user_id=changed_by_user_id,
                        changed_at=datetime.now(timezone.utc),
                        diff_json={
                            "before": row.before or {},
                            "after": row.after or {},
                            "fields": list(row.fields_changed),
                        },
                        reason=revision_reason,
                    )
                )
                revisions_created += 1

        elif row.action == "delete":
            ok = await _apply_soft_delete(db, row)
            if ok:
                db.add(
                    RaceResultRevision(
                        result_id=row.result_id,
                        action=RaceResultRevisionAction.delete,
                        changed_by_user_id=changed_by_user_id,
                        changed_at=datetime.now(timezone.utc),
                        diff_json={"removed": row.before or {}},
                        reason=revision_reason,
                    )
                )
                revisions_created += 1

        # action=unchanged → skip silencioso (no genera RaceResultRevision)

    # Promover parse_import → committed con linaje
    parse_import.status = RaceImportStatus.committed
    parse_import.parent_import_id = revision_context.parent_import_id
    parse_import.revision_reason = revision_reason
    parse_import.event_id = event.id
    parse_import.stats_json = {
        "is_revision": True,
        "n_create": diff_report.summary.n_create,
        "n_update": diff_report.summary.n_update,
        "n_delete": diff_report.summary.n_delete,
        "n_unchanged": diff_report.summary.n_unchanged,
        "revisions_created": revisions_created,
        # Backward-compat con stats_json del flow F-UP:
        "results_inserted": diff_report.summary.n_create,
    }

    await db.flush()

    # Privacidad: NO loggear texto del reason (solo length)
    logger.info(
        "race_import_revision_commit parse_id=%s parent_import_id=%s event_id=%s "
        "creates=%d updates=%d deletes=%d unchanged=%d revisions=%d reason_len=%d",
        parse_import.id,
        revision_context.parent_import_id,
        event.id,
        diff_report.summary.n_create,
        diff_report.summary.n_update,
        diff_report.summary.n_delete,
        diff_report.summary.n_unchanged,
        revisions_created,
        len(revision_reason) if revision_reason else 0,
    )

    return CommitRevisionReport(
        parse_import_id=parse_import.id,
        parent_import_id=revision_context.parent_import_id,
        event_id=event.id,
        n_create=diff_report.summary.n_create,
        n_update=diff_report.summary.n_update,
        n_delete=diff_report.summary.n_delete,
        n_unchanged=diff_report.summary.n_unchanged,
        revisions_created=revisions_created,
        warnings=warnings,
    )


async def _apply_create(
    db: AsyncSession,
    row: DiffRow,
    event_id: int,
    parse_import_id: int,
    user_id: int,
) -> Optional[RaceResult]:
    """Aplica un create del diff: upsert competitor + insert RaceResult.

    Reusa el patrón del ingestor (upsert por normalized_name + sex_from_code
    fallback). Para revisión simplificamos: si competitor no existe lo creamos
    sin sex (puede actualizarse vía endpoint dedicado en el futuro).
    """
    after = row.after or {}
    category_id = after.get("category_id")
    if category_id is None:
        return None

    # Upsert competitor (reusa la convención del ingestor)
    norm_name = row.competitor_normalized_name
    if not norm_name:
        return None

    comp_result = await db.execute(
        select(RaceCompetitor).where(
            RaceCompetitor.normalized_name == norm_name
        )
    )
    competitor = comp_result.scalar_one_or_none()
    if competitor is None:
        competitor = RaceCompetitor(
            normalized_name=norm_name,
            display_name=row.competitor_display_name,
            club_text=None,
            sex=None,
        )
        db.add(competitor)
        await db.flush()

    # Parsear status enum desde el snapshot serializado (string)
    status_str = after.get("status")
    try:
        status_enum = ResultStatus(status_str) if status_str else ResultStatus.DNF
    except ValueError:
        status_enum = ResultStatus.DNF

    laps_behind_val = after.get("laps_behind")
    if laps_behind_val is not None and laps_behind_val <= 0:
        laps_behind_val = None

    new_result = RaceResult(
        event_id=event_id,
        category_id=category_id,
        competitor_id=competitor.id,
        athlete_id=None,  # athlete linkage F2 — no se asigna en revisión
        bib_number=after.get("bib_number"),
        position=after.get("position"),
        status=status_enum,
        race_time_ms=after.get("race_time_ms"),
        laps_behind=laps_behind_val,
        points_awarded=after.get("points_awarded", 0),
        imported_from_id=parse_import_id,
        created_by_user_id=user_id,
    )
    db.add(new_result)
    await db.flush()
    return new_result


async def _apply_update(
    db: AsyncSession,
    row: DiffRow,
    user_id: int,
) -> bool:
    """Aplica un update del diff a un RaceResult existente.

    Preserva ``athlete_id`` (linkage TyR del coach NO se sobrescribe).
    Returns True si update se aplicó OK.
    """
    if row.result_id is None:
        return False
    result_obj = await db.get(RaceResult, row.result_id)
    if result_obj is None or result_obj.deleted_at is not None:
        return False

    after = row.after or {}
    fields = row.fields_changed or []

    # Aplicar SOLO los campos del diff (no tocar athlete_id, competitor_id, etc.)
    if "position" in fields:
        result_obj.position = after.get("position")
    if "status" in fields:
        status_str = after.get("status")
        try:
            result_obj.status = ResultStatus(status_str) if status_str else result_obj.status
        except ValueError:
            pass
    if "race_time_ms" in fields:
        result_obj.race_time_ms = after.get("race_time_ms")
    if "laps_behind" in fields:
        laps_val = after.get("laps_behind")
        if laps_val is not None and laps_val <= 0:
            laps_val = None
        result_obj.laps_behind = laps_val
    if "points_awarded" in fields:
        result_obj.points_awarded = after.get("points_awarded", 0)

    result_obj.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def _apply_soft_delete(
    db: AsyncSession,
    row: DiffRow,
) -> bool:
    """Aplica soft-delete (``deleted_at = NOW()``) preservando ``status``.

    Política (revision-design.md §4.3): el soft-delete es metadata operacional;
    el status semántico (DSQ/DNF/FINISHED) refleja lo que la fed publicó. Si
    el coach quiere expresar "fue descalificado", lo hace en revision_reason.
    """
    if row.result_id is None:
        return False
    result_obj = await db.get(RaceResult, row.result_id)
    if result_obj is None or result_obj.deleted_at is not None:
        return False
    result_obj.deleted_at = datetime.now(timezone.utc)
    result_obj.updated_at = datetime.now(timezone.utc)
    # NO modificamos status — preserva semántica oficial federación.
    await db.flush()
    return True
