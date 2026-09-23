"""Infografía de participación histórica en la válida de Yumbo + proyección del año en curso.

Lee producción en modo solo lectura (la conexión termina en rollback) y extrae SOLO
conteos agregados — ningún nombre de corredor, ningún id de atleta sale del script.

Proyección: razón año contra año de las sedes que se repiten entre la temporada
anterior y la actual (misma sede, mismo circuito), aplicada al dato de Yumbo del año
anterior. La dispersión de esas razones da el intervalo (t de Student, n-1 gl).

Uso:
    cd backend && source .venv/bin/activate
    python scripts/infografia_yumbo.py --year 2026
Salida: output/copa-valle-yumbo/participacion-yumbo-<year>.{pdf,png,html,json}
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from copa_valle_participantes import load_env  # noqa: E402
from infografia_participacion import (  # noqa: E402
    GRID, INK, INK2, INK3, PLANE, S1, S2, S3, SURFACE, MESES, col_bar, row_bar,
)

ROOT = Path(__file__).resolve().parents[2]
SEDE = "Yumbo"
SERIE = "Copa Valle de Ciclomontañismo"
# Grupos de edad; incluye los códigos históricos (2024–2025) que la copa ya no usa.
GRUPOS = [
    ("Teteros (hasta 5)", ["TET_SP", "TET_CP"]),
    ("Preinfantil M (6-8)", ["PRE_A", "PRE_B"]),
    ("Preinfantil F (6-8)", ["PRE_A_F", "PRE_B_F", "PRE_F_U"]),
    ("Infantil M (9-12)", ["INF_A", "INF_B"]),
    ("Infantil F (9-12)", ["INF_A_F", "INF_B_F"]),
    ("Prejuvenil M (13-14)", ["PJUV_A", "PJUV_B"]),
    ("Prejuvenil F (13-14)", ["PJUV_A_F", "PJUV_B_F"]),
    ("Junior M (15-16)", ["JUN_M"]),
    ("Junior F (15-16)", ["JUN_F"]),
    ("Élite M (17+)", ["ELITE_M"]),
    ("Élite F (17+)", ["ELITE_F"]),
    ("Promocional", ["PROMO"]),
    ("Máster A (30-39)", ["MAS_A"]),
    ("Máster B (40-49)", ["MAS_B1", "MAS_B2", "MAS_B_2025"]),
    ("Máster C (50-59)", ["MAS_C1", "MAS_C2", "MAS_C_2025"]),
    ("Máster D (60+)", ["MAS_D"]),
    ("Máster F (30+)", ["MAS_F"]),
]
# Cuantiles t de Student bilaterales por grados de libertad (80 % y 95 %).
T80 = {1: 3.078, 2: 1.886, 3: 1.638, 4: 1.533, 5: 1.476, 6: 1.440, 7: 1.415}
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365}


def t_cdf(t: float, df: int) -> float:
    """CDF de t de Student por integración numérica (Simpson) — sin scipy."""
    c = math.gamma((df + 1) / 2) / (math.sqrt(df * math.pi) * math.gamma(df / 2))
    f = lambda x: c * (1 + x * x / df) ** (-(df + 1) / 2)  # noqa: E731
    a, b, n = 0.0, abs(t), 2000
    h = (b - a) / n
    s = f(a) + f(b) + sum((4 if i % 2 else 2) * f(a + i * h) for i in range(1, n))
    area = s * h / 3
    return 0.5 + area if t >= 0 else 0.5 - area


def sede_base(loc: str | None) -> str:
    return (loc or "").split(" (")[0].split(",")[0].strip()


def fetch() -> tuple[list[dict], list[dict]]:
    env = load_env()
    conn = pymysql.connect(
        host=env["MYSQL_HOST"], port=int(env["MYSQL_PORT"]), user=env["MYSQL_USER"],
        password=env["MYSQL_PASS"], database=env["MYSQL_DB"], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, connect_timeout=30,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, s.season_year, e.sequence_number, e.event_date, e.location, e.status,
                       COUNT(DISTINCT r.competitor_id) AS corredores,
                       COUNT(DISTINCT r.category_id) AS categorias,
                       COUNT(DISTINCT NULLIF(TRIM(c.club_text), '')) AS clubes,
                       COUNT(DISTINCT CASE WHEN cat.sex = 'F' THEN r.competitor_id END) AS femenino,
                       COUNT(DISTINCT CASE WHEN r.status IN ('finished','minus_laps') THEN r.competitor_id END) AS terminaron
                FROM race_events e
                JOIN race_series s ON s.id = e.series_id
                LEFT JOIN race_results r ON r.event_id = e.id AND r.deleted_at IS NULL
                LEFT JOIN race_competitors c ON c.id = r.competitor_id
                LEFT JOIN race_categories cat ON cat.id = r.category_id
                WHERE s.name = %s
                GROUP BY e.id
                ORDER BY e.event_date
                """,
                (SERIE,),
            )
            eventos = cur.fetchall()
            ids = [e["id"] for e in eventos if sede_base(e["location"]) == SEDE]
            cur.execute(
                f"""
                SELECT r.event_id, cat.code, COUNT(DISTINCT r.competitor_id) AS n
                FROM race_results r JOIN race_categories cat ON cat.id = r.category_id
                WHERE r.deleted_at IS NULL AND r.event_id IN ({",".join(["%s"] * len(ids))})
                GROUP BY r.event_id, cat.code
                """,
                ids,
            )
            por_cat = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()
    return eventos, por_cat


