"""Tests TDD para ``app.services.race.comparison_groups`` (feature 039).

El módulo bajo prueba todavía no existe (lo crea T005) — estos tests deben
fallar por ``ImportError`` hasta entonces. Contrato exacto en
``specs/039-season-comparison-groups/research.md`` (D1/D2) y
``specs/039-season-comparison-groups/data-model.md`` (§1/§3):

- ``build_comparison_group(kind, series_id) -> str``
  ``"cup:{id}"`` | ``"championship:{id}"``. ``kind`` puede ser
  ``RaceSeriesKind`` o su valor string (``"cup"`` / ``"championship"``).
- ``group_label(kind, level, name, season_year, location=None) -> str``
  Copas: ``f"{name} {season_year}"`` (``location`` se ignora).
  Campeonatos: delega en ``race_labels.build_race_label(kind, 1, location,
  level=level)``.
- ``split_progression(rows) -> SplitProgression``
  ``rows`` son dicts (o filas de pandas) con ``series_id``, ``series_kind``,
  ``series_level``, ``series_name``, ``season_year``, ``event_date``,
  ``location``. Las copas se agrupan por ``series_id`` y se ordenan entre sí
  por la fecha de su válida más temprana; las filas dentro de cada copa
  quedan cronológicas. Los campeonatos NO se agrupan (una fila por
  campeonato, INV-2) y quedan en una lista aparte, cronológica. Entrada
  vacía → listas vacías.

Todos los datos son ficticios (nombres, fechas, sedes) — no corresponden a
ningún atleta ni carrera real del club.
"""
from __future__ import annotations

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.services.race.race_labels import build_race_label

# Objeto bajo prueba — el import en sí ya es la primera aserción TDD: debe
# fallar con ImportError mientras T005 no exista.
from app.services.race.comparison_groups import (
    CupProgression,
    SplitProgression,
    build_comparison_group,
    group_label,
    split_progression,
)


# ---------------------------------------------------------------------------
# Helpers de fila (dicts — el "row" mínimo que consume split_progression)
# ---------------------------------------------------------------------------


def _cup_row(
    *,
    series_id: int,
    series_name: str = "Copa Valle de Ciclomontañismo",
    season_year: int = 2026,
    event_id: int,
    valida_num: int,
    event_date: str,
    location: str = "Sevilla",
    series_level: str = "departmental",
) -> dict:
    return {
        "event_id": event_id,
        "series_id": series_id,
        "series_kind": "cup",
        "series_level": series_level,
        "series_name": series_name,
        "season_year": season_year,
        "valida_num": valida_num,
        "event_date": event_date,
        "location": location,
    }


def _championship_row(
    *,
    series_id: int,
    series_name: str,
    season_year: int = 2026,
    event_id: int,
    event_date: str,
    location: str,
    series_level: str,
) -> dict:
    return {
        "event_id": event_id,
        "series_id": series_id,
        "series_kind": "championship",
        "series_level": series_level,
        "series_name": series_name,
        "season_year": season_year,
        "valida_num": 1,
        "event_date": event_date,
        "location": location,
    }


# ===========================================================================
# build_comparison_group
# ===========================================================================


class TestBuildComparisonGroup:
    def test_cup_with_enum_kind(self):
        assert build_comparison_group(RaceSeriesKind.cup, 12) == "cup:12"

    def test_championship_with_enum_kind(self):
        assert build_comparison_group(RaceSeriesKind.championship, 31) == "championship:31"

    def test_accepts_string_kind_cup(self):
        assert build_comparison_group("cup", 5) == "cup:5"

    def test_accepts_string_kind_championship(self):
        assert build_comparison_group("championship", 9) == "championship:9"


# ===========================================================================
# group_label
# ===========================================================================


class TestGroupLabel:
    def test_cup_label_is_name_plus_season(self):
        label = group_label(
            RaceSeriesKind.cup,
            RaceSeriesLevel.departmental,
            "Copa Valle de Ciclomontañismo",
            2026,
        )
        assert label == "Copa Valle de Ciclomontañismo 2026"

    def test_cup_label_ignores_location(self):
        """D2: la ubicación no forma parte de la etiqueta de una copa."""
        with_location = group_label(
            RaceSeriesKind.cup,
            RaceSeriesLevel.departmental,
            "Copa Valle de Ciclomontañismo",
            2026,
            location="Sevilla",
        )
        without_location = group_label(
            RaceSeriesKind.cup,
            RaceSeriesLevel.departmental,
            "Copa Valle de Ciclomontañismo",
            2026,
        )
        assert with_location == without_location == "Copa Valle de Ciclomontañismo 2026"

    def test_championship_departmental_delegates_to_build_race_label(self):
        label = group_label(
            RaceSeriesKind.championship,
            RaceSeriesLevel.departmental,
            "Campeonato Departamental de Ciclomontañismo",
            2026,
            location="Ginebra",
        )
        assert label == build_race_label(
            RaceSeriesKind.championship, 1, "Ginebra", level=RaceSeriesLevel.departmental
        )
        assert label == "Cto. Dep. — Ginebra"

    def test_championship_national_delegates_to_build_race_label(self):
        label = group_label(
            RaceSeriesKind.championship,
            RaceSeriesLevel.national,
            "Campeonato Nacional de Ciclomontañismo",
            2026,
            location="Pereira",
        )
        assert label == build_race_label(
            RaceSeriesKind.championship, 1, "Pereira", level=RaceSeriesLevel.national
        )
        assert label == "Cto. Nal. — Pereira"

    def test_accepts_string_kind_and_level(self):
        """``kind``/``level`` como strings (ej. valores ya serializados de DB)."""
        label = group_label("championship", "national", "Campeonato Nacional", 2026, location="Pereira")
        assert label == "Cto. Nal. — Pereira"


