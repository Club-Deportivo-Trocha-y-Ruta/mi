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
from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_course_variant import RaceCourseVariant
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
            "location": e.location,
        }
        for e in events
    ]
    return pd.DataFrame(
        rows,
        columns=["event_id", "series_id", "valida_num", "event_date", "location"],
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


def _scoped_events(
    events: list[RaceEvent],
    series: list[RaceSeries],
    *,
    season: int,
    series_id: int | None,
) -> dict[int, RaceEvent]:
    """``{event_id: RaceEvent}`` acotado a una serie o a toda una temporada.

    Compartido por ``fetch_results_for_athlete``, ``fetch_event_conditions``
    y ``fetch_course_context`` para no duplicar la lógica de resolución
    (y evitar que las tres variantes diverjan).

    Cuando ``series_id`` se provee, se ignora ``season`` — la serie ya
    determina la temporada — y solo se consideran sus eventos (esto es lo
    que desambigua ``sequence_number`` cuando dos copas de la misma
    temporada comparten número de válida). Con ``series_id=None`` se
    conserva el filtrado por temporada completa (comportamiento histórico).
    """
    if series_id is not None:
        return {e.id: e for e in events if e.series_id == series_id}
    series_ids_in_season = {s.id for s in series if s.season_year == season}
    return {e.id: e for e in events if e.series_id in series_ids_in_season}


def _conditions_row(event: RaceEvent | None) -> dict[str, Any]:
    """Fila de condiciones de carrera para un evento (o todo-``None`` si falta).

    Compartida por ``fetch_event_conditions`` y
    ``fetch_event_conditions_by_event`` para que ambas variantes no puedan
    divergir en qué campos exponen.
    """
    if event is None:
        return {
            "climate": None,
            "temperature_c": None,
            "surface_condition": None,
            "altitude_msnm": None,
            "weather_notes": None,
        }
    surface = getattr(event, "surface_condition", None)
    temp = getattr(event, "temperature_c", None)
    return {
        "climate": getattr(event, "climate", None),
        "temperature_c": float(temp) if temp is not None else None,
        "surface_condition": (
            surface.value if hasattr(surface, "value") else surface
        ),
        "altitude_msnm": getattr(event, "altitude_msnm", None),
        "weather_notes": getattr(event, "weather_notes", None),
    }


def _course_row(
    event: RaceEvent | None,
    match: tuple[RaceCourseCategorySetup, RaceCourseVariant] | None,
) -> dict[str, Any]:
    """Fila de perfil de circuito para un evento (``{}`` si no hay dato).

    Compartida por ``fetch_course_context`` y ``fetch_course_context_by_event``
    — NUNCA incluye ``course_notes`` (FR-020, exclusión estructural): ni
    ``RaceCourseCategorySetup`` ni ``RaceCourseVariant`` tienen esa columna,
    y el texto libre del ``RaceEvent`` (``course_notes``) simplemente no se
    lee aquí.
    """
    if event is None or match is None:
        return {}
    setup, variant = match
    terrain = getattr(event, "terrain_type", None)
    return {
        "lap_distance_m": variant.lap_distance_m,
        "elevation_gain_m": variant.elevation_gain_m,
        "laps": setup.laps,
        "terrain_type": terrain.value if terrain is not None else None,
        "technical_difficulty": event.technical_difficulty,
        "key_sectors": event.key_sectors or [],
    }


async def _load_course_setups(
    db: AsyncSession, category_id: int, event_ids: list[int]
) -> dict[int, tuple[RaceCourseCategorySetup, RaceCourseVariant]]:
    """Setups de circuito (``{event_id: (setup, variant)}``) para una categoría.

    Única query que toca ``race_course_category_setups``/
    ``race_course_variants`` — ninguna de las dos tablas tiene columna
    ``course_notes``, así que este ``select`` nunca puede filtrarla.
    """
    if not event_ids:
        return {}
    stmt = select(RaceCourseCategorySetup, RaceCourseVariant).join(
        RaceCourseVariant,
        RaceCourseVariant.id == RaceCourseCategorySetup.variant_id,
    ).where(
        RaceCourseCategorySetup.category_id == category_id,
        RaceCourseCategorySetup.race_event_id.in_(event_ids),
    )
    res = await db.execute(stmt)
    return {setup.race_event_id: (setup, variant) for setup, variant in res.all()}


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
    *,
    series_id: int | None = None,
) -> list[RaceResult]:
    """Resultados de un atleta TyR en una temporada (opcionalmente filtrados).

    Filtra:
    - ``RaceResult.athlete_id == athlete_id`` (matches confirmados, NULL no).
    - ``RaceResult.deleted_at IS NULL``.
    - ``event.series.season_year == season`` (o ``event.series_id == series_id``
      cuando este se provee — ver más abajo).
    - Si ``valida_nums`` se provee: ``event.sequence_number IN valida_nums``.

    Orden: ascendente por ``event.event_date`` (cronológico).

    IMPORTANTE: ``sequence_number`` (``valida_num``) es único solo **dentro
    de una serie** (``uq_race_events_series_sequence``) — dos copas de la
    misma temporada pueden compartir el mismo número de válida (p. ej.
    ambas tienen una "Válida 4"). Todo llamador que analice UNA válida de
    UNA copa concreta debe pasar ``series_id``; de lo contrario
    ``valida_nums`` puede resolver al evento equivocado (otra copa).

    Args:
        db: Sesión async.
        athlete_id: PK ``Athlete``.
        season: año de temporada (vía ``RaceSeries.season_year``). Ignorado
            para el filtro de eventos cuando ``series_id`` se provee (la
            serie ya determina la temporada sin ambigüedad).
        valida_nums: lista opcional de números de válida (1, 2, 3, ...).
        series_id: PK opcional de ``RaceSeries``. Cuando se provee, solo se
            consideran eventos de esa serie (desambigua ``sequence_number``
            repetido entre copas). ``None`` (default) mantiene el
            comportamiento previo, sin cambios, filtrando por temporada.

    Returns:
        Lista de ``RaceResult`` ya filtrada y ordenada. Vacía si no hay match.
    """
    results = await load_results(db)
    events = await load_events(db)
    series = await load_series(db)

    events_in_season_by_id = _scoped_events(
        events, series, season=season, series_id=series_id
    )
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


