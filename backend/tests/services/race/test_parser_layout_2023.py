"""Parser: acta Copa Valle 2023 («tiempo antes del club»).

Las actas 2023 imprimen ``Pos N° Apellidos Nombres Time Club o Equipo [Copa]``
(``Municipio``/``Medalla`` en el departamental): el tiempo va entre el nombre y
el club, la categoría es una fila combinada de la propia tabla con la tanda de
salida al final (``TETERO SIN PEDALES 1``) y solo algunas válidas imprimen
puntos. Ver el docstring del módulo ``pdf_parser`` y ``_TIME_FIRST_HEADER_RE``.

Datos **100 % sintéticos** (nombres inventados, ninguna persona real). Dos
niveles:

- unitario, sobre las funciones puras y el camino por líneas (dobles de
  ``pdfplumber``), sin WeasyPrint;
- extremo a extremo, con PDFs que genera WeasyPrint con tablas de rulings
  (el camino por banda de verdad). Requiere ``DYLD_FALLBACK_LIBRARY_PATH``
  en este Mac, igual que ``test_parser_historical_layout.py``.

Los formatos 2022 y 2024+ no se ejercitan aquí: lo hacen
``test_parser_edge_cases.py``, ``test_parser_historical_layout.py`` y
``test_2026_unchanged.py``.
"""
from __future__ import annotations

from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import Any, Optional

import pytest
from weasyprint import HTML

from app.services.race import pdf_parser as parser_mod
from app.services.race.pdf_parser import ParsedResults, parse_results_document

_COLS_PUNTOS = "Pos N° Apellidos Nombres Time Club o Equipo Copa"
_COLS_SIN_PUNTOS = "Pos N° Apellidos Nombres Time Club o Equipo"
_COLS_MEDALLA = "Pos N° Apellidos Nombres Time Municipio Medalla"


# ===========================================================================
# Funciones puras
# ===========================================================================


class TestEncabezadoDeColumnas:
    @pytest.mark.parametrize(
        "line",
        [_COLS_PUNTOS, _COLS_SIN_PUNTOS, _COLS_MEDALLA, "pos n° apellidos nombres time club"],
    )
    def test_reconoce_el_encabezado_2023(self, line: str) -> None:
        assert parser_mod._is_time_first_header(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "Ord No. Nombre Ciudad Club/Patrocinador Tiempo Puntos",  # 2024+
            "Ord No. Nombre Club Patrocinador Ciudad Tiempo",  # 2022
            "Pos 12 Apellidos Nombres",
            "1 2000 PEREZ ANA 0:01:53 CLUB FICTICIO 40",
        ],
    )
    def test_no_confunde_otros_formatos(self, line: str) -> None:
        assert parser_mod._is_time_first_header(line) is False

    def test_page_layout_distingue_puntos_por_la_columna_copa(self) -> None:
        assert parser_mod._page_layout(f"TITULO\n{_COLS_PUNTOS}\n") == (True, True)
        assert parser_mod._page_layout(f"TITULO\n{_COLS_SIN_PUNTOS}\n") == (True, False)
        assert parser_mod._page_layout(f"TITULO\n{_COLS_MEDALLA}\n") == (True, False)

    def test_page_layout_de_los_otros_formatos_no_cambia(self) -> None:
        con = "Ord No. Nombre Club Patrocinador Ciudad Tiempo Puntos"
        sin = "Ord No. Nombre Club Patrocinador Ciudad Tiempo"
        assert parser_mod._page_layout(con) == (False, True)
        assert parser_mod._page_layout(sin) == (False, False)
        assert parser_mod._page_layout("1 10 A B 0:01:00 40") == (False, True)


