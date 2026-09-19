"""Tests unitarios de ``_band_text`` (feature 044, T011).

``_band_text(chars, bbox) -> str`` es el lector de bandas descrito en
``specs/044-race-history-backfill/research.md`` R-01 punto 2 y en el
contrato ``contracts/reading-integrity.md``: reconstruye el texto de una
fila de resultados leyendo ``page.chars`` **en orden de flujo del PDF**
(nunca ordenado por ``x``), porque cuando un ``Club/Patrocinador`` largo se
desborda visualmente sobre la columna ``Tiempo``, ordenar por posición ``x``
produce texto intercalado ilegible mientras que el orden en que el PDF
*dibuja* los caracteres mantiene club y tiempo limpios y contiguos.

Regla exacta de inserción de espacio (R-01 punto 2, única fuente de verdad
para estos tests): "Insert a space when the gap to the previous char exceeds
1 pt or when x jumps backwards (the start of the next cell's text run)". Es
decir, puramente mecánica sobre ``x0``/``x1`` — ``_band_text`` no intenta
adivinar límites de columna ni contar cuántas columnas quedaron vacías.

Función pura, sin PDF real: los "chars" son diccionarios armados a mano con
las claves que expone ``page.chars`` de pdfplumber (``text``, ``x0``,
``x1``, ``top``, ``bottom``). El filtrado por banda ("chars whose top/bottom
fall inside the band", R-01 punto 2) usa solo el rango vertical de ``bbox``
— el ancho horizontal de ``bbox`` no filtra nada porque el propósito mismo
del band-first reading es capturar texto que se desborda horizontalmente
fuera de su columna nominal.

Supuesto de forma de ``bbox`` (el contrato solo da el nombre del parámetro,
no su forma): tupla ``(x0, top, x1, bottom)``, la misma convención que usa
pdfplumber en ``Page.crop``/``Table.rows[i].bbox`` y que ya sigue este
módulo en ``_TABLE_SETTINGS``. Si la implementación real (T015) usa otra
forma, este archivo es el primer lugar a ajustar — ver el reporte de
ambigüedades a ``engineering-lead``.

Nota de alcance: el caso "club que termina en dígito no debe tragarse la
hora" se prueba aquí solo a nivel de ``_band_text`` (ningún carácter se
pierde ni se fusiona en la reconstrucción). La garantía real anti-swallow —
que el regex de fila no confunda ese dígito con la hora — vive en el
lookbehind ``(?<![\\d:])`` de ``_RESULTS_ROW_RE`` (R-01 punto 3) y se
prueba en ``test_parser_historical_layout.py`` (T012), no aquí.
"""
from __future__ import annotations

import pytest

from app.services.race import pdf_parser

# ---------------------------------------------------------------------------
# Helpers de construcción de chars sintéticos
# ---------------------------------------------------------------------------

#: Banda "normal" de fila usada por la mayoría de los casos — 10pt de alto,
#: ancho de sobra para no recortar nada horizontalmente (ver docstring).
_ROW_BBOX = (0.0, 200.0, 900.0, 210.0)


def _char(text: str, x0: float, x1: float, *, top: float = 200.0, bottom: float = 210.0) -> dict:
    """Un char sintético con las claves mínimas de ``page.chars``."""
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom}


def _run(
    s: str,
    start_x: float,
    *,
    char_width: float = 6.0,
    top: float = 200.0,
    bottom: float = 210.0,
) -> list[dict]:
    """Genera chars contiguos (gap=0 entre ellos) para un run de texto.

    pdfplumber no emite un char de espacio entre columnas — por eso
    ``_band_text`` reconstruye el espaciado a partir de los huecos en
    ``x``, nunca de un carácter de espacio real en el stream. Dentro de un
    mismo run (misma "palabra") los chars están pegados (gap=0), igual que
    en un PDF real bien formado.
    """
    chars = []
    x = start_x
    for ch in s:
        chars.append(_char(ch, x, x + char_width, top=top, bottom=bottom))
        x += char_width
    return chars


def _last_x1(chars: list[dict]) -> float:
    return chars[-1]["x1"]


