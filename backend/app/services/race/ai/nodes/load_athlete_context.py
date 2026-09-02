"""Nodo (feature 037, T103): ``load_athlete_context`` — antropometría,
ventana de entrenamiento y catálogo del club, previos a ``anonymize``.

Se registra entre ``load_race_data`` y ``anonymize`` en el grafo. Resuelve la
fecha de referencia (evento anclado, o última válida del set, o hoy para
``analysis_kind="season"``), calcula el rango ``[date_from, date_to]`` y
delega en los loaders puros de :mod:`app.services.race.ai.athlete_context`.

Best-effort por diseño (FR data-model.md §037 T103): cualquier loader que
falle deja su clave en ``None``/valor vacío y agrega una entrada a
``state["errors"]`` — el run NUNCA se interrumpe por esta carga
complementaria.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.models.athlete import Athlete
from app.services.race.ai.athlete_context import (
    age_band_from_age,
    load_anthro_context,
    load_catalog_context,
    load_club_forbidden_names,
    load_training_window,
)
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.queries import load_events

NODE_NAME = "load_athlete_context"

logger = logging.getLogger(__name__)

_DEFAULT_TRAINING_WINDOW_DAYS = 28

_EMPTY_CATALOG: dict[str, list] = {
    "technique_skills": [],
    "strength_blocks": [],
    "interval_templates": [],
}


def _resolve_window_days() -> int:
    """Lee ``settings.race_ai_training_window_days`` si existe (T101).

    Best-effort: T101 (fixes + config) es una tarea paralela que puede o no
    haber añadido el campo aún al mergear. Sin él, cae al default (28 días)
    documentado en plan.md §Modules.
    """
    try:
        from app.config import settings

        return int(getattr(settings, "race_ai_training_window_days", _DEFAULT_TRAINING_WINDOW_DAYS))
    except Exception:  # noqa: BLE001
        return _DEFAULT_TRAINING_WINDOW_DAYS


async def _resolve_reference_date(db: Any, state: dict) -> date:
    """Fecha de corte para antropometría/ventana de entrenamiento.

    - ``analysis_kind == "season"`` → hoy (la ventana es toda la temporada).
    - Evento anclado (``event_id``) → su ``event_date``.
    - Sin ancla → fecha del último resultado cronológico del set
      (``full_season_results``, ya recortado por ``load_race_data``).
    - Sin ninguna referencia disponible → hoy (no bloquea el run).
    """
    if state.get("analysis_kind") == "season":
        return date.today()

    event_id = state.get("event_id")
    events = await load_events(db)

    if event_id is not None:
        anchored = next((e for e in events if e.id == event_id), None)
        if anchored is not None and anchored.event_date is not None:
            return anchored.event_date

    full_season = state.get("full_season_results") or []
    event_date_by_id = {e.id: e.event_date for e in events}
    candidate_dates = [
        d
        for r in full_season
        if (d := event_date_by_id.get(r.get("event_id"))) is not None
    ]
    if candidate_dates:
        return max(candidate_dates)

    return date.today()


async def _resolve_club_id(db: Any, athlete_id: int) -> int | None:
    result = await db.execute(select(Athlete.club_id).where(Athlete.id == athlete_id))
    return result.scalar_one_or_none()


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def load_athlete_context(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]
    season = state.get("season")
    athlete_age = state.get("athlete_age")

    update: dict[str, Any] = {
        "anthro_context": None,
        "training_window": None,
        "catalog_context": dict(_EMPTY_CATALOG),
        "club_forbidden_names": [],
    }
    errors: list[dict[str, Any]] = []

    async with get_session() as db:
        reference_date = await _resolve_reference_date(db, state)
        club_id = await _resolve_club_id(db, athlete_id)

        if state.get("analysis_kind") == "season":
            date_from = date(season, 1, 1) if season else reference_date.replace(month=1, day=1)
            date_to = reference_date
        else:
            date_to = reference_date
            date_from = reference_date - timedelta(days=_resolve_window_days())

        try:
            update["anthro_context"] = await load_anthro_context(db, athlete_id, reference_date)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "load_athlete_context: anthro_context falló para atleta %d: %s",
                athlete_id,
                type(exc).__name__,
                exc_info=True,
            )
            errors.append(
                {
                    "node": NODE_NAME,
                    "field": "anthro_context",
                    "error": type(exc).__name__,
                    "message": str(exc)[:200],
                }
            )

        if club_id is not None:
            try:
                update["training_window"] = await load_training_window(
                    db, athlete_id, club_id, date_from, date_to
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "load_athlete_context: training_window falló para atleta %d: %s",
                    athlete_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                errors.append(
                    {
                        "node": NODE_NAME,
                        "field": "training_window",
                        "error": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                )

            try:
                age_band = (
                    age_band_from_age(float(athlete_age)) if athlete_age is not None else None
                )
                update["catalog_context"] = await load_catalog_context(db, club_id, age_band)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "load_athlete_context: catalog_context falló para club %s: %s",
                    club_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                errors.append(
                    {
                        "node": NODE_NAME,
                        "field": "catalog_context",
                        "error": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                )

            try:
                update["club_forbidden_names"] = await load_club_forbidden_names(db, club_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "load_athlete_context: club_forbidden_names falló para club %s: %s",
                    club_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                errors.append(
                    {
                        "node": NODE_NAME,
                        "field": "club_forbidden_names",
                        "error": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                )
        else:
            errors.append(
                {
                    "node": NODE_NAME,
                    "field": "club_id",
                    "error": "AthleteNotFound",
                    "message": f"sin club_id para atleta {athlete_id}",
                }
            )

    if errors:
        update["errors"] = list(state.get("errors") or []) + errors

    return update


__all__ = ["load_athlete_context", "NODE_NAME"]
