"""Unit tests for the surname-split heuristic (feature 047, US2, T023).

All surnames used here are fictitious (CLAUDE.md, Ley 1581) — chosen only
because they are common Spanish surname shapes, not because they belong to
any real minor or family in the club.
"""

from __future__ import annotations

import pytest

from app.services.imderty.surnames import propose_split, rebuilds


class TestProposeSplit:
    def test_two_simple_surnames(self) -> None:
        assert propose_split("GARCÍA PÉREZ") == ("GARCÍA", "PÉREZ")

    def test_particle_attached_to_first_surname(self) -> None:
        assert propose_split("DE LA CRUZ GÓMEZ") == ("DE LA CRUZ", "GÓMEZ")

    def test_particle_falls_into_second_surname(self) -> None:
        assert propose_split("SÁNCHEZ DEL RÍO") == ("SÁNCHEZ", "DEL RÍO")

    def test_single_surname_has_no_second(self) -> None:
        first, second = propose_split("GARCÍA")
        assert first == "GARCÍA"
        assert second is None

    def test_single_surname_with_particle_has_no_second(self) -> None:
        first, second = propose_split("DE LA CRUZ")
        assert first == "DE LA CRUZ"
        assert second is None

    def test_del_particle_attached_to_first_surname(self) -> None:
        assert propose_split("DEL RÍO GÓMEZ") == ("DEL RÍO", "GÓMEZ")


class TestRebuilds:
    def test_exact_match(self) -> None:
        assert rebuilds("GARCÍA PÉREZ", "GARCÍA", "PÉREZ") is True

    def test_single_surname_match(self) -> None:
        assert rebuilds("GARCÍA", "GARCÍA", None) is True

    def test_particle_split_match(self) -> None:
        assert rebuilds("DE LA CRUZ GÓMEZ", "DE LA CRUZ", "GÓMEZ") is True

    def test_case_insensitive(self) -> None:
        assert rebuilds("García Pérez", "garcía", "pérez") is True

    def test_accent_insensitive(self) -> None:
        assert rebuilds("GARCÍA PÉREZ", "GARCIA", "PEREZ") is True

    def test_extra_whitespace_ignored(self) -> None:
        assert rebuilds("GARCÍA   PÉREZ", "GARCÍA", "PÉREZ") is True

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("GARCÍA", "GÓMEZ"),
            ("PÉREZ", "GARCÍA"),
            ("GARCÍA", None),
        ],
    )
    def test_mismatch_rejected(self, first: str, second: str | None) -> None:
        assert rebuilds("GARCÍA PÉREZ", first, second) is False
