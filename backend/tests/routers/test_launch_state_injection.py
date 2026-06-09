"""US2 (feature 011): grounding helpers feeding initial_state.

Covers the age→LTAD mapping and the latest-maturation lookup that both launch
routers inject. On unfixed code the graph never received these → Pre-PHV/Bambino
defaults for everyone.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.race.ai.grounding import (
    latest_maturation_status,
    ltad_group_from_age,
)
from app.services.race.schemas import LTADGroup


def test_ltad_group_from_age_mapping():
    assert ltad_group_from_age(10.0) == LTADGroup.BAMBINO
    assert ltad_group_from_age(12.0) == LTADGroup.BAMBINO
    assert ltad_group_from_age(13.0) == LTADGroup.JUVENIL
    assert ltad_group_from_age(15.0) == LTADGroup.JUVENIL
    assert ltad_group_from_age(16.5) == LTADGroup.JUNIOR


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
