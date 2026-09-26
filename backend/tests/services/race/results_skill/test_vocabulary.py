"""Tests de ``results_skill.vocabulary`` (amendment 2026-09-26, T118).

Pins descritos en ``contracts/masked-view.md`` § Vocabulario.
"""
from __future__ import annotations

import unicodedata

import pytest

from app.services.race.normalizer import HEADER_TO_CODE
from app.services.race.results_skill.vocabulary import VOCABULARY, is_vocabulary_word

_MONTHS = {
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
    "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
}
_WEEKDAYS = {
    "LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO",
}

_COLUMN_WORDS = {
    "POS", "POSICION", "PUESTO", "DORSAL", "NUMERO", "NO", "NOMBRE",
    "NOMBRES", "APELLIDO", "APELLIDOS", "DEPORTISTA", "CORREDOR",
    "CLUB", "EQUIPO", "PATROCINADOR", "CIUDAD", "MUNICIPIO", "TIEMPO",
    "DIFERENCIA", "DIF", "VUELTAS", "PUNTOS", "PTS", "CATEGORIA", "EDAD",
}
_DOCUMENT_WORDS = {
    "RESULTADOS", "VALIDA", "COPA", "CAMPEONATO", "CLASIFICACION", "OFICIAL", "OFICIALES",
}
_ROMAN_WORDS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
_CONNECTOR_WORDS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "EN"}


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


class TestHeaderWords:
    def test_every_header_to_code_word_is_present(self):
        for header in HEADER_TO_CODE:
            for word in _fold(header).split():
                assert word in VOCABULARY, f"{word!r} (de {header!r}) falta en VOCABULARY"

    def test_cat_is_present(self):
        assert "CAT" in VOCABULARY


class TestFixedLists:
    @pytest.mark.parametrize("word", sorted(_COLUMN_WORDS))
    def test_column_word_present(self, word):
        assert word in VOCABULARY

    @pytest.mark.parametrize("word", sorted(_DOCUMENT_WORDS))
    def test_document_word_present(self, word):
        assert word in VOCABULARY

    @pytest.mark.parametrize("word", sorted(_ROMAN_WORDS))
    def test_roman_numeral_present(self, word):
        assert word in VOCABULARY

    @pytest.mark.parametrize("word", sorted(_CONNECTOR_WORDS))
    def test_connector_present(self, word):
        assert word in VOCABULARY


class TestNoMonthOrWeekday:
    def test_no_month_name(self):
        assert not (VOCABULARY & _MONTHS)

    def test_no_weekday_name(self):
        assert not (VOCABULARY & _WEEKDAYS)


class TestCharsetAndLength:
    def test_only_uppercase_letters_and_digits_after_folding(self):
        import re

        for word in VOCABULARY:
            assert re.fullmatch(r"[A-Z0-9]+", word), f"{word!r} tiene un carácter fuera de [A-Z0-9]"

    def test_no_word_longer_than_14_letters(self):
        for word in VOCABULARY:
            assert len(word) <= 14, f"{word!r} supera 14 letras"


class TestIsVocabularyWord:
    def test_folds_accents_before_lookup(self):
        assert is_vocabulary_word("categoria") is True
        assert is_vocabulary_word("CATEGORÍA") is True

    def test_rejects_a_name_word(self):
        assert is_vocabulary_word("FICTICIO") is False
