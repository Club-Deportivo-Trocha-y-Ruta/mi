"""Renderiza el informe anual personalizado de un/a deportista a PDF.

El contenido narrativo (Markdown) se redacta aparte (ver skill/workflow de
"informe anual") y se pasa como archivo de entrada — este script SOLO:
1. Lee las carreras y mediciones antropométricas reales del deportista desde
   la base de datos (misma fuente de verdad que el resto de la app).
2. Construye las gráficas SVG reusando los macros/builders ya existentes
   (`charts/gap_pct.svg.jinja`, `charts/percentile_curves.svg.jinja`,
   `growth_chart_builder.build_percentile_chart_ctx`) — nunca reinventa la
   geometría ni la curva de referencia OMS.
3. Convierte el Markdown a HTML e inserta las gráficas en los marcadores
   `<!--CHART:gap_trend-->` / `<!--CHART:growth-->`, y `<!--PAGEBREAK-->`
   como salto de página, luego renderiza con WeasyPrint.

Uso:
    cd backend
    DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib" python -m scripts.render_annual_report \\
        --athlete-id 2 --content data/reports/<atleta>_annual_report_content.md \\
        --output data/reports/<atleta>_temporada_2026.pdf

Privacidad: el contenido Markdown de entrada y el PDF de salida SÍ contienen
el nombre real del deportista (es un documento personal, no un fixture) —
por eso ambos viven bajo `backend/data/`, ignorado por git.
"""
from __future__ import annotations

import argparse
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import markdown as md_to_html
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.athlete import Athlete
from app.models.anthropometry import AnthropometricRecord
from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries

TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates"


def _series_label(series_name: str, sequence_number: int) -> str:
    if series_name == "Copa Valle de Ciclomontañismo":
        return f"V{sequence_number}"
    if series_name.startswith("Campeonato Departamental"):
        return "Depto"
    if series_name.startswith("Campeonato Nacional"):
        return "Nacional"
    if "Let's Go" in series_name:
        return "Alcalá"
    return series_name[:10]


async def _build_race_chart_points(db: AsyncSession, athlete_id: int) -> tuple[list[dict], list[dict]]:
    """Construye positions/gap_pcts en el mismo formato que consumen los
    macros SVG existentes: [{"x": idx, "label": str, "y": float|int|None}].
    """
    mine_q = await db.execute(
        select(RaceResult, RaceEvent, RaceSeries, RaceCategory)
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
        .join(RaceCategory, RaceCategory.id == RaceResult.category_id)
        .where(RaceResult.athlete_id == athlete_id, RaceResult.deleted_at.is_(None))
        .order_by(RaceEvent.event_date)
    )
    rows = mine_q.all()

    positions: list[dict] = []
    gap_pcts: list[dict] = []

    for idx, (result, event, series, category) in enumerate(rows, start=1):
        label = _series_label(series.name, event.sequence_number)

        gap_pct = None
        if result.race_time_ms is not None:
            winner_q = await db.execute(
                select(RaceResult.race_time_ms).where(
                    RaceResult.event_id == event.id,
                    RaceResult.category_id == category.id,
                    RaceResult.position == 1,
                    RaceResult.deleted_at.is_(None),
                )
            )
            winner_ms = winner_q.scalar_one_or_none()
            if winner_ms:
                gap_pct = round((result.race_time_ms - winner_ms) / winner_ms * 100, 1)

        positions.append({"x": idx, "label": label, "y": result.position})
        gap_pcts.append({"x": idx, "label": label, "y": gap_pct})

    return positions, gap_pcts


async def _build_points_accumulated(db: AsyncSession, athlete_id: int) -> list[dict]:
    """Puntos acumulados SOLO de la serie Copa Valle (única serie con
    ranking de temporada) en el formato del macro `points_accumulated`.
    """
    rows_q = await db.execute(
        select(RaceResult.points_awarded, RaceEvent.sequence_number)
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
        .where(
            RaceResult.athlete_id == athlete_id,
            RaceResult.deleted_at.is_(None),
            RaceSeries.name == "Copa Valle de Ciclomontañismo",
        )
        .order_by(RaceEvent.sequence_number)
    )
    rows = rows_q.all()

    points: list[dict] = []
    acc = 0
    for points_awarded, sequence_number in rows:
        acc += points_awarded or 0
        points.append({"x": sequence_number, "label": f"V{sequence_number}", "y": acc})
    return points


async def _build_growth_chart_ctx(db: AsyncSession, athlete: Athlete):
    from app.services.training.growth_chart_builder import build_percentile_chart_ctx

    records_q = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date)
    )
    records = list(records_q.scalars().all())
    phv_age = None
    for r in reversed(records):
        if r.age_at_phv is not None:
            phv_age = float(r.age_at_phv)
            break

    return await build_percentile_chart_ctx(
        db=db,
        athlete_id=athlete.id,
        birth_date=athlete.birth_date,
        sex=athlete.sex.value,
        records=records,
        indicator="height",
        phv_age_decimal=phv_age,
    )


_MARK_RE = re.compile(r"==(.+?)==")


def _apply_marks(text: str) -> str:
    """`==frase==` → trazo lima de resaltado (`.editorial-mark` del sitio)."""
    return _MARK_RE.sub(r'<span class="editorial-mark">\1</span>', text)


def _render_markdown(text: str) -> str:
    return md_to_html(text, extensions=["nl2br", "sane_lists", "tables"])


