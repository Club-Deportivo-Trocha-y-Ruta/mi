"""Regresiones detectadas en la verificación SC-1 de la feature 037 (2026-09-02).

1. Antropometría: sin medición previa a la carrera se usa la posterior más
   cercana con flag ``measured_after_event`` (antes → ``None`` → "sin datos").
2. Verdad de campo del critic v3: la maduración sale de ``anthro_context``
   (misma fuente que el analista), no del último registro sin fecha.
3. El analista v3 usa ``race_ai_v3_timeout_seconds`` (120 s), no los 30 s de
   ``ai_timeout_seconds`` que mandaban al modelo fuerte a fallback.
4. Prechecks rellenan ``catalog_ref.label`` con el nombre del catálogo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.race.ai.nodes.critic_agent import _build_ground_truth
from app.services.race.ai.prechecks import _catalog_label


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    """Devuelve primero los registros ``<= fecha`` y luego los ``> fecha``."""

    def __init__(self, before, after):
        self._responses = [_FakeResult(before), _FakeResult(after)]
        self.calls = 0

    async def execute(self, _stmt):
        res = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return res


def _record(day: date, offset: float, status: str = "Post-PHV"):
    return SimpleNamespace(
        evaluation_date=day,
        maturity_offset=Decimal(str(offset)),
        age_at_phv=Decimal("12.4"),
        maturation_status=SimpleNamespace(value=status),
        height_percentile=Decimal("55.0"),
        standing_height_cm=Decimal("150.0"),
    )


@pytest.mark.asyncio
async def test_anthro_context_falls_back_to_first_record_after_event():
    from app.services.race.ai.athlete_context import load_anthro_context

    after = _record(date(2026, 8, 14), 1.2)
    db = _FakeDb(before=[], after=[after])
    ctx = await load_anthro_context(db, athlete_id=1, reference_date=date(2026, 1, 31))

    assert ctx is not None
    assert ctx["latest"]["maturation_status"] == "Post-PHV"
    assert ctx["latest"]["days_before_event"] < 0
    assert "measured_after_event" in ctx["flags"]
    for forbidden in ("weight_kg", "bmi", "nutritional_status"):
        assert forbidden not in ctx["latest"]


@pytest.mark.asyncio
async def test_anthro_context_none_when_no_records_at_all():
    from app.services.race.ai.athlete_context import load_anthro_context

    db = _FakeDb(before=[], after=[])
    assert await load_anthro_context(db, athlete_id=1, reference_date=date(2026, 1, 31)) is None


def test_critic_ground_truth_uses_anthro_context_in_v3_runs():
    state = {
        "anthro_context": {
            "latest": {"maturation_status": "Post-PHV"},
            "flags": ["measured_after_event"],
        },
        "maturation_status": "Post-PHV",
        "full_season_results": [],
        "event_conditions": {},
        "podium_context": {},
    }
    text = _build_ground_truth(state, 1)
    assert "Post-PHV (medición posterior a la carrera — aproximación)" in text


def test_critic_ground_truth_declares_gap_when_v3_has_no_anthro():
    state = {
        "anthro_context": None,
        "maturation_status": "Post-PHV",  # último registro sin fecha: NO debe usarse en v3
        "full_season_results": [],
        "event_conditions": {},
        "podium_context": {},
    }
    text = _build_ground_truth(state, 1)
    assert "sin registro de maduración a la fecha de la carrera" in text
    assert "Post-PHV" not in text


def test_critic_ground_truth_legacy_runs_keep_maturation_status():
    state = {"maturation_status": "Circa-PHV", "full_season_results": [], "event_conditions": {}}
    assert "Circa-PHV" in _build_ground_truth(state, 1)


def test_v3_timeout_setting_defaults_to_120s():
    from app.config import settings

    assert settings.race_ai_v3_timeout_seconds >= 90.0


def test_invoke_v3_reads_v3_timeout_setting():
    import inspect

    from app.services.race.agents.analyst import RaceAnalystAgent

    src = inspect.getsource(RaceAnalystAgent.invoke_v3)
    assert "race_ai_v3_timeout_seconds" in src
    assert "settings.ai_timeout_seconds" not in src


def test_catalog_label_resolves_name_for_valid_code():
    catalog = {
        "technique_skills": [{"code": "H", "name": "Cambios y cadencia", "focus": "x"}],
        "strength_blocks": [{"id": 2, "name": "Full Body (13-15)"}],
        "interval_templates": [],
    }
    assert _catalog_label(catalog, "technique_skill", "H") == "Cambios y cadencia"
    assert _catalog_label(catalog, "strength_block", "2") == "Full Body (13-15)"
    assert _catalog_label(catalog, "technique_skill", "Z") is None
    assert _catalog_label(None, "technique_skill", "H") is None
