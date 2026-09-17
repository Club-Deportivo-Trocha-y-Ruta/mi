"""US2 (feature 011): grounding helpers feeding initial_state.

Covers the age→LTAD mapping and the latest-maturation lookup that both launch
routers inject. On unfixed code the graph never received these → Pre-PHV/Bambino
defaults for everyone.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.race.ai.grounding import (
    is_adult_age,
    latest_maturation_status,
    ltad_group_from_age,
    resolve_maturation_status,
)
from app.services.race.schemas import LTADGroup


def test_ltad_group_from_age_mapping():
    assert ltad_group_from_age(10.0) == LTADGroup.BAMBINO
    assert ltad_group_from_age(12.0) == LTADGroup.BAMBINO
    assert ltad_group_from_age(13.0) == LTADGroup.JUVENIL
    assert ltad_group_from_age(15.0) == LTADGroup.JUVENIL
    assert ltad_group_from_age(16.5) == LTADGroup.JUNIOR


def test_ltad_group_from_age_adult_mapping():
    """Feature 'adult athlete path': el club tiene al menos un atleta adulto
    de competición activo (owner decision, 2026-09-16) — agregar la
    categoría explícita en vez de excluir adultos. Real bug de producción:
    un atleta de 31 años caía en JUNIOR (16-17), la clasificación menos
    incorrecta pero igual equivocada."""
    assert ltad_group_from_age(18.0) == LTADGroup.ADULTO
    assert ltad_group_from_age(31.0) == LTADGroup.ADULTO
    assert ltad_group_from_age(65.0) == LTADGroup.ADULTO
    # Frontera: 17.9 sigue siendo junior (floor → 17).
    assert ltad_group_from_age(17.9) == LTADGroup.JUNIOR


@pytest.mark.parametrize(
    "age,expected",
    [
        (None, False),
        (17, False),
        (17.9, False),
        (18, True),
        (18.0, True),
        (31, True),
        ("not-a-number", False),
    ],
)
def test_is_adult_age(age, expected):
    assert is_adult_age(age) is expected


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row

    async def execute(self, *_a, **_k):
        return _FakeResult(self._row)


@pytest.mark.asyncio
async def test_maturation_status_from_latest_record():
    record = SimpleNamespace(
        maturation_status=SimpleNamespace(value="Circa-PHV")
    )
    db = _FakeDB(record)
    assert await latest_maturation_status(db, athlete_id=3) == "Circa-PHV"


@pytest.mark.asyncio
async def test_maturation_status_none_when_no_records():
    db = _FakeDB(None)
    assert await latest_maturation_status(db, athlete_id=99) is None


class _ExplodingDB:
    """DB stub que falla si se le consulta — usado para probar que un
    adulto NUNCA dispara la query de maduración (ni siquiera para
    descartarla)."""

    async def execute(self, *_a, **_k):  # pragma: no cover - debe no llamarse
        raise AssertionError(
            "resolve_maturation_status no debe consultar la BD para un adulto"
        )


@pytest.mark.asyncio
async def test_resolve_maturation_status_adult_short_circuits_without_query():
    """Feature 'adult athlete path': PHV no aplica a un adulto — ni se
    consulta la tabla antropométrica (defensa en profundidad: aunque el
    club tuviera un registro viejo de cuando el atleta era menor, nunca
    debe viajar al prompt de un análisis para adulto)."""
    db = _ExplodingDB()
    assert await resolve_maturation_status(db, athlete_id=1, athlete_age=31) is None


@pytest.mark.asyncio
async def test_resolve_maturation_status_minor_delegates_to_latest_maturation_status():
    record = SimpleNamespace(maturation_status=SimpleNamespace(value="Pre-PHV"))
    db = _FakeDB(record)
    result = await resolve_maturation_status(db, athlete_id=1, athlete_age=12)
    assert result == "Pre-PHV"


@pytest.mark.asyncio
async def test_resolve_maturation_status_none_age_delegates_conservatively():
    """``athlete_age=None`` no es adulto (conservador) — sigue consultando."""
    record = SimpleNamespace(maturation_status=SimpleNamespace(value="Circa-PHV"))
    db = _FakeDB(record)
    result = await resolve_maturation_status(db, athlete_id=1, athlete_age=None)
    assert result == "Circa-PHV"