def proyectar(eventos: list[dict], year: int) -> dict:
    corridas = [e for e in eventos if int(e["corredores"]) > 0]
    prev = {sede_base(e["location"]): int(e["corredores"]) for e in corridas if e["season_year"] == year - 1}
    act = {sede_base(e["location"]): int(e["corredores"]) for e in corridas if e["season_year"] == year}
    pares = sorted(((s, prev[s], act[s]) for s in act if s in prev), key=lambda p: p[0])
    razones = [a / p for _, p, a in pares]
    n = len(razones)
    media = sum(razones) / n
    sd = math.sqrt(sum((r - media) ** 2 for r in razones) / (n - 1))
    sd_pred = sd * math.sqrt(1 + 1 / n)  # incertidumbre de un año nuevo, no solo de la media
    base = prev[SEDE]
    df = n - 1
    centro = base * media

    def rango(tq: float) -> tuple[int, int]:
        return round(base * (media - tq * sd_pred)), round(base * (media + tq * sd_pred))

    def p_mayor(umbral: float) -> float:
        return 1 - t_cdf((umbral / base - media) / sd_pred, df)

    # Contraste 1: Yumbo como fracción del promedio de su temporada × promedio del año actual.
    prom = {y: [int(e["corredores"]) for e in corridas if e["season_year"] == y] for y in (year - 2, year - 1, year)}
    yum = {e["season_year"]: int(e["corredores"]) for e in corridas if sede_base(e["location"]) == SEDE}
    fracs = [yum[y] / (sum(prom[y]) / len(prom[y])) for y in (year - 2, year - 1) if y in yum and prom[y]]
    alt_frac = round(sum(fracs) / len(fracs) * sum(prom[year]) / len(prom[year]))
    # Contraste 2: extrapolación lineal solo con Yumbo (dos puntos).
    alt_lineal = round(yum[year - 1] + (yum[year - 1] - yum[year - 2])) if year - 2 in yum else None

    return {
        "pares": pares, "razones": razones, "media": media, "sd_pred": sd_pred, "df": df,
        "centro": round(centro), "r80": rango(T80[df]), "r95": rango(T95[df]),
        "p_supera_prev": p_mayor(base), "p_supera_200": p_mayor(199.5),
        "p_supera_max": p_mayor(max(yum.values())),
        "alt_frac": alt_frac, "alt_lineal": alt_lineal,
        "prom_temporada": {y: round(sum(v) / len(v)) for y, v in prom.items() if v},
        "n_temporada": {y: len(v) for y, v in prom.items()},
    }


