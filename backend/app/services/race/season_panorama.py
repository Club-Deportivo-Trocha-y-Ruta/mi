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


class SeasonPanoramaRow(NamedTuple):
    """Fila agregada por deportista para una temporada.

    Nota: ``category`` NO se incluye — en este dominio la categoría se computa
    en application layer desde ``birth_date`` (CLAUDE.md), no es columna. El
    frontend la resuelve por separado si la necesita.
    """

    athlete_id: int
    first_name: str
    last_name: str
    races_count: int
    wins: int
    podiums: int
    best_position: int | None
    total_points: int


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
        - Una sola query agregada (no N+1).
        - ``best_position`` puede ser ``None`` si ningún resultado tiene
          posición (todos DNF/DNS). En ese caso ``races_count`` puede ser >0.
    """
    result = await db.execute(_PANORAMA_SQL, {"season": season, "club_id": club_id})
    rows: list[SeasonPanoramaRow] = []
    for r in result:
        m = r._mapping
        rows.append(
            SeasonPanoramaRow(
                athlete_id=int(m["athlete_id"]),
                first_name=str(m["first_name"]),
                last_name=str(m["last_name"]),
                races_count=int(m["races_count"] or 0),
                wins=int(m["wins"] or 0),
                podiums=int(m["podiums"] or 0),
                best_position=(
                    int(m["best_position"]) if m["best_position"] is not None else None
                ),
                total_points=int(m["total_points"] or 0),
            )
        )
    return rows


__all__ = ["SeasonPanoramaRow", "fetch_season_panorama"]
