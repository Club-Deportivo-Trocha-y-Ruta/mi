"""``apply_profile`` sobre un layout ficticio de segundo organizador (T123).

Prueba que el motor no está pensado solo para Copa Valle: un layout sin
rulings, con columnas en otro orden y el nombre partido en apellidos/nombres
(``tests/fixtures/race_profiles/fictional-unruled.json``) se recupera
completo con su propio perfil.
"""
from __future__ import annotations

from datetime import date

from app.services.race.results_skill.apply import apply_profile
from app.services.race.results_skill.profile import load_profile
from tests.helpers.results_pdf_builder import (
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)

_PROFILE_PATH = "tests/fixtures/race_profiles/fictional-unruled.json"


def _load_unruled_profile():
    from pathlib import Path

    return load_profile(Path(_PROFILE_PATH))


class TestUnruledLayoutFullRecovery:
    def test_every_row_recovered_with_surname_and_given_name(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 5)]
        out = tmp_path / "unruled.pdf"
        build_results_pdf(
            out,
            valida_num=2,
            location="Ciudad Ficticia",
            event_date=date(2026, 4, 1),
            categories=cats,
            name_generator=gen,
            layout="unruled",
        )

        profile = _load_unruled_profile()
        got = apply_profile(out.read_bytes(), "pdf", profile)

        assert len(got.categories) == 1
        assert got.categories[0].code == "INF_A"
        rows = got.categories[0].rows
        assert len(rows) == 5
        for i, row in enumerate(rows, start=1):
            assert row.position == i
            assert row.name.strip() != ""
            assert row.club.strip() != ""
            assert row.city.strip() != ""
            assert row.time_raw != ""
            assert row.points > 0
            # apellidos antes que nombre de pila en este layout: el nombre
            # completo generado por el builder (given, surname) debe seguir
            # presente entero, aunque en otro orden de impresión.
            given, _, surname = gen.generated[i - 1].partition(" ")
            for part in surname.split():
                assert part in row.name
            assert given in row.name

    def test_multiple_categories_and_lap_deficit(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [
            sequential_category("INFANTIL A", 2),
            sequential_category("PREJUVENIL A DAMAS", 2),
        ]
        cats[1].rows[0].time_raw = None
        cats[1].rows[0].minus_laps = 1
        out = tmp_path / "unruled2.pdf"
        build_results_pdf(
            out,
            valida_num=2,
            location="Ciudad Ficticia",
            event_date=date(2026, 4, 1),
            categories=cats,
            name_generator=gen,
            layout="unruled",
        )

        profile = _load_unruled_profile()
        got = apply_profile(out.read_bytes(), "pdf", profile)

        assert [c.header_raw for c in got.categories] == ["INFANTIL A", "PREJUVENIL A DAMAS"]
        assert got.categories[1].rows[0].time_raw == "(-1 VUELTA)"