def fecha(d) -> str:
    return f"{d.day} {MESES[d.month]} {d.year}"


def chart_anios(hist: list[tuple[int, int, str]], proy: dict, year: int, fecha_proy: str) -> str:
    W, H = 712, 172
    ml, mr, mt, mb = 40, 20, 24, 40
    plot_h = H - mt - mb
    top = 300
    slots = len(hist) + 1
    slot_w = (W - ml - mr) / slots
    bw = 92.0
    y_of = lambda v: mt + plot_h * (1 - v / top)  # noqa: E731
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    for t in range(0, top + 1, 50):
        p.append(f'<line x1="{ml}" y1="{y_of(t):.1f}" x2="{W - mr}" y2="{y_of(t):.1f}" stroke="{GRID}"/>')
        p.append(f'<text x="{ml - 8}" y="{y_of(t) + 3.5:.1f}" text-anchor="end" font-size="10" fill="{INK3}">{t}</text>')
    centros = []
    for i, (yr, v, f) in enumerate(hist):
        cx = ml + slot_w * i + slot_w / 2
        centros.append((cx, v))
        p.append(col_bar(cx - bw / 2, y_of(v), bw, plot_h * v / top, 5, S1))
        p.append(f'<text x="{cx:.1f}" y="{y_of(v) - 9:.1f}" text-anchor="middle" font-size="18" font-weight="700" fill="{INK}">{v}</text>')
        p.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 17:.1f}" text-anchor="middle" font-size="13" font-weight="700" fill="{INK}">{yr}</text>')
        p.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 32:.1f}" text-anchor="middle" font-size="10" fill="{INK3}">{f}</text>')
    # Año proyectado: barra punteada + banda del 80 % + bigotes del 95 %.
    cx = ml + slot_w * len(hist) + slot_w / 2
    c = proy["centro"]
    lo80, hi80 = proy["r80"]
    lo95, hi95 = proy["r95"]
    p.append(f'<rect x="{cx - bw / 2:.1f}" y="{y_of(c):.1f}" width="{bw}" height="{plot_h * c / top:.1f}" rx="5" '
             f'fill="{S2}" fill-opacity="0.14" stroke="{S2}" stroke-width="1.6" stroke-dasharray="5 4"/>')
    p.append(f'<rect x="{cx - 14:.1f}" y="{y_of(hi80):.1f}" width="28" height="{y_of(lo80) - y_of(hi80):.1f}" rx="3" fill="{S2}" fill-opacity="0.35"/>')
    p.append(f'<line x1="{cx:.1f}" y1="{y_of(hi95):.1f}" x2="{cx:.1f}" y2="{y_of(lo95):.1f}" stroke="{S2}" stroke-width="1.4"/>')
    for v in (lo95, hi95):
        p.append(f'<line x1="{cx - 8:.1f}" y1="{y_of(v):.1f}" x2="{cx + 8:.1f}" y2="{y_of(v):.1f}" stroke="{S2}" stroke-width="1.4"/>')
    p.append(f'<line x1="{cx - bw / 2:.1f}" y1="{y_of(c):.1f}" x2="{cx + bw / 2:.1f}" y2="{y_of(c):.1f}" stroke="{S2}" stroke-width="2.4"/>')
    p.append(f'<text x="{cx + bw / 2 + 6:.1f}" y="{y_of(c) + 5:.1f}" font-size="18" font-weight="700" fill="{S2}">≈{c}</text>')
    p.append(f'<text x="{cx + bw / 2 + 6:.1f}" y="{y_of(c) + 19:.1f}" font-size="9.5" fill="{INK2}">{lo80}–{hi80}</text>')
    p.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 17:.1f}" text-anchor="middle" font-size="13" font-weight="700" fill="{S2}">{year} (proyección)</text>')
    p.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 32:.1f}" text-anchor="middle" font-size="10" fill="{INK3}">{fecha_proy}</text>')
    # Línea de tendencia que une los puntos reales con la proyección.
    pts = centros + [(cx, c)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y_of(v):.1f}" for i, (x, v) in enumerate(pts))
    p.append(f'<path d="{path}" fill="none" stroke="{INK2}" stroke-width="1.3" stroke-dasharray="2 4"/>')
    for x, v in centros:
        p.append(f'<circle cx="{x:.1f}" cy="{y_of(v):.1f}" r="3.2" fill="{INK}"/>')
    p.append(f'<line x1="{ml}" y1="{mt + plot_h:.1f}" x2="{W - mr}" y2="{mt + plot_h:.1f}" stroke="{INK3}"/>')
    p.append("</svg>")
    return "".join(p)


