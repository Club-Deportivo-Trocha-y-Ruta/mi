"""Vocabulario de palabras estructurales (amendment 2026-09-26, T125).

``VOCABULARY`` es el conjunto cerrado de palabras que ``masking.py`` puede
mostrar verbatim en una línea estructural (``contracts/masked-view.md`` §
Vocabulario): encabezados de columna, palabras de documento, numerales
romanos y conectores gramaticales — nunca un nombre, ciudad o club de un
corredor.

**Regla de revisión**: añadir una palabra requiere un pull request tocado
por ``data-privacy-guard``. El motivo es que este conjunto es la única
barrera entre el archivo real y lo que un LLM llega a leer — una palabra
añadida sin revisión podría, en teoría, colar un nombre propio si alguna
vez coincide por accidente con una palabra de columna o categoría. El
propio ``skill`` (fase 15+) solo puede *proponer* una palabra cuando el
operador ya la leyó impresa en el archivo y confirma que es una palabra de
columna o de categoría, nunca parte del nombre de una persona.
"""
from __future__ import annotations

import unicodedata

from app.services.race.normalizer import HEADER_TO_CODE


def _fold(text: str) -> str:
    """Mayúsculas, sin acentos, tal como pide el contrato ("[A-Z0-9] tras
    plegar acentos")."""
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.upper()


def _header_words() -> frozenset[str]:
    """Cada palabra de cada key de ``normalizer.HEADER_TO_CODE``, más ``CAT``."""
    words: set[str] = {"CAT"}
    for header in HEADER_TO_CODE:
        for word in _fold(header).split():
            words.add(word)
    return frozenset(words)


#: Títulos de columna observados en actas oficiales (contracts/masked-view.md).
_COLUMN_WORDS: frozenset[str] = frozenset(
    {
        "POS", "POSICION", "PUESTO", "ORD", "DORSAL", "NUMERO", "NO", "NOMBRE",
        "NOMBRES", "APELLIDO", "APELLIDOS", "DEPORTISTA", "CORREDOR",
        "CLUB", "EQUIPO", "PATROCINADOR", "CIUDAD", "MUNICIPIO", "TIEMPO",
        "DIFERENCIA", "DIF", "VUELTAS", "PUNTOS", "PTS", "CATEGORIA", "EDAD",
        "COMPLETO",
    }
)

#: Palabras de portada/documento.
_DOCUMENT_WORDS: frozenset[str] = frozenset(
    {"RESULTADOS", "VALIDA", "COPA", "CAMPEONATO", "CLASIFICACION", "OFICIAL", "OFICIALES"}
)

#: Numerales romanos I..XII (número de válida).
_ROMAN_WORDS: frozenset[str] = frozenset(
    {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
)

#: Conectores gramaticales del español que aparecen en encabezados/headers.
_CONNECTOR_WORDS: frozenset[str] = frozenset({"DE", "DEL", "LA", "LAS", "LOS", "Y", "EN"})

#: El vocabulario completo — congelado, construido una sola vez al importar.
VOCABULARY: frozenset[str] = frozenset(
    _header_words() | _COLUMN_WORDS | _DOCUMENT_WORDS | _ROMAN_WORDS | _CONNECTOR_WORDS
)


def is_vocabulary_word(word: str) -> bool:
    """``True`` si ``word`` (ya plegada o no) está en ``VOCABULARY``."""
    return _fold(word) in VOCABULARY
