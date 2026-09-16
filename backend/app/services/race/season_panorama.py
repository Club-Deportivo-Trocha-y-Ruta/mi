"""Servicio de panorama de temporada (PR3 unificación /competitions).

Expone :func:`fetch_season_panorama`, que devuelve una vista agregada por
deportista del club a lo largo de TODAS las válidas de una temporada
(``season_year``). Alimenta la subpágina ``/competitions/insights/season/:year``.

Diseño anti-N+1
===============
Una **única** consulta SQL con ``JOIN`` + ``GROUP BY athlete_id`` calcula
todas las métricas agregadas. NO se itera en application layer disparando una
query por atleta (anti-pattern explícito del workflow §7).

La consulta usa SQL crudo (``text()``) — patrón ya establecido en
``race_analysis.py`` / ``athlete_race_analysis.py`` para agregaciones — y es
portable entre MySQL 8.4 (prod) y SQLite (tests):
- ``SUM(CASE WHEN ... THEN 1 ELSE 0 END)`` para conteos condicionales.
- ``MIN(position)`` para mejor posición.
- Sin window functions ni CTEs (compatibilidad amplia).

Solo cuenta resultados con ``athlete_id`` no nulo (deportistas del club ya
enlazados) y ``deleted_at IS NULL`` (resultados vigentes). El filtro de
temporada se hace por ``race_series.season_year`` (la temporada es atributo
de la serie, no del evento).

Privacidad
==========
Esta capa retorna datos crudos por ``athlete_id``. El endpoint
(coach/admin only) resuelve nombres reales porque el caller está autorizado.
Cualquier narrativa IA sobre el panorama global DEBE generarse con
``forbidden_names=[]`` (redacción anónima) — pero PR3 NO genera texto IA aquí:
es agregación numérica pura.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SeasonPanoramaSeriesRow(NamedTuple):
    """Métricas de un deportista acotadas a UNA copa de la temporada.

    Ver hotfix "identidad de válida" (``~/.claude/plans/multicopa-identidad-valida.md``
    bug #8, 2026-09-16): antes ``fetch_season_panorama`` sumaba TODAS las
    copas de la temporada en un único total por deportista — con dos copas
    activas (ej. Copa Valle + Copa Let's Go) eso mezcla puntos/podios de una
    con los de la otra. Cada ``SeasonPanoramaSeriesRow`` es el desglose de
    UNA copa; ``SeasonPanoramaRow.by_series`` trae una entrada por copa
    corrida. Solo copas (``race_series.kind = 'cup'``) — los campeonatos ya
    se excluyen de este endpoint desde spec 023 (SC-004) y esta iteración no
    cambia eso.
    """

    series_id: int
    series_name: str
    series_short_name: str | None
    series_kind: str
    races: int
    points: int
    podiums: int
    wins: int
    best_position: int | None


class SeasonPanoramaRow(NamedTuple):
    """Fila agregada por deportista para una temporada.

    Nota: ``category`` NO se incluye — en este dominio la categoría se computa
    en application layer desde ``birth_date`` (CLAUDE.md), no es columna. El
    frontend la resuelve por separado si la necesita.

    Los campos ``races_count``/``wins``/``podiums``/``best_position``/
    ``total_points`` son sumas A TRAVÉS DE TODAS LAS COPAS de la temporada —
    quedan para no romper a los consumidores existentes, pero están
    DEPRECADOS desde el hotfix "identidad de válida" (2026-09-16): con más
    de una copa activa no representan ningún total real ("puntos Copa
    Valle" deja de ser cierto apenas exista una segunda copa). El desglose
    correcto, por copa, vive en ``by_series``.
    """

    athlete_id: int
    first_name: str
    last_name: str
    races_count: int
    wins: int
    podiums: int
    best_position: int | None
    total_points: int
    by_series: tuple[SeasonPanoramaSeriesRow, ...] = ()


# Agregación en una sola pasada. GROUP BY athlete_id; sin N+1.
# Filtramos por temporada vía race_series.season_year.
_PANORAMA_SQL = text(
    """
    SELECT
        a.id                AS athlete_id,
        a.first_name        AS first_name,
        a.last_name         AS last_name,
        COUNT(rr.id)        AS races_count,
        SUM(CASE WHEN rr.position = 1 THEN 1 ELSE 0 END)  AS wins,
        SUM(CASE WHEN rr.position IS NOT NULL AND rr.position <= 3
                 THEN 1 ELSE 0 END)                       AS podiums,
        MIN(rr.position)    AS best_position,
        COALESCE(SUM(rr.points_awarded), 0)  AS total_points
    FROM race_results AS rr
    JOIN race_events AS re   ON re.id = rr.event_id
    JOIN race_series AS rs   ON rs.id = re.series_id
    JOIN athletes    AS a    ON a.id = rr.athlete_id
    WHERE rs.season_year = :season
      AND rs.kind = 'cup'
      AND rr.athlete_id IS NOT NULL
      AND rr.deleted_at IS NULL
      AND (:club_id IS NULL OR a.club_id = :club_id)
    GROUP BY a.id, a.first_name, a.last_name
    ORDER BY total_points DESC, podiums DESC, a.last_name ASC
    """
)


# Desglose por copa (athlete_id, series_id). Mismas condiciones WHERE que
# ``_PANORAMA_SQL`` (incluido ``rs.kind = 'cup'`` — los campeonatos siguen
# excluidos, sin cambios de spec 023 SC-004) para que ``by_series`` nunca
# contradiga los totales deprecados de arriba. ``MIN(re.event_date)`` solo
# se usa para ordenar en Python — no se expone en el schema.
_PANORAMA_BY_SERIES_SQL = text(
    """
    SELECT
        a.id                AS athlete_id,
        rs.id               AS series_id,
        rs.name             AS series_name,
        rs.short_name       AS series_short_name,
        rs.kind             AS series_kind,
        COUNT(rr.id)        AS races,
        COALESCE(SUM(rr.points_awarded), 0) AS points,
        SUM(CASE WHEN rr.position IS NOT NULL AND rr.position <= 3
                 THEN 1 ELSE 0 END)         AS podiums,
        SUM(CASE WHEN rr.position = 1 THEN 1 ELSE 0 END) AS wins,
        MIN(rr.position)    AS best_position,
        MIN(re.event_date)  AS first_event_date
    FROM race_results AS rr
    JOIN race_events AS re   ON re.id = rr.event_id
    JOIN race_series AS rs   ON rs.id = re.series_id
    JOIN athletes    AS a    ON a.id = rr.athlete_id
    WHERE rs.season_year = :season
      AND rs.kind = 'cup'
      AND rr.athlete_id IS NOT NULL
      AND rr.deleted_at IS NULL
      AND (:club_id IS NULL OR a.club_id = :club_id)
    GROUP BY a.id, rs.id, rs.name, rs.short_name, rs.kind
    """
)


async def _fetch_by_series(
    db: AsyncSession, *, season: int, club_id: int | None
) -> dict[int, list[SeasonPanoramaSeriesRow]]:
    """Desglose por copa, agrupado por ``athlete_id`` y ordenado por la
    fecha de la primera válida corrida de cada copa (copas más antiguas
    primero — mismo criterio que el selector de comparación de spec 039)."""
    result = await db.execute(
        _PANORAMA_BY_SERIES_SQL, {"season": season, "club_id": club_id}
    )
    # (sort_key, row) por athlete_id; sort_key = str(first_event_date), que
    # ordena cronológicamente tanto si el driver devuelve un ``date`` (MySQL)
    # como un string ISO (sqlite crudo vía text()).
    staged: dict[int, list[tuple[str, SeasonPanoramaSeriesRow]]] = {}
    for r in result:
        m = r._mapping
        athlete_id = int(m["athlete_id"])
        row = SeasonPanoramaSeriesRow(
            series_id=int(m["series_id"]),
            series_name=str(m["series_name"]),
            series_short_name=(
                str(m["series_short_name"])
                if m["series_short_name"] is not None
                else None
            ),
            series_kind=str(m["series_kind"]),
            races=int(m["races"] or 0),
            points=int(m["points"] or 0),
            podiums=int(m["podiums"] or 0),
            wins=int(m["wins"] or 0),
            best_position=(
                int(m["best_position"]) if m["best_position"] is not None else None
            ),
        )
        sort_key = str(m["first_event_date"]) if m["first_event_date"] is not None else ""
        staged.setdefault(athlete_id, []).append((sort_key, row))

    by_athlete: dict[int, list[SeasonPanoramaSeriesRow]] = {}
    for athlete_id, entries in staged.items():
        entries.sort(key=lambda pair: pair[0])
        by_athlete[athlete_id] = [row for _, row in entries]
    return by_athlete


async def fetch_season_panorama(
    db: AsyncSession,
    *,
    season: int,
    club_id: int | None = None,
) -> list[SeasonPanoramaRow]:
    """Agregado por deportista de todos sus resultados en una temporada.

    Args:
        db: Sesión async.
        season: Año de la temporada (``race_series.season_year``).
        club_id: Si se pasa, restringe a deportistas de ese club. Si es
            ``None``, incluye todos los deportistas con resultados enlazados
            en la temporada (uso admin / panorama global).

    Returns:
        Lista de :class:`SeasonPanoramaRow` ordenada por puntos desc, luego
        podios desc, luego apellido. Lista vacía si no hay resultados.

    Notas:
        - Dos queries agregadas (no N+1 — ninguna itera por atleta): una para
          los totales de temporada (deprecados, cross-cup) y otra para el
          desglose ``by_series`` por copa.
        - ``best_position`` puede ser ``None`` si ningún resultado tiene
          posición (todos DNF/DNS). En ese caso ``races_count`` puede ser >0.
        - ``by_series`` solo trae copas con las que el atleta tiene
          resultados en la temporada; un atleta que SOLO corrió un
          campeonato (sin ninguna copa) no aparece en absoluto en este
          endpoint — comportamiento preexistente (spec 023 SC-004), sin
          cambios en este hotfix.
    """
    result = await db.execute(_PANORAMA_SQL, {"season": season, "club_id": club_id})
    by_series = await _fetch_by_series(db, season=season, club_id=club_id)
    rows: list[SeasonPanoramaRow] = []
    for r in result:
        m = r._mapping
        athlete_id = int(m["athlete_id"])
        rows.append(
            SeasonPanoramaRow(
                athlete_id=athlete_id,
                first_name=str(m["first_name"]),
                last_name=str(m["last_name"]),
                races_count=int(m["races_count"] or 0),
                wins=int(m["wins"] or 0),
                podiums=int(m["podiums"] or 0),
                best_position=(
                    int(m["best_position"]) if m["best_position"] is not None else None
                ),
                total_points=int(m["total_points"] or 0),
                by_series=tuple(by_series.get(athlete_id, [])),
            )
        )
    return rows


__all__ = ["SeasonPanoramaRow", "SeasonPanoramaSeriesRow", "fetch_season_panorama"]
