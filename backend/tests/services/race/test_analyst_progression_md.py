"""Regression (feature 036, Wave 3 / US2): ``_progression_to_md`` y DNF.

Bug encontrado durante la integración de T059: un record con
``position: None`` (DNF/DNS/DSQ — ver golden ``case_003``/``case_009``, que
ya traían esta forma antes de esta ola) se renderizaba como la columna
literal ``None`` en la tabla markdown, porque ``dict.get("position", "")``
sólo aplica el default cuando la CLAVE está ausente, no cuando el valor es
``None``. La cadena ``"None"`` terminaba en el contexto que recibe el LLM,
lo mismo que la Sección "Recorrido hasta acá" del prompt v2 consume.
``race_time_ms`` no tiene este problema porque ya pasa por
``_format_ms_hhmmss``, que sí tiene un caso explícito para ``None``.
"""
from __future__ import annotations

from app.services.race.agents.analyst import _progression_to_md


def test_progression_to_md_dnf_row_shows_placeholder_not_literal_none():
    """Fila DNF (position=None, race_time_ms=None) no debe imprimir "None"."""
    md = _progression_to_md(
        [
            {
                "valida_num": 3,
                "event_date": "2026-04-19",
                "position": None,
                "race_time_ms": None,
                "points_awarded": 0,
            }
        ]
    )
    assert "None" not in md
    assert "—" in md


def test_progression_to_md_populated_row_unaffected():
    """Control positivo: una fila normal sigue mostrando su posición real."""
    md = _progression_to_md(
        [
            {
                "valida_num": 1,
                "event_date": "2026-03-01",
                "position": 4,
                "race_time_ms": 2_179_000,
                "points_awarded": 12,
            }
        ]
    )
    assert "| 4 |" in md
    assert "None" not in md


def test_progression_to_md_only_cup_rows_has_no_heading():
    """Solo copa (sin campeonato) mantiene la tabla única de siempre (F-4)."""
    md = _progression_to_md(
        [
            {
                "valida_num": 1,
                "event_date": "2026-03-01",
                "series_kind": "cup",
                "position": 4,
                "race_time_ms": 2_179_000,
                "points_awarded": 12,
            }
        ]
    )
    assert "**Válidas de copa**" not in md
    assert "**Campeonatos" not in md
    assert "| 4 |" in md


def test_progression_to_md_splits_cup_and_championship_into_two_tables():
    """Copa + campeonato en la misma temporada → dos tablas rotuladas (F-4)."""
    md = _progression_to_md(
        [
            {
                "valida_num": 1,
                "event_date": "2026-03-01",
                "series_kind": "cup",
                "position": 4,
                "race_time_ms": 2_179_000,
                "points_awarded": 12,
            },
            {
                "valida_num": 6,
                "event_date": "2026-06-14",
                "series_kind": "championship",
                "series_level": "national",
                "position": 9,
                "race_time_ms": 2_500_000,
                "points_awarded": 0,
            },
        ]
    )
    assert "**Válidas de copa**" in md
    assert "**Campeonatos (pelotón propio, no comparable con la copa)**" in md
    cup_heading_idx = md.index("**Válidas de copa**")
    champ_heading_idx = md.index("**Campeonatos")
    champ_row_idx = md.index("| 6 |")
    assert cup_heading_idx < champ_heading_idx < champ_row_idx
    assert "Cto. Nacional" in md


def test_progression_to_md_groups_cup_rows_by_series_when_series_id_present():
    """Dos copas distintas (``series_id`` presente) → una sub-tabla cada una."""
    md = _progression_to_md(
        [
            {
                "valida_num": 1,
                "event_date": "2026-03-01",
                "series_kind": "cup",
                "series_id": 10,
                "series_name": "Copa Valle",
                "position": 4,
                "race_time_ms": 2_179_000,
                "points_awarded": 12,
            },
            {
                "valida_num": 1,
                "event_date": "2026-04-01",
                "series_kind": "cup",
                "series_id": 11,
                "series_name": "Copa Norte",
                "position": 2,
                "race_time_ms": 2_050_000,
                "points_awarded": 20,
            },
        ]
    )
    assert "*Copa Valle*" in md
    assert "*Copa Norte*" in md
    assert "**Campeonatos" not in md
