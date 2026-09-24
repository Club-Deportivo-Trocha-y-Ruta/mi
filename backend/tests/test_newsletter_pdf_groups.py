"""T010 (feature 039) — render del PDF de la bitácora de etapa con grupos de
comparación (copas vs. campeonatos).

Cubre ``contracts/newsletter-context.md`` § Template behavior:

- (a) Un snapshot NUEVO (``pdf_only_blocks.charts_context`` con ``cups[]`` y
  ``email_blocks.race_results`` con ``championships[]``) debe producir, en
  ``templates/documents/pdf/athlete_stage_log.html``:
    - el encabezado ``"Evolución en la {copa} {año}"`` por cada copa
      (D2/D13 — nunca "Copa Valle" hardcodeado; el nombre viene del fixture),
    - una sección "Campeonatos",
    - las cuatro etiquetas de la tarjeta de campeonato (Posición / Parrilla /
      Brecha vs. mediana / Percentil — glosario 045),
    - la nota D13 ("Un campeonato reúne una parrilla distinta...").
- (b) Un snapshot VIEJO (sin ``cups``/``championships`` — solo
  ``progression_history`` y las claves planas heredadas ``positions`` /
  ``gap_pcts`` / ``points_accumulated``) debe renderizar SIN error y SIN la
  sección "Campeonatos" (back-compat — data-model.md §6: "el template PDF
  debe tratar claves ausentes como listas vacías").

Renderiza HTML puro vía Jinja2 (sin WeasyPrint) — mismo patrón que
``tests/intervals/test_instructivo_pdf.py::TestInstructivoTemplateRendering``
y ``tests/test_newsletter_svg_charts.py``: este entorno de desarrollo no
tiene las librerías nativas de WeasyPrint (pango/glib) instaladas
(``OSError: cannot load library 'libgobject-2.0-0'``); en Docker/Render sí
están presentes. El entorno Jinja2 y sus filtros (``markdown``, ``hms``,
``date_es``, ``num_es``) son los mismos que usa ``DocumentGenerator`` en
producción.

Nombres y datos ficticios (CLAUDE.md, Ley 1581) — mismo escenario narrativo
que ``tests/fixtures/race_groups.py`` (Copa Valle de Ciclomontañismo 2026,
Cto. Departamental en Ginebra, Cto. Nacional en Pereira).
"""
from __future__ import annotations

import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.notification.document_generator import (
    _TEMPLATES_ROOT,
    _format_hms,
    _render_markdown,
)
from app.services.utils.dates_es import format_date_es
from app.services.utils.numbers_es import format_number_es

_TEMPLATE = "documents/pdf/athlete_stage_log.html"

_CUP_LABEL = "Copa Valle de Ciclomontañismo 2026"


