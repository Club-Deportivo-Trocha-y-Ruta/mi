"""Helper: resultados de competencia del club en un mes dado.

Consulta los ``RaceResult`` de atletas del club cuyo evento cae dentro
del mes solicitado, los enriquece con nombre del atleta, categoría y
evento, y devuelve una lista de ``CompetitionResultItem`` lista para
persistir en ``MonthlyReport.competition_results``.

PRIVACIDAD:
- Los nombres de atletas son intencionales: este helper sirve al PDF
  del Informe Técnico Mensual, documento de distribución restringida
  (solo coach/admin del club). El router garantiza RBAC.
- Los nombres NUNCA se pasan a la IA (ver ``build_blocks_context`` en el
  use case de bloques). La IA trabaja únicamente con datos agregados y
  posiciones numéricas.
- Degrada limpio: cualquier error de BD devuelve [] sin romper el informe.

Spec 022 (T017): el query ahora hace JOIN (outer, defensivo) con
``RaceSeries`` para poblar ``event_id``, ``series_kind`` y ``awards_points``
en cada ``CompetitionResultItem`` sin round-trips adicionales:
``awards_points = (series_kind == "cup")`` — los campeonatos (spec 014,
``RaceSeriesKind.championship``) no otorgan puntos de ranking acumulado.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.training_session import CompetitionResultItem

logger = logging.getLogger(__name__)


async def build_competition_results(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
) -> list[CompetitionResultItem]:
    """Devuelve resultados de competencia del club para el mes indicado.

    Query:
        RaceResult JOIN RaceEvent (event_date dentro del mes)
                  JOIN RaceCategory
                  JOIN Athlete (athlete_id en el club)
                  LEFT OUTER JOIN RaceSeries (RaceEvent.series_id)
        WHERE deleted_at IS NULL AND position IS NOT NULL
        ORDER BY event_date ASC, position ASC

    Args:
        db: sesión async de SQLAlchemy.
        club_id: ID del club cuyos atletas se consultan.
        year: año del período.
        month: mes del período (1-12).

    Returns:
        Lista de CompetitionResultItem ordenada por evento y posición.
        Lista vacía si no hay resultados o ante cualquier error.
    """
    try:
        from app.models.athlete import Athlete
        from app.models.race_category import RaceCategory
        from app.models.race_event import RaceEvent
        from app.models.race_result import RaceResult
        from app.models.race_series import RaceSeries, RaceSeriesKind

        month_start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)

        # Primero: IDs de atletas del club con race_results vinculados.
        # Hacemos un JOIN explícito para no cargar todos los atletas.
        # LEFT OUTER JOIN a RaceSeries: series_id es NOT NULL hoy, pero se
        # mantiene defensivo (Spec 022) para no romper si un evento legacy
        # quedara sin serie resoluble — en ese caso series_kind/awards_points
        # caen a sus defaults seguros (None / True).
        result = await db.execute(
            select(
                RaceEvent.id.label("event_id"),
                RaceResult.position,
                RaceResult.points_awarded,
                RaceEvent.name.label("event_name"),
                RaceEvent.event_date,
                RaceCategory.label.label("category_label"),
                Athlete.first_name,
                Athlete.last_name,
                RaceSeries.kind.label("series_kind"),
            )
            .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
            .join(RaceCategory, RaceCategory.id == RaceResult.category_id)
            .join(Athlete, Athlete.id == RaceResult.athlete_id)
            .outerjoin(RaceSeries, RaceSeries.id == RaceEvent.series_id)
            .where(
                Athlete.club_id == club_id,
                RaceEvent.event_date >= month_start,
                RaceEvent.event_date <= month_end,
                RaceResult.deleted_at.is_(None),
                RaceResult.position.is_not(None),
            )
            .order_by(RaceEvent.event_date.asc(), RaceResult.position.asc())
        )
        rows = result.all()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "competition_results: error en query club_id=%d %d-%02d (%s: %s)",
            club_id, year, month,
            type(exc).__name__, exc,
        )
        return []

    items: list[CompetitionResultItem] = []
    for row in rows:
        series_kind_raw = row.series_kind
        series_kind_enum = (
            series_kind_raw
            if isinstance(series_kind_raw, RaceSeriesKind)
            else (RaceSeriesKind(series_kind_raw) if series_kind_raw is not None else None)
        )
        items.append(
            CompetitionResultItem(
                athlete_name=f"{row.first_name} {row.last_name}",
                category=row.category_label,
                position=row.position,
                points=row.points_awarded if row.points_awarded else None,
                event_name=row.event_name,
                event_date=row.event_date,
                event_id=row.event_id,
                series_kind=series_kind_enum.value if series_kind_enum is not None else None,
                awards_points=(series_kind_enum == RaceSeriesKind.cup)
                if series_kind_enum is not None
                else True,
            )
        )
    return items