def _make_jinja_env() -> Environment:
    from app.services.notification.document_generator import _format_hms, _render_markdown as _md_filter
    from app.services.utils.dates_es import format_date_es
    from app.services.utils.numbers_es import format_number_es

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown"] = _md_filter
    env.filters["hms"] = _format_hms
    env.filters["date_es"] = format_date_es
    env.filters["num_es"] = format_number_es
    return env


def _render_chart_snippet(env: Environment, macro_import: str, call: str, **ctx) -> str:
    tpl = env.from_string("{% import '" + macro_import + "' as m %}" + call)
    return tpl.render(**ctx)


async def run(athlete_id: int, content_path: Path, output_path: Path, fmt: str) -> None:
    async with AsyncSessionLocal() as db:
        athlete = await db.get(Athlete, athlete_id)
        if athlete is None:
            raise SystemExit(f"Athlete id={athlete_id} no encontrado")

        positions, gap_pcts = await _build_race_chart_points(db, athlete_id)
        points_acc = await _build_points_accumulated(db, athlete_id)
        growth_ctx = await _build_growth_chart_ctx(db, athlete)
        category_label = (
            await db.execute(
                select(RaceCategory.label)
                .join(RaceResult, RaceResult.category_id == RaceCategory.id)
                .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
                .where(RaceResult.athlete_id == athlete_id, RaceResult.deleted_at.is_(None))
                .order_by(RaceEvent.event_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none() or ""

    env = _make_jinja_env()

    large = fmt == "slides"
    gap_size = "width=980, height=360" if large else ""
    growth_size = "width=560, height=250" if large else ""
    points_size = "width=980, height=360" if large else ""

    gap_svg = _render_chart_snippet(
        env,
        "documents/pdf/charts/gap_pct.svg.jinja",
        "{{ m.gap_pct(points" + (", " + gap_size if gap_size else "") + ") }}",
        points=gap_pcts,
    )
    positions_svg = _render_chart_snippet(
        env,
        "documents/pdf/charts/line_positions.svg.jinja",
        "{{ m.line_positions(points) }}",
        points=positions,
    )
    points_svg = _render_chart_snippet(
        env,
        "documents/pdf/charts/points_accumulated.svg.jinja",
        "{{ m.points_accumulated(points" + (", " + points_size if points_size else "") + ") }}",
        points=points_acc,
    )
    growth_svg = _render_chart_snippet(
        env,
        "documents/pdf/charts/percentile_curves.svg.jinja",
        "{{ m.percentile_curves(chart" + (", " + growth_size if growth_size else "") + ") }}",
        chart=growth_ctx,
    )

    raw_content = _apply_marks(content_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from weasyprint import HTML

    if fmt == "slides":
        # Los macros SVG usan width="100%" del contenedor — sin acotarlo,
        # se estiran al ancho completo de la diapositiva (11.7in) y el alto
        # escala con ellos por el viewBox, desbordando la página. Se acota
        # el ancho del contenedor para que el alto renderizado quede acorde
        # al viewBox width/height que se le pasó al macro.
        gap_wrapped = f'<div style="max-width: 900pt; margin: 0 auto;">{gap_svg}</div>'
        points_wrapped = f'<div style="max-width: 900pt; margin: 0 auto;">{points_svg}</div>'
        growth_wrapped = f'<div style="max-width: 460pt; margin: 0 auto;">{growth_svg}</div>'

        slides_raw = raw_content.split("<!--SLIDE-->")
        slides_html = []
        for chunk in slides_raw:
            chunk = chunk.strip()
            if not chunk:
                continue
            chunk = chunk.replace("<!--CHART:gap_trend-->", gap_wrapped)
            chunk = chunk.replace("<!--CHART:growth-->", growth_wrapped)
            chunk = chunk.replace("<!--CHART:points_trend-->", points_wrapped)
            slides_html.append(Markup(chunk))

        template = env.get_template("documents/pdf/annual_report_slides.html")
        final_html = template.render(
            athlete_full_name=f"{athlete.first_name} {athlete.last_name}",
            slides=slides_html,
        )
    else:
        html_content = _render_markdown(raw_content)
        html_content = html_content.replace(
            "<!--CHART:gap_trend-->",
            f'<div class="chart-row"><div>{gap_svg}</div><div>{positions_svg}</div></div>',
        )
        html_content = html_content.replace(
            "<!--CHART:points_trend-->",
            f'<div class="chart-single">{points_svg}</div>',
        )
        html_content = html_content.replace(
            "<!--CHART:growth-->",
            f'<div class="chart-single">{growth_svg}</div>',
        )
        html_content = html_content.replace(
            "<!--PAGEBREAK-->", '<div class="page-break"></div>'
        )

        template = env.get_template("documents/pdf/annual_report.html")
        final_html = template.render(
            athlete_full_name=f"{athlete.first_name} {athlete.last_name}",
            athlete_first_name=athlete.first_name.split()[0],
            category_label=category_label,
            season_year=2026,
            generated_at=datetime.now(timezone.utc).strftime("%d/%m/%Y"),
            body_html=Markup(html_content),
        )

    HTML(string=final_html, base_url=str(TEMPLATES_ROOT)).write_pdf(
        str(output_path), optimize_images=True
    )
    print(f"PDF generado: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--athlete-id", required=True, type=int)
    parser.add_argument("--content", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--format", choices=["report", "slides"], default="report")
    args = parser.parse_args()
    asyncio.run(run(args.athlete_id, args.content, args.output, args.format))


if __name__ == "__main__":
    main()
