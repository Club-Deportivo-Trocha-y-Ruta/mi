"""Completa la Copa Let's GO Interdepartamental 2026 con sus cinco válidas.

Corrección de una carga previa: Alcalá se registró como «I Válida» cuando en
realidad es la **Gran Final** de la copa, la quinta fecha. El club no asistió
a las cuatro anteriores, pero forman parte de la serie y hacen falta para que
la numeración de la final sea correcta y para que cualquier análisis por copa
tenga el calendario completo.

Calendario oficial (afiche de Let's Go Productions, temporada 2026):

    I   Válida   Quindío              8 feb
    II  Válida   Sevilla (Valle)     12 abr
    III Válida   Viterbo (Caldas)    24 may   (movida desde el 31 may por
                                               las elecciones presidenciales)
    IV  Válida   Anserma (Caldas)     9 ago   (movida desde el 2 ago por la
                                               alianza con la Copa Valle)
    Gran Final   Alcalá (Valle)      12-13 sep — sáb XCR Team Relay,
                                      dom XCO individual. Es además la
                                      primera válida interamericana,
                                      clasificatoria a Querétaro (México).

Qué hace:

- Crea las cuatro válidas anteriores como ``race_events`` en estado
  ``completed`` (ya ocurrieron). **No** les crea evento de calendario: el
  club no asistió, así que no deben aparecer en su agenda; existen solo como
  contexto de la serie.
- Renumera Alcalá a la posición 5 y le corrige el nombre, tanto en la carrera
  como en su evento de calendario.

La fecha registrada para Alcalá es el **domingo 13**, que es el día del XCO
individual; el sábado 12 es el relevo por equipos.

Uso (desde ``backend/`` con el venv activo)::

    python scripts/fix_lets_go_series_2026.py                 # simulacro
    python scripts/fix_lets_go_series_2026.py --commit        # aplica

Idempotente: identifica lo existente por (serie, fecha) y no duplica.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime
from pathlib import Path

_MYSQL_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB")

SERIES_NAME = "Copa Let's GO Interdepartamental"
SEASON = 2026
COACH_USER_ID = 2

#: Válidas anteriores: (nº, nombre, fecha, lugar). El club no asistió.
PAST_ROUNDS = [
    (1, "I Válida XCO — Quindío", date(2026, 2, 8), "Quindío"),
    (2, "II Válida XCO — Sevilla", date(2026, 4, 12), "Sevilla (Valle)"),
    (3, "III Válida XCO — Viterbo", date(2026, 5, 24), "Viterbo (Caldas)"),
    (4, "IV Válida XCO — Anserma", date(2026, 8, 9), "Anserma (Caldas)"),
]

FINAL_DATE = date(2026, 9, 13)
FINAL_NAME = "Gran Final XCO — Alcalá"
FINAL_SEQUENCE = 5


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
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id FROM race_series WHERE name=%s AND season_year=%s",
                (SERIES_NAME, SEASON),
            )
            row = await cur.fetchone()
            if row is None:
                print(f"No existe la serie «{SERIES_NAME}» {SEASON}.", file=sys.stderr)
                await conn.rollback()
                return 1
            series_id = row[0]
            print(f"  serie id={series_id} · {SERIES_NAME} {SEASON}")

            # --- La final: renumerar y renombrar (VA PRIMERO) -----------------
            await cur.execute(
                "SELECT id, sequence_number, name, calendar_event_id FROM race_events"
                " WHERE series_id=%s AND event_date=%s",
                (series_id, FINAL_DATE),
            )
            final = await cur.fetchone()
            if final is None:
                print(f"  ! No se encontró la carrera de Alcalá ({FINAL_DATE}).", file=sys.stderr)
            else:
                race_id, seq, name, cal_id = final
                if seq == FINAL_SEQUENCE and name == FINAL_NAME:
                    print(f"  = la final ya estaba como «{FINAL_NAME}» (nº {FINAL_SEQUENCE})")
                else:
                    print(f"  ~ final id={race_id}: «{name}» (nº {seq}) → «{FINAL_NAME}» (nº {FINAL_SEQUENCE})")
                    await cur.execute(
                        "UPDATE race_events SET sequence_number=%s, name=%s, updated_at=%s WHERE id=%s",
                        (FINAL_SEQUENCE, FINAL_NAME, now, race_id),
                    )
                    if cal_id:
                        await cur.execute(
                            "UPDATE calendar_events SET title=%s, updated_at=%s WHERE id=%s",
                            (FINAL_NAME, now, cal_id),
                        )
                        print(f"    y su evento de calendario id={cal_id}")

            # --- Válidas anteriores ------------------------------------------
            # Va después de renumerar la final: `uq_race_events_series_sequence`
            # es único por (serie, nº), y Alcalá ocupaba el nº 1 que ahora usa
            # la válida de Quindío. Insertar primero chocaría con esa clave.
            for seq, name, event_date, location in PAST_ROUNDS:
                await cur.execute(
                    "SELECT id FROM race_events WHERE series_id=%s AND event_date=%s",
                    (series_id, event_date),
                )
                if await cur.fetchone():
                    print(f"  = {name} · {event_date} ya existía")
                    continue
                await cur.execute(
                    "INSERT INTO race_events (series_id, sequence_number, name, event_date,"
                    " location, is_championship, status, created_by_user_id, created_at,"
                    " updated_at) VALUES (%s,%s,%s,%s,%s,0,'completed',%s,%s,%s)",
                    (series_id, seq, name, event_date, location, COACH_USER_ID, now, now),
                )
                print(f"  + {name} · {event_date} · {location} (id={cur.lastrowid}, sin evento de calendario)")

            await cur.execute(
                "SELECT sequence_number, name, event_date, location, status FROM race_events"
                " WHERE series_id=%s ORDER BY sequence_number",
                (series_id,),
            )
            print("\n  Serie completa:")
            for seq, name, event_date, location, status in await cur.fetchall():
                print(f"    {seq}. {event_date}  {name} · {location} · {status}")

        if commit:
            await conn.commit()
            print("\nCOMMIT aplicado.")
        else:
            await conn.rollback()
            print("\nSIMULACRO: nada se escribió. Repite con --commit.")
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
    parser.add_argument("--commit", action="store_true", help="aplica (por defecto simulacro)")
    parser.add_argument("--env-file", default=".env.production", help="archivo con las MYSQL_*")
    args = parser.parse_args()

    _load_env(Path(args.env_file))
    return asyncio.run(_run(args.commit))


if __name__ == "__main__":
    sys.exit(main())
