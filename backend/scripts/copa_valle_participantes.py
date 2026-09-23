"""Agregados de participación por válida (read-only sobre prod).

Extrae SOLO conteos agregados — ningún nombre de corredor, ningún id de atleta.
Nunca escribe en la base: la conexión termina en rollback().

Uso:
    cd backend && source .venv/bin/activate
    python scripts/copa_valle_participantes.py --year 2026
Salida: output/copa-valle-2026/participantes.json
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[2]

# Agrupación de categorías oficiales en grupos de edad legibles.
GRUPOS = {
    "Teteros": ["TET_SP", "TET_CP"],
    "Preinfantil M": ["PRE_A", "PRE_B"],
    "Preinfantil F": ["PRE_A_F", "PRE_B_F"],
    "Infantil M": ["INF_A", "INF_B"],
    "Infantil F": ["INF_A_F", "INF_B_F"],
    "Prejuvenil M": ["PJUV_A", "PJUV_B"],
    "Prejuvenil F": ["PJUV_A_F", "PJUV_B_F"],
    "Junior M": ["JUN_M"],
    "Junior F": ["JUN_F"],
    "Élite M": ["ELITE_M"],
    "Élite F": ["ELITE_F"],
    "Promocional": ["PROMO"],
    "Máster A": ["MAS_A"],
    "Máster B1": ["MAS_B1"],
    "Máster B2": ["MAS_B2"],
    "Máster C1": ["MAS_C1"],
    "Máster C2": ["MAS_C2"],
    "Máster D": ["MAS_D"],
    "Máster F": ["MAS_F"],
}

GRUPO_DE = {code: grupo for grupo, codes in GRUPOS.items() for code in codes}


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / "backend" / ".env.production").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()

    env = load_env()
    conn = pymysql.connect(
        host=env["MYSQL_HOST"],
        port=int(env["MYSQL_PORT"]),
        user=env["MYSQL_USER"],
        password=env["MYSQL_PASS"],
        database=env["MYSQL_DB"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
    )
    out: dict[str, object] = {"year": args.year}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, short_name, season_year, kind, level, organizer "
                "FROM race_series WHERE season_year = %s ORDER BY id",
                (args.year,),
            )
            out["series"] = cur.fetchall()

            cur.execute(
                """
                SELECT e.id, e.series_id, s.name AS series_name, s.short_name AS series_short,
                       s.kind AS series_kind, e.sequence_number, e.name, e.event_date,
                       e.location, e.status, e.is_championship,
                       COUNT(r.id) AS inscripciones,
                       COUNT(DISTINCT r.competitor_id) AS corredores_unicos,
                       COUNT(DISTINCT r.category_id) AS categorias,
                       COUNT(DISTINCT NULLIF(TRIM(c.club_text), '')) AS clubes,
                       SUM(r.status = 'finished') AS finished,
                       SUM(r.status = 'minus_laps') AS minus_laps,
                       SUM(r.status = 'dnf') AS dnf,
                       SUM(r.status = 'dsq') AS dsq,
                       SUM(r.status = 'dns') AS dns,
                       SUM(c.sex = 'F') AS femenino,
                       SUM(c.sex = 'M') AS masculino,
                       SUM(c.sex IS NULL) AS sexo_sin_dato
                FROM race_events e
                JOIN race_series s ON s.id = e.series_id
                LEFT JOIN race_results r ON r.event_id = e.id AND r.deleted_at IS NULL
                LEFT JOIN race_competitors c ON c.id = r.competitor_id
                WHERE s.season_year = %s
                GROUP BY e.id
                ORDER BY e.event_date, e.sequence_number
                """,
                (args.year,),
            )
            out["eventos"] = cur.fetchall()

            cur.execute(
                """
                SELECT e.id AS event_id, cat.code, cat.label, cat.sex, cat.tier,
                       cat.sort_order, COUNT(r.id) AS inscripciones
                FROM race_results r
                JOIN race_events e ON e.id = r.event_id
                JOIN race_series s ON s.id = e.series_id
                JOIN race_categories cat ON cat.id = r.category_id
                WHERE s.season_year = %s AND r.deleted_at IS NULL
                GROUP BY e.id, cat.id
                ORDER BY e.id, cat.sort_order, cat.code
                """,
                (args.year,),
            )
            out["por_categoria"] = cur.fetchall()

            cur.execute(
                """
                SELECT s.id AS series_id, COUNT(DISTINCT r.competitor_id) AS corredores_unicos_temporada,
                       COUNT(DISTINCT NULLIF(TRIM(c.club_text), '')) AS clubes_temporada
                FROM race_results r
                JOIN race_events e ON e.id = r.event_id
                JOIN race_series s ON s.id = e.series_id
                JOIN race_competitors c ON c.id = r.competitor_id
                WHERE s.season_year = %s AND r.deleted_at IS NULL
                GROUP BY s.id
                """,
                (args.year,),
            )
            out["totales_serie"] = cur.fetchall()

            # Distribución de asistencia: en cuántas válidas corrió cada corredor (agregado)
            cur.execute(
                """
                SELECT s.id AS series_id, validas_corridas, COUNT(*) AS corredores
                FROM (
                    SELECT e.series_id AS sid, r.competitor_id,
                           COUNT(DISTINCT r.event_id) AS validas_corridas
                    FROM race_results r
                    JOIN race_events e ON e.id = r.event_id
                    JOIN race_series s2 ON s2.id = e.series_id
                    WHERE s2.season_year = %s AND r.deleted_at IS NULL
                    GROUP BY e.series_id, r.competitor_id
                ) t
                JOIN race_series s ON s.id = t.sid
                GROUP BY s.id, validas_corridas
                ORDER BY s.id, validas_corridas
                """,
                (args.year,),
            )
            out["distribucion_asistencia"] = cur.fetchall()
            # Asignación de cada corredor a UNA sola categoría (la última corrida en la
            # temporada) para poder contar personas distintas por grupo de edad y rama
            # sin contar dos veces a quien corrió varias válidas. Se traen filas mínimas
            # (id interno + categoría + fecha), nunca nombres, y solo se persisten conteos.
            cur.execute(
                """
                SELECT e.series_id, r.competitor_id, e.event_date, cat.code, cat.sex, cat.sort_order
                FROM race_results r
                JOIN race_events e ON e.id = r.event_id
                JOIN race_series s ON s.id = e.series_id
                JOIN race_categories cat ON cat.id = r.category_id
                WHERE s.season_year = %s AND r.deleted_at IS NULL
                """,
                (args.year,),
            )
            crudo = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()

    ultimas: dict[tuple[int, int], dict] = {}
    for row in crudo:
        key = (row["series_id"], row["competitor_id"])
        prev = ultimas.get(key)
        if prev is None or (row["event_date"], row["sort_order"]) > (prev["event_date"], prev["sort_order"]):
            ultimas[key] = row
    por_grupo: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    por_rama: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    multi: dict[int, set] = collections.defaultdict(set)
    grupos_vistos: dict[tuple[int, int], set] = collections.defaultdict(set)
    for row in crudo:
        grupos_vistos[(row["series_id"], row["competitor_id"])].add(GRUPO_DE.get(row["code"], "otros"))
    for (sid, cid), row in ultimas.items():
        por_grupo[sid][GRUPO_DE.get(row["code"], "otros")] += 1
        por_rama[sid][row["sex"]] += 1
        if len(grupos_vistos[(sid, cid)]) > 1:
            multi[sid].add(cid)
    out["unicos_por_grupo"] = {str(k): dict(v) for k, v in por_grupo.items()}
    out["unicos_por_rama"] = {str(k): dict(v) for k, v in por_rama.items()}
    out["corredores_multi_grupo"] = {str(k): len(v) for k, v in multi.items()}

    dest = ROOT / "output" / f"copa-valle-{args.year}" / "participantes.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -> {dest}")
    for ev in out["eventos"]:
        print(f"  [{ev['series_short'] or ev['series_name']}] V{ev['sequence_number']} "
              f"{ev['event_date']} {ev['location'] or ''}: {ev['inscripciones']} inscripciones")


if __name__ == "__main__":
    main()
