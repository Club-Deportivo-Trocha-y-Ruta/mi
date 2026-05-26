"""Nodo 10: ``persist_insight`` — escribe la fila en ``athlete_ai_insights``.

Refactor BE-2
=============
El nodo ahora usa el modelo ORM ``AthleteAiInsight`` (introducido en BE-1)
en vez de SQL crudo. Esto:

1. Centraliza la lógica de versionado en :mod:`app.services.race.insights_history`
   (función :func:`deprecate_previous_active`).
2. Garantiza que el campo ``is_active`` se asigne correctamente al
   sentinel ``1`` (sólo cuando ``coach_approved=True``).
3. Mantiene la cadena ``superseded_by_insight_id`` consistente: se hace
   un UPDATE post-flush sobre la fila previa con la nueva PK.

Convenciones
============
- ``coach_approved=True`` ⇒ deprecar fila previa de la misma terna y
  ``is_active=1`` para la nueva.
- ``coach_approved=False`` (HITL rejected / draft pending) ⇒ insertar con
  ``is_active=NULL`` y no tocar previos.
- ``valida_num=None`` para use_cases agregados se mapea a ``0`` antes de
  persistir (CHECK relax permite ``>=0``).

Fix BUG-001 (fan-out por válida)
================================
El grafo recibe ``valida_nums: list[int]`` en el initial state (el coach
selecciona una o varias válidas a analizar). El análisis textual es uno
solo — analiza el conjunto — pero el insight debe persistirse **una vez
por cada válida** seleccionada, para que el Comparador (que indexa por
``valida_num`` específico) pueda encontrarlo.

Reglas de derivación del/los ``valida_num`` a persistir:

1. Si ``state["valida_num"]`` (singular) está seteado → usar ese.
   Este es el contrato histórico que usan los tests unitarios y
   futuros use cases agregados.
2. Else si ``state["valida_nums"]`` (plural) trae una lista no vacía →
   fan-out: una fila por cada válida en la lista, todas con el mismo
   ``summary_text`` y mismo ``draft_analysis``. El versionado/deprecation
   se aplica por (athlete, season, valida_num) — independiente por
   válida.
3. Else → sentinel ``0`` (use_cases agregados sin válida específica).

Si la persistencia falla, registramos el error en ``state.errors`` pero
no rompemos el grafo — ``notify_coach`` aún tiene valor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.athlete_ai_insight import AthleteAiInsight, InsightConfidence
from app.models.race_result import ResultStatus
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.insights_history import deprecate_previous_active
from app.services.race.queries import load_events, load_results, load_series

logger = logging.getLogger(__name__)

NODE_NAME = "persist_insight"

_USE_CASE = "race_progression"
_SUMMARY_MAX_CHARS = 5000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serializable(obj: Any) -> Any:
    """Convierte recursivamente Pydantic/dataclass/enum a dict/list JSON-safe."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    return obj


async def _compute_category_stats(
    db: Any, season: int, category_id: Optional[int]
) -> dict[int, dict[str, Optional[int]]]:
    """Devuelve estadísticas por válida para el percentil de categoría.

    Formato: ``{valida_num: {"size": int, "time_min_ms": int|None,
    "time_max_ms": int|None}}``.

    Override coach real (2026-05-25): el club usa percentil por TIEMPO
    en vez de por posición, asumiendo el trade-off biológico documentado
    en CLAUDE.md (sección "Edad biológica > cronológica"). El coach
    interpreta la métrica con ese contexto.

    Solo considera ``status='finished'`` con ``race_time_ms`` no-null.
    """
    if category_id is None:
        return {}
    results = await load_results(db)
    events = await load_events(db)
    series_list = await load_series(db)
    series_ids = {s.id for s in series_list if s.season_year == season}
    events_in_season = {
        e.id: e for e in events if e.series_id in series_ids
    }
    stats: dict[int, dict[str, Optional[int]]] = {}
    for event_id, event in events_in_season.items():
        if not event.sequence_number:
            continue
        finished_times = [
            r.race_time_ms
            for r in results
            if r.event_id == event_id
            and r.category_id == category_id
            and r.status == ResultStatus.FINISHED
            and r.race_time_ms is not None
        ]
        if not finished_times:
            continue
        stats[int(event.sequence_number)] = {
            "size": len(finished_times),
            "time_min_ms": int(min(finished_times)),
            "time_max_ms": int(max(finished_times)),
        }
    return stats


