"""Todo perfil committeado valida contra el esquema v1 (amendment 2026-09-26, T121).

Barre ``backend/race_reading_profiles/`` y ``backend/tests/fixtures/race_profiles/``
— ningún archivo ahí puede llevar una clave o cadena fuera de lo que
``profile.py`` acepta (esa es la garantía de que un perfil nunca lleva un
dato de un corredor).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.race.results_skill.profile import PROFILES_DIR, ReadingProfile

_FIXTURE_PROFILES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "race_profiles"


def _all_profile_files() -> list[Path]:
    files: list[Path] = []
    for directory in (PROFILES_DIR, _FIXTURE_PROFILES_DIR):
        if directory.exists():
            files.extend(sorted(directory.glob("*.json")))
    return files


_PROFILE_FILES = _all_profile_files()


class TestEveryCommittedProfileValidates:
    def test_at_least_one_profile_exists(self):
        assert _PROFILE_FILES, "no se encontró ningún perfil committeado"

    @pytest.mark.parametrize("path", _PROFILE_FILES, ids=lambda p: p.name)
    def test_profile_validates_against_schema_v1(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = ReadingProfile.model_validate(payload)
        assert profile.profile_id == path.stem
