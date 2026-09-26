"""``assert_no_fake_names`` (amendment 2026-09-26, T110).

Guardia reutilizable de privacidad para los tests de esta feature: falla si
cualquier palabra de tres o más letras de los nombres, clubes o ciudades que
un ``FakeNameGenerator`` produjo (o pudo producir — los pools de club/ciudad
son fijos por módulo, no por instancia) aparece en un texto dado, plegando
acentos primero (para no dejar pasar "Ficticio" vs "FICTICIO" o una "í" vs
"i" sueltas).

Lo reusan T119 (masking), el CLI de la fase 15 (stdout) y este mismo test de
``staged_document`` (T112): en los tres casos el riesgo es el mismo — un
nombre, ciudad o club de un corredor sintético coló a un lugar que un LLM o
una consola pueden leer.

No usa la lista real de nombres del proyecto ni ninguna lista de personas
reales: el vocabulario viene siempre del generador de fixtures.
"""
from __future__ import annotations

import re
import unicodedata

from tests.helpers.results_pdf_builder import (
    CITY_POOL,
    CLUB_POOL,
    FIRST_NAMES,
    LAST_NAMES,
    LONG_CLUB_POOL,
    FakeNameGenerator,
)

_WORD_RE = re.compile(r"[A-Za-z]+")


def _fold(text: str) -> str:
    """Mayúsculas, sin acentos — ``"Ficticio"`` y ``"FICTÍCIO"`` pliegan igual."""
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.upper()


def _words(text: str, *, min_len: int = 3) -> set[str]:
    return {w for w in _WORD_RE.findall(_fold(text)) if len(w) >= min_len}


def fake_name_vocabulary(generator: FakeNameGenerator) -> set[str]:
    """Todas las palabras (plegadas, ``len >= 3``) que el generador puede
    producir: sus nombres ya generados más los pools fijos de ciudad/club
    que ``next_city``/``next_club``/``next_long_club`` usan."""
    vocab: set[str] = set()
    for name in generator.generated:
        vocab |= _words(name)
    for pool in (FIRST_NAMES, LAST_NAMES, CITY_POOL, CLUB_POOL, LONG_CLUB_POOL):
        for entry in pool:
            vocab |= _words(entry)
    return vocab


def assert_no_fake_names(text: str, generator: FakeNameGenerator) -> None:
    """Lanza ``AssertionError`` si alguna palabra del vocabulario ficticio
    del generador (``len >= 3``, plegada) aparece como palabra completa en
    ``text``."""
    found = fake_name_vocabulary(generator) & _words(text)
    assert not found, (
        f"texto contiene {len(found)} palabra(s) del generador de nombres "
        f"ficticios: {sorted(found)}"
    )
