"""Cálculo de edad decimal y categoría FCC 2026."""

from datetime import date


def compute_age_decimal(birth_date: date, reference_date: date | None = None) -> float:
    """Calcula la edad decimal: (referencia - nacimiento) / 365.25."""
    if reference_date is None:
        reference_date = date.today()
    delta = reference_date - birth_date
    return round(delta.days / 365.25, 2)


def compute_years_in_club(club_join_date: date, reference_date: date | None = None) -> float:
    """Calcula los años en el club: (referencia - ingreso) / 365.25."""
    if reference_date is None:
        reference_date = date.today()
    delta = reference_date - club_join_date
    return round(delta.days / 365.25, 2)


def get_category(birth_year: int, sex: str) -> str:
    """Determina la categoría FCC 2026 según año de nacimiento y sexo.

    Tabla oficial de la Federación Colombiana de Ciclismo 2026.
    """
    # ---------- Masters (M) ----------
    if sex == "M":
        if birth_year <= 1966:
            return "Master D"
        if 1967 <= birth_year <= 1971:
            return "Master C 2"
        if 1972 <= birth_year <= 1976:
            return "Master C 1"
        if 1977 <= birth_year <= 1981:
            return "Master B 2"
        if 1982 <= birth_year <= 1986:
            return "Master B 1"
        if 1987 <= birth_year <= 1991:
            return "Master A"

    # ---------- Masters (F) ----------
    if sex == "F" and birth_year <= 1991:
        return "Master Damas"

    # ---------- Elite (2007 y menos) ----------
    if birth_year <= 2007:
        return "Elite femenina" if sex == "F" else "Elite"

    # ---------- Categorías juveniles ----------
    f = " femenino" if sex == "F" else ""

    if 2008 <= birth_year <= 2009:
        return f"Junior{f}"
    if 2010 <= birth_year <= 2011:
        return f"Pre-juvenil B{f}"
    if 2012 <= birth_year <= 2013:
        return f"Pre-juvenil A{f}"
    if 2014 <= birth_year <= 2015:
        return f"Infantil B{f}"
    if 2016 <= birth_year <= 2017:
        return f"Infantil A{f}"
    if 2018 <= birth_year <= 2019:
        return f"Pre-Infantil B{f}"
    if 2020 <= birth_year <= 2021:
        return f"Pre-Infantil A{f}"

    # ---------- 2022+ ----------
    return "Teteros"