def chart_razones(pares: list[tuple[str, int, int]], media: float, year: int) -> str:
    W, H = 330, 112
    ml, mr, mt = 70, 44, 4
    rows = len(pares)
    slot = (H - mt - 20) / rows
    bh = 12.0
    lo, hi = 0.8, 1.1
    x_of = lambda r: ml + (W - ml - mr) * (r - lo) / (hi - lo)  # noqa: E731
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    x1 = x_of(1.0)
    for i, (s, a, b) in enumerate(pares):
        r = b / a
        y = mt + slot * i + (slot - bh) / 2
        color = S3 if r >= 1 else S2
        xa, xb = sorted((x1, x_of(r)))
        p.append(f'<rect x="{xa:.1f}" y="{y:.1f}" width="{xb - xa:.1f}" height="{bh}" rx="3" fill="{color}"/>')
        p.append(f'<text x="{ml - 6}" y="{y + bh - 2.5:.1f}" text-anchor="end" font-size="9.5" fill="{INK2}">{s}</text>')
        pct = round(100 * (r - 1))
        tx = xb + 5 if r >= 1 else xa - 5
        anchor = "start" if r >= 1 else "end"
        if r < 1 and xa - 40 < ml:
            tx, anchor = xb + 5, "start"
        p.append(f'<text x="{tx:.1f}" y="{y + bh - 2.5:.1f}" text-anchor="{anchor}" font-size="9.5" font-weight="700" fill="{INK}">{pct:+d} %</text>')
    yb = H - 14
    p.append(f'<line x1="{x1:.1f}" y1="{mt}" x2="{x1:.1f}" y2="{yb:.1f}" stroke="{INK3}"/>')
    xm = x_of(media)
    p.append(f'<line x1="{xm:.1f}" y1="{mt}" x2="{xm:.1f}" y2="{yb:.1f}" stroke="{INK}" stroke-width="1.4" stroke-dasharray="3 3"/>')
    p.append(f'<text x="{xm:.1f}" y="{H - 2}" text-anchor="middle" font-size="9" font-weight="700" fill="{INK}">promedio {round(100 * (media - 1)):+d} %</text>')
    p.append(f'<text x="{x1 + 3:.1f}" y="{H - 2}" font-size="9" fill="{INK3}">  igual</text>')
    p.append("</svg>")
    return "".join(p)


