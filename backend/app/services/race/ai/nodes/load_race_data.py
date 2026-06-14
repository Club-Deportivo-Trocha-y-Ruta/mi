"""Nodo 2: ``load_race_data`` — carga raw data del atleta + contexto podio.

Llama a :func:`queries.fetch_results_for_athlete` para traer los results
filtrados por ``valida_nums`` (set lanzado) y por separado los de la
temporada hasta la última válida lanzada cronológicamente, para calcular
``season_validas_count`` e ``is_first_in_season``.

La regla N=1 se aplica cuando el contexto cronológico recortado tiene
exactamente 1 válida disputada. Esto incluye:
- Atleta con 1 sola válida en toda la temporada.
- Coach lanza solo la primera válida cronológica (aunque existan más
  posteriores): el "Recorrido hasta aquí" se acota a esa válida y se
  trata como N=1 (no se inventa tendencia con datos futuros).

Si el coach no especifica ``valida_nums`` (lanzamiento global), se carga
la temporada completa sin recorte.

Si no hay resultados → no es error fatal (validate_input ya verificó
``athlete_exists``), pero el state queda con ``raw_data=[]`` y nodos
downstream lo gestionan.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.queries import (
    fetch_all_results_for_season,
    fetch_event_conditions,
    fetch_podium_context,
    fetch_results_for_athlete,
    load_events,
    load_series,
)

NODE_NAME = "load_race_data"

logger = logging.getLogger(__name__)

# Statuses que NO aportan participación real (se excluyen del conteo N=1).
_NON_FINISH_STATUSES = {"dns", "dnf", "dsq"}


def _serialize_result(r: Any) -> dict[str, Any]:
    """Convierte un RaceResult ORM a dict JSON-serializable."""
    row: dict[str, Any] = {
        "result_id": getattr(r, "id", None),
        "event_id": getattr(r, "event_id", None),
        "category_id": getattr(r, "category_id", None),
        "competitor_id": getattr(r, "competitor_id", None),
        "athlete_id": getattr(r, "athlete_id", None),
        "position": getattr(r, "position", None),
        "race_time_ms": getattr(r, "race_time_ms", None),
        "points_awarded": getattr(r, "points_awarded", None),
        "status": getattr(r.status, "value", None) if getattr(r, "status", None) else None,
    }
    # T019 — include raw coach note (scrubbing happens later in anonymize).
    # Key is only present when the note is not None so that downstream code
    # can detect absence with a simple `.get("coach_note")` check.
    note = getattr(r, "coach_note", None)
    if note is not None:
        row["coach_note"] = note
    return row


def _build_winner_map(all_results: list[Any]) -> dict[int, int | None]:
    """Devuelve un dict {event_id: winner_race_time_ms} para el set de resultados.

    El ganador es el resultado con position=1 en cada event_id. Si no hay
    ninguno, el valor es None.
    """
    winner_map: dict[int, int | None] = {}
    for r in all_results:
        event_id = getattr(r, "event_id", None)
        position = getattr(r, "position", None)
        race_time_ms = getattr(r, "race_time_ms", None)
        if event_id is None:
            continue
        if position == 1 and race_time_ms is not None:
            # Prefer the first P1 found (idempotent si hay duplicados).
            if event_id not in winner_map:
                winner_map[event_id] = race_time_ms
        elif event_id not in winner_map:
            winner_map[event_id] = None
    return winner_map


def _compacted_season_record(
    r: Any,
    winner_time_ms: int | None,
) -> dict[str, Any]:
    """Versión compacta de un resultado para full_season_results.

    Calcula ``gap_to_winner_ms`` y ``gap_pct`` reales a partir del tiempo
    del ganador (position=1) en el mismo event_id.
    """
    race_time_ms: int | None = getattr(r, "race_time_ms", None)
    gap_to_winner_ms: int | None = None
    gap_pct: float | None = None

    if race_time_ms is not None and winner_time_ms is not None and winner_time_ms > 0:
        gap_to_winner_ms = race_time_ms - winner_time_ms
        gap_pct = round(gap_to_winner_ms / winner_time_ms * 100.0, 2)

    return {
        "result_id": getattr(r, "id", None),
        "event_id": getattr(r, "event_id", None),
        "valida_num": getattr(r, "sequence_number", None),
        "position": getattr(r, "position", None),
        "race_time_ms": race_time_ms,
        "gap_to_winner_ms": gap_to_winner_ms,
        "gap_pct": gap_pct,
        "status": getattr(r.status, "value", None) if getattr(r, "status", None) else None,
    }


async def _resolve_max_launched_date(
    db: Any, season: int, valida_nums: list[int] | None
) -> Any:
    """Devuelve la fecha del evento más tardío entre los ``valida_nums`` lanzados.

    Resuelve por ``sequence_number`` dentro de la temporada solicitada (vía
    ``RaceSeries.season_year``). Si ningún evento coincide o ninguno tiene
    fecha → ``None`` (el caller no aplica recorte).
    """
    if not valida_nums:
        return None
    series_in_season = {
        s.id for s in await load_series(db) if s.season_year == season
    }
    valida_set = set(valida_nums)
    candidate_dates = [
        e.event_date
        for e in await load_events(db)
        if e.series_id in series_in_season
        and e.sequence_number in valida_set
        and e.event_date is not None
    ]
    return max(candidate_dates) if candidate_dates else None


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def load_race_data(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]
    season = state["season"]
    valida_nums = state.get("valida_nums")

    async with get_session() as db:
        # ---- Set filtrado (para el análisis concreto) ----
        results = await fetch_results_for_athlete(db, athlete_id, season, valida_nums)
        serialized = [_serialize_result(r) for r in results]

        # ---- Temporada completa (base) ----
        full_season_raw = await fetch_results_for_athlete(
            db, athlete_id, season, valida_nums=None
        )

        # ---- Recorte cronológico al lanzamiento del coach ----
        # Si el coach lanzó válidas específicas, el contexto "Recorrido hasta
        # aquí" se acota a las válidas con fecha ≤ última lanzada. Así N=1
        # aplica cuando solo se lanza la primera cronológica y los datos de
        # válidas futuras no contaminan el análisis retrospectivo solicitado.
        if valida_nums:
            max_launched_date = await _resolve_max_launched_date(
                db, season, valida_nums
            )
            if max_launched_date is not None:
                events_all = await load_events(db)
                event_date_by_id = {e.id: e.event_date for e in events_all}
                full_season_raw = [
                    r
                    for r in full_season_raw
                    if (d := event_date_by_id.get(getattr(r, "event_id", None)))
                    is not None
                    and d <= max_launched_date
                ]

        # Construir mapa de tiempos de ganador por event_id.
        # Para calcular el gap real necesitamos el P1 de cada evento en la
        # misma categoría. Cargamos todos los resultados de la temporada para
        # la categoría del atleta (si está disponible).
        category_id_for_season: int | None = None
        if full_season_raw:
            category_id_for_season = getattr(full_season_raw[0], "category_id", None)

        winner_map: dict[int, int | None] = {}
        if category_id_for_season is not None:
            try:
                all_cat_results = await fetch_all_results_for_season(
                    db, category_id_for_season, season
                )
                winner_map = _build_winner_map(all_cat_results)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "load_race_data: no se pudo cargar resultados de categoría "
                    "para calcular gap_to_winner_ms; los gaps quedarán None.",
                    exc_info=True,
                )

        # Contar válidas distintas con participación real (excluir DNS/DNF/DSQ).
        seen_validas: set[int | None] = set()
        full_season_records: list[dict[str, Any]] = []
        for r in full_season_raw:
            status_str = (
                r.status.value.lower() if getattr(r, "status", None) else None
            )
            if status_str in _NON_FINISH_STATUSES:
                continue
            event_id_val = getattr(r, "event_id", None)
            seen_validas.add(event_id_val)  # distinct por event (proxy de valida)
            winner_time = winner_map.get(event_id_val) if event_id_val is not None else None
            if winner_time is None and event_id_val is not None:
                logger.warning(
                    "load_race_data: sin ganador (position=1) para event_id=%s; "
                    "gap_to_winner_ms quedará None para ese resultado.",
                    event_id_val,
                )
            full_season_records.append(_compacted_season_record(r, winner_time))

        season_validas_count = len(seen_validas)
        is_first_in_season: bool = season_validas_count <= 1

        # ---- Condiciones registradas por válida (feature 011) ----
        # Una entrada por cada válida lanzada (o, en lanzamiento global, por
        # cada válida en que el atleta participó). Eventos sin condiciones
        # registradas producen una entrada con los cinco campos en None.
        if valida_nums:
            condition_validas = list(valida_nums)
        else:
            events_by_id = {e.id: e for e in await load_events(db)}
            condition_validas = sorted(
                {
                    int(seq)
                    for r in serialized
                    if (ev := events_by_id.get(r.get("event_id"))) is not None
                    and (seq := getattr(ev, "sequence_number", None)) is not None
                }
            )
        event_conditions = await fetch_event_conditions(
            db, season, condition_validas
        )

        # T019/T021 — build {valida_num: raw_coach_note} from the serialized
        # rows so that anonymize can scrub and analyst_agent can inject.
        # Requires the event_id → valida_num mapping from the events table.
        # events_by_id may already be built above (global launch path); rebuild
        # only when needed (valida_nums path) — cheap since load_events is cached.
        _events_by_id: dict[int, Any] = {e.id: e for e in await load_events(db)}
        coach_notes_by_valida: dict[int, str | None] = {}
        for row in serialized:
            note = row.get("coach_note")
            raw_event_id = row.get("event_id")
            ev = _events_by_id.get(int(raw_event_id)) if raw_event_id is not None else None
            seq = getattr(ev, "sequence_number", None) if ev is not None else None
            if seq is not None:
                # Last writer wins for multi-result edge cases; notes are per-event.
                if note is not None or seq not in coach_notes_by_valida:
                    coach_notes_by_valida[int(seq)] = note

        if not serialized:
            return {
                "raw_data": [],
                "competitor_id": None,
                "category_id": None,
                "podium_context": {},
                "event_conditions": event_conditions,
                "coach_notes_by_valida": coach_notes_by_valida,
                "full_season_results": full_season_records,
                "season_validas_count": season_validas_count,
                "is_first_in_season": is_first_in_season,
            }

        first = serialized[0]
        competitor_id = first.get("competitor_id")
        category_id = first.get("category_id")

        # Evento foco: el último cronológico (results ya viene ordenado asc).
        focus_event_id = serialized[-1].get("event_id")
        podium_ctx: dict[str, Any] = {}
        if focus_event_id is not None and category_id is not None:
            podium_ctx = await fetch_podium_context(db, category_id, focus_event_id)

    return {
        "raw_data": serialized,
        "competitor_id": competitor_id,
        "category_id": category_id,
        "podium_context": podium_ctx,
        "event_conditions": event_conditions,
        "coach_notes_by_valida": coach_notes_by_valida,
        "full_season_results": full_season_records,
        "season_validas_count": season_validas_count,
        "is_first_in_season": is_first_in_season,
    }


__all__ = ["load_race_data", "NODE_NAME"]
