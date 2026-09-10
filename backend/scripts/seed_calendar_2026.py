"""Carga en la base las carreras que faltan del calendario 2026.

Motivo: en septiembre de 2026 la base no tenía NINGUNA carrera futura, así
que el boletín familiar caía a una lista literal del código que anunciaba a
las familias una válida en Roldanillo el 12 de septiembre. El calendario
oficial (afiche de la Comisión Vallecaucana) la fija el 7-8 de noviembre.

Qué crea (nada más, y solo si falta):

- Serie ``Copa Let's GO Interdepartamental`` 2026.
- ``I Válida Copa Let's GO — Alcalá``   dom 13 sep 2026
- ``VI Válida XCO``                     dom 18 oct 2026 · Yumbo
- ``VII Válida XCO``                    dom  8 nov 2026 · Roldanillo

De cada carrera crea también su evento de calendario (``competition``,
07:00-12:00, zona ``America/Bogota``) y enlaza ambos lados.

Es IDEMPOTENTE: identifica lo ya existente por (serie, fecha) y lo omite, así
que volver a correrlo no duplica nada.

Uso (desde ``backend/`` con el venv activo)::

    python scripts/seed_calendar_2026.py                      # simulacro, no escribe
    python scripts/seed_calendar_2026.py --commit             # escribe de verdad
    python scripts/seed_calendar_2026.py --commit --env-file .env    # base local

Por defecto apunta a ``.env.production``. Solo lee las variables ``MYSQL_*``
del env-file y nunca imprime su valor.

Nota sobre el nivel de la serie: el enum ``race_series.level`` solo admite
``departmental`` y ``national``; la Copa Let's GO es interdepartamental, así
que se registra como ``departmental``, que es el valor más cercano
disponible. Cambiarlo exigiría una migración de enum.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, time
from pathlib import Path

_MYSQL_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB")

COACH_USER_ID = 2
CLUB_ID = 1
COPA_VALLE_SERIES_ID = 2

LETS_GO = {
    "name": "Copa Let's GO Interdepartamental",
    "season_year": 2026,
    "kind": "cup",
    "level": "departmental",
    "points_scheme_code": "copa_lets_go_2026",
    "organizer": "Inter-American XCO Cup",
}

#: (clave de serie, nº de válida, nombre, fecha, lugar)
#: ``series`` es ``"lets_go"`` (la serie que crea este script) o un id entero.
RACES = [
    ("lets_go", 1, "I Válida Copa Let's GO — Alcalá", date(2026, 9, 13), "Alcalá"),
    (COPA_VALLE_SERIES_ID, 6, "VI Válida XCO", date(2026, 10, 18), "Yumbo"),
    (COPA_VALLE_SERIES_ID, 7, "VII Válida XCO", date(2026, 11, 8), "Roldanillo"),
]


def _load_env(env_file: Path) -> None:
    from dotenv import dotenv_values

    if not env_file.exists():
        sys.exit(f"No existe {env_file}.")
    values = dotenv_values(env_file)
    missing = [k for k in _MYSQL_KEYS if not values.get(k)]
    if missing:
        sys.exit(f"Faltan variables en {env_file.name}: {', '.join(missing)}")
    for key in _MYSQL_KEYS:
        os.environ[key] = str(values[key])


async def _run(commit: bool) -> int:
    import aiomysql

    now = datetime.now()
    conn = await aiomysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASS"],
        db=os.environ["MYSQL_DB"],
        autocommit=False,
    )
    created: list[str] = []
    skipped: list[str] = []
    try:
        async with conn.cursor() as cur:
            # --- Serie Copa Let's GO (solo si no existe ya) -----------------
            await cur.execute(
                "SELECT id FROM race_series WHERE name=%s AND season_year=%s",
                (LETS_GO["name"], LETS_GO["season_year"]),
            )
            row = await cur.fetchone()
            if row:
                lets_go_id = row[0]
                skipped.append(f"serie «{LETS_GO['name']}» ya existía (id={lets_go_id})")
            else:
                await cur.execute(
                    "INSERT INTO race_series (name, season_year, kind, level,"
                    " points_scheme_code, organizer, created_at, updated_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        LETS_GO["name"], LETS_GO["season_year"], LETS_GO["kind"],
                        LETS_GO["level"], LETS_GO["points_scheme_code"],
                        LETS_GO["organizer"], now, now,
                    ),
                )
                lets_go_id = cur.lastrowid
                created.append(f"serie «{LETS_GO['name']}» (id={lets_go_id})")

            # --- Carreras + sus eventos de calendario -----------------------
            for series_key, seq, name, event_date, location in RACES:
                series_id = lets_go_id if series_key == "lets_go" else series_key

                await cur.execute(
                    "SELECT id FROM race_events WHERE series_id=%s AND event_date=%s",
                    (series_id, event_date),
                )
                row = await cur.fetchone()
                if row:
                    skipped.append(f"{name} · {event_date} ya existía (id={row[0]})")
                    continue

                await cur.execute(
                    "INSERT INTO race_events (series_id, sequence_number, name, event_date,"
                    " location, is_championship, status, created_by_user_id, created_at,"
                    " updated_at) VALUES (%s,%s,%s,%s,%s,0,'scheduled',%s,%s,%s)",
                    (series_id, seq, name, event_date, location, COACH_USER_ID, now, now),
                )
                race_id = cur.lastrowid

                await cur.execute(
                    "INSERT INTO calendar_events (club_id, event_type, status, title,"
                    " start_at, end_at, all_day, timezone, location, race_event_id,"
                    " created_by_user_id, created_at, updated_at)"
                    " VALUES (%s,'competition','scheduled',%s,%s,%s,0,'America/Bogota',%s,%s,%s,%s,%s)",
                    (
                        CLUB_ID, name,
                        datetime.combine(event_date, time(7, 0)),
                        datetime.combine(event_date, time(12, 0)),
                        location, race_id, COACH_USER_ID, now, now,
                    ),
                )
                cal_id = cur.lastrowid
                await cur.execute(
                    "UPDATE race_events SET calendar_event_id=%s WHERE id=%s",
                    (cal_id, race_id),
                )
                created.append(
                    f"{name} · {event_date} · {location} (carrera id={race_id}, calendario id={cal_id})"
                )

            await cur.execute(
                "SELECT name, event_date, location FROM race_events"
                " WHERE event_date > CURDATE() ORDER BY event_date"
            )
            upcoming = await cur.fetchall()

        for line in created:
            print(f"  + {line}")
        for line in skipped:
            print(f"  = {line}")
        print("\n  Carreras futuras en la base:")
        for name, event_date, location in upcoming:
            print(f"    {event_date}  {name} · {location}")

        if commit:
            await conn.commit()
            print("\nCOMMIT aplicado.")
        else:
            await conn.rollback()
            print("\nSIMULACRO: nada se escribió. Repite con --commit para aplicarlo.")
        return 0
    except Exception as exc:
        await conn.rollback()
        print(f"ROLLBACK — {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--commit", action="store_true", help="escribe de verdad (por defecto simulacro)")
    parser.add_argument("--env-file", default=".env.production", help="archivo con las MYSQL_* ")
    args = parser.parse_args()

    _load_env(Path(args.env_file))
    return asyncio.run(_run(args.commit))


if __name__ == "__main__":
    sys.exit(main())
