"""Cumpleaños virtuales para el calendario.

Los cumpleaños NO se persisten en `calendar_events`. Se computan al consultar
el calendario desde `athlete.birth_date` y se inyectan como eventos virtuales
con ID negativo (decodificable a `(year, athlete_id)`).

Decisión: todos los miembros del club ven todos los cumpleaños (decisión de
producto). El UI muestra solo el nombre del atleta y la edad que cumple — no
expone la fecha de nacimiento ni el año exacto.

Reglas:
- Read-only: el cliente NO puede crear, editar, cancelar ni hacer RSVP sobre
  un evento de tipo BIRTHDAY. El router devuelve 400 en esos casos.
- All-day: el evento ocupa el día completo en zona America/Bogota.
- 29 de febrero: en años no bisiestos se desplaza al 28 de febrero.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.calendar_event import EventStatus, EventType

if TYPE_CHECKING:
    from app.models.user import User


# ---------------------------------------------------------------------------
# Codificación de ID virtual
# ---------------------------------------------------------------------------
#
# Un evento de cumpleaños virtual tiene `id = -(year * 1_000_000 + athlete_id)`.
# Los IDs negativos son inequívocos: BIGINT autoincrement nunca produce
# negativos. Decodificar es trivial y permite reconstruir el evento sin tocar BD.

_BIRTHDAY_ID_BASE = 1_000_000


def encode_birthday_id(year: int, athlete_id: int) -> int:
    return -(year * _BIRTHDAY_ID_BASE + athlete_id)


def decode_birthday_id(event_id: int) -> tuple[int, int] | None:
    """Devuelve (year, athlete_id) si el id es un birthday virtual; si no, None."""
    if event_id >= 0:
        return None
    n = -event_id
    year, athlete_id = divmod(n, _BIRTHDAY_ID_BASE)
    if year < 1900 or year > 2100 or athlete_id <= 0:
        return None
    return year, athlete_id


def is_birthday_id(event_id: int) -> bool:
    return decode_birthday_id(event_id) is not None


# ---------------------------------------------------------------------------
# Cálculo del día del cumpleaños en un año dado
# ---------------------------------------------------------------------------


def birthday_in_year(birth_date: date, year: int) -> date:
    """Devuelve la fecha del cumpleaños del atleta en `year`.

    Manejo del 29-feb: si `year` no es bisiesto, retorna el 28 de febrero.
    """
    if birth_date.month == 2 and birth_date.day == 29:
        try:
            return date(year, 2, 29)
        except ValueError:
            return date(year, 2, 28)
    return date(year, birth_date.month, birth_date.day)


# ---------------------------------------------------------------------------
# Construcción del evento virtual
# ---------------------------------------------------------------------------


def _build_virtual_event(athlete: Athlete, occurrence: date) -> SimpleNamespace:
    """Construye un objeto compatible con CalendarEvent (duck-typed).

    Los serializers y routers acceden a los atributos vía punto. Usamos
    SimpleNamespace para evitar persistir nada en la sesión SQLAlchemy.
    """
    age_turning = occurrence.year - athlete.birth_date.year
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=encode_birthday_id(occurrence.year, athlete.id),
        club_id=athlete.club_id,
        event_type=EventType.BIRTHDAY,
        status=EventStatus.SCHEDULED,
        title=f"🎂 Cumpleaños de {athlete.first_name}",
        description=None,
        location=None,
        start_at=datetime.combine(occurrence, time.min),
        end_at=datetime.combine(occurrence, time.max),
        all_day=True,
        timezone="America/Bogota",
        event_data={
            "athlete_id": athlete.id,
            "athlete_first_name": athlete.first_name,
            "age_turning": age_turning,
        },
        color_hex=None,
        created_by_user_id=0,  # marca: sistema
        created_at=now,
        updated_at=now,
        audiences=[],
        attendances=[],
    )


# ---------------------------------------------------------------------------
# Listado de cumpleaños en un rango
# ---------------------------------------------------------------------------


async def list_birthday_events_in_range(
    db: AsyncSession,
    club_id: int,
    from_date: date,
    to_date: date,
    athlete_ids: list[int] | None = None,
) -> list[SimpleNamespace]:
    """Devuelve cumpleaños virtuales del club en el rango.

    Si `athlete_ids` es None, considera todos los atletas activos del club.
    Si es una lista, restringe a esos IDs (usado para filtros de coach/admin
    por atleta; padres se manejan en la capa superior).
    """
    if from_date > to_date:
        return []

    stmt = select(Athlete).where(Athlete.club_id == club_id)
    if athlete_ids is not None:
        if not athlete_ids:
            return []
        stmt = stmt.where(Athlete.id.in_(athlete_ids))

    result = await db.execute(stmt)
    athletes = list(result.scalars().all())

    events: list[SimpleNamespace] = []
    for athlete in athletes:
        # Por cada año cubierto por el rango, computar la ocurrencia.
        for year in range(from_date.year, to_date.year + 1):
            occurrence = birthday_in_year(athlete.birth_date, year)
            if from_date <= occurrence <= to_date:
                events.append(_build_virtual_event(athlete, occurrence))

    events.sort(key=lambda e: e.start_at)
    return events


# ---------------------------------------------------------------------------
# Lookup por ID virtual
# ---------------------------------------------------------------------------


async def get_birthday_event(
    db: AsyncSession,
    event_id: int,
) -> SimpleNamespace | None:
    """Reconstruye el evento de cumpleaños virtual desde su ID negativo."""
    decoded = decode_birthday_id(event_id)
    if decoded is None:
        return None
    year, athlete_id = decoded

    result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = result.scalar_one_or_none()
    if athlete is None:
        return None

    occurrence = birthday_in_year(athlete.birth_date, year)
    return _build_virtual_event(athlete, occurrence)
