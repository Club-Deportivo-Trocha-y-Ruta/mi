"""Pruebas de la semilla de barrios/sectores IMDERTY (feature 047, T003)."""

from app.services.imderty.barrios_seed import BARRIOS_YUMBO

VALID_ZONES = {"1", "2", "3", "4", "ZONA NORTE", "ZONA CENTRO", "ZONA SUR"}


def test_count_is_within_expected_range():
    # La hoja SECTOR del libro fuente trae 83 filas; dos grafías duplicadas
    # del mismo barrio ("ALTO DE SAN JORGE" / "ALTO SAN JORGE", misma zona)
    # se colapsaron en una sola entrada -> 82.
    assert len(BARRIOS_YUMBO) == 82


def test_names_are_unique():
    names = [name for name, _zone in BARRIOS_YUMBO]
    assert len(names) == len(set(names))


def test_names_are_upper_case_and_stripped():
    for name, _zone in BARRIOS_YUMBO:
        assert name == name.upper()
        assert name == name.strip()
        assert name != ""


def test_zones_are_valid():
    for name, zone in BARRIOS_YUMBO:
        assert zone in VALID_ZONES, f"zona inválida para {name!r}: {zone!r}"


def test_entries_are_name_zone_pairs():
    for entry in BARRIOS_YUMBO:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