def chart_grupos_yoy(filas: list[tuple[str, int, int]], y0: int, y1: int) -> str:
    W, H = 712, 148
    gutter = 26.0
    col_w = (W - gutter) / 2
    ml, mr = 128, 60
    plot_w = col_w - ml - mr
    maxv = max(max(a, b) for _, a, b in filas)
    n_izq = (len(filas) + 1) // 2
    nfil = max(n_izq, len(filas) - n_izq)
    slot = H / nfil
    bh = 6.0
    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    for i, (label, a, b) in enumerate(filas):
        col, fila = (0, i) if i < n_izq else (1, i - n_izq)
        x0 = col * (col_w + gutter)
        y = slot * fila + (slot - 2 * bh - 2) / 2
        p.append(f'<text x="{x0 + ml - 8:.1f}" y="{y + bh + 4:.1f}" text-anchor="end" font-size="9.5" fill="{INK2}">{label}</text>')
        p.append(row_bar(x0 + ml, y, plot_w * a / maxv, bh, 3, INK3))
        p.append(row_bar(x0 + ml, y + bh + 2, plot_w * b / maxv, bh, 3, S1))
        d = b - a
        color = S3 if d > 0 else (S2 if d < 0 else INK3)
        p.append(f'<text x="{x0 + ml + plot_w * max(a, b) / maxv + 6:.1f}" y="{y + bh + 4:.1f}" font-size="9.5" fill="{INK}">'
                 f'<tspan font-weight="700">{b}</tspan> <tspan fill="{color}">({d:+d})</tspan></text>')
    p.append("</svg>")
    return "".join(p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--corte", default="22 de septiembre de 2026")
    args = ap.parse_args()

    if not os.environ.get("DYLD_FALLBACK_LIBRARY_PATH") and sys.platform == "darwin":
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib"
        os.execv(sys.executable, [sys.executable, *sys.argv])

    eventos, por_cat = fetch()
    yumbo = [e for e in eventos if sede_base(e["location"]) == SEDE]
    hist = [e for e in yumbo if int(e["corredores"]) > 0]
    prox = next(e for e in yumbo if e["season_year"] == args.year)
    pr = proyectar(eventos, args.year)

    y0, y1 = hist[-2]["season_year"], hist[-1]["season_year"]
    ev_id = {e["season_year"]: e["id"] for e in hist}
    cnt: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in por_cat:
        cnt[row["event_id"]][row["code"]] += int(row["n"])
    filas = []
    mapeados = {c for _, codes in GRUPOS for c in codes}
    sin_grupo = {c for ev in cnt.values() for c in ev if c not in mapeados}
    if sin_grupo:
        sys.exit(f"Códigos de categoría sin grupo: {sorted(sin_grupo)}")
    for label, codes in GRUPOS:
        a = sum(cnt[ev_id[y0]][c] for c in codes)
        b = sum(cnt[ev_id[y1]][c] for c in codes)
        if a or b:
            filas.append((label, a, b))

    ult, ante = hist[-1], hist[-2]
    var = round(100 * (int(ult["corredores"]) / int(ante["corredores"]) - 1))
    lo80, hi80 = pr["r80"]
    pct = lambda x: f"{round(100 * x)}&nbsp;%"  # noqa: E731
    prom = pr["prom_temporada"]

    detalle = "".join(
        f'<tr><td class="c">{e["season_year"]}</td><td class="c">V{e["sequence_number"]} de {sum(1 for x in eventos if x["season_year"] == e["season_year"])}</td>'
        f'<td class="c">{fecha(e["event_date"])}</td><td class="n b">{e["corredores"]}</td>'
        f'<td class="n">{e["terminaron"]}</td><td class="n">{e["femenino"]}</td><td class="n">{e["categorias"]}</td>'
        f'<td class="n">{e["clubes"]}</td><td class="n">{prom.get(e["season_year"], "—")}</td></tr>'
        for e in hist
    )
    pares_txt = ", ".join(f"{s} {a}→{b}" for s, a, b in pr["pares"])

    css = f"""
    @page {{ size: A4 portrait; margin: 9mm 10mm 7mm 10mm; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: Helvetica, Arial, sans-serif; color: {INK}; background: {PLANE}; margin: 0; }}
    .hd {{ border-bottom: 2.5px solid {INK}; padding-bottom: 5px; margin-bottom: 8px; }}
    .kicker {{ font-size: 9.5pt; letter-spacing: .09em; text-transform: uppercase; color: {INK2}; font-weight: 700; }}
    h1 {{ font-size: 21pt; margin: 3px 0 2px; line-height: 1.05; }}
    .sub {{ font-size: 9.5pt; color: {INK2}; }}
    .kpis {{ display: flex; gap: 6px; margin-bottom: 8px; }}
    .kpi {{ flex: 1; background: {SURFACE}; border: 1px solid {GRID}; border-radius: 7px; padding: 6px 8px; }}
    .kpi.hl {{ border-color: {S2}; border-width: 1.5px; }}
    .kpi .v {{ font-size: 19pt; font-weight: 700; line-height: 1; }}
    .kpi.hl .v {{ color: {S2}; }}
    .kpi .l {{ font-size: 8pt; color: {INK2}; margin-top: 3px; line-height: 1.2; }}
    .card {{ background: {SURFACE}; border: 1px solid {GRID}; border-radius: 7px; padding: 8px 11px; margin-bottom: 7px; }}
    .card h2 {{ font-size: 11pt; margin: 0 0 1px; }}
    .card .cap {{ font-size: 8.5pt; color: {INK2}; margin: 0 0 7px; line-height: 1.3; }}
    .cols {{ display: flex; gap: 7px; margin-bottom: 7px; }}
    .cols > div {{ flex: 1; margin-bottom: 0; }}
    .key {{ white-space: nowrap; }}
    .dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin: 0 4px 0 10px; }}
    ul.p {{ margin: 0; padding-left: 14px; font-size: 8.2pt; line-height: 1.3; }}
    ul.p b {{ color: {INK}; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; }}
    th {{ text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .05em;
         color: {INK2}; border-bottom: 1px solid {GRID}; padding: 3px 4px; }}
    td {{ padding: 2.6px 4px; border-bottom: 1px solid #f2f1ee; }}
    td.n, th.n {{ text-align: right; }}
    td.c, th.c {{ text-align: center; }}
    td.b {{ font-weight: 700; }}
    .foot {{ font-size: 7pt; color: {INK3}; line-height: 1.25; margin: 3px 0 0; }}
    .card:last-child {{ margin-bottom: 0; }}
    """

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="hd">
  <div class="kicker">Copa Valle de Ciclomontañismo · Sede {SEDE}</div>
  <h1>¿Cuántos corredores llegan a Yumbo?</h1>
  <div class="sub">Participación en la válida de {SEDE} {y0}–{y1} y proyección para la VI válida del {fecha(prox["event_date"])} · todos los corredores de los resultados oficiales, cada persona contada una vez · corte {args.corte}</div>
</div>

<div class="kpis">
  <div class="kpi"><div class="v">{ante["corredores"]}</div><div class="l">corredores en Yumbo {y0}</div></div>
  <div class="kpi"><div class="v">{ult["corredores"]}</div><div class="l">corredores en Yumbo {y1} ({var:+d} %)</div></div>
  <div class="kpi hl"><div class="v">≈{pr["centro"]}</div><div class="l">proyección {args.year} · rango probable {lo80}–{hi80}</div></div>
  <div class="kpi"><div class="v">{pct(pr["p_supera_200"])}</div><div class="l">probabilidad de pasar de 200 corredores</div></div>
  <div class="kpi"><div class="v">{pct(pr["p_supera_prev"])}</div><div class="l">probabilidad de superar los {ult["corredores"]} de {y1}</div></div>
</div>

<div class="card">
  <h2>Corredores por año en la válida de {SEDE}</h2>
  <p class="cap">Barras azules: dato oficial. Barra naranja punteada: proyección {args.year}; la franja sólida es el rango probable (80 %) y los bigotes el rango amplio (95 %: {pr["r95"][0]}–{pr["r95"][1]}).</p>
  {chart_anios([(e["season_year"], int(e["corredores"]), fecha(e["event_date"])) for e in hist], pr, args.year, fecha(prox["event_date"]))}
</div>

<div class="cols">
  <div class="card">
    <h2>La copa {args.year} viene más corta</h2>
    <p class="cap">Mismas sedes, {args.year - 1} contra {args.year}: cambio de corredores por válida. Esta es la señal que usa la proyección.</p>
    {chart_razones(pr["pares"], pr["media"], args.year)}
  </div>
  <div class="card">
    <h2>Cómo leer la proyección</h2>
    <ul class="p">
      <li>Las sedes que se repitieron en {args.year} tuvieron en promedio <b>{round(100 * (pr["media"] - 1)):+d}&nbsp;%</b> de corredores frente a {args.year - 1}. Aplicado a los {ult["corredores"]} de Yumbo {y1} da <b>≈{pr["centro"]}</b>.</li>
      <li>Promedio por válida de la copa: <b>{prom.get(y0)}</b> ({y0}) → <b>{prom.get(y1)}</b> ({y1}) → <b>{prom.get(args.year)}</b> ({args.year}, {pr["n_temporada"][args.year]} válidas).</li>
      <li>Dos cálculos de control coinciden: Yumbo como fracción del promedio de su temporada da <b>{pr["alt_frac"]}</b>; prolongar solo la línea de Yumbo da <b>{pr["alt_lineal"]}</b>.</li>
      <li>Superar el máximo histórico de {max(int(e["corredores"]) for e in hist)} tiene <b>{pct(pr["p_supera_max"])}</b> de probabilidad.</li>
    </ul>
  </div>
</div>

<div class="card">
  <h2>Yumbo por categoría: {y0} contra {y1}</h2>
  <p class="cap">Corredores distintos por grupo de edad en cada edición; entre paréntesis el cambio.
    <span class="key"><span class="dot" style="background:{INK3}"></span>{y0}<span class="dot" style="background:{S1}"></span>{y1}</span></p>
  {chart_grupos_yoy(filas, y0, y1)}
</div>

<div class="card">
  <h2>Detalle por edición</h2>
  <table>
    <thead><tr><th class="c">Año</th><th class="c">Válida</th><th class="c">Fecha</th><th class="n">Corredores</th>
    <th class="n">Terminaron</th><th class="n">Rama femenina</th><th class="n">Categorías</th><th class="n">Clubes</th>
    <th class="n">Prom. copa</th></tr></thead>
    <tbody>{detalle}</tbody>
  </table>
  <p class="foot">Método de la proyección: razón año contra año de las {len(pr["pares"])} sedes repetidas entre {args.year - 1} y {args.year} ({pares_txt}), aplicada al dato de Yumbo {y1}; el intervalo usa la dispersión de esas razones (t de Student, {pr["df"]} grados de libertad) e incluye la incertidumbre de un año nuevo. Con solo dos ediciones de Yumbo es una orientación, no un pronóstico cerrado: fecha, clima y circuito pueden moverla. «Terminaron» incluye vueltas de menos; «Prom. copa» es el promedio por válida de esa temporada.<br>
  Fuente: resultados oficiales de la Copa Valle, procesados por el Club Deportivo Trocha y Ruta. Corte {args.corte}.</p>
</div>
</body></html>"""

    base = ROOT / "output" / "copa-valle-yumbo"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"participacion-yumbo-{args.year}.html").write_text(html, encoding="utf-8")
    resumen = {
        "historico": [{k: e[k] for k in ("season_year", "sequence_number", "event_date", "corredores", "terminaron",
                                         "femenino", "categorias", "clubes")} for e in hist],
        "proyeccion": {k: v for k, v in pr.items()},
        "por_grupo": [{"grupo": g, str(y0): a, str(y1): b} for g, a, b in filas],
    }
    (base / f"participacion-yumbo-{args.year}.json").write_text(
        json.dumps(resumen, default=str, ensure_ascii=False, indent=2), encoding="utf-8")

    from weasyprint import HTML  # noqa: E402

    pdf = base / f"participacion-yumbo-{args.year}.pdf"
    HTML(string=html, base_url=str(base)).write_pdf(str(pdf))
    png_base = base / f"participacion-yumbo-{args.year}"
    subprocess.run(["pdftoppm", "-png", "-r", "170", "-singlefile", str(pdf), str(png_base)], check=True)
    print(json.dumps(pr, default=str, ensure_ascii=False, indent=1))
    print(f"PDF: {pdf}\nPNG: {png_base}.png")


if __name__ == "__main__":
    main()
