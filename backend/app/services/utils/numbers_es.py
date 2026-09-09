"""Shared Spanish (es-CO) number formatting helper.

Inputs: a number (`int`/`float`/`None`), a decimal-place count, and two
optional flags. Outputs: a locale-independent Spanish string using `,` as
decimal separator (e.g. "8,6"), or "" when the input is `None`.
Side-effects: none (pure function).

Español neutro de Colombia usa coma decimal, nunca punto (CLAUDE.md
"Language split": copy de cara a la familia = español con diacríticos
completos). Antes de este helper, cada plantilla PDF formateaba números
directo con el filtro `format` de Jinja (`"%.1f"|format(x)`), que produce
salida con notación inglesa ("8.6") sin importar el locale — de ahí que el
boletín completo imprimiera punto decimal. Centralizado acá (mismo patrón
que `dates_es.py::format_date_es`) para no repetir el `.replace(".", ",")`
en cada plantilla, y para que un futuro cambio de convención se edite en un
solo lugar.

Registrado como filtro Jinja `num_es` en
``DocumentGenerator`` (junto a `date_es`/`hms`/`markdown`) — ver
``app/services/notification/document_generator.py``.
"""

from __future__ import annotations


def format_number_es(
    value: float | int | None,
    decimals: int = 1,
    *,
    sign: bool = False,
    trim_zero: bool = False,
) -> str:
    """Formatea un número con coma decimal (es-CO).

    Args:
        value: el número a formatear, o `None` (retorna "").
        decimals: cantidad fija de decimales (antes de cualquier recorte).
        sign: si `True`, antepone siempre '+' a valores >= 0 (ej. maturity
            offset: "+1,19" / "-1,66") — igual que el `:+.Nf` de Python.
        trim_zero: si `True`, quita el decimal cuando es ",0" sobrante (ej.
            "12,0" -> "12") para números donde esa precisión no aporta
            (ej. horas de entrenamiento redondas) — nunca se usa en tablas
            con columnas alineadas, donde la cantidad de decimales debe ser
            constante fila a fila.

    Ej.: format_number_es(8.6) -> "8,6"; format_number_es(-1.66, 2) -> "-1,66";
    format_number_es(1.19, 2, sign=True) -> "+1,19";
    format_number_es(12.0, 1, trim_zero=True) -> "12".
    """
    if value is None:
        return ""
    num = float(value)
    text = f"{num:+.{decimals}f}" if sign else f"{num:.{decimals}f}"
    if trim_zero and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")