class TestCategoria2023:
    @pytest.mark.parametrize(
        "above, esperado",
        [
            ("TETERO SIN PEDALES 1", "TETERO SIN PEDALES"),
            ("PRE-JUVENIL B 4A", "PRE-JUVENIL B"),
            ("MASTER D1 3B", "MASTER D1"),
            ("MASTER A2 3B", "MASTER A2"),
            ("ELITE DAMAS 2", "ELITE DAMAS"),
            ("PRE-INFANTIL B - MAS 1", "PRE-INFANTIL B - MAS"),
            ("INFANTIL A NIÑAS 1", "INFANTIL A NIÑAS"),
            # Departamental: sin tanda al final.
            ("MASTER A1", "MASTER A1"),
            ("TETEROS CON PEDALES", "TETEROS CON PEDALES"),
        ],
    )
    def test_quita_la_tanda_y_conserva_el_rotulo(self, above: str, esperado: str) -> None:
        assert parser_mod._time_first_category(above) == esperado

    @pytest.mark.parametrize(
        "above",
        [
            "",
            "IV válida CALI",
            "CLASIFICACIONES",
            "XXVII COPA VALLE - WILL BIKE",
            "Corredora 908 se relega del 9 al 11 por no pasar por control",
            "Se relega a la corredora 304 por asistencia mecanica",
            "A" * 80,
            "CAT: INFANTIL A",
        ],
    )
    def test_rechaza_lo_que_no_es_un_rotulo(self, above: str) -> None:
        assert parser_mod._time_first_category(above) is None


class TestFilaTiempoPrimero:
    """``_match_row_text(..., time_first=True)``: tiempo entre nombre y club."""

    @pytest.mark.parametrize(
        "row, time_raw, club, points",
        [
            ("1 2000 PEREZ LOPEZ ANA 0:01:53 CLUB FICTICIO UNO 40", "0:01:53", "CLUB FICTICIO UNO", "40"),
            ("5 2002 SOTO RUIZ LUIS 0:02:15 CLUB DOS 27", "0:02:15", "CLUB DOS", "27"),
            ("12 801 GOMEZ DIAZ EVA 0:09:00 0 25", "0:09:00", "0", "25"),
            ("3 70 ROJAS PAZ OMAR DNF CLUB TRES 1", "DNF", "CLUB TRES", "1"),
            ("9 71 ROJAS PAZ OMAR DNS CLUB TRES 0", "DNS", "CLUB TRES", "0"),
            ("7 12 VEGA SOL RIO - 1 VUELTA CLUB CUATRO 1", "- 1 VUELTA", "CLUB CUATRO", "1"),
            ("8 13 VEGA SOL RIO -2 VUELTAS CLUB CUATRO 1", "-2 VUELTAS", "CLUB CUATRO", "1"),
            # Club vacío: lo último son los puntos.
            ("2 5 LUNA MAR 0:03:00 36", "0:03:00", None, "36"),
        ],
    )
    def test_con_columna_copa(self, row: str, time_raw: str, club: Optional[str], points: str) -> None:
        match, time = parser_mod._match_row_text(row, has_points=True, time_first=True)
        assert match is not None and time == time_raw
        assert match.group("club") == club
        assert match.group("points") == points

    @pytest.mark.parametrize(
        "row, time_raw, club",
        [
            ("1 2001 PEREZ LOPEZ ANA 0:02:00 CLUB FICTICIO UNO", "0:02:00", "CLUB FICTICIO UNO"),
            # Sin columna de puntos un ``0`` final es el club «sin club».
            ("6 2012 SOTO RUIZ LUIS 0:02:23 0", "0:02:23", "0"),
            ("2 1802 ROJAS PAZ OMAR DNF CLUB X", "DNF", "CLUB X"),
            ("4 33 VEGA SOL RIO - 1 Vuelta CLUB X/Y", "- 1 Vuelta", "CLUB X/Y"),
            # Apellido compuesto con guion: no es déficit de vueltas.
            ("1 40 DE-LA PAZ ANA 0:04:10 CLUB Z", "0:04:10", "CLUB Z"),
        ],
    )
    def test_sin_columna_de_puntos(self, row: str, time_raw: str, club: str) -> None:
        match, time = parser_mod._match_row_text(row, has_points=False, time_first=True)
        assert match is not None and time == time_raw
        assert match.group("club") == club
        assert "points" not in match.groupdict()

    def test_fila_sin_token_de_tiempo_no_es_fila_por_texto(self) -> None:
        for has_points in (True, False):
            assert parser_mod._match_row_text(
                "11 3 SOTO RUIZ LUIS Sancion CLUB", has_points=has_points, time_first=True
            ) == (None, "")

    def test_el_camino_por_defecto_no_cambia(self) -> None:
        """Una fila 2024+ sigue leyéndose con ``_RESULTS_ROW_RE`` (tiempo
        antes de los puntos, club antes del tiempo)."""
        match, time = parser_mod._match_row_text("1 10 Persona Uno CLUB Ciudad 0:01:00 40")
        assert match is not None and time == "0:01:00"
        assert "club" not in match.groupdict()