# ===========================================================================
# Caso 1 — club y tiempo superpuestos (R-01 punto 2, desborde real)
# ===========================================================================


class TestOverlappingClubAndTime:
    """Club largo desbordado sobre Tiempo: orden de flujo, no orden por x."""

    def test_stream_order_reconstructs_club_then_time_with_inserted_space(self):
        """El club completo se dibuja primero (orden de flujo); el tiempo
        empieza visualmente ANTES de que el club termine (desborde real:
        x0 del tiempo < x1 del último char del club) — eso es justo el
        salto hacia atrás que dispara el espacio insertado."""
        club = _run("FUNDACIONFICTICIA", start_x=300.0)  # x1 final = 408.0
        time = _run("0:40:07", start_x=390.0)  # 390 < 408 -> salto atrás
        chars = club + time  # orden de flujo real del PDF

        text = pdf_parser._band_text(chars, _ROW_BBOX)

        assert text == "FUNDACIONFICTICIA 0:40:07"

    def test_backward_jump_triggers_exactly_one_inserted_space(self):
        """El espacio insertado es siempre uno solo, sin importar cuánto
        se solape el club sobre el tiempo (no es proporcional al desborde)."""
        club = _run("ASOCIACIONFICTICIACOMUNITARIA", start_x=300.0)
        time = _run("0:41:14", start_x=305.0)  # solape mucho mayor
        chars = club + time

        text = pdf_parser._band_text(chars, _ROW_BBOX)

        assert text == "ASOCIACIONFICTICIACOMUNITARIA 0:41:14"
        assert "  " not in text  # nunca dos espacios seguidos


# ===========================================================================
# Caso 2 — club pegado al tiempo sin espacio (R-01, "segundo modo de pérdida")
# ===========================================================================


class TestClubFlushAgainstTime:
    """Club que termina exactamente donde empieza Tiempo: gap=0, sin salto
    hacia atrás -> ninguna de las dos condiciones de la regla se cumple, así
    que ``_band_text`` NO inventa un espacio. Reproduce fielmente el
    defecto real descrito en R-01 (segundo modo de pérdida, más pequeño que
    el solape)."""

    def test_zero_gap_no_backward_jump_produces_no_space(self):
        club = _run("FICTICIOFC", start_x=300.0)  # x1 final = 360.0
        time = _run("0:40:07", start_x=_last_x1(club))  # flush exacto
        chars = club + time

        text = pdf_parser._band_text(chars, _ROW_BBOX)

        assert text == "FICTICIOFC0:40:07"


# ===========================================================================
# Caso 3 — club que termina en dígito: no se pierde ni se funde ningún carácter
# ===========================================================================


class TestClubEndingInDigitDoesNotSwallowHour:
    """Club terminado en dígito, pegado (gap=0) a una hora de un solo
    dígito. A nivel de ``_band_text`` la garantía es que NINGÚN carácter se
    pierde o se fusiona en la reconstrucción — evitar que la hora quede
    "tragada" en el regex de fila (R-01 punto 3, lookbehind
    ``(?<![\\d:])``) es responsabilidad de una capa distinta, probada en
    T012/T015."""

    def test_both_digits_survive_adjacent_and_untouched(self):
        club = _run("MODELOFC7", start_x=300.0)  # último char: dígito "7"
        time = _run("9:15:22", start_x=_last_x1(club))  # hora de 1 dígito "9"
        chars = club + time

        text = pdf_parser._band_text(chars, _ROW_BBOX)

        assert text == "MODELOFC79:15:22"
        # Ambos dígitos están presentes, adyacentes, en el orden correcto —
        # ninguno fue eliminado ni se generó un carácter espurio entre ellos.
        assert "79:15:22" in text
        assert len(text) == len(club) + len(time)


# ===========================================================================
# Caso 4 — fila sin tiempo ("clasificada sin tiempo", R-01 punto 4)
# ===========================================================================


