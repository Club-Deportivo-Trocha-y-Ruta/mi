"""Primitivas de consulta del módulo Race (Fase race-results v2 — F1).

Funciones puras reutilizables que cargan filas crudas desde la DB y construyen
DataFrames JSON-serializables. Sirven a:

- ``analytics.py`` (capa determinista de v1): funciones longitudinales
  (``athlete_progression``, ``podium_gap``, ``club_ranking``, ``projection``)
  que orquestan estas primitivas con pandas.
- ``ai/nodes/`` (capa agéntica de v2): nodos del grafo LangGraph
  (``validate_input``, ``load_race_data``) consumen ``athlete_exists``,
  ``fetch_results_for_athlete`` y ``fetch_podium_context`` para alimentar el
  contexto del ``RaceAnalystAgent``.

Decisiones de diseño:
- Las queries son **planas por tabla** (``select(Model)`` sin joins SQL).
  Los joins se hacen con pandas. Razón: el dataset por temporada es chico
  (cientos de filas) y mantiene el ``FakeAsyncSession`` simple — no
  necesitamos soportar ``IN``, ``IS NULL`` ni joins en el fake.
- Filtros ``deleted_at IS NULL`` se aplican en Python después del select.
- DataFrames devueltos son JSON-serializables (``.to_dict("records")``
  funciona): fechas convertidas a ISO string, ints/floats nativos.

Privacidad (CLAUDE.md):
- ``competitor_id`` y agregados están OK — el coach autenticado ya sabe
  a quién consulta.
- ``fetch_podium_context`` retorna ``competitor_id`` (no nombre); la
  anonimización a pseudónimo se hace en el nodo ``anonymize`` del grafo,
  no aquí.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries


# ---------------------------------------------------------------------------
# Loaders crudos (async)
# ---------------------------------------------------------------------------


async def load_results(db: AsyncSession) -> list[RaceResult]:
    """Carga ``race_results`` no eliminados (filtra ``deleted_at`` en Python).

    Razón del filtrado in-memory: el ``FakeAsyncSession`` no soporta
    ``IS NULL`` en su mini-router. Coste irrelevante por tamaño de dataset.
    """
    res = await db.execute(select(RaceResult))
    rows = list(res.scalars().all())
    return [r for r in rows if getattr(r, "deleted_at", None) is None]


async def load_events(db: AsyncSession) -> list[RaceEvent]:
    res = await db.execute(select(RaceEvent))
    return list(res.scalars().all())


async def load_categories(db: AsyncSession) -> list[RaceCategory]:
    res = await db.execute(select(RaceCategory))
    return list(res.scalars().all())


async def load_competitors(db: AsyncSession) -> list[RaceCompetitor]:
    res = await db.execute(select(RaceCompetitor))
    return list(res.scalars().all())


async def load_series(db: AsyncSession) -> list[RaceSeries]:
    res = await db.execute(select(RaceSeries))
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# DataFrame builders (sync, puros)
# ---------------------------------------------------------------------------


def events_to_df(events: list[RaceEvent]) -> pd.DataFrame:
    """DataFrame de eventos. ``event_date`` se serializa como ISO string."""
    rows = [
        {
            "event_id": e.id,
            "series_id": e.series_id,
            "valida_num": e.sequence_number,
            "event_date": e.event_date.isoformat() if e.event_date else None,
        }
        for e in events
    ]
    return pd.DataFrame(
        rows, columns=["event_id", "series_id", "valida_num", "event_date"]
    )


def categories_to_df(categories: list[RaceCategory]) -> pd.DataFrame:
    rows = [
        {
            "category_id": c.id,
            "category_code": c.code,
            "tier": c.tier.value if c.tier else None,
        }
        for c in categories
    ]
    return pd.DataFrame(rows, columns=["category_id", "category_code", "tier"])


def results_to_df(results: list[RaceResult]) -> pd.DataFrame:
    """DataFrame plano de ``race_results``. ``race_time_ms`` es nullable."""
    rows = [
        {
            "result_id": r.id,
            "event_id": r.event_id,
            "category_id": r.category_id,
            "competitor_id": r.competitor_id,
            "athlete_id": r.athlete_id,
            "position": r.position,
            "race_time_ms": r.race_time_ms,
            "points_awarded": r.points_awarded,
            "status": r.status.value if r.status else None,
        }
        for r in results
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "result_id",
            "event_id",
            "category_id",
            "competitor_id",
            "athlete_id",
            "position",
            "race_time_ms",
            "points_awarded",
            "status",
        ],
    )


# ---------------------------------------------------------------------------
# Primitivas para nodos del grafo agentico (design §6.3 / §9 nodo 1-2)
# ---------------------------------------------------------------------------


async def athlete_exists(db: AsyncSession, athlete_id: int) -> bool:
    """¿El atleta tiene al menos 1 resultado de carrera persistido?

    Usado por el nodo ``validate_input`` del grafo LangGraph antes de gastar
    tokens en el agente: si no hay ningún ``race_result`` con
    ``athlete_id == X`` (match confirmado por el coach), no tiene sentido
    intentar análisis.

    Args:
        db: Sesión async (real o ``FakeAsyncSession``).
        athlete_id: PK del ``Athlete`` (no del ``RaceCompetitor``).

    Returns:
        ``True`` si existe ≥1 ``RaceResult`` no eliminado con ese
        ``athlete_id``. ``False`` en cualquier otro caso.
    """
    results = await load_results(db)
    return any(r.athlete_id == athlete_id for r in results)


async def fetch_results_for_athlete(
    db: AsyncSession,
    athlete_id: int,
    season: int,
    valida_nums: Optional[list[int]] = None,
) -> list[RaceResult]:
    """Resultados de un atleta TyR en una temporada (opcionalmente filtrados).

    Filtra:
    - ``RaceResult.athlete_id == athlete_id`` (matches confirmados, NULL no).
    - ``RaceResult.deleted_at IS NULL``.
    - ``event.series.season_year == season``.
    - Si ``valida_nums`` se provee: ``event.sequence_number IN valida_nums``.

    Orden: ascendente por ``event.event_date`` (cronológico).

    Args:
        db: Sesión async.
        athlete_id: PK ``Athlete``.
        season: año de temporada (vía ``RaceSeries.season_year``).
        valida_nums: lista opcional de números de válida (1, 2, 3, ...).

    Returns:
        Lista de ``RaceResult`` ya filtrada y ordenada. Vacía si no hay match.
    """
    results = await load_results(db)
    events = await load_events(db)
    series = await load_series(db)

    series_ids_in_season = {s.id for s in series if s.season_year == season}
    events_in_season_by_id = {
        e.id: e for e in events if e.series_id in series_ids_in_season
    }
    if valida_nums is not None:
        valida_set = set(valida_nums)
        events_in_season_by_id = {
            eid: e
            for eid, e in events_in_season_by_id.items()
            if e.sequence_number in valida_set
        }

    if not events_in_season_by_id:
        return []

    filtered = [
        r
        for r in results
        if r.athlete_id == athlete_id and r.event_id in events_in_season_by_id
    ]

    # Orden cronológico por event_date (None va al final).
    def _sort_key(r: RaceResult) -> tuple[int, Any]:
        ev = events_in_season_by_id.get(r.event_id)
        d = ev.event_date if ev else None
        return (0, d) if d is not None else (1, 0)

    filtered.sort(key=_sort_key)
    return filtered


async def fetch_podium_context(
    db: AsyncSession, category_id: int, event_id: int
) -> dict[str, Any]:
    """Tiempos de podio (P1, P2, P3) en una válida + categoría.

    Usado por el nodo ``load_race_data`` para alimentar al agente con el
    contexto competitivo: cuán cerca/lejos quedó del podio. No retorna
    nombres — sólo ``competitor_id`` y tiempos. La anonimización (pseudónimo
    estable) se aplica en el nodo ``anonymize`` del grafo.

    Args:
        db: Sesión async.
        category_id: PK ``RaceCategory``.
        event_id: PK ``RaceEvent``.

    Returns:
        ``dict`` JSON-serializable:

        ```
        {
            'category_id': int,
            'event_id': int,
            'podium': [
                {'position': 1, 'competitor_id': int, 'race_time_ms': int | None},
                {'position': 2, ...},
                {'position': 3, ...},
            ],
            'finishers_count': int,  # total FINISHED en (cat, event)
        }
        ```

        Si no hay finishers, ``podium=[]`` y ``finishers_count=0``.
    """
    results = await load_results(db)

    in_scope = [
        r
        for r in results
        if r.category_id == category_id
        and r.event_id == event_id
        and r.status == ResultStatus.FINISHED
    ]

    podium_rows: list[dict[str, Any]] = []
    for pos in (1, 2, 3):
        cand = [r for r in in_scope if r.position == pos]
        if not cand:
            continue
        # Defensivo: si hay >1 con la misma posición (no debería), tomamos
        # el de menor race_time_ms — ints o None tratados consistentemente.
        cand.sort(key=lambda r: r.race_time_ms if r.race_time_ms is not None else 10**12)
        winner = cand[0]
        podium_rows.append(
            {
                "position": pos,
                "competitor_id": winner.competitor_id,
                "race_time_ms": winner.race_time_ms,
            }
        )

    return {
        "category_id": category_id,
        "event_id": event_id,
        "podium": podium_rows,
        "finishers_count": len(in_scope),
    }