class TestPuntosInferidos2023:
    @pytest.mark.parametrize(
        "position, time_raw, esperado",
        [
            (1, "0:01:53", 40),
            (6, "0:02:16", 25),
            (16, "0:09:00", 5),
            (17, "0:09:10", 4),
            (18, "0:09:20", 3),
            (19, "0:09:30", 2),
            (20, "0:09:40", 1),
            (21, "0:09:50", 1),
            (60, "0:20:00", 1),
            (7, "- 1 VUELTA", 23),
            (5, "DNF", 1),
            (9, "DNS", 0),
            (3, "DSQ", 0),
        ],
    )
    def test_escala_2023(self, position: int, time_raw: str, esperado: int) -> None:
        points = parser_mod._infer_points(position, time_raw, parser_mod._POSITION_POINTS_2023)
        assert points == esperado

    def test_la_escala_2022_por_defecto_no_cambia(self) -> None:
        assert parser_mod._infer_points(17, "0:09:10") == 3
        assert parser_mod._infer_points(18, "0:09:10") == 1
        assert parser_mod._POSITION_POINTS_2022[16:] == (3, 1)

    def test_las_dos_escalas_coinciden_hasta_el_16(self) -> None:
        assert parser_mod._POSITION_POINTS_2023[:16] == parser_mod._POSITION_POINTS_2022[:16]


# ===========================================================================
# Camino por líneas (dobles de pdfplumber, sin tablas)
# ===========================================================================


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text

    def extract_tables(self, table_settings: Optional[dict] = None):
        return []