def _resolve_valida_nums_to_persist(state: dict, use_case: str) -> list[int]:
    """Determina la lista de ``valida_num`` a persistir.

    Reglas (ver módulo docstring, fix BUG-001):

    1. ``state["valida_num"]`` (singular) seteado → ``[valida_num]``.
       Contrato histórico usado por tests unitarios y use cases puntuales.
    2. Else si ``state["valida_nums"]`` (plural) trae lista no vacía →
       fan-out: la lista íntegra (dedup + filtro de valores válidos).
       Cada elemento se persiste como una fila independiente.
    3. Else → ``[0]`` (sentinel para use cases agregados sin válida
       específica — season_summary, projection, etc.).
    """
    raw_singular = state.get("valida_num")
    if raw_singular is not None:
        try:
            return [int(raw_singular)]
        except (TypeError, ValueError):
            pass

    raw_plural = state.get("valida_nums")
    if raw_plural:
        cleaned: list[int] = []
        seen: set[int] = set()
        for v in raw_plural:
            try:
                vi = int(v)
            except (TypeError, ValueError):
                continue
            if vi < 0:
                continue
            if vi in seen:
                continue
            seen.add(vi)
            cleaned.append(vi)
        if cleaned:
            return cleaned

    # Sentinel para agregados.
    return [0]


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def persist_insight(state: dict) -> dict[str, Any]:
    draft = state.get("draft_analysis")
    per_valida_drafts: dict[int, Any] | None = state.get("per_valida_drafts")

    # Sin ningún análisis disponible → no persistir.
    if draft is None and not per_valida_drafts:
        return {}

    decision = (state.get("hitl_decision") or {}).get("decision", "auto-approve")
    approved = decision in {"approve", "auto-approve"}
    archived = decision == "reject"

    athlete_id = state["athlete_id"]
    season = state["season"]
    coach_id = state.get("coach_id") or 0
    competitor_id = state.get("competitor_id")
    event_id = state.get("event_id")
    use_case = state.get("use_case") or _USE_CASE

    # v2: si per_valida_drafts existe, usamos su mapping {valida_num: draft}
    # para que cada fila tenga summary_text DISTINTO (spec §Output).
    # v1: fan-out con el mismo summary_text para todas las válidas en la lista.
    is_v2 = bool(per_valida_drafts)

    if is_v2:
        # Construir lista de pares (valida_num, summary_text) desde los drafts v2.
        v2_pairs: list[tuple[int, str, Any, Any]] = []
        for vn, vn_draft in (per_valida_drafts or {}).items():
            vn_raw_md = getattr(vn_draft, "raw_markdown", None) or ""
            vn_summary = vn_raw_md[:_SUMMARY_MAX_CHARS]
            vn_recs = _serializable(getattr(vn_draft, "recommendations", None) or [])
            v2_pairs.append((int(vn), vn_summary, vn_recs, vn_draft))
        valida_nums_db = [p[0] for p in v2_pairs]
    else:
        # Flujo v1: derivar la lista de válidas a persistir (BUG-001).
        valida_nums_db = _resolve_valida_nums_to_persist(state, use_case)
        v2_pairs = []

    persisted_insight_ids: list[int] = []

    aggregate = state.get("aggregate_metrics") or {}

    # Valores base para v1 (compartidos por todas las válidas en v1).
    base_draft = draft or (list(per_valida_drafts.values())[0] if per_valida_drafts else None)
    base_recommendations = _serializable(getattr(base_draft, "recommendations", None) or [])
    risks = _serializable(getattr(base_draft, "risk_flags", None) or [])
    principles = _serializable(state.get("principles") or [])

    base_raw_md = (
        getattr(state.get("final_analysis"), "raw_markdown", None)
        or getattr(base_draft, "raw_markdown", None)
        or ""
    )
    base_summary_text = base_raw_md[:_SUMMARY_MAX_CHARS]
    prompt_version = aggregate.get("prompt_version_analyst", "race_analyst_v1")

    metrics_snapshot: dict[str, Any] = {
        "progression": state.get("metrics", {}).get("progression", []),
        "podium_gap": state.get("metrics", {}).get("podium_gap", []),
        "podium_context": state.get("podium_context", {}),
        "aggregate": aggregate,
        "risks": risks,
        "category_stats": {},
    }

    confidence_value = state.get("confidence") or InsightConfidence.medium
    if isinstance(confidence_value, str):
        try:
            confidence_enum = InsightConfidence(confidence_value)
        except ValueError:
            confidence_enum = InsightConfidence.medium
    else:
        confidence_enum = confidence_value

    now = _now()

    try:
        async with get_session() as db:
            from sqlalchemy import update as sa_update

            try:
                category_id = state.get("category_id")
                metrics_snapshot["category_stats"] = (
                    await _compute_category_stats(db, season, category_id)
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "compute_category_stats failed; snapshot stays without stats",
                    exc_info=True,
                )

            if is_v2:
                # v2: una fila por válida con summary_text DISTINTO.
                for vn_num, vn_summary, vn_recs, _vn_draft in v2_pairs:
                    previous_id: Optional[int] = None
                    is_active_value: Optional[int] = None

                    if approved:
                        previous_id = await deprecate_previous_active(
                            db,
                            athlete_id=athlete_id,
                            season=season,
                            valida_num=vn_num,
                            new_insight_id=None,
                        )
                        is_active_value = 1

                    new_row = AthleteAiInsight(
                        athlete_id=athlete_id,
                        competitor_id=competitor_id,
                        event_id=event_id,
                        agent_run_id=state.get("agent_run_id"),
                        generated_by_user_id=coach_id,
                        season=season,
                        valida_num=vn_num,
                        use_case=use_case,
                        summary_text=vn_summary,  # DISTINTO por válida (v2)
                        recommendations_json=vn_recs,
                        metrics_snapshot_json=metrics_snapshot,
                        principles_cited_json=principles,
                        confidence=confidence_enum,
                        model="gemini-2.5-flash-lite",
                        prompt_version=prompt_version,
                        coach_approved=approved,
                        coach_edits_count=0,
                        generated_at=now,
                        approved_at=now if approved else None,
                        archived_at=now if archived else None,
                        deprecated_at=None,
                        is_active=is_active_value,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(new_row)
                    await db.flush()
                    # `new_row.id` puede ser None en tests con FakeSession (no
                    # autoassign de PK). En prod siempre es int post-flush.
                    if new_row.id is not None:
                        persisted_insight_ids.append(int(new_row.id))

                    if approved and previous_id is not None:
                        await db.execute(
                            sa_update(AthleteAiInsight)
                            .where(AthleteAiInsight.id == previous_id)
                            .values(
                                superseded_by_insight_id=new_row.id,
                                updated_at=now,
                            )
                        )
            else:
                # v1: fan-out con el mismo summary_text para todas las válidas.
                for valida_num_db in valida_nums_db:
                    previous_id = None
                    is_active_value = None

                    if approved:
                        previous_id = await deprecate_previous_active(
                            db,
                            athlete_id=athlete_id,
                            season=season,
                            valida_num=valida_num_db,
                            new_insight_id=None,
                        )
                        is_active_value = 1

                    new_row = AthleteAiInsight(
                        athlete_id=athlete_id,
                        competitor_id=competitor_id,
                        event_id=event_id,
                        agent_run_id=state.get("agent_run_id"),
                        generated_by_user_id=coach_id,
                        season=season,
                        valida_num=valida_num_db,
                        use_case=use_case,
                        summary_text=base_summary_text,
                        recommendations_json=base_recommendations,
                        metrics_snapshot_json=metrics_snapshot,
                        principles_cited_json=principles,
                        confidence=confidence_enum,
                        model="gemini-2.5-flash-lite",
                        prompt_version=prompt_version,
                        coach_approved=approved,
                        coach_edits_count=0,
                        generated_at=now,
                        approved_at=now if approved else None,
                        archived_at=now if archived else None,
                        deprecated_at=None,
                        is_active=is_active_value,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(new_row)
                    await db.flush()
                    # `new_row.id` puede ser None en tests con FakeSession (no
                    # autoassign de PK). En prod siempre es int post-flush.
                    if new_row.id is not None:
                        persisted_insight_ids.append(int(new_row.id))

                    if approved and previous_id is not None:
                        await db.execute(
                            sa_update(AthleteAiInsight)
                            .where(AthleteAiInsight.id == previous_id)
                            .values(
                                superseded_by_insight_id=new_row.id,
                                updated_at=now,
                            )
                        )

            await db.commit()

    except Exception as exc:  # noqa: BLE001
        logger.error("persist_insight: insert falló: %s", type(exc).__name__)
        return {
            "errors": list(state.get("errors") or [])
            + [
                {
                    "node": NODE_NAME,
                    "error": type(exc).__name__,
                    "message": str(exc)[:200],
                }
            ]
        }

    return {
        "persisted_insight_ids": persisted_insight_ids,
        "insight_approved": approved,
    }


__all__ = ["persist_insight", "NODE_NAME", "_resolve_valida_nums_to_persist"]
