"""Grupo de comparación derivado para copas y campeonatos (feature 039).

Módulo puro — sin acceso a base de datos ni efectos secundarios. Expone tres
funciones consumidas por ``analytics.athlete_progression`` (T007),
``analytics_charts.build_evolution`` (US2) y
``newsletter_builder._build_race_block`` / ``_build_charts_context`` (US1):

- :func:`build_comparison_group` — clave estable ``"cup:{id}"`` /
  ``"championship:{id}"`` para agrupar filas de progreso.
- :func:`group_label` — etiqueta legible del grupo (copa o campeonato).
- :func:`split_progression` — separa un histórico plano en copas (agrupadas
  por serie, ordenadas entre sí por su válida más temprana) y campeonatos
  (una fila cada uno, cronológicos, sin agrupar).

Decisión (``research.md`` D1): el grupo de comparación NO se persiste — es
una función pura de columnas que ya existen en ``race_series``
(``kind``, ``id``). Cada campeonato ya es su propia serie (spec 014), así que
agrupar por ``series_id`` alcanza sin migración. D2 fija las reglas de
etiquetado: las copas usan ``"{name} {season_year}"`` (la ubicación se
ignora); los campeonatos delegan en ``race_labels.build_race_label`` con
``sequence_number=1`` (INV-2: un campeonato tiene un único evento).

Todas las funciones aceptan ``RaceSeriesKind``/``RaceSeriesLevel`` como enum
o como su valor string — mismo patrón dual-driver que
``analytics_charts.py`` (aiosqlite conserva el enum de Python; otros paths
de serialización pueden entregar el string crudo).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.services.race.race_labels import build_race_label

__all__ = [
    "CupProgression",
    "SplitProgression",
    "build_comparison_group",
    "group_label",
    "split_progression",
]

#: Fila mínima que consume ``split_progression`` — dict o ``pandas.Series``,
#: cualquier cosa indexable por nombre de columna sirve.
ProgressionRow = Mapping[str, Any]


# ---------------------------------------------------------------------------
# Normalización enum/string (mismo patrón que analytics_charts.py)
# ---------------------------------------------------------------------------


def _normalize_kind(kind: RaceSeriesKind | str) -> RaceSeriesKind:
    """Normaliza ``kind`` (enum ``RaceSeriesKind`` o su valor string)."""
    kind_str = kind.value if isinstance(kind, RaceSeriesKind) else str(kind)
    return RaceSeriesKind(kind_str)


def _normalize_level(level: RaceSeriesLevel | str | None) -> RaceSeriesLevel:
    """Normaliza ``level`` (enum, string o ``None``/vacío → ``departmental``)."""
    level_str = level.value if isinstance(level, RaceSeriesLevel) else str(level or "")
    return RaceSeriesLevel(level_str) if level_str else RaceSeriesLevel.departmental


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def build_comparison_group(kind: RaceSeriesKind | str, series_id: int) -> str:
    """Construye la clave estable del grupo de comparación de una serie.

    Args:
        kind: ``RaceSeriesKind`` o su valor string (``"cup"``/``"championship"``).
        series_id: PK de ``RaceSeries``.

    Returns:
        ``"cup:{series_id}"`` o ``"championship:{series_id}"``.
    """
    return f"{_normalize_kind(kind).value}:{series_id}"


def group_label(
    kind: RaceSeriesKind | str,
    level: RaceSeriesLevel | str,
    name: str,
    season_year: int,
    location: str | None = None,
) -> str:
    """Etiqueta legible de un grupo de comparación.

    Args:
        kind: ``RaceSeriesKind`` o su valor string.
        level: ``RaceSeriesLevel`` o su valor string; ignorado para copas.
        name: nombre de la serie (``race_series.name``, sin año).
        season_year: año de temporada.
        location: ciudad del evento; ignorada para copas (D2 — una copa
            recorre varias sedes, no tiene una sola ubicación).

    Returns:
        Copas: ``f"{name} {season_year}"``. Campeonatos: delega en
        ``race_labels.build_race_label(kind, 1, location, level=level)``
        (``sequence_number=1`` — INV-2, un campeonato es un único evento).
    """
    kind_enum = _normalize_kind(kind)
    if kind_enum is RaceSeriesKind.championship:
        return build_race_label(kind_enum, 1, location, level=_normalize_level(level))
    return f"{name} {season_year}"


@dataclass(frozen=True)
class CupProgression:
    """Historial de una copa dentro de un ``SplitProgression``.

    ``rows`` queda ordenado cronológicamente por ``event_date``.
    """

    series_id: int
    label: str
    rows: list[ProgressionRow]


@dataclass(frozen=True)
class SplitProgression:
    """Resultado de :func:`split_progression`.

    ``cups`` está ordenado entre sí por la fecha de su válida más temprana
    (no por ``series_id`` ni por orden de inserción). ``championships`` no
    se agrupa (INV-2: una fila por campeonato) y queda cronológico.
    """

    cups: list[CupProgression]
    championships: list[ProgressionRow]


def split_progression(rows: Sequence[ProgressionRow]) -> SplitProgression:
    """Separa un histórico plano de progreso en copas y campeonatos.

    Args:
        rows: filas con, como mínimo, ``series_id``, ``series_kind``,
            ``series_level``, ``series_name``, ``season_year`` y
            ``event_date`` (p. ej. columnas de
            ``analytics.athlete_progression``). Entrada vacía → resultado
            con ambas listas vacías.

    Returns:
        ``SplitProgression`` con las copas agrupadas por ``series_id``
        (filas internas cronológicas, copas entre sí ordenadas por su
        válida más temprana) y los campeonatos como filas sueltas,
        cronológicas y sin agrupar (INV-2).
    """
    cup_rows_by_series: dict[int, list[ProgressionRow]] = {}
    championship_rows: list[ProgressionRow] = []

    for row in rows:
        if _normalize_kind(row["series_kind"]) is RaceSeriesKind.championship:
            championship_rows.append(row)
        else:
            cup_rows_by_series.setdefault(row["series_id"], []).append(row)

    cups: list[CupProgression] = []
    for series_id, group_rows in cup_rows_by_series.items():
        sorted_rows = sorted(group_rows, key=lambda r: r["event_date"])
        first_row = sorted_rows[0]
        label = group_label(
            first_row["series_kind"],
            first_row.get("series_level"),
            first_row["series_name"],
            first_row["season_year"],
        )
        cups.append(CupProgression(series_id=series_id, label=label, rows=sorted_rows))

    # Copas entre sí: por la fecha de su válida más temprana (rows[0] ya es
    # la más temprana dentro de cada copa gracias al sort anterior).
    cups.sort(key=lambda cup: cup.rows[0]["event_date"])
    championship_rows = sorted(championship_rows, key=lambda r: r["event_date"])

    return SplitProgression(cups=cups, championships=championship_rows)