class _FakePdf:
    def __init__(self, pages: list[_FakePage]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_pdf(tmp_path: Path, monkeypatch):
    def _make(pages: list[_FakePage]) -> Path:
        path = tmp_path / "fake.pdf"
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")

        @contextmanager
        def _opener(_path: Any):
            yield _FakePdf(pages)

        monkeypatch.setattr(
            parser_mod, "pdfplumber", type("X", (), {"open": _opener})
        )
        return path

    return _make


class TestDocumentoPorLineas:
    def test_validas_con_y_sin_copa_en_el_mismo_documento(self, fake_pdf) -> None:
        pagina = _FakePage(
            "XXVII COPA VALLE - WILL BIKE\n"
            "CICLOMONTAÑISMO 2023\n"
            "CLASIFICACIONES\n"
            "I válida CIUDAD FICTICIA\n"
            "TETERO SIN PEDALES 1\n"
            f"{_COLS_PUNTOS}\n"
            "1 2000 PEREZ LOPEZ ANA 0:01:53 CLUB UNO 40\n"
            "2 2001 SOTO RUIZ LUIS DNF CLUB DOS 1\n"
            "INFANTIL B 1\n"
            f"{_COLS_PUNTOS}\n"
            "1 815 GOMEZ DIAZ EVA 0:05:30 0 40\n"
        )
        parsed = parse_results_document(fake_pdf([pagina]))

        assert [c.header_raw for c in parsed.categories] == ["TETERO SIN PEDALES", "INFANTIL B"]
        assert [c.code for c in parsed.categories] == ["TET_SP", "INF_B"]
        assert [len(c.rows) for c in parsed.categories] == [2, 1]
        assert [[r.points for r in c.rows] for c in parsed.categories] == [[40, 1], [40]]
        assert parsed.points_inferred_rows == 0
        assert parsed.unreadable_rows == []

    def test_sin_copa_los_puntos_se_infieren_con_la_escala_2023(self, fake_pdf) -> None:
        filas = "\n".join(
            f"{pos} {100 + pos} PERSONA N{pos} 0:0{pos % 10}:00 CLUB FICTICIO"
            for pos in range(1, 19)
        )
        pagina = _FakePage(f"ELITE 4A\n{_COLS_SIN_PUNTOS}\n{filas}\n")
        parsed = parse_results_document(fake_pdf([pagina]))

        (cat,) = parsed.categories
        assert cat.header_raw == "ELITE" and cat.code == "ELITE_M"
        assert [r.points for r in cat.rows][14:18] == [7, 5, 4, 3]
        assert parsed.points_inferred_rows == 18

    def test_el_nombre_por_texto_conserva_el_orden_impreso(self, fake_pdf) -> None:
        """Sin celdas de tabla no hay forma fiable de separar apellidos y
        nombres: el respaldo por texto deja el cuerpo tal cual."""
        pagina = _FakePage(
            f"JUNIOR 4A\n{_COLS_SIN_PUNTOS}\n1 10 PEREZ LOPEZ ANA 0:01:00 CLUB UNO\n"
        )
        (row,) = parse_results_document(fake_pdf([pagina])).categories[0].rows
        assert row.name == "PEREZ LOPEZ ANA"
        assert row.club == "CLUB UNO"
        assert row.city == ""

    def test_categoria_desconocida_conserva_las_filas(self, fake_pdf) -> None:
        pagina = _FakePage(
            f"NOVATOS 2\n{_COLS_SIN_PUNTOS}\n1 10 PEREZ LOPEZ ANA 0:01:00 CLUB UNO\n"
        )
        (cat,) = parse_results_document(fake_pdf([pagina])).categories
        assert cat.header_raw == "NOVATOS" and cat.code is None
        assert len(cat.rows) == 1

    def test_pagina_2024_en_el_mismo_documento_no_usa_el_camino_nuevo(self, fake_pdf) -> None:
        pagina = _FakePage(
            "CAT: INFANTIL A\n"
            "Ord N° Nombre Ciudad Club/Patrocinador Tiempo Puntos\n"
            "1 10 Persona Uno CLUB Ciudad 0:01:00 40\n"
        )
        (cat,) = parse_results_document(fake_pdf([pagina])).categories
        assert cat.code == "INF_A"
        assert (cat.rows[0].time_raw, cat.rows[0].points) == ("0:01:00", 40)


# ===========================================================================
# Extremo a extremo con PDFs reales (camino por banda)
# ===========================================================================

_CSS = """
@page { size: Letter; margin: 1.2cm; }
body { font-family: sans-serif; font-size: 9pt; }
table { border-collapse: collapse; table-layout: fixed; width: 700px; margin-bottom: 8px; }
th, td { border: 1px solid black; padding: 2px 3px; white-space: nowrap; font-size: 8.5pt; }
.pb { page-break-before: always; }
"""

#: anchos (px): pos, bib, apellidos, nombres, time, club, última (Copa|Medalla)
_WIDTHS = (40, 45, 150, 120, 85, 200, 60)


def _colgroup(n_cols: int) -> str:
    return "<colgroup>" + "".join(f'<col style="width:{w}px">' for w in _WIDTHS[:n_cols]) + "</colgroup>"


def _table(
    category: str,
    wave: str,
    columns: list[str],
    rows: list[list[str]],
    *,
    header: bool = True,
    note: Optional[str] = None,
    page_break: bool = False,
) -> str:
    """Una tabla como las de 2023: fila de categoría combinada, encabezado y filas."""
    n = len(columns)
    html = [f'<table{" class=pb" if page_break else ""}>{_colgroup(n)}']
    if category:
        html.append(
            f'<tr><td colspan="{n - 1}">{escape(category)}</td><td>{escape(wave)}</td></tr>'
        )
    if header:
        html.append("<tr>" + "".join(f"<th>{escape(c)}</th>" for c in columns) + "</tr>")
    for row in rows:
        html.append("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>")
    if note:
        html.append(f'<tr><td colspan="{n}">{escape(note)}</td></tr>')
    html.append("</table>")
    return "".join(html)


def _pdf(tmp_path: Path, tables: list[str], title: bool = True) -> Path:
    titulo = (
        "<p>XXVII COPA VALLE - WILL BIKE</p><p>CICLOMONTAÑISMO 2023</p>"
        "<p>CLASIFICACIONES</p><p>II válida CIUDAD FICTICIA</p>"
        if title
        else ""
    )
    out = tmp_path / "acta_2023.pdf"
    HTML(string=f"<html><head><style>{_CSS}</style></head><body>{titulo}{''.join(tables)}</body></html>").write_pdf(str(out))
    return out


_COLS_PTS = ["Pos", "N°", "Apellidos", "Nombres", "Time", "Club o Equipo", "Copa"]
_COLS_NOPTS = _COLS_PTS[:-1]
_COLS_MED = ["Pos", "N°", "Apellidos", "Nombres", "Time", "Club o Equipo", "Medalla"]


def _by_header(parsed: ParsedResults) -> dict[str, list]:
    return {c.header_raw: c.rows for c in parsed.categories}


@pytest.fixture
def acta_con_copa(tmp_path: Path) -> Path:
    return _pdf(
        tmp_path,
        [
            _table(
                "TETERO SIN PEDALES", "1", _COLS_PTS,
                [
                    ["1", "2000", "Pérez Lopera", "Ana Lucía", "0:01:53", "Club Ficticio Uno", "40"],
                    ["2", "2001", "Soto Ruiz", "Luis", "0:01:59", "Club Dos", "36"],
                    ["3", "2010", "Gómez Díaz", "Eva María", "0:02:03", "0", "33"],
                    ["4", "2013", "Rojas Paz", "Omar", "DNF", "Club Tres", "1"],
                    ["5", "2002", "Vega Sol", "Río", "- 1 VUELTA", "Club Cuatro", "1"],
                    ["6", "2004", "Luna Mar", "Eli", "DNS", "Club Cinco", "0"],
                ],
            ),
            _table(
                "PREJUVENIL A DAMAS", "2", _COLS_PTS,
                [
                    ["1", "700", "Mora Vidal", "Sara", "0:30:11", "Club Seis", "40"],
                    ["2", "701", "Nieto Cano", "Paula", "0:31:20", "Club Siete", "36"],
                ],
            ),
        ],
    )


class TestPdfConCopa:
    def test_filas_categorias_y_puntos_impresos(self, acta_con_copa: Path) -> None:
        parsed = parse_results_document(acta_con_copa)

        assert [c.header_raw for c in parsed.categories] == [
            "TETERO SIN PEDALES",
            "PREJUVENIL A DAMAS",
        ]
        assert [c.code for c in parsed.categories] == ["TET_SP", "PJUV_A_F"]
        assert parsed.unreadable_rows == []
        assert parsed.points_inferred_rows == 0

        tetero, damas = (c.rows for c in parsed.categories)
        assert [r.position for r in tetero] == [1, 2, 3, 4, 5, 6]
        assert [r.bib for r in tetero] == ["2000", "2001", "2010", "2013", "2002", "2004"]
        assert [r.time_raw for r in tetero] == [
            "0:01:53", "0:01:59", "0:02:03", "DNF", "- 1 VUELTA", "DNS",
        ]
        assert [r.points for r in tetero] == [40, 36, 33, 1, 1, 0]
        assert [r.points for r in damas] == [40, 36]

    def test_nombre_invertido_a_nombres_apellidos_y_club_de_su_celda(self, acta_con_copa: Path) -> None:
        """El acta imprime ``Apellidos | Nombres``; el resto de las temporadas
        imprime el nombre de pila primero y la identidad compara el texto."""
        tetero = parse_results_document(acta_con_copa).categories[0].rows
        assert tetero[0].name == "Ana Lucía Pérez Lopera"
        assert tetero[0].club == "Club Ficticio Uno"
        assert tetero[0].city == ""
        assert tetero[1].name == "Luis Soto Ruiz"
        # El marcador «sin club» se conserva tal cual: lo vacía el normalizador.
        assert tetero[2].club == "0"

    def test_la_tanda_no_forma_parte_de_la_categoria(self, acta_con_copa: Path) -> None:
        headers = [c.header_raw for c in parse_results_document(acta_con_copa).categories]
        assert all(not h[-1].isdigit() for h in headers)


class TestPdfSinCopa:
    def test_puntos_inferidos_con_la_escala_2023(self, tmp_path: Path) -> None:
        filas = [
            [str(pos), str(300 + pos), f"Apellido{chr(64 + pos)}", f"Nombre{chr(64 + pos)}",
             f"0:{10 + pos}:00", "Club Ficticio", ]
            for pos in range(1, 21)
        ]
        parsed = parse_results_document(_pdf(tmp_path, [_table("ELITE", "4A", _COLS_NOPTS, filas)]))

        (cat,) = parsed.categories
        assert cat.header_raw == "ELITE" and cat.code == "ELITE_M"
        assert len(cat.rows) == 20 and parsed.unreadable_rows == []
        assert [r.points for r in cat.rows][:6] == [40, 36, 33, 30, 27, 25]
        assert [r.points for r in cat.rows][15:] == [5, 4, 3, 2, 1]
        assert parsed.points_inferred_rows == 20

    def test_club_cero_final_no_se_lee_como_puntos(self, tmp_path: Path) -> None:
        filas = [["1", "55", "Soto Ruiz", "Luis", "0:02:23", "0"]]
        parsed = parse_results_document(_pdf(tmp_path, [_table("INFANTIL A", "1", _COLS_NOPTS, filas)]))
        (row,) = parsed.categories[0].rows
        assert row.club == "0" and row.points == 40 and row.time_raw == "0:02:23"


class TestPdfCasosBorde:
    def test_clasificado_sin_tiempo_y_sancion(self, tmp_path: Path) -> None:
        """Celda ``Time`` vacía o con una palabra de sanción: la fila se
        conserva con ``time_raw == ""`` en vez de perderse."""
        filas = [
            ["1", "10", "Pérez Lopera", "Ana", "0:03:00", "Club Uno"],
            ["2", "11", "Soto Ruiz", "Luis", "Sanción", "Club Dos"],
            ["3", "12", "Rojas Paz", "Omar", "", "Club Tres"],
        ]
        parsed = parse_results_document(_pdf(tmp_path, [_table("JUNIOR", "5", _COLS_NOPTS, filas)]))

        (cat,) = parsed.categories
        assert parsed.unreadable_rows == []
        assert [(r.position, r.time_raw) for r in cat.rows] == [
            (1, "0:03:00"), (2, ""), (3, ""),
        ]
        assert cat.rows[1].name == "Luis Soto Ruiz" and cat.rows[1].club == "Club Dos"

    def test_nota_del_jurado_no_es_fila_ni_ilegible(self, tmp_path: Path) -> None:
        filas = [
            ["1", "10", "Pérez Lopera", "Ana", "0:03:00", "Club Uno"],
            ["2", "11", "Soto Ruiz", "Luis", "0:03:10", "Club Dos"],
        ]
        nota = "Corredora 11 se relega del 1 al 2, por no realizar paso por control"
        parsed = parse_results_document(
            _pdf(tmp_path, [_table("ELITE DAMAS", "2", _COLS_NOPTS, filas, note=nota)])
        )
        assert parsed.unreadable_rows == []
        assert len(parsed.categories[0].rows) == 2
        # Ninguna celda de nota se coló en una fila.
        assert all("relega" not in (r.name + r.club) for r in parsed.categories[0].rows)

    def test_pagina_de_continuacion_sin_encabezado_hereda_el_formato(self, tmp_path: Path) -> None:
        """La última fila de una categoría cae sola en la página siguiente, sin
        encabezado de columnas ni categoría."""
        primera = _table(
            "PRE-JUVENIL B", "4A", _COLS_NOPTS,
            [["1", "20", "Pérez Lopera", "Ana", "0:20:00", "Club Uno"],
             ["2", "21", "Soto Ruiz", "Luis", "0:20:30", "Club Dos"]],
        )
        resto = _table(
            "", "", _COLS_NOPTS,
            [["3", "22", "Rojas Paz", "Omar", "0:21:00", "Club Tres"]],
            header=False, page_break=True,
        )
        parsed = parse_results_document(_pdf(tmp_path, [primera, resto]))

        assert parsed.unreadable_rows == []
        (cat,) = parsed.categories
        assert cat.header_raw == "PRE-JUVENIL B" and cat.code == "PJUV_B"
        assert [r.position for r in cat.rows] == [1, 2, 3]
        assert cat.rows[2].name == "Omar Rojas Paz"

    def test_categoria_que_continua_con_su_rotulo_repetido(self, tmp_path: Path) -> None:
        primera = _table("INFANTIL B", "2", _COLS_NOPTS,
                         [["1", "30", "Pérez Lopera", "Ana", "0:10:00", "Club Uno"]])
        segunda = _table("INFANTIL B", "2", _COLS_NOPTS,
                         [["2", "31", "Soto Ruiz", "Luis", "0:10:30", "Club Dos"]], page_break=True)
        parsed = parse_results_document(_pdf(tmp_path, [primera, segunda]))
        assert len(parsed.categories) == 1
        assert [r.position for r in parsed.categories[0].rows] == [1, 2]

    def test_categorias_sin_codigo_conservan_sus_filas(self, tmp_path: Path) -> None:
        tablas = [
            _table("NOVATOS", "2", _COLS_NOPTS,
                   [["1", "40", "Pérez Lopera", "Ana", "0:10:00", "Club Uno"]]),
            _table("PRE-INFANTIL A-MIXTO", "1", _COLS_NOPTS,
                   [["1", "41", "Soto Ruiz", "Luis", "0:04:00", "Club Dos"]]),
        ]
        parsed = parse_results_document(_pdf(tmp_path, tablas))
        assert [(c.header_raw, c.code, len(c.rows)) for c in parsed.categories] == [
            ("NOVATOS", None, 1),
            ("PRE-INFANTIL A-MIXTO", None, 1),
        ]


class TestPdfDepartamental:
    def test_medalla_no_se_mezcla_con_el_club_ni_con_los_puntos(self, tmp_path: Path) -> None:
        filas = [
            ["1", "467", "Pérez Lopera", "Ana", "0:03:42", "Club Uno", "Oro"],
            ["2", "272", "Soto Ruiz", "Luis", "0:04:35", "Club Dos", "Plata"],
            ["3", "432", "Rojas Paz", "Omar", "- 1 VUELTA", "Club Tres", ""],
            ["4", "461", "Vega Sol", "Río", "DNF", "Club Cuatro", ""],
        ]
        parsed = parse_results_document(
            _pdf(tmp_path, [_table("TETERO SIN PEDALES", "", _COLS_MED, filas)])
        )
        (cat,) = parsed.categories
        assert cat.header_raw == "TETERO SIN PEDALES" and cat.code == "TET_SP"
        assert parsed.unreadable_rows == []
        assert [r.club for r in cat.rows] == ["Club Uno", "Club Dos", "Club Tres", "Club Cuatro"]
        assert [r.time_raw for r in cat.rows] == ["0:03:42", "0:04:35", "- 1 VUELTA", "DNF"]
        assert [r.points for r in cat.rows] == [40, 36, 33, 1]
        assert parsed.points_inferred_rows == 4

    def test_municipio_en_lugar_de_club(self, tmp_path: Path) -> None:
        columnas = ["Pos", "N°", "Apellidos", "Nombres", "Time", "Municipio", "Medalla"]
        filas = [["1", "467", "Pérez Lopera", "Ana", "0:03:42", "Ciudad Ficticia", "Oro"]]
        parsed = parse_results_document(
            _pdf(tmp_path, [_table("TETERO SIN PEDALES", "", columnas, filas)])
        )
        (row,) = parsed.categories[0].rows
        assert row.club == "Ciudad Ficticia" and row.name == "Ana Pérez Lopera"


class TestCategoriasPorTemporada:
    """``apply_season_categories``: la temporada viene de los parámetros del
    staging, no del PDF, y re-resuelve los encabezados que 2023 escribe igual
    que 2022 (Sport, Máster A1/A2) o que solo existen en 2023."""

    def _pdf_2023(self, tmp_path: Path) -> Path:
        fila = lambda bib: [["1", bib, "Pérez Lopera", "Ana", "0:10:00", "Club Uno"]]  # noqa: E731
        return _pdf(
            tmp_path,
            [
                _table("SPORT A", "3A", _COLS_NOPTS, fila("11")),
                _table("MASTER A1", "3B", _COLS_NOPTS, fila("12")),
                _table("NOVATOS", "2", _COLS_NOPTS, fila("13")),
                _table("NOVATAS", "2", _COLS_NOPTS, fila("14")),
                _table("PRE-INFANTIL A-MIXTO", "1", _COLS_NOPTS, fila("15")),
                _table("MASTER D1", "3B", _COLS_NOPTS, fila("16")),
            ],
        )

    def test_con_2023_usa_los_codigos_de_la_temporada(self, tmp_path: Path) -> None:
        from app.services.race.pdf_parser import apply_season_categories

        parsed = apply_season_categories(parse_results_document(self._pdf_2023(tmp_path)), 2023)
        assert [c.code for c in parsed.categories] == [
            "SPORT_A_2023", "MAS_A1_2023", "NOV_2023", "NOV_F_2023",
            "PRE_A_MIX_2023", "MAS_D",
        ]
        assert all(len(c.rows) == 1 for c in parsed.categories)

    def test_sin_temporada_o_con_2022_nada_cambia(self, tmp_path: Path) -> None:
        from app.services.race.pdf_parser import apply_season_categories

        for season in (None, 2022):
            parsed = apply_season_categories(
                parse_results_document(self._pdf_2023(tmp_path)), season
            )
            assert [c.code for c in parsed.categories] == [
                "SPORT_A_2022", "MAS_A1_2022", None, None, None, "MAS_D",
            ]

    def test_es_idempotente(self, tmp_path: Path) -> None:
        from app.services.race.pdf_parser import apply_season_categories

        parsed = parse_results_document(self._pdf_2023(tmp_path))
        once = [c.code for c in apply_season_categories(parsed, 2023).categories]
        twice = [c.code for c in apply_season_categories(parsed, 2023).categories]
        assert once == twice


def test_categories_read_clasifica_2023_como_propia_de_temporada() -> None:
    from types import SimpleNamespace

    from app.services.race.import_staging import _categories_read
    from app.services.race.pdf_parser import ParsedCategory

    parsed = ParsedResults(
        categories=[ParsedCategory(header_raw="SPORT A", code="SPORT_A_2023", rows=[])]
    )
    cats = {"SPORT_A_2023": SimpleNamespace(is_active=False, label="Sport A (2023)")}
    (read,) = _categories_read(parsed, cats, 2023)
    assert read.code == "SPORT_A_2023" and read.mapping_kind == "season_specific"