async def fetch_all_results_for_season(
    db: AsyncSession,
    category_id: int,
    season: int,
) -> list[RaceResult]:
    """Todos los resultados de una categoría en una temporada.

    No filtra por atleta — retorna TODOS los competidores de la categoría en
    todos los eventos de la temporada. Se usa para calcular el tiempo del
    ganador (position=1) por event_id y así calcular ``gap_to_winner_ms`` en
    ``load_race_data``.

    Args:
        db: Sesión async.
        category_id: PK ``RaceCategory``.
        season: año de temporada (vía ``RaceSeries.season_year``).

    Returns:
        Lista de ``RaceResult`` filtrada por categoría + temporada. Vacía si
        no hay resultados.
    """
    results = await load_results(db)
    events = await load_events(db)
    series = await load_series(db)

    series_ids_in_season = {s.id for s in series if s.season_year == season}
    event_ids_in_season = {
        e.id for e in events if e.series_id in series_ids_in_season
    }

    return [
        r
        for r in results
        if r.category_id == category_id and r.event_id in event_ids_in_season
    ]


async def fetch_event_conditions(
    db: AsyncSession,
    season: int,
    valida_nums: list[int],
    *,
    series_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    """Condiciones registradas por válida para una temporada (feature 011).

    Devuelve las cinco condiciones de carrera (``climate``, ``temperature_c``,
    ``surface_condition``, ``altitude_msnm``, ``weather_notes``) para cada
    ``valida_num`` solicitado. Reutiliza los caches de ``load_events`` /
    ``load_series`` (cero round-trips extra cuando ``load_race_data`` ya los
    cargó en la misma sesión).

    Invariante (contracts/graph-state.md): cada ``valida_num`` resuelto a un
    evento aparece como clave; un evento SIN condiciones registradas produce
    una entrada cuyos cinco campos son ``None`` (la ausencia debe ser
    representable — FR-003). Una válida sin evento en la temporada (o sin
    evento en ``series_id``, cuando este se provee) no aparece.

    IMPORTANTE: ``sequence_number`` (``valida_num``) es único solo **dentro
    de una serie** (``uq_race_events_series_sequence``). Sin ``series_id``,
    dos copas de la misma temporada con el mismo número de válida colisionan
    (gana la primera que se recorra en memoria — no determinístico para el
    llamador). Todo análisis de UNA válida de UNA copa concreta debe pasar
    ``series_id``.

    Args:
        db: Sesión async.
        season: año de temporada (vía ``RaceSeries.season_year``). Ignorado
            para el filtro de eventos cuando ``series_id`` se provee.
        valida_nums: números de válida a resolver (``sequence_number``).
        series_id: PK opcional de ``RaceSeries``. Cuando se provee, solo se
            consideran eventos de esa serie. ``None`` (default) mantiene el
            comportamiento previo, sin cambios.

    Returns:
        ``{valida_num: {climate, temperature_c, surface_condition,
        altitude_msnm, weather_notes}}``.
    """
    if not valida_nums:
        return {}

    events = await load_events(db)
    series = await load_series(db)

    scoped = _scoped_events(events, series, season=season, series_id=series_id)
    valida_set = set(valida_nums)

    out: dict[int, dict[str, Any]] = {}
    for e in scoped.values():
        seq = e.sequence_number
        if seq not in valida_set or seq in out:
            continue
        out[int(seq)] = _conditions_row(e)
    return out


async def fetch_event_conditions_by_event(
    db: AsyncSession, event_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """Condiciones de carrera keyed por ``event_id`` (sin ambigüedad de válida).

    Misma forma de valor que :func:`fetch_event_conditions` — ``{climate,
    temperature_c, surface_condition, altitude_msnm, weather_notes}`` — pero
    indexada directamente por ``event_id``, para el resumen de temporada
    (que itera eventos concretos, ya resueltos, en vez de números de válida
    potencialmente ambiguos entre copas).

    Invariante: TODO ``event_id`` solicitado aparece como clave, incluso si
    no existe como ``RaceEvent`` (entrada con los cinco campos en ``None``).

    Args:
        db: Sesión async.
        event_ids: PKs de ``RaceEvent`` a resolver.

    Returns:
        ``{event_id: {climate, temperature_c, surface_condition,
        altitude_msnm, weather_notes}}`` — una entrada por cada id pedido.
    """
    if not event_ids:
        return {}

    events = await load_events(db)
    events_by_id = {e.id: e for e in events}

    return {eid: _conditions_row(events_by_id.get(eid)) for eid in event_ids}


async def fetch_course_context(
    db: AsyncSession,
    season: int,
    valida_nums: list[int],
    category_id: int | None,
    *,
    series_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    """Perfil de circuito registrado por válida para una categoría (feature 043).

    Mismo patrón que :func:`fetch_event_conditions`: reutiliza los caches de
    ``load_events``/``load_series`` para resolver ``valida_num -> RaceEvent``
    dentro de la temporada (o dentro de ``series_id``, ver más abajo).

    Invariante (contracts/ai-course-block.md §1): **toda** válida solicitada
    aparece como clave del dict devuelto, incluso cuando no hay evento en la
    temporada, ``category_id is None`` o el evento resuelto no tiene
    ``RaceCourseCategorySetup`` para esa categoría — en cualquiera de esos
    casos el valor es ``{}`` (la ausencia debe ser representable).

    Cuando hay setup, el valor es ``{lap_distance_m, elevation_gain_m, laps,
    terrain_type, technical_difficulty, key_sectors}`` — NUNCA
    ``course_notes`` (FR-020, exclusión estructural): terreno/dificultad/
    sectores se leen del ``RaceEvent`` ya cacheado (columnas planas, sin
    query extra); solo ``lap_distance_m``/``elevation_gain_m``/``laps``
    requieren la única query adicional de esta función (``_load_course_setups``),
    que selecciona ``RaceCourseCategorySetup`` unido a ``RaceCourseVariant`` —
    ninguna de las dos tablas tiene columna ``course_notes``.

    IMPORTANTE: ``sequence_number`` (``valida_num``) es único solo **dentro
    de una serie** (``uq_race_events_series_sequence``). Sin ``series_id``,
    dos copas de la misma temporada con el mismo número de válida colisionan
    (gana la primera que se recorra en memoria). Todo análisis de UNA válida
    de UNA copa concreta debe pasar ``series_id``.

    Args:
        db: Sesión async.
        season: año de temporada (vía ``RaceSeries.season_year``). Ignorado
            para el filtro de eventos cuando ``series_id`` se provee.
        valida_nums: números de válida a resolver (``sequence_number``).
        category_id: categoría del corredor. ``None`` → todas las entradas
            quedan en ``{}`` (p. ej. el resumen de temporada, donde puede
            haber ambigüedad de categoría o simplemente ninguna que pasar).
        series_id: PK opcional de ``RaceSeries``. Cuando se provee, solo se
            consideran eventos de esa serie. ``None`` (default) mantiene el
            comportamiento previo, sin cambios.

    Returns:
        ``{valida_num: {...} | {}}`` — una clave por cada ``valida_num``
        solicitado, sin excepción.
    """
    if not valida_nums:
        return {}

    out: dict[int, dict[str, Any]] = {int(v): {} for v in valida_nums}

    events = await load_events(db)
    series = await load_series(db)

    scoped = _scoped_events(events, series, season=season, series_id=series_id)
    valida_set = set(valida_nums)

    event_by_valida: dict[int, RaceEvent] = {}
    for e in scoped.values():
        seq = e.sequence_number
        if seq not in valida_set or seq in event_by_valida:
            continue
        event_by_valida[int(seq)] = e

    if category_id is None or not event_by_valida:
        return out

    event_ids = [e.id for e in event_by_valida.values()]
    setup_by_event_id = await _load_course_setups(db, category_id, event_ids)

    for valida_num, event in event_by_valida.items():
        out[valida_num] = _course_row(event, setup_by_event_id.get(event.id))

    return out


async def fetch_course_context_by_event(
    db: AsyncSession, event_ids: list[int], category_id: int | None
) -> dict[int, dict[str, Any]]:
    """Perfil de circuito keyed por ``event_id`` (sin ambigüedad de válida).

    Misma forma de valor que :func:`fetch_course_context` — ``{}`` cuando no
    hay setup para la categoría, o el dict completo cuando sí lo hay — pero
    indexada directamente por ``event_id``, para el resumen de temporada.
    NUNCA incluye ``course_notes`` (ver :func:`_course_row`).

    Invariante: TODO ``event_id`` solicitado aparece como clave, incluso si
    no existe como ``RaceEvent`` o si ``category_id is None`` (entrada
    ``{}``).

    Args:
        db: Sesión async.
        event_ids: PKs de ``RaceEvent`` a resolver.
        category_id: categoría del corredor. ``None`` → todas las entradas
            quedan en ``{}``.

    Returns:
        ``{event_id: {...} | {}}`` — una clave por cada ``event_id`` pedido.
    """
    if not event_ids:
        return {}

    out: dict[int, dict[str, Any]] = {eid: {} for eid in event_ids}

    if category_id is None:
        return out

    events = await load_events(db)
    events_by_id = {e.id: e for e in events}
    requested_ids = [eid for eid in event_ids if eid in events_by_id]

    setup_by_event_id = await _load_course_setups(db, category_id, requested_ids)

    for eid in event_ids:
        out[eid] = _course_row(events_by_id.get(eid), setup_by_event_id.get(eid))

    return out


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
