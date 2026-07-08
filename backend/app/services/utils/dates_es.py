"""Shared Spanish (es-CO) date formatting helper.

Inputs: a single `datetime.date` (or `None`).
Outputs: a locale-independent Spanish string like "1 de agosto de 2026",
or "" when the input is `None`.
Side-effects: none (pure function).

Ported from `race_insight_dispatcher._format_date_es` (R8) so it can be
reused as a Jinja filter (`date_es`) across notification templates without
depending on `babel` or the OS locale via `strftime("%B")`.
"""

from __future__ import annotations

from datetime import date, datetime

_MONTHS_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def format_date_es(d: date | str | None) -> str:
    """Formatea una fecha como '1 de agosto de 2026'. Retorna '' si `d` es None.

    Acepta un ``datetime.date`` o una cadena ISO ('2026-08-01'), porque los
    boletines persisten ``email_blocks`` en una columna JSON donde las fechas
    quedan serializadas como strings ISO. Una cadena no parseable se devuelve
    tal cual (degradación elegante, nunca lanza en render).
    """
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    elif isinstance(d, datetime):
        d = d.date()
    return f"{d.day} de {_MONTHS_ES[d.month]} de {d.year}"