# ===========================================================================
# split_progression
# ===========================================================================


class TestSplitProgressionEmpty:
    def test_empty_input_returns_empty_lists(self):
        result = split_progression([])
        assert isinstance(result, SplitProgression)
        assert result.cups == []
        assert result.championships == []


class TestSplitProgressionCups:
    def test_groups_cup_rows_by_series_id(self):
        rows = [
            _cup_row(series_id=12, event_id=901, valida_num=1, event_date="2026-01-31"),
            _cup_row(series_id=12, event_id=902, valida_num=2, event_date="2026-02-28"),
            _cup_row(
                series_id=13,
                series_name="Liga Departamental",
                event_id=903,
                valida_num=1,
                event_date="2026-03-10",
            ),
        ]
        result = split_progression(rows)
        assert len(result.cups) == 2
        assert {c.series_id for c in result.cups} == {12, 13}
        assert result.championships == []

    def test_cups_ordered_by_earliest_raced_round(self):
        """La copa con la válida más temprana va primero, sin importar
        ``series_id`` ni el orden de inserción en ``rows``."""
        rows = [
            # series_id=13 iría segundo por id, pero su Válida I es la más
            # temprana del set — debe quedar primera.
            _cup_row(
                series_id=13,
                series_name="Liga Departamental",
                event_id=903,
                valida_num=1,
                event_date="2026-01-05",
            ),
            _cup_row(series_id=12, event_id=901, valida_num=1, event_date="2026-01-31"),
            _cup_row(series_id=12, event_id=902, valida_num=2, event_date="2026-02-28"),
        ]
        result = split_progression(rows)
        assert [c.series_id for c in result.cups] == [13, 12]

    def test_rows_within_a_cup_are_chronological(self):
        """Las filas dentro de una copa quedan ordenadas por fecha aunque
        lleguen desordenadas."""
        rows = [
            _cup_row(series_id=12, event_id=903, valida_num=3, event_date="2026-03-31"),
            _cup_row(series_id=12, event_id=901, valida_num=1, event_date="2026-01-31"),
            _cup_row(series_id=12, event_id=902, valida_num=2, event_date="2026-02-28"),
        ]
        result = split_progression(rows)
        assert len(result.cups) == 1
        cup = result.cups[0]
        assert isinstance(cup, CupProgression)
        assert [r["event_date"] for r in cup.rows] == ["2026-01-31", "2026-02-28", "2026-03-31"]
        assert [r["valida_num"] for r in cup.rows] == [1, 2, 3]

    def test_cup_label_matches_group_label(self):
        rows = [_cup_row(series_id=12, event_id=901, valida_num=1, event_date="2026-01-31")]
        result = split_progression(rows)
        assert result.cups[0].label == group_label(
            RaceSeriesKind.cup, RaceSeriesLevel.departmental, "Copa Valle de Ciclomontañismo", 2026
        )
        assert result.cups[0].label == "Copa Valle de Ciclomontañismo 2026"

    def test_only_cups_no_championships(self):
        rows = [_cup_row(series_id=12, event_id=901, valida_num=1, event_date="2026-01-31")]
        result = split_progression(rows)
        assert len(result.cups) == 1
        assert result.championships == []


class TestSplitProgressionChampionships:
    def test_championships_separated_and_chronological(self):
        rows = [
            _cup_row(series_id=12, event_id=901, valida_num=1, event_date="2026-01-31"),
            _championship_row(
                series_id=51,
                series_name="Campeonato Nacional de Ciclomontañismo",
                event_id=903,
                event_date="2026-08-22",
                location="Pereira",
                series_level="national",
            ),
            _championship_row(
                series_id=50,
                series_name="Campeonato Departamental de Ciclomontañismo",
                event_id=902,
                event_date="2026-06-20",
                location="Ginebra",
                series_level="departmental",
            ),
        ]
        result = split_progression(rows)
        assert len(result.cups) == 1
        assert [c["series_id"] for c in result.championships] == [50, 51]
        assert [c["event_date"] for c in result.championships] == ["2026-06-20", "2026-08-22"]

    def test_only_championships_no_cups(self):
        rows = [
            _championship_row(
                series_id=51,
                series_name="Campeonato Nacional de Ciclomontañismo",
                event_id=903,
                event_date="2026-08-22",
                location="Pereira",
                series_level="national",
            )
        ]
        result = split_progression(rows)
        assert result.cups == []
        assert len(result.championships) == 1
        assert result.championships[0]["series_id"] == 51

    def test_accepts_string_and_enum_series_kind_equivalently(self):
        """``series_kind`` puede llegar como ``str`` (dato de DataFrame) o
        como ``RaceSeriesKind`` — ambos deben clasificarse igual."""
        row_as_string = _championship_row(
            series_id=51,
            series_name="Campeonato Nacional de Ciclomontañismo",
            event_id=903,
            event_date="2026-08-22",
            location="Pereira",
            series_level="national",
        )
        row_as_enum = dict(row_as_string, series_kind=RaceSeriesKind.championship)
        result_str = split_progression([row_as_string])
        result_enum = split_progression([row_as_enum])
        assert len(result_str.championships) == len(result_enum.championships) == 1
        assert result_str.cups == result_enum.cups == []
