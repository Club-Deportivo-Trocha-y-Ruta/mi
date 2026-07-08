"""Constructor de etiquetas legibles para resultados de carrera.

Función pura que convierte ``(kind, sequence_number, location, level)`` en
una cadena de texto lista para mostrar en la UI y en reportes.  No accede a
la base de datos ni produce efectos secundarios.

Contrato:
    - ``cup``                             → ``"Válida {romano} — {ciudad}"``
      (``level`` se ignora — las copas no exponen ámbito territorial).
    - ``championship`` + ``departmental`` → ``"Cto. Dep. — {ciudad}"``
      (``sequence_number`` ignorado).
    - ``championship`` + ``national``     → ``"Cto. Nal. — {ciudad}"``
      (spec 023 — Campeonato Nacional MTB 2026, Pereira).
    - Si ``location`` es ``None`` o cadena vacía, se omite el sufijo
      ``" — {ciudad}"`` completo.
    - Números romanos del 1 al 7; fuera de ese rango se usa el entero como
      cadena de texto.
    - ``level`` es un parámetro con valor por defecto (``departmental``) —
      todo llamador previo a la feature 023 sigue compilando y produciendo
      el mismo resultado sin modificarse.

Reutilizado por:
    - ``GET /races`` (US2 — lista de carreras)
    - ``GET /evolution`` serializer (US3 — gráfico de evolución)
"""
from __future__ import annotations

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel

__all__ = ["build_race_label"]

# ---------------------------------------------------------------------------
# Helper privado: numerales romanos
# ---------------------------------------------------------------------------

_ROMAN: dict[int, str] = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
    6: "VI",
    7: "VII",
}


def _to_roman(n: int) -> str:
    """Devuelve el numeral romano para *n* (1..7) o el entero como cadena."""
    return _ROMAN.get(n, str(n))


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def build_race_label(
    kind: RaceSeriesKind,
    sequence_number: int,
    location: str | None,
    level: RaceSeriesLevel = RaceSeriesLevel.departmental,
) -> str:
    """Construye la etiqueta visible de una carrera.

    Args:
        kind:            Tipo de serie (``cup`` o ``championship``).
        sequence_number: Número de válida dentro de la copa (ignorado para
                         campeonatos).
        location:        Ciudad o nombre del lugar.  ``None`` o cadena vacía
                         omite el sufijo geográfico.
        level:           Ámbito territorial del campeonato (``departmental``
                         o ``national``, spec 023). Ignorado para copas.
                         Por defecto ``departmental`` — mantiene compatible
                         a todo llamador anterior a la feature 023.

    Returns:
        Cadena en español neutro lista para la UI, p. ej.
        ``"Válida IV — Cali"``, ``"Cto. Dep. — Ginebra"`` o
        ``"Cto. Nal. — Pereira"``.
    """
    city_part = f" — {location}" if location and location.strip() else ""

    if kind is RaceSeriesKind.championship:
        prefix = "Cto. Nal." if level is RaceSeriesLevel.national else "Cto. Dep."
        return f"{prefix}{city_part}"

    # cup (predeterminado)
    return f"Válida {_to_roman(sequence_number)}{city_part}"
