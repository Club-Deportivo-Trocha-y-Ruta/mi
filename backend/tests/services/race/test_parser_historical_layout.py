"""Tests de ``parse_results_document`` sobre PDFs sintéticos (feature 044, T012).

Ejercita el lector band-first completo (R-01) end-to-end sobre PDFs reales
generados con ``tests/helpers/results_pdf_builder.py`` — a diferencia de
``test_band_reader.py`` (T011), que prueba ``_band_text`` de forma aislada
sobre diccionarios armados a mano.

Cubre exactamente los puntos de ``tasks.md`` T012:

- 100 % de las filas se recupera con posición, dorsal, tiempo y puntos
  correctos (incluida la fila con club largo desbordado — el defecto real
  de R-01 — dentro de una categoría reconocida).
- Una categoría con encabezado desconocido se devuelve CON sus filas (no
  se descarta) — ``code is None``, ``rows`` no vacío.
- Cero filas ilegibles (``unreadable_rows == []``) incluso mezclando
  filas con tiempo, "clasificada sin tiempo", ``DNF`` y ``(-N VUELTAS)``
  dentro de la misma categoría.
- El numeral ``VIII`` del encabezado se parsea (``parse_event_header``,
  hoy limitado a I-VII — R-02).
- ``parse_results_pdf`` (wrapper de retrocompatibilidad) conserva
  exactamente la forma de retorno de hoy: ``dict[str, list[ResultsRow]]``,
  solo categorías reconocidas.

Requiere WeasyPrint (vía el builder) — en este Mac hace falta anteponer
``DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`` al comando de pytest.

Nota de alcance: ``ResultsRow.name/city/club`` no se comparan en los casos de
T012 — ese contrato solo pide posición/dorsal/tiempo/puntos. El builder no
"recuerda" los nombres/ciudades/clubes que autogenera por fila (solo
``FakeNameGenerator.generated`` para nombres), así que comparar esos campos
exigiría fijar valores explícitos por fila sin aportar cobertura adicional
al contrato de esa tarea.

``TestOverflowingClubIsRecoveredWhole``, al final del archivo, es una adición
posterior a T012 y sí fija el club: se descubrió que la celda de la tabla lo
devuelve truncado justo en las filas desbordadas, y ese valor alimenta la
firma de identidad entre temporadas. Esos casos pasan el club explícitamente
al builder para poder compararlo.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.race.pdf_parser import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    parse_event_header,
    parse_results_document,
    parse_results_pdf,
)
from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    RowSpec,
    build_results_pdf,
    sequential_category,
)


def _build(
    tmp_path: Path,
    categories: list[CategorySpec],
    *,
    valida_num: int = 8,
    location: str = "Ciudad Ficticia",
    event_date: date = date(2025, 8, 9),
) -> Path:
    return build_results_pdf(
        tmp_path / "sintetico.pdf",
        valida_num=valida_num,
        location=location,
        event_date=event_date,
        categories=categories,
        name_generator=FakeNameGenerator(),
    )


def _by_bib(rows: list[ResultsRow]) -> dict[str, ResultsRow]:
    return {r.bib: r for r in rows}


def _category(parsed: ParsedResults, header: str) -> ParsedCategory:
    for cat in parsed.categories:
        if cat.header_raw == header:
            return cat
    raise AssertionError(
        f"Categoría {header!r} no encontrada en {[c.header_raw for c in parsed.categories]}"
    )


# ===========================================================================
# 100 % de filas recuperadas — posición/dorsal/tiempo/puntos correctos
# ===========================================================================


class TestFullRowRecovery:
    def test_all_rows_recovered_including_long_club_overflow(self, tmp_path: Path):
        """Categoría conocida con 8 filas normales + 1 fila con club largo
        desbordado (el defecto real de R-01) — las 9 deben recuperarse con
        posición/dorsal/tiempo/puntos exactos."""
        category = sequential_category("INFANTIL A", 9)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(700 + i)
        category.rows[4].long_club = True  # posición 5, en medio del lote

        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        assert parsed.unreadable_rows == []
        parsed_cat = _category(parsed, "INFANTIL A")
        assert parsed_cat.code == "INF_A"
        assert len(parsed_cat.rows) == len(category.rows)

        by_bib = _by_bib(parsed_cat.rows)
        for spec_row in category.rows:
            got = by_bib[spec_row.bib]
            assert got.position == spec_row.position
            assert got.time_raw == spec_row.time_raw
            assert got.points == spec_row.points

    def test_20_row_category_all_recovered_no_losses(self, tmp_path: Path):
        """SC-001 ("0 filas perdidas") a mayor volumen: 20 filas, todas con
        club largo desbordado."""
        category = sequential_category("JUNIOR", 20)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(900 + i)
            row.long_club = True

        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        assert parsed.unreadable_rows == []
        parsed_cat = _category(parsed, "JUNIOR")
        assert len(parsed_cat.rows) == 20

        by_bib = _by_bib(parsed_cat.rows)
        for spec_row in category.rows:
            got = by_bib[spec_row.bib]
            assert got.position == spec_row.position
            assert got.time_raw == spec_row.time_raw
            assert got.points == spec_row.points


# ===========================================================================
# Encabezado desconocido: se conserva CON sus filas, no se descarta
# ===========================================================================


class TestUnknownHeaderKeepsRows:
    def test_unknown_header_category_is_kept_with_its_rows(self, tmp_path: Path):
        unknown = CategorySpec(
            header="SUPER ELITE COSMICO",
            rows=[
                RowSpec(position=1, bib="601", time_raw="0:30:00", points=50),
                RowSpec(position=2, bib="602", time_raw="0:31:00", points=45),
                RowSpec(position=3, bib="603", time_raw="0:32:00", points=40, long_club=True),
            ],
        )
        pdf_path = _build(tmp_path, [unknown])
        parsed = parse_results_document(pdf_path)

        parsed_cat = _category(parsed, "SUPER ELITE COSMICO")
        assert parsed_cat.code is None
        assert len(parsed_cat.rows) == 3
        assert parsed.unreadable_rows == []

    def test_document_order_preserved_across_known_and_unknown_categories(self, tmp_path: Path):
        known = sequential_category("INFANTIL A", 2)
        unknown = CategorySpec(
            header="SUPER ELITE COSMICO",
            rows=[RowSpec(position=1, bib="701", time_raw="0:20:00", points=50)],
        )
        pdf_path = _build(tmp_path, [known, unknown])
        parsed = parse_results_document(pdf_path)

        headers = [c.header_raw for c in parsed.categories]
        assert headers.index("INFANTIL A") < headers.index("SUPER ELITE COSMICO")


# ===========================================================================
# Cero filas ilegibles — mezcla de tiempo / sin tiempo / DNF / vueltas
# ===========================================================================


class TestZeroUnreadableRowsMixedStatuses:
    def test_mixed_category_has_no_unreadable_rows(self, tmp_path: Path):
        category = CategorySpec(
            header="INFANTIL A",
            rows=[
                RowSpec(position=1, bib="801", time_raw="0:40:07", points=50),
                # "clasificada sin tiempo" (R-01 punto 4): celda Tiempo vacía.
                RowSpec(position=2, bib="802", points=45),
                RowSpec(position=3, bib="803", status="DNF", points=0),
                RowSpec(position=4, bib="804", minus_laps=2, points=10),
                RowSpec(
                    position=5, bib="805", time_raw="0:44:35", points=40,
                    long_club=True,
                ),
            ],
        )
        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        assert parsed.unreadable_rows == []
        parsed_cat = _category(parsed, "INFANTIL A")
        assert len(parsed_cat.rows) == 5

        by_bib = _by_bib(parsed_cat.rows)
        assert by_bib["801"].time_raw == "0:40:07"
        assert by_bib["801"].points == 50
        # Clasificada sin tiempo -> time_raw == "" (contrato reading-integrity.md).
        assert by_bib["802"].time_raw == ""
        assert by_bib["802"].position == 2
        assert by_bib["802"].points == 45
        assert by_bib["803"].time_raw.upper() == "DNF"
        assert by_bib["804"].time_raw == "(-2 VUELTAS)"
        assert by_bib["805"].position == 5
        assert by_bib["805"].time_raw == "0:44:35"


# ===========================================================================
# Header numeral VIII (R-02)
# ===========================================================================


class TestEventHeaderNumeralVIII:
    def test_valida_viii_header_is_parsed(self, tmp_path: Path):
        category = sequential_category("INFANTIL A", 1)
        pdf_path = _build(tmp_path, [category], valida_num=8)

        header = parse_event_header(pdf_path)

        assert header is not None, (
            "parse_event_header no reconoció VALIDA VIII — "
            "_EVENT_HEADER_RE/_ROMAN_TO_INT aún no extendidos a I-XII (R-02, T016)"
        )
        assert header.valida_num == 8
        assert header.location == "CIUDAD FICTICIA"
        assert header.event_date == date(2025, 8, 9)


# ===========================================================================
# parse_results_pdf — wrapper de retrocompatibilidad
# ===========================================================================


class TestBackCompatWrapper:
    def test_wrapper_keeps_todays_return_shape(self, tmp_path: Path):
        known = sequential_category("INFANTIL A", 3)
        known.rows[1].long_club = True
        for i, row in enumerate(known.rows, start=1):
            row.bib = str(750 + i)
        unknown = CategorySpec(
            header="SUPER ELITE COSMICO",
            rows=[
                RowSpec(position=1, bib="601", time_raw="0:30:00", points=50),
                RowSpec(position=2, bib="602", time_raw="0:31:00", points=45),
            ],
        )
        pdf_path = _build(tmp_path, [known, unknown])

        out = parse_results_pdf(pdf_path)

        assert isinstance(out, dict)
        # Solo categorías reconocidas — la desconocida queda fuera del wrapper.
        assert set(out.keys()) == {"INF_A"}
        assert len(out["INF_A"]) == 3
        assert all(isinstance(r, ResultsRow) for r in out["INF_A"])

        by_bib = _by_bib(out["INF_A"])
        for spec_row in known.rows:
            got = by_bib[spec_row.bib]
            assert got.position == spec_row.position
            assert got.time_raw == spec_row.time_raw
            assert got.points == spec_row.points


# ===========================================================================
# Club desbordado: se recupera íntegro, no truncado
# ===========================================================================


class TestOverflowingClubIsRecoveredWhole:
    """El ``Club/Patrocinador`` largo llega completo a ``ResultsRow.club``.

    Adición posterior a T012. La celda 4 de la tabla devuelve el club
    **truncado** justo en las filas donde se desborda sobre la columna
    ``Tiempo``, y el recorte depende de cuánto se desbordó el texto. Como
    ``club_norm`` es uno de los tres componentes de la firma que identifica a
    un competidor entre temporadas, un club truncado produce una firma
    distinta para la misma persona: la misma persona en dos válidas con
    desbordes de distinta longitud se partiría en dos competidores.
    """

    #: Dos longitudes distintas a propósito: si el parser devolviera el valor
    #: recortado por la celda, cada una se truncaría en un punto diferente.
    LONG_CLUB = "Fundacion Deportiva Ficticia Comunitaria del Valle del Cauca"
    LONGER_CLUB = "Asociacion Ficticia Comunitaria Metropolitana del Sur Occidente"

    def test_overflowing_club_arrives_untruncated(self, tmp_path: Path):
        category = sequential_category("INFANTIL A", 3)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(300 + i)
        category.rows[1].long_club = True
        category.rows[1].club = self.LONG_CLUB

        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        got = _by_bib(_category(parsed, "INFANTIL A").rows)["302"]
        assert got.club == self.LONG_CLUB
        # El tiempo de esa misma fila sigue leyéndose bien (el club no se lo
        # comió ni quedó pegado dentro del club).
        assert got.time_raw == category.rows[1].time_raw

    def test_two_different_overflow_lengths_both_arrive_whole(self, tmp_path: Path):
        """Dos desbordes de longitud distinta en la misma categoría: ambos
        clubes completos y distintos entre sí — que es justo lo que garantiza
        que dos firmas de identidad no colisionen ni se dupliquen."""
        category = sequential_category("INFANTIL A", 4)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(400 + i)
        category.rows[0].long_club = True
        category.rows[0].club = self.LONG_CLUB
        category.rows[2].long_club = True
        category.rows[2].club = self.LONGER_CLUB

        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        by_bib = _by_bib(_category(parsed, "INFANTIL A").rows)
        assert by_bib["401"].club == self.LONG_CLUB
        assert by_bib["403"].club == self.LONGER_CLUB

    def test_normal_row_club_still_matches_the_cell(self, tmp_path: Path):
        """Control: en una fila sin desborde la reconstrucción devuelve
        exactamente el mismo club que imprimió el builder."""
        category = sequential_category("INFANTIL A", 2)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(500 + i)
        category.rows[0].club = "Modelo FC"

        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        got = _by_bib(_category(parsed, "INFANTIL A").rows)["501"]
        assert got.club == "Modelo FC"

    def test_long_city_is_also_recovered_whole(self, tmp_path: Path):
        """La ciudad se trunca igual que el club cuando se desborda.

        Medido en la válida IV de 2026: ``table.extract()`` devolvía la ciudad
        recortada y, peor, el club de esa misma fila salía como texto
        intercalado con el desborde de la ciudad. ``city_norm`` es el tercer
        componente de la firma de identidad, así que se verifica igual que el
        club: ambos campos llegan íntegros y el tiempo no se contamina.
        """
        long_city = "Municipio Ejemplo de la Montaña Occidental"
        category = sequential_category("INFANTIL A", 3)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(600 + i)
        category.rows[1].city = long_city
        category.rows[1].club = self.LONG_CLUB
        category.rows[1].long_club = True

        pdf_path = _build(tmp_path, [category])
        parsed = parse_results_document(pdf_path)

        got = _by_bib(_category(parsed, "INFANTIL A").rows)["602"]
        assert got.city == long_city
        assert got.club == self.LONG_CLUB
        assert got.time_raw == category.rows[1].time_raw
        # Ningún resto de tiempo se coló en los campos de texto.
        assert ":" not in got.city + got.club
