"""Backfill manual de ``calendar_events.race_event_id``.

Contexto
========
La migración BE-1 ``8c1d2e3f4a5b`` agregó ``calendar_events.race_event_id``
(NULL) y un CHECK que exige el link para eventos con ``event_type='competition'``.
Las filas legacy quedaron NULL porque su CHECK aplica solo a inserts/updates
nuevos (constraint level), pero el coach debe revisar y enlazar manualmente
las competencias históricas.

Este script implementa un dry-run que propone matches por intersección
de fecha + ubicación. NO modifica la DB salvo que se pase ``--apply``,
y aún así pide confirmación interactiva por cada match.

Uso
===

    # Dry-run (default): imprime tabla con propuestas + nivel de confianza.
    python -m backend.scripts.backfill_calendar_race_events

    # Aplicar (interactivo, pide y/n por cada match).
    python -m backend.scripts.backfill_calendar_race_events --apply

    # Aplicar solo matches de alta confianza, sin prompts (peligroso).
    python -m backend.scripts.backfill_calendar_race_events --apply --auto-high

Criterios de match
==================
1. ``event_date`` debe coincidir +/- 1 día (carrera puede planificarse el
   día antes/después por logística).
2. ``location`` (de calendar_events) debe contener el ``location`` de
   race_events (o viceversa) por substring case-insensitive sin acentos.
3. Si la categoría del atleta filtra resultados, prioriza el race_event
   cuya categoría coincide más con el ``audience_value`` del calendar.

Confianza:
- ``high``: fecha exacta + match exacto de ubicación normalizada.
- ``medium``: fecha +/-1d + match parcial substring.
- ``low``: solo fecha exacta sin match de ubicación; requiere confirmar.

Salida
======
Imprime tabla CSV-friendly con:
``calendar_event_id, calendar_date, calendar_title, race_event_id, race_date,
race_name, confidence, would_apply``

NO se ejecuta automáticamente en deploys. El coach lo invoca cuando
quiera limpiar legacy.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

# NOTA: imports diferidos hasta llamar main() para no romper en colectado
# de tests si el path no está en sys.path.


Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class MatchProposal:
    calendar_event_id: int
    calendar_date: str
    calendar_title: str
    calendar_location: str | None
    race_event_id: int
    race_date: str
    race_name: str
    race_location: str | None
    confidence: Confidence


def _norm(s: str | None) -> str:
    """Normaliza para comparación: lowercase, sin acentos, espacios colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _classify(
    cal_date,
    race_date,
    cal_loc: str | None,
    race_loc: str | None,
) -> Confidence | None:
    """Decide confianza del match. Retorna None si no hay match razonable."""
    nc, nr = _norm(cal_loc), _norm(race_loc)
    delta_days = abs((cal_date - race_date).days)

    if delta_days == 0 and nc and nr and (nc == nr):
        return "high"
    if delta_days <= 1 and nc and nr and (nc in nr or nr in nc):
        return "medium"
    if delta_days == 0:
        return "low"
    return None


async def _propose_matches() -> list[MatchProposal]:
    """Carga competencias del calendar sin race_event_id + propone matches."""
    from sqlalchemy import select

    from app.database import get_async_session_factory
    from app.models.calendar_event import CalendarEvent, EventType
    from app.models.race_event import RaceEvent

    proposals: list[MatchProposal] = []

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        cal_q = await session.execute(
            select(CalendarEvent).where(
                CalendarEvent.event_type == EventType.COMPETITION,
                CalendarEvent.race_event_id.is_(None),
            )
        )
        calendars = list(cal_q.scalars())

        if not calendars:
            return []

        # Carga todos los race_events una sola vez (típicamente <100 filas).
        race_q = await session.execute(select(RaceEvent))
        races = list(race_q.scalars())

    for cal in calendars:
        best: tuple[Confidence, RaceEvent] | None = None
        order = {"high": 3, "medium": 2, "low": 1}
        for race in races:
            conf = _classify(
                cal.start_at.date(),
                race.event_date,
                cal.location,
                race.location,
            )
            if conf is None:
                continue
            if best is None or order[conf] > order[best[0]]:
                best = (conf, race)

        if best is None:
            continue
        conf, race = best
        proposals.append(
            MatchProposal(
                calendar_event_id=cal.id,
                calendar_date=cal.start_at.date().isoformat(),
                calendar_title=cal.title,
                calendar_location=cal.location,
                race_event_id=race.id,
                race_date=race.event_date.isoformat(),
                race_name=race.name,
                race_location=race.location,
                confidence=conf,
            )
        )
    return proposals


def _print_table(proposals: list[MatchProposal], *, apply: bool) -> None:
    print(
        "calendar_event_id,calendar_date,calendar_title,calendar_location,"
        "race_event_id,race_date,race_name,race_location,confidence,would_apply"
    )
    for p in proposals:
        print(
            f"{p.calendar_event_id},{p.calendar_date},{p.calendar_title!r},"
            f"{p.calendar_location!r},{p.race_event_id},{p.race_date},"
            f"{p.race_name!r},{p.race_location!r},{p.confidence},{apply}"
        )


async def _apply(proposals: list[MatchProposal], *, auto_high: bool) -> int:
    from app.database import get_async_session_factory
    from app.models.calendar_event import CalendarEvent

    session_factory = get_async_session_factory()
    applied = 0
    async with session_factory() as session:
        for p in proposals:
            ok = True
            if not (auto_high and p.confidence == "high"):
                ans = input(
                    f"Apply calendar_event {p.calendar_event_id} -> "
                    f"race_event {p.race_event_id} ({p.confidence})? [y/N] "
                ).strip().lower()
                ok = ans == "y"
            if not ok:
                continue
            cal = await session.get(CalendarEvent, p.calendar_event_id)
            if cal is None:
                continue
            cal.race_event_id = p.race_event_id
            applied += 1
        await session.commit()
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Si se pasa, ejecuta los UPDATEs (interactivo).",
    )
    parser.add_argument(
        "--auto-high",
        action="store_true",
        help="Junto con --apply, aplica matches de confianza alta sin preguntar.",
    )
    args = parser.parse_args()

    proposals = asyncio.run(_propose_matches())
    if not proposals:
        print("# No hay competencias sin race_event_id que tengan match.")
        return 0

    _print_table(proposals, apply=args.apply)

    if args.apply:
        applied = asyncio.run(_apply(proposals, auto_high=args.auto_high))
        print(f"\n# applied={applied}/{len(proposals)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
