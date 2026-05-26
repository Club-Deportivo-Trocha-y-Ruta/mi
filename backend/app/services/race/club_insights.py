"""Servicio de consulta de insights agrupados por club + válida (Sprint 3).

Expone :func:`fetch_club_insights_by_race` que devuelve los atletas del
club que corrieron una válida específica, cada uno acompañado de su insight
activo aprobado más reciente (si existe).

Decisiones de diseño:
- La query usa SQLAlchemy async con ``select()`` estilo moderno. No usa
  pandas ni DataFrames (el dataset es pequeño y orientado a filas, no a
  series numéricas).
- LEFT JOIN simulado en Python para compatibilidad con SQLite en tests:
  se cargan atletas del club que tienen race_result en el evento, y luego
  se cargan los insights por athlete_id en una segunda consulta. Se evita
  un JOIN SQL multi-tabla que el FakeAsyncSession no podría reproducir.
- Filtros de actividad de insights: ``is_active=1 AND coach_approved=1
  AND deprecated_at IS NULL AND archived_at IS NULL`` — idéntica semántica
  que el resto del módulo.

Privacidad:
- Esta capa retorna datos crudos (ORM). La serialización con enmascaramiento
  de nombres y filtrado de ``confidence`` para parent ocurre en el router,
  después de conocer el rol del caller y los IDs de hijos propios.
"""
from __future__ import annotations

import logging
from typing import NamedTuple, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult

logger = logging.getLogger(__name__)


class ClubAthleteInsightRow(NamedTuple):
    """Fila cruda devuelta por :func:`fetch_club_insights_by_race`.

    Contiene el atleta del club que corrió la válida y su insight más
    reciente (puede ser None si no tiene análisis aprobado).
    """

    athlete: Athlete
    insight: Optional[AthleteAiInsight]


async def fetch_club_insights_by_race(
    db: AsyncSession,
    *,
    race_event_id: int,
    club_id: int,
    latest_only: bool = True,
    limit: int = 50,
) -> list[ClubAthleteInsightRow]:
    """Atletas del club que corrieron la válida + su insight activo más reciente.

    Args:
        db: Sesión async.
        race_event_id: PK del ``RaceEvent`` de la válida.
        club_id: PK del club cuyos atletas se quieren listar.
        latest_only: Si True (default), retorna el insight más reciente por
            atleta. Si False, podría retornar múltiples (no implementado en
            esta versión — siempre se retorna a lo sumo 1 por atleta).
        limit: Número máximo de atletas a retornar (default 50).

    Returns:
        Lista de :class:`ClubAthleteInsightRow`, uno por atleta, ordenada
        por apellido + nombre. Si un atleta corrió pero no tiene insight
        aprobado, su ``insight`` es ``None``.

    Raises:
        No lanza excepciones. Si el evento no existe o no hay resultados,
        retorna lista vacía. El 404 lo gestiona el router.
    """
    # 1. Atletas del club que tienen al menos un race_result en esta válida.
    #    Usamos una subconsulta para obtener los athlete_id únicos primero.
    athlete_ids_stmt = (
        select(RaceResult.athlete_id)
        .where(
            RaceResult.event_id == race_event_id,
            RaceResult.athlete_id.is_not(None),
        )
        .distinct()
    )
    athlete_ids_result = await db.execute(athlete_ids_stmt)
    race_athlete_ids: set[int] = {
        row for row in athlete_ids_result.scalars().all()
        if row is not None
    }

    if not race_athlete_ids:
        return []

    # 2. Cargar los atletas del club que están en la lista anterior.
    athletes_stmt = (
        select(Athlete)
        .where(
            Athlete.id.in_(race_athlete_ids),
            Athlete.club_id == club_id,
        )
        .order_by(Athlete.last_name, Athlete.first_name)
        .limit(limit)
    )
    athletes_result = await db.execute(athletes_stmt)
    athletes: list[Athlete] = list(athletes_result.scalars().all())

    if not athletes:
        return []

    # 3. Cargar el insight activo aprobado más reciente de cada atleta
    #    para esta misma válida (vinculado por event_id o valida_num).
    #    Condición de elegibilidad: is_active=1, coach_approved=1,
    #    deprecated_at IS NULL, archived_at IS NULL.
    #
    #    Estrategia: cargamos todos los insights elegibles para los atletas
    #    del club en esta válida y luego agrupamos en Python. SQLite en tests
    #    no soporta ROW_NUMBER() / PARTITION BY, así que lo hacemos en Python.
    club_athlete_ids = [a.id for a in athletes]

    insights_stmt = (
        select(AthleteAiInsight)
        .where(
            AthleteAiInsight.athlete_id.in_(club_athlete_ids),
            AthleteAiInsight.event_id == race_event_id,
            AthleteAiInsight.is_active == 1,
            AthleteAiInsight.coach_approved.is_(True),
            AthleteAiInsight.deprecated_at.is_(None),
            AthleteAiInsight.archived_at.is_(None),
        )
        .order_by(AthleteAiInsight.generated_at.desc())
    )
    insights_result = await db.execute(insights_stmt)
    raw_insights: list[AthleteAiInsight] = list(insights_result.scalars().all())

    # Agrupar por athlete_id — tomamos el primero (más reciente por ORDER BY).
    best_insight_by_athlete: dict[int, AthleteAiInsight] = {}
    for ins in raw_insights:
        if ins.athlete_id not in best_insight_by_athlete:
            best_insight_by_athlete[ins.athlete_id] = ins

    # 4. Combinar: cada atleta con su insight (o None).
    rows: list[ClubAthleteInsightRow] = []
    for athlete in athletes:
        insight = best_insight_by_athlete.get(athlete.id)
        rows.append(ClubAthleteInsightRow(athlete=athlete, insight=insight))

    return rows


async def get_race_event_or_none(
    db: AsyncSession,
    race_event_id: int,
) -> Optional[RaceEvent]:
    """Carga el RaceEvent por PK. Retorna None si no existe."""
    result = await db.execute(
        select(RaceEvent).where(RaceEvent.id == race_event_id)
    )
    return result.scalar_one_or_none()


def build_race_event_label(event: RaceEvent) -> str:
    """Construye la etiqueta legible del evento para el response wrapper.

    Formato:
    - Si tiene ``location``: ``"Válida {N} — {location} {date}"``
    - Si no:                 ``"{name} {date}"``

    Date en formato ``DD mmm YYYY`` (español abreviado).
    """
    _MONTHS_ES = {
        1: "ene", 2: "feb", 3: "mar", 4: "abr",
        5: "may", 6: "jun", 7: "jul", 8: "ago",
        9: "sep", 10: "oct", 11: "nov", 12: "dic",
    }
    date_str = ""
    if event.event_date:
        m = _MONTHS_ES.get(event.event_date.month, str(event.event_date.month))
        date_str = f"{event.event_date.day} {m} {event.event_date.year}"

    if event.location:
        return f"Válida {event.sequence_number} — {event.location} {date_str}".strip()
    return f"{event.name} {date_str}".strip()