class TestRowWithoutTime:
    """Banda que solo trae ``pos bib body points`` — sin ningún run de
    tiempo. ``_band_text`` no requiere un run de tiempo para funcionar:
    simplemente reconstruye lo que hay."""

    def test_reconstructs_body_and_points_without_a_time_run(self):
        body = _run("NOMBREFICTICIOCIUDADCLUB", start_x=100.0)
        points = _run("50", start_x=_last_x1(body) + 5.0)  # gap > 1pt

        text = pdf_parser._band_text(body + points, _ROW_BBOX)

        assert text == "NOMBREFICTICIOCIUDADCLUB 50"
        assert ":" not in text  # ningún resto de tiempo


# ===========================================================================
# Caso 5 — tokens de estado DNF / DSQ / DNS
# ===========================================================================


class TestStatusTokens:
    """``_band_text`` no reconoce estos tokens de forma especial — solo
    reconstruye el texto tal cual aparece; el regex de fila es quien los
    interpreta (sin cambios en esta capa)."""

    @pytest.mark.parametrize("token", ["DNF", "DSQ", "DNS"])
    def test_status_token_reconstructed_as_plain_text(self, token: str):
        body = _run("CORREDORFICTICIO", start_x=100.0)
        status = _run(token, start_x=_last_x1(body) + 4.0)
        points = _run("0", start_x=_last_x1(status) + 4.0)

        text = pdf_parser._band_text(body + status + points, _ROW_BBOX)

        assert text == f"CORREDORFICTICIO {token} 0"


# ===========================================================================
# Caso 6 — "(-2 VUELTAS)"
# ===========================================================================


class TestMinusLapsToken:
    def test_parenthesized_minus_laps_reconstructed_with_internal_space(self):
        # "(-2" pegado (gap=0); espacio real (gap>1pt) antes de "VUELTAS)".
        open_part = _run("(-2", start_x=100.0)
        close_part = _run("VUELTAS)", start_x=_last_x1(open_part) + 4.0)

        text = pdf_parser._band_text(open_part + close_part, _ROW_BBOX)

        assert text == "(-2 VUELTAS)"


# ===========================================================================
# Caso 7 — ciudad y club vacíos (columnas sin chars, no una banda vacía)
# ===========================================================================


class TestEmptyCityAndClub:
    """Cuando ciudad y club no imprimieron ningún carácter (columnas en
    blanco del PDF oficial), el hueco en ``x`` entre el nombre y el tiempo
    es simplemente un gap grande — y la regla mecánica de ``_band_text``
    lo colapsa a UN solo espacio, igual que cualquier otro gap > 1pt. No
    hay lógica especial para "columnas saltadas": eso es justo lo que hace
    a la regla predecible."""

    def test_large_gap_from_skipped_columns_collapses_to_one_space(self):
        name = _run("NOMBREFICTICIO", start_x=100.0)
        # Gap grande (ciudad + club en blanco) — muy por encima de 1pt.
        time = _run("0:40:07", start_x=_last_x1(name) + 50.0)

        text = pdf_parser._band_text(name + time, _ROW_BBOX)

        assert text == "NOMBREFICTICIO 0:40:07"
        assert "  " not in text


# ===========================================================================
# Filtrado vertical por banda (bbox.top/bottom) — implícito en la firma
# ===========================================================================


class TestBandVerticalFiltering:
    """``_band_text`` recibe la lista completa de chars relevantes y un
    ``bbox`` por fila; debe ignorar chars de una banda vecina aunque
    aparezcan intercalados en la lista de entrada (como ocurriría si se
    pasara ``page.chars`` de la página completa sin pre-filtrar)."""

    def test_ignores_chars_outside_the_band_even_if_interleaved(self):
        band_a = _run("UNO", start_x=100.0, top=200.0, bottom=210.0)
        band_b = _run("DOS", start_x=100.0, top=211.0, bottom=221.0)  # fila vecina
        interleaved = [c for pair in zip(band_a, band_b) for c in pair]

        bbox_a = (0.0, 200.0, 900.0, 210.0)
        bbox_b = (0.0, 211.0, 900.0, 221.0)

        assert pdf_parser._band_text(interleaved, bbox_a) == "UNO"
        assert pdf_parser._band_text(interleaved, bbox_b) == "DOS"

    def test_empty_chars_list_returns_empty_string(self):
        assert pdf_parser._band_text([], _ROW_BBOX) == ""
