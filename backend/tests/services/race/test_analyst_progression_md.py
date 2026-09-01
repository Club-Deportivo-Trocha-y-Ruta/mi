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
