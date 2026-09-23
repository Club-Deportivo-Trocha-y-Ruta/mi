"""Infografía de participación por válida (PDF + PNG) a partir de agregados.

Entrada: output/copa-valle-<year>/participantes.json (ver copa_valle_participantes.py).
Solo usa conteos agregados — ningún nombre de corredor aparece en la salida.

Uso:
    cd backend && source .venv/bin/activate
    python scripts/infografia_participacion.py --year 2026
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- Paleta (dataviz skill, instancia de referencia; validada con validate_palette.js) ---
SURFACE = "#fcfcfb"
PLANE = "#f9f9f7"
INK = "#0b0b0b"
INK2 = "#52514e"
INK3 = "#87867f"
GRID = "#e8e7e3"
S1 = "#2a78d6"  # blue
S2 = "#eb6834"  # orange
S3 = "#1baf7a"  # aqua

MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
         7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

# (etiqueta, códigos oficiales, rama) — la rama da el color de la barra.
GRUPOS = [
    ("Teteros (hasta 5)", ["TET_SP", "TET_CP"], "MIXED"),
    ("Preinfantil M (6-8)", ["PRE_A", "PRE_B"], "M"),
    ("Preinfantil F (6-8)", ["PRE_A_F", "PRE_B_F"], "F"),
    ("Infantil M (9-12)", ["INF_A", "INF_B"], "M"),
    ("Infantil F (9-12)", ["INF_A_F", "INF_B_F"], "F"),
    ("Prejuvenil M (13-14)", ["PJUV_A", "PJUV_B"], "M"),
    ("Prejuvenil F (13-14)", ["PJUV_A_F", "PJUV_B_F"], "F"),
    ("Junior M (15-16)", ["JUN_M"], "M"),
    ("Junior F (15-16)", ["JUN_F"], "F"),
    ("Élite M (17+)", ["ELITE_M"], "M"),
    ("Élite F (17+)", ["ELITE_F"], "F"),
    ("Promocional", ["PROMO"], "MIXED"),
    ("Máster A (30-39)", ["MAS_A"], "M"),
    ("Máster B1 (40-44)", ["MAS_B1"], "M"),
    ("Máster B2 (45-49)", ["MAS_B2"], "M"),
    ("Máster C1 (50-54)", ["MAS_C1"], "M"),
    ("Máster C2 (55-59)", ["MAS_C2"], "M"),
    ("Máster D (60+)", ["MAS_D"], "M"),
    ("Máster F (30+)", ["MAS_F"], "F"),
]


def mil(n: int) -> str:
    """Separador de miles con punto (convención es-CO)."""
    return f"{n:,}".replace(",", ".")


def fecha_corta(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MESES[int(m)]}"


def col_bar(x: float, y: float, w: float, h: float, r: float, color: str) -> str:
    """Columna vertical: extremo superior redondeado (r), base cuadrada."""
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    return (
        f'<path d="M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} '
        f'Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} L{x + w - r:.1f},{y:.1f} '
        f'Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h:.1f} Z" fill="{color}"/>'
    )


def row_bar(x: float, y: float, w: float, h: float, r: float, color: str) -> str:
    """Barra horizontal: extremo derecho redondeado (r), origen cuadrado."""
    if w <= 0:
        return ""
    r = min(r, h / 2, w)
    return (
        f'<path d="M{x:.1f},{y:.1f} L{x + w - r:.1f},{y:.1f} '
        f'Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h - r:.1f} '
        f'Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} L{x:.1f},{y + h:.1f} Z" fill="{color}"/>'
    )


def chart_validas(evs_done: list[dict], evs_pend: list[dict]) -> str:
    W, H = 712, 160
    ml, mr, mt, mb = 34, 6, 16, 34
    plot_h = H - mt - mb
    slots = len(evs_done) + len(evs_pend)
    slot_w = (W - ml - mr) / slots
    top = 260
    ticks = [0, 50, 100, 150, 200, 250]
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    for t in ticks:
        y = mt + plot_h * (1 - t / top)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W - mr}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{ml - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="9.5" fill="{INK3}">{t}</text>')
    bw = 24.0
    for i, e in enumerate(evs_done):
        v = int(e["corredores_unicos"])
        h = plot_h * v / top
        cx = ml + slot_w * i + slot_w / 2
        x = cx - bw / 2
        y = mt + plot_h - h
        parts.append(col_bar(x, y, bw, h, 4, S1))
        parts.append(f'<text x="{cx:.1f}" y="{y - 7:.1f}" text-anchor="middle" font-size="14" font-weight="700" fill="{INK}">{v}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 15:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" fill="{INK}">V{e["sequence_number"]} · {e["location"]}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 28:.1f}" text-anchor="middle" font-size="9.5" fill="{INK3}">{fecha_corta(str(e["event_date"]))}</text>')
    for j, e in enumerate(evs_pend):
        i = len(evs_done) + j
        cx = ml + slot_w * i + slot_w / 2
        parts.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{mt + plot_h - 34:.1f}" width="{bw}" height="34" rx="4" '
            f'fill="none" stroke="{GRID}" stroke-width="1.5" stroke-dasharray="3 3"/>'
        )
        parts.append(f'<text x="{cx:.1f}" y="{mt + plot_h - 42:.1f}" text-anchor="middle" font-size="9" fill="{INK3}">por correr</text>')
        parts.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 15:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" fill="{INK3}">V{e["sequence_number"]} · {e["location"]}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 28:.1f}" text-anchor="middle" font-size="9.5" fill="{INK3}">{fecha_corta(str(e["event_date"]))}</text>')
    parts.append(f'<line x1="{ml}" y1="{mt + plot_h:.1f}" x2="{W - mr}" y2="{mt + plot_h:.1f}" stroke="{INK3}" stroke-width="1"/>')
    parts.append("</svg>")
    return "".join(parts)


def chart_grupos(grupos: list[tuple[str, int, str]]) -> str:
    """Barras horizontales en dos columnas (misma escala), coloreadas por rama."""
    W, H = 712, 214
    gutter = 26.0
    col_w = (W - gutter) / 2
    ml, mr, mt = 122, 34, 2
    plot_w = col_w - ml - mr
    maxv = max(v for _, v, _ in grupos)
    n_izq = (len(grupos) + 1) // 2
    filas = max(n_izq, len(grupos) - n_izq)
    slot = (H - mt) / filas
    bh = 13.0
    color = {"M": S1, "F": S2, "MIXED": S3}
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    for i, (label, v, rama) in enumerate(grupos):
        col, fila = (0, i) if i < n_izq else (1, i - n_izq)
        x0 = col * (col_w + gutter)
        y = mt + slot * fila + (slot - bh) / 2
        w = plot_w * v / maxv
        parts.append(f'<text x="{x0 + ml - 8:.1f}" y="{y + bh - 3:.1f}" text-anchor="end" font-size="9.5" fill="{INK2}">{label}</text>')
        parts.append(row_bar(x0 + ml, y, w, bh, 4, color[rama]))
        parts.append(f'<text x="{x0 + ml + w + 6:.1f}" y="{y + bh - 3:.1f}" font-size="10.5" font-weight="700" fill="{INK}">{v}</text>')
    parts.append("</svg>")
    return "".join(parts)


def chart_genero(segs: list[tuple[str, int, str]], total: int) -> str:
    W, H = 330, 78
    bar_y, bh = 6, 26
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    x = 0.0
    gap = 2.0
    usable = W - gap * (len(segs) - 1)
    for i, (label, v, color) in enumerate(segs):
        w = usable * v / total
        r = 4 if i in (0, len(segs) - 1) else 0
        if i == 0:
            parts.append(f'<path d="M4,{bar_y} L{x + w:.1f},{bar_y} L{x + w:.1f},{bar_y + bh} L4,{bar_y + bh} '
                         f'Q0,{bar_y + bh} 0,{bar_y + bh - 4} L0,{bar_y + 4} Q0,{bar_y} 4,{bar_y} Z" fill="{color}"/>')
        elif i == len(segs) - 1:
            parts.append(row_bar(x, bar_y, w, bh, 4, color))
        else:
            parts.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="{bh}" fill="{color}"/>')
        pct = round(100 * v / total)
        if w > 34:
            parts.append(f'<text x="{x + w / 2:.1f}" y="{bar_y + bh / 2 + 4:.1f}" text-anchor="middle" '
                         f'font-size="11" font-weight="700" fill="#ffffff">{pct} %</text>')
        x += w + gap
    lx = 0.0
    for label, v, color in segs:
        parts.append(f'<circle cx="{lx + 4.5:.1f}" cy="{bar_y + bh + 21:.1f}" r="4.5" fill="{color}"/>')
        parts.append(f'<text x="{lx + 14:.1f}" y="{bar_y + bh + 25:.1f}" font-size="10" fill="{INK2}">{label} · {v}</text>')
        lx += 13 + 6.0 * len(label) + 26
    parts.append("</svg>")
    return "".join(parts)


def chart_fidelidad(dist: dict[int, int]) -> str:
    W, H = 330, 90
    mt, mb = 14, 28
    plot_h = H - mt - mb
    maxv = max(dist.values())
    slot_w = W / 5
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">']
    bw = 24.0
    for i in range(1, 6):
        v = dist.get(i, 0)
        h = plot_h * v / maxv
        cx = slot_w * (i - 1) + slot_w / 2
        y = mt + plot_h - h
        parts.append(col_bar(cx - bw / 2, y, bw, h, 4, S1))
        parts.append(f'<text x="{cx:.1f}" y="{y - 5:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="{INK}">{v}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{mt + plot_h + 14:.1f}" text-anchor="middle" font-size="10" fill="{INK2}">{i}</text>')
    parts.append(f'<line x1="0" y1="{mt + plot_h:.1f}" x2="{W}" y2="{mt + plot_h:.1f}" stroke="{INK3}" stroke-width="1"/>')
    parts.append(f'<text x="{W / 2:.1f}" y="{H - 4}" text-anchor="middle" font-size="9.5" fill="{INK3}">válidas disputadas por corredor</text>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--series-id", type=int, default=2)
    ap.add_argument("--corte", default="18 de septiembre de 2026")
    args = ap.parse_args()

    base = ROOT / "output" / f"copa-valle-{args.year}"
    data = json.loads((base / "participantes.json").read_text(encoding="utf-8"))
    serie = next(s for s in data["series"] if s["id"] == args.series_id)
    evs = [e for e in data["eventos"] if e["series_id"] == args.series_id]
    done = [e for e in evs if int(e["inscripciones"]) > 0]
    pend = [e for e in evs if int(e["inscripciones"]) == 0]

    max_valida = max(int(e["corredores_unicos"]) for e in done)
    tot = data["totales_serie"]
    ser_tot = next(t for t in tot if t["series_id"] == args.series_id)
    unicos = int(ser_tot["corredores_unicos_temporada"])
    clubes = int(ser_tot["clubes_temporada"])
    ev_ids = {e["id"] for e in evs}
    cats = [c for c in data["por_categoria"] if c["event_id"] in ev_ids]
    n_cats = len({c["code"] for c in cats})
    prom = round(sum(int(e["corredores_unicos"]) for e in done) / len(done))

    sid = str(args.series_id)
    g_unicos = data["unicos_por_grupo"][sid]
    rama = data["unicos_por_rama"][sid]
    grupos = [(label, g_unicos.get(label.split(" (")[0], 0), rama) for label, _, rama in GRUPOS]
    menores = sum(v for l, v, _ in grupos if l.startswith(("Teteros", "Preinfantil", "Infantil", "Prejuvenil")))
    femenino = sum(v for l, v, r in grupos if r == "F")

    dist = {int(d["validas_corridas"]): int(d["corredores"])
            for d in data["distribucion_asistencia"] if d["series_id"] == args.series_id}

    filas = "".join(
        f'<tr><td class="c">V{e["sequence_number"]}</td><td>{e["location"]}</td>'
        f'<td class="c">{fecha_corta(str(e["event_date"]))}</td>'
        f'<td class="n b">{e["corredores_unicos"]}</td>'
        f'<td class="n">{e["categorias"]}</td><td class="n">{e["clubes"]}</td></tr>'
        for e in done
    )

    css = f"""
    @page {{ size: A4 portrait; margin: 10mm 10mm 8mm 10mm; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: Helvetica, Arial, sans-serif; color: {INK}; background: {PLANE}; margin: 0; }}
    .hd {{ border-bottom: 2.5px solid {INK}; padding-bottom: 5px; margin-bottom: 8px; }}
    .kicker {{ font-size: 9.5pt; letter-spacing: .09em; text-transform: uppercase; color: {INK2}; font-weight: 700; }}
    h1 {{ font-size: 20pt; margin: 3px 0 2px; line-height: 1.05; }}
    .sub {{ font-size: 9.5pt; color: {INK2}; }}
    .kpis {{ display: flex; gap: 6px; margin-bottom: 8px; }}
    .kpi {{ flex: 1; background: {SURFACE}; border: 1px solid {GRID}; border-radius: 7px; padding: 6px 8px; }}
    .kpi .v {{ font-size: 18pt; font-weight: 700; line-height: 1; }}
    .kpi .l {{ font-size: 8pt; color: {INK2}; margin-top: 3px; line-height: 1.2; }}
    .card {{ background: {SURFACE}; border: 1px solid {GRID}; border-radius: 7px; padding: 8px 11px; margin-bottom: 7px; }}
    .card h2 {{ font-size: 11pt; margin: 0 0 1px; }}
    .card .cap {{ font-size: 8.5pt; color: {INK2}; margin: 0 0 7px; }}
    .key {{ white-space: nowrap; }}
    .dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin: 0 4px 0 12px; }}
    .cols {{ display: flex; gap: 7px; margin-bottom: 7px; }}
    .cols > div {{ flex: 1; margin-bottom: 0; }}
    .stack > div:first-child {{ margin-bottom: 7px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; }}
    th {{ text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .05em;
         color: {INK2}; border-bottom: 1px solid {GRID}; padding: 3px 4px; }}
    td {{ padding: 2.6px 4px; border-bottom: 1px solid #f2f1ee; }}
    td.n, th.n {{ text-align: right; }}
    td.c, th.c {{ text-align: center; }}
    td.b {{ font-weight: 700; }}
    tr.tot td {{ font-weight: 700; border-top: 1.5px solid {INK}; border-bottom: none; }}
    .foot {{ font-size: 7.2pt; color: {INK3}; line-height: 1.3; margin-top: 2px; }}
    """

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="hd">
  <div class="kicker">Participación · Temporada {args.year}</div>
  <h1>{serie["name"]} {args.year}</h1>
  <div class="sub">{serie["organizer"]} · todos los corredores de los resultados oficiales, de cualquier categoría y club · cada persona se cuenta una sola vez · corte {args.corte}</div>
</div>

<div class="kpis">
  <div class="kpi"><div class="v">{unicos}</div><div class="l">corredores distintos compitieron en la copa</div></div>
  <div class="kpi"><div class="v">{clubes}</div><div class="l">clubes y equipos representados</div></div>
  <div class="kpi"><div class="v">{n_cats}</div><div class="l">categorías en competencia</div></div>
  <div class="kpi"><div class="v">{prom}</div><div class="l">corredores en promedio por válida</div></div>
  <div class="kpi"><div class="v">{len(done)} de {len(evs)}</div><div class="l">válidas disputadas al día de hoy</div></div>
</div>

<div class="card">
  <h2>Corredores en cada válida</h2>
  <p class="cap">Personas distintas que tomaron la partida ese día. Las válidas 6 y 7 aún no se han corrido.</p>
  {chart_validas(done, pend)}
</div>

<div class="card">
  <h2>Por categoría</h2>
  <p class="cap">Los {unicos} corredores repartidos sin repetir a nadie · {menores} ({round(100 * menores / unicos)} %) son categorías menores.
    <span class="key"><span class="dot" style="background:{S1}"></span>masculina<span class="dot" style="background:{S2}"></span>femenina<span class="dot" style="background:{S3}"></span>mixta</span></p>
  {chart_grupos(grupos)}
</div>

<div class="cols">
  <div class="card">
    <h2>Por rama</h2>
    <p class="cap">Los mismos {unicos} corredores, según la categoría en que compiten.</p>
    {chart_genero([("Masculina", rama.get("M", 0), S1), ("Femenina", rama.get("F", 0), S2), ("Mixta", rama.get("MIXED", 0), S3)], unicos)}
  </div>
  <div class="card">
    <h2>Constancia en la copa</h2>
    <p class="cap">{dist.get(5, 0)} corredores estuvieron en las {len(done)} válidas y {dist.get(1, 0)} corrieron una sola.</p>
    {chart_fidelidad(dist)}
  </div>
</div>

<div class="card">
  <h2>Detalle por válida</h2>
  <table>
    <thead><tr><th class="c">Válida</th><th>Sede</th><th class="c">Fecha</th><th class="n">Corredores</th>
    <th class="n">Categorías</th><th class="n">Clubes</th></tr></thead>
    <tbody>{filas}
      <tr class="tot"><td class="c">Temporada</td><td>{len(done)} válidas disputadas</td><td></td><td class="n">{unicos}</td>
      <td class="n">{n_cats}</td><td class="n">{clubes}</td></tr>
    </tbody>
  </table>
  <p class="foot">La fila «Temporada» no suma las columnas: cuenta personas, clubes y categorías distintas en el conjunto de la copa, de modo que quien corrió varias válidas aparece una sola vez. A cada corredor se le cuenta la última categoría en que compitió: {data["corredores_multi_grupo"].get(sid, 0)} corredores corrieron en dos grupos distintos durante el año, así que una tabla oficial de categoría suelta puede diferir en un corredor. Cada corredor se identifica por su nombre tal como aparece en los resultados oficiales: si una válida lo escribió distinto, puede quedar contado dos veces.<br>
  Fuente: resultados oficiales de la {serie["organizer"]}, procesados por el Club Deportivo Trocha y Ruta. Corte {args.corte}.</p>
</div>
</body></html>"""

    out_html = base / "infografia-participacion.html"
    out_html.write_text(html, encoding="utf-8")

    if not os.environ.get("DYLD_FALLBACK_LIBRARY_PATH") and sys.platform == "darwin":
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib"
        os.execv(sys.executable, [sys.executable, *sys.argv])

    from weasyprint import HTML  # noqa: E402

    pdf = base / f"participacion-copa-valle-{args.year}.pdf"
    HTML(string=html, base_url=str(base)).write_pdf(str(pdf))
    png_base = base / f"participacion-copa-valle-{args.year}"
    subprocess.run(["pdftoppm", "-png", "-r", "170", "-singlefile", str(pdf), str(png_base)], check=True)
    print(f"PDF: {pdf}")
    print(f"PNG: {png_base}.png")


if __name__ == "__main__":
    main()
