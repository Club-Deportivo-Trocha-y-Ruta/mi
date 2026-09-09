"""Realinea los eventos de calendario cuya fecha no coincide con su carrera.

Un ``calendar_event`` de tipo competición apunta a un ``race_event`` mediante
``race_event_id``. Las dos filas guardan la fecha por separado, y nada obliga
hoy a que coincidan: si alguien corrige la fecha de la carrera, el evento del
calendario se queda donde estaba y el desfase no lo detecta nadie.

Caso real que motivó el script: el evento «V Válida» estaba fechado el 2 de
septiembre de 2026 mientras la carrera correspondía al 2 de agosto — un mes
de diferencia. El boletín familiar lee el calendario, así que anunciaba a las
familias un evento del club en una fecha en la que no había nada.

Criterio: manda la fecha de la CARRERA (``race_events.event_date``), que es
la que viene del calendario oficial de la Comisión. Del evento de calendario
se conserva la hora del día, así que un evento de 07:00 a 12:00 sigue siendo
de 07:00 a 12:00, solo que en el día correcto.

Uso (desde ``backend/`` con el venv activo)::

    python scripts/fix_calendar_race_dates.py                   # simulacro
    python scripts/fix_calendar_race_dates.py --commit          # aplica
    python scripts/fix_calendar_race_dates.py --commit --env-file .env

Solo lee las variables ``MYSQL_*`` del env-file y nunca imprime su valor. Es
idempotente: una segunda corrida no encuentra nada que corregir.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

_MYSQL_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASS", "MYSQL_DB")


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
                "SELECT ce.id, ce.title, ce.start_at, ce.end_at, re.event_date, re.location"
                " FROM calendar_events ce"
                " JOIN race_events re ON re.id = ce.race_event_id"
                " WHERE DATE(ce.start_at) <> re.event_date"
                " ORDER BY re.event_date"
            )
            rows = await cur.fetchall()
            if not rows:
                print("  Nada que corregir: toda fecha de calendario coincide con su carrera.")
                await conn.rollback()
                return 0

            now = datetime.now()
            for cal_id, title, start_at, end_at, race_date, location in rows:
                new_start = datetime.combine(race_date, start_at.time())
                # `end_at` conserva su hora y se ancla al mismo día que el
                # inicio; un evento que cruzaba la medianoche mantiene su
                # duración corriendo el fin al día siguiente.
                new_end = datetime.combine(race_date, end_at.time())
                if new_end < new_start:
                    new_end = new_end.replace(day=new_end.day + 1)

                print(f"  «{title}» ({location})")
                print(f"    antes: {start_at:%Y-%m-%d %H:%M} → {end_at:%Y-%m-%d %H:%M}")
                print(f"    ahora: {new_start:%Y-%m-%d %H:%M} → {new_end:%Y-%m-%d %H:%M}")

                await cur.execute(
                    "UPDATE calendar_events SET start_at=%s, end_at=%s, updated_at=%s WHERE id=%s",
                    (new_start, new_end, now, cal_id),
                )

        if commit:
            await conn.commit()
            print(f"\nCOMMIT aplicado: {len(rows)} evento(s) realineado(s).")
        else:
            await conn.rollback()
            print(f"\nSIMULACRO: {len(rows)} evento(s) por corregir. Repite con --commit.")
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
