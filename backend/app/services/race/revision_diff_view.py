"""Vista read-only del diff de la última revisión de una válida (PR4).

Construye ``RaceEventDiffResponse`` a partir de las filas ``RaceResultRevision``
persistidas de la última re-ingesta de un ``RaceEvent``. NO recomputa contra
un PDF — es estrictamente de lectura (alimenta ``/competitions/:id/import`` para
mostrar "qué cambió en la última revisión").

Agrupación UI (workflow §5):
- create / delete              → ``added_removed``
- update con ``position``      → ``position``
- update con ``race_time_ms``  → ``time``
- update con ``laps_behind``   → ``gap_gc``
- update con ``category_id``   → ``category_reclassified``

Una fila ``update`` puede tocar varios campos; emitimos un item por (campo,
grupo) relevante para que los conteos por grupo sean precisos.

Privacidad: ``reason`` se expone tal cual (catálogo cerrado desde PR4; puede
haber legacy free-text de revisiones previas — el endpoint lo marca). Los logs
no incluyen el texto del motivo.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_competitor import RaceCompetitor
from app.models.race_result import RaceResult
from app.models.race_result_revision import RaceResultRevision
from app.schemas.race_imports import (
    RaceEventDiffResponse,
    RevisionDiffGroupCounts,
    RevisionDiffItem,
)

logger = logging.getLogger(__name__)

# Mapeo campo cambiado → grupo UI para acciones update.
_FIELD_TO_GROUP: dict[str, str] = {
    "position": "position",
    "race_time_ms": "time",
    "laps_behind": "gap_gc",
    "category_id": "category_reclassified",
}


def _fmt_time(ms: Any) -> str | None:
    """Formatea ms → 'H:MM:SS' o 'MM:SS' para display. None si no aplica."""
    if ms is None:
        return None
    try:
        total = int(ms) // 1000
    except (TypeError, ValueError):
        return None
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _display_value(field: str, raw: Any) -> str | None:
    if raw is None:
        return None
    if field == "race_time_ms":
        return _fmt_time(raw)
    return str(raw)


async def build_event_diff_view(
    db: AsyncSession,
    race_event_id: int,
) -> RaceEventDiffResponse:
    """Construye la vista read-only del diff de la última revisión del evento.

    Estrategia: tomamos el ``changed_at`` máximo de las revisiones cuyos
    ``result_id`` pertenecen a ``race_event_id`` (o cuyo diff_json referencia
    el evento), y devolvemos todas las filas de ese batch (mismo timestamp de
    commit). Esto representa la "última re-ingesta".

    Si no hay revisiones → ``has_revision=False``.
    """
    # 1. Resolver los result_ids del evento (incluye soft-deleted para captar
    #    deletes). Cargamos también competidores para display names.
    res_rows = await db.execute(
        select(RaceResult.id, RaceResult.competitor_id, RaceResult.category_id).where(
            RaceResult.event_id == race_event_id
        )
    )
    result_meta: dict[int, tuple[int | None, int | None]] = {}
    for rid, comp_id, cat_id in res_rows:
        result_meta[int(rid)] = (comp_id, cat_id)

    if not result_meta:
        return RaceEventDiffResponse(
            race_event_id=race_event_id, has_revision=False
        )

    # 2. Revisiones de esos results, más recientes primero.
    rev_rows = await db.execute(
        select(RaceResultRevision)
        .where(RaceResultRevision.result_id.in_(list(result_meta.keys())))
        .order_by(RaceResultRevision.changed_at.desc())
    )
    revisions = list(rev_rows.scalars().all())
    if not revisions:
        return RaceEventDiffResponse(
            race_event_id=race_event_id, has_revision=False
        )

    # 3. Batch de la última revisión: todas las filas con el changed_at máximo.
    latest_at: datetime = revisions[0].changed_at
    batch = [r for r in revisions if r.changed_at == latest_at]
    reason_code = batch[0].reason

    # 4. Cargar display names de los competidores involucrados.
    comp_ids = {
        result_meta[r.result_id][0]
        for r in batch
        if r.result_id is not None and r.result_id in result_meta
    }
    comp_ids.discard(None)
    comp_names: dict[int, str] = {}
    if comp_ids:
        comp_q = await db.execute(
            select(RaceCompetitor.id, RaceCompetitor.display_name).where(
                RaceCompetitor.id.in_(list(comp_ids))
            )
        )
        comp_names = {int(cid): name for cid, name in comp_q}

    items: list[RevisionDiffItem] = []
    counts = RevisionDiffGroupCounts()

    for rev in batch:
        comp_id = (
            result_meta.get(rev.result_id, (None, None))[0]
            if rev.result_id is not None
            else None
        )
        display_name = comp_names.get(comp_id, "—") if comp_id is not None else "—"
        diff_json: dict[str, Any] = rev.diff_json or {}

        action = rev.action.value if hasattr(rev.action, "value") else str(rev.action)

        if action in ("create", "delete"):
            snap = diff_json.get("after") or diff_json.get("removed") or {}
            items.append(
                RevisionDiffItem(
                    action=action,
                    group="added_removed",
                    competitor_display_name=display_name,
                    category_code=None,
                    field_before=None if action == "create" else "—",
                    field_after="—" if action == "create" else None,
                )
            )
            counts.added_removed += 1
            continue

        # update: un item por campo relevante.
        before = diff_json.get("before") or {}
        after = diff_json.get("after") or {}
        fields = diff_json.get("fields") or list(
            {k for k in after.keys()} - {"result_id"}
        )
        emitted = False
        for field in fields:
            group = _FIELD_TO_GROUP.get(field)
            if group is None:
                continue
            items.append(
                RevisionDiffItem(
                    action="update",
                    group=group,
                    competitor_display_name=display_name,
                    category_code=None,
                    field_before=_display_value(field, before.get(field)),
                    field_after=_display_value(field, after.get(field)),
                )
            )
            setattr(counts, group, getattr(counts, group) + 1)
            emitted = True
        # Si el update no tocó campos mapeados (ej. solo points/status), lo
        # contamos como cambio de posición genérico para no perderlo.
        if not emitted:
            items.append(
                RevisionDiffItem(
                    action="update",
                    group="position",
                    competitor_display_name=display_name,
                    category_code=None,
                    field_before=None,
                    field_after=None,
                )
            )
            counts.position += 1

    logger.info(
        "race_event_diff_view event_id=%s revisions_in_batch=%d",
        race_event_id,
        len(batch),
    )

    return RaceEventDiffResponse(
        race_event_id=race_event_id,
        has_revision=True,
        last_revision_at=latest_at,
        reason_code=reason_code,
        counts=counts,
        items=items,
    )


__all__ = ["build_event_diff_view"]