def _env() -> Environment:
    """Mismo ``Environment`` (loader + filtros) que ``DocumentGenerator``."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown"] = _render_markdown
    env.filters["hms"] = _format_hms
    env.filters["date_es"] = format_date_es
    env.filters["num_es"] = format_number_es
    return env


def _base_context(*, charts_annex: dict, race_results: dict) -> dict:
    """Contexto mínimo pero completo del template (variables ``.get()``
    tolerantes a ausencia — ver docstring del template). ``anthro_annex``
    va en ``None`` a propósito: la sección de temporada (copas +
    campeonatos) debe renderizar aunque el mes no tenga mediciones
    antropométricas (spec FR-004/FR-005; hallazgo de la verificación de la
    oleada 2, donde el bloque había quedado anidado dentro del anexo de
    crecimiento)."""
    return {
        "athlete_first_name": "Ciclista",
        "athlete_last_name": "Ficticia Salazar",
        "club_name": "Club Ficticio de Prueba",
        "month_label": "Agosto 2026",
        "season_year": "2026",
        "generated_at": "2026-09-03 10:00 COT",
        "stage_log": {
            "stage_number": 8,
            "period_label": "Agosto 2026",
            "trail": [],
            "summit": None,
            "observations": [],
            "analyst_reading": None,
            "effort_profile": [],
            "next_segment": None,
            "family_compass": None,
            "badges": [],
            "photos": [],
            "coach_note": None,
        },
        "anthro_annex": None,
        "percentile_annex": None,
        "charts_annex": charts_annex,
        "race_results": race_results,
    }


def _new_shape_context() -> dict:
    """(a) Snapshot NUEVO — feature 039: ``cups[]`` + ``championships[]``."""
    charts_annex = {
        "has_data": True,
        "has_championship": True,
        "cups": [
            {
                "series_id": 6001,
                "label": _CUP_LABEL,
                "n_samples": 5,
                "low_confidence": False,
                "positions": [{"x": i, "label": f"V{i}", "y": i} for i in range(1, 6)],
                "median_gap_pcts": [
                    {"x": i, "label": f"V{i}", "y": y}
                    for i, y in enumerate([-1.3, 0.8, 2.4, -0.5, 1.1], start=1)
                ],
                "points_accumulated": [
                    {"x": i, "label": f"V{i}", "y": i * 30} for i in range(1, 6)
                ],
            }
        ],
    }
    race_results = {
        "has_races": True,
        "competitor_id": 8500,
        "results": [],
        "progression_history": [],
        "cups": [
            {
                "series_id": 6001,
                "label": _CUP_LABEL,
                "history": [
                    {
                        "event_id": 60010 + i,
                        "valida_num": i,
                        "event_date": f"2026-0{i}-15",
                        "position": i,
                        "points_awarded": i * 30,
                        "gap_to_winner_pct": float(i),
                        "series_kind": "cup",
                        "series_level": "departmental",
                        "location": "Sevilla",
                        "label": f"V{i}",
                    }
                    for i in range(1, 6)
                ],
            }
        ],
        "championships": [
            {
                "event_id": 60111,
                "label": "Campeonato Departamental",
                "short_label": "Cto. Dep. — Ginebra",
                "level": "departmental",
                "location": "Ginebra",
                "event_date": "2026-06-20",
                "category_label": "Infantil A Ficticio",
                "finished": True,
                "position": 4,
                "field_size": 4,
                "gap_pct": 5.6,
                "gap_to_median_pct": 1.0,
                "percentile": 75.0,
            },
            {
                "event_id": 60121,
                "label": "Campeonato Nacional",
                "short_label": "Cto. Nal. — Pereira",
                "level": "national",
                "location": "Pereira",
                "event_date": "2026-08-22",
                "category_label": "Infantil A Ficticio",
                "finished": True,
                "position": 11,
                "field_size": 34,
                "gap_pct": 35.6,
                "gap_to_median_pct": -2.5,
                "percentile": 69.7,
            },
        ],
        "projection": None,
    }
    return _base_context(charts_annex=charts_annex, race_results=race_results)


def _old_shape_context(*, with_chart_data: bool = True) -> dict:
    """(b) Snapshot VIEJO — anterior a la feature 039: sin ``cups``/
    ``championships``, solo el histórico plano + las claves heredadas
    ``positions``/``gap_pcts``/``points_accumulated`` a nivel raíz.

    ``with_chart_data=False`` (F-5) modela un snapshot viejo que nunca tuvo
    sustancia de gráfico (las tres listas vienen vacías, ``has_data=False``)
    — distinto del caso con datos, que ahora sí debe mostrar el encabezado
    heredado "Evolución en la temporada" (F-5)."""
    charts_annex = {
        "has_data": with_chart_data,
        "has_championship": False,
        "positions": (
            [{"x": i, "label": f"V{i}", "y": i} for i in range(1, 4)]
            if with_chart_data
            else []
        ),
        "gap_pcts": (
            [{"x": i, "label": f"V{i}", "y": float(i)} for i in range(1, 4)]
            if with_chart_data
            else []
        ),
        "points_accumulated": (
            [{"x": i, "label": f"V{i}", "y": i * 30} for i in range(1, 4)]
            if with_chart_data
            else []
        ),
        "low_confidence": True,
    }
    race_results = {
        "has_races": True,
        "competitor_id": 8500,
        "results": [],
        "progression_history": [
            {
                "valida_num": i,
                "event_date": f"2026-0{i}-15",
                "position": i,
                "points_awarded": i * 30,
                "gap_to_winner_pct": float(i),
                "series_kind": "cup",
                "series_level": "departmental",
                "location": "Sevilla",
                "label": f"V{i}",
            }
            for i in range(1, 4)
        ],
        "projection": None,
    }
    return _base_context(charts_annex=charts_annex, race_results=race_results)


class TestStageLogPdfComparisonGroups:
    """(a) Snapshot nuevo: copa(s) + campeonatos renderizados por separado."""

    def test_cup_heading_uses_series_name_not_hardcoded(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        assert f"Evolución en la {_CUP_LABEL}" in html

    def test_championships_section_present(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        assert "Campeonatos" in html

    def test_championship_card_tile_labels_present(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        for label in ("Posición", "Parrilla", "Brecha vs. mediana", "Percentil"):
            assert label in html, f"Etiqueta de tarjeta '{label}' ausente del PDF"

    def test_championship_note_sentence_present(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        assert "Un campeonato reúne una parrilla distinta" in html


class TestStageLogPdfMedianGapNotWinnerGap:
    """Feature 045 (US4, FR-020/FR-022): la familia lee la «Brecha vs.
    mediana»; ningún rótulo ni valor del gap al ganador llega al PDF."""

    def test_no_winner_gap_label_anywhere(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        for retired in ("Gap al P1", "P1=0", "Pelotón", "al primer lugar"):
            assert retired not in html, f"Rótulo retirado '{retired}' sigue en el PDF"

    def test_championship_card_shows_median_gap_not_winner_gap(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        assert "+1,0 %" in html
        assert "-2,5 %" in html
        # Centinelas: el gap al ganador de las tarjetas (gap_pct) no se pinta.
        assert "+5,6" not in html
        assert "+35,6" not in html

    def test_championship_card_without_median_shows_sin_dato_not_winner_gap(self):
        """Snapshot generado antes de la 045 (o parrilla bajo el mínimo): la
        tarjeta trae ``gap_pct`` pero no ``gap_to_median_pct`` → «sin dato»."""
        ctx = _new_shape_context()
        for championship in ctx["race_results"]["championships"]:
            championship.pop("gap_to_median_pct")
        html = _env().get_template(_TEMPLATE).render(**ctx)
        assert "+5,6" not in html
        assert "+35,6" not in html
        assert "sin dato" in html


_CARD_MACRO = (
    '{% from "documents/pdf/charts/championship_card.html.jinja" '
    "import championship_card %}{{ championship_card(reading) }}"
)


def _render_card(reading: dict) -> str:
    return _env().from_string(_CARD_MACRO).render(reading=reading)


def _tile_values(html: str) -> dict[str, str]:
    """Texto de cada una de las cuatro celdas, indexado por su rótulo."""
    tiles = re.findall(
        r'<p style="margin: 0; font-size: 8pt; color: #6b7280;">([^<]+)</p>\s*'
        r'<p style="[^"]*">([^<]*)</p>',
        html,
    )
    return {label: value.strip() for label, value in tiles}


class TestChampionshipCardSinDato:
    """Feature 045 (FR-020, US2/AC3): una estadística sin valor se rotula
    «sin dato», nunca con un guion suelto — la familia lee este PDF."""

    def test_all_four_empty_tiles_read_sin_dato(self):
        html = _render_card(
            {
                "label": "Campeonato Departamental",
                "finished": True,
                "position": None,
                "field_size": None,
                "gap_to_median_pct": None,
                "percentile": None,
            }
        )
        assert _tile_values(html) == {
            "Posición": "sin dato",
            "Parrilla": "sin dato",
            "Brecha vs. mediana": "sin dato",
            "Percentil": "sin dato",
        }
        assert html.count("sin dato") == 4
        # Ninguna celda cae a un guion suelto (el «—» del encabezado no aplica:
        # aquí no hay lugar ni fecha).
        assert "—" not in html

    def test_missing_keys_of_a_pre_045_snapshot_read_sin_dato(self):
        html = _render_card({"label": "Campeonato Nacional", "finished": True})
        assert html.count("sin dato") == 4
        assert "—" not in html

    def test_percentile_under_min_field_reads_sin_dato(self):
        """Parrilla de 3: el percentil no informa → «sin dato», el resto se ve."""
        html = _render_card(
            {
                "label": "Campeonato Departamental",
                "finished": True,
                "position": 3,
                "field_size": 3,
                "category_label": "Prejuvenil A Femenino",
                "gap_to_median_pct": 1.6,
                "percentile": 0.0,
            }
        )
        tiles = _tile_values(html)
        assert tiles["Percentil"] == "sin dato"
        assert tiles["Posición"] == "P3"
        assert tiles["Parrilla"] == "3 en Prejuvenil A Femenino"
        assert tiles["Brecha vs. mediana"] == "+1,6 %"

    def test_filled_tiles_do_not_read_sin_dato(self):
        html = _render_card(
            {
                "label": "Campeonato Departamental",
                "finished": True,
                "position": 4,
                "field_size": 20,
                "gap_to_median_pct": 1.6,
                "percentile": 84.2,
            }
        )
        assert "sin dato" not in html
        assert _tile_values(html)["Percentil"] == "84"

    def test_dnf_card_keeps_its_note_instead_of_empty_tiles(self):
        html = _render_card({"label": "Campeonato Departamental", "finished": False})
        assert "No completó la prueba." in html
        assert "sin dato" not in html

    def test_cup_panel_titled_and_plots_median_gap(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        assert "Brecha vs. mediana (%)" in html
        # Valores firmados de la serie de la copa (negativo = más rápido).
        assert "-1,3%" in html
        assert "2,4%" in html

    def test_glossary_defines_median_gap_and_time_based_percentile(self):
        html = _env().get_template(_TEMPLATE).render(**_new_shape_context())
        assert "<strong>Brecha vs. mediana:</strong>" in html
        assert "<strong>Percentil:</strong>" in html
        # El percentil ya no se explica por puestos ("un P2 entre 5 marca 75").
        assert "un P2 entre 5" not in html


_CUP_LABEL_2 = "Liga Departamental 2026"


def _two_cups_shape_context() -> dict:
    """(c) Snapshot con DOS copas (T041, feature 039) — ``charts_annex.cups``
    trae "Liga Departamental" primero (válida más temprana, ya resuelto por
    ``_build_charts_context``) y la copa principal después. El template NO
    reordena — solo itera ``charts_annex.cups`` en el orden recibido (ver
    contrato ``newsletter-context.md`` § Template behavior) — por eso el
    orden de la lista de abajo es el que debe aparecer en el HTML."""
    charts_annex = {
        "has_data": True,
        "has_championship": False,
        "cups": [
            {
                "series_id": 6002,
                "label": _CUP_LABEL_2,
                "n_samples": 3,
                "low_confidence": True,
                "positions": [{"x": i, "label": f"V{i}", "y": i} for i in range(1, 4)],
                "median_gap_pcts": [{"x": i, "label": f"V{i}", "y": float(i)} for i in range(1, 4)],
                "points_accumulated": [
                    {"x": i, "label": f"V{i}", "y": i * 36} for i in range(1, 4)
                ],
            },
            {
                "series_id": 6001,
                "label": _CUP_LABEL,
                "n_samples": 5,
                "low_confidence": False,
                "positions": [{"x": i, "label": f"V{i}", "y": i} for i in range(1, 6)],
                "median_gap_pcts": [{"x": i, "label": f"V{i}", "y": float(i)} for i in range(1, 6)],
                "points_accumulated": [
                    {"x": i, "label": f"V{i}", "y": i * 36} for i in range(1, 6)
                ],
            },
        ],
    }
    race_results = {
        "has_races": True,
        "competitor_id": 8500,
        "results": [],
        "progression_history": [],
        "cups": [],
        "championships": [],
        "projection": None,
    }
    return _base_context(charts_annex=charts_annex, race_results=race_results)


class TestStageLogPdfTwoCups:
    """(c) Snapshot con dos copas: dos encabezados "Evolución en la …"
    (T041, feature 039)."""

    def test_two_evolution_headings_in_order(self):
        html = _env().get_template(_TEMPLATE).render(**_two_cups_shape_context())

        heading_liga = f"Evolución en la {_CUP_LABEL_2}"
        heading_main = f"Evolución en la {_CUP_LABEL}"

        assert html.count("Evolución en la ") == 2
        assert heading_liga in html
        assert heading_main in html
        # El template itera charts_annex.cups sin reordenar — Liga (la copa
        # con la válida más temprana, ya resuelta aguas arriba) debe
        # aparecer PRIMERO en el HTML.
        assert html.index(heading_liga) < html.index(heading_main)

    def test_no_championships_section_when_only_cups(self):
        html = _env().get_template(_TEMPLATE).render(**_two_cups_shape_context())
        assert "Campeonatos" not in html


class TestStageLogPdfBackCompatOldSnapshot:
    """(b) Snapshot viejo (sin cups/championships): sin error, sin Campeonatos."""

    def test_renders_without_error(self):
        html = _env().get_template(_TEMPLATE).render(**_old_shape_context())
        assert html  # no excepción, HTML no vacío

    def test_no_championships_section_for_old_snapshot(self):
        html = _env().get_template(_TEMPLATE).render(**_old_shape_context())
        assert "Campeonatos" not in html

    def test_legacy_evolution_heading_present_when_old_snapshot_has_chart_data(self):
        """F-5: un snapshot viejo CON datos de gráfico ya no pierde su página
        de temporada — cae al encabezado heredado en vez del nuevo por-copa."""
        html = _env().get_template(_TEMPLATE).render(**_old_shape_context())
        assert "Evolución en la temporada" in html
        assert "Campeonatos" not in html

    def test_persisted_winner_gap_series_is_never_drawn(self):
        """Feature 045: un snapshot persistido antes de la 045 solo trae la
        serie ``gap_pcts`` (gap al ganador). El template ya no la lee: se
        vuelve a descargar el PDF y el valor centinela no aparece."""
        ctx = _old_shape_context()
        ctx["charts_annex"]["gap_pcts"] = [
            {"x": i, "label": f"V{i}", "y": 41.3} for i in range(1, 4)
        ]
        html = _env().get_template(_TEMPLATE).render(**ctx)
        assert "41,3" not in html
        assert "Gap al P1" not in html


class TestStageLogPdfSeasonSectionIsIndependentOfAnthro:
    """La sección de temporada no depende del anexo de crecimiento (FR-004/FR-005)."""

    def test_renders_without_anthro_records(self):
        ctx = _new_shape_context()
        assert ctx["anthro_annex"] is None
        html = _env().get_template(_TEMPLATE).render(**ctx)
        assert f"Evolución en la {_CUP_LABEL}" in html
        assert "Campeonatos" in html
        assert "Anexo de crecimiento" not in html

    def test_renders_with_anthro_records_too(self):
        ctx = _new_shape_context()
        ctx["anthro_annex"] = {"has_records": True, "records": [], "latest": None}
        html = _env().get_template(_TEMPLATE).render(**ctx)
        assert "Anexo de crecimiento" in html
        assert f"Evolución en la {_CUP_LABEL}" in html
        assert "Campeonatos" in html
        # La sección de temporada va DESPUÉS del anexo, no dentro de él.
        assert html.index("Anexo de crecimiento") < html.index("Campeonatos")

    def test_old_snapshot_with_legacy_chart_data_still_has_season_page(self):
        """F-5: con datos de gráfico heredados, la página de temporada
        sobrevive (encabezado legacy) aunque no haya anexo de crecimiento."""
        html = _env().get_template(_TEMPLATE).render(**_old_shape_context())
        assert "Evolución en la temporada" in html
        assert "Campeonatos" not in html

    def test_old_snapshot_without_any_chart_data_has_no_season_page(self):
        """F-5: sin NINGÚN dato de gráfico (ni cups ni las listas planas
        heredadas), la sección de temporada completa se omite — no un
        encabezado con gráficos vacíos."""
        html = _env().get_template(_TEMPLATE).render(
            **_old_shape_context(with_chart_data=False)
        )
        assert "Evolución en la" not in html
        assert "Campeonatos" not in html
