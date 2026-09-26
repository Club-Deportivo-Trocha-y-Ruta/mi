"""Especificación de categorías reutilizada por el golden de paridad (T122).

Un solo lugar para las categorías/filas usadas tanto para generar
``tests/fixtures/race/parity/{historical,2026}.json`` (con el parser
retirado, antes de que T153 lo borre) como para reconstruir el mismo PDF en
``test_apply_profile.py`` y compararlo fila por fila contra ese golden.

Cubre a propósito (contracts/reading-profile.md § Tests):
- un club desbordado sobre la columna Tiempo (``long_club``, solo tiene
  efecto visual en el layout ``historical``);
- un ordinal quitado (4) y uno duplicado;
- una fila clasificada sin tiempo.

No se llama con el mismo ``FakeNameGenerator`` entre corridas del builder y
del golden generator — cada llamador crea su propio generador con la misma
semilla por defecto (``DEFAULT_SEED``), así que los nombres producidos son
siempre los mismos.
"""
from __future__ import annotations

from tests.helpers.results_pdf_builder import CategorySpec, sequential_category


def build_parity_categories() -> list[CategorySpec]:
    cats = [
        sequential_category("INFANTIL A", 5),
        sequential_category("PREJUVENIL A DAMAS", 3),
    ]
    cats[0].rows[1].long_club = True
    del cats[0].rows[3]
    cats[0].rows[-1].position = cats[0].rows[-2].position
    cats[1].rows[0].time_raw = None
    cats[1].rows[0].status = None
    cats[1].rows[0].minus_laps = None
    return cats
