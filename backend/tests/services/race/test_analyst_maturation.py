"""US2 (feature 011): _build_v2_context uses real maturation, not a default.

Regression: the context read ``podium_context.get("maturation_status", "Pre-PHV")``
(a key never set) → every athlete framed as Pre-PHV. Now it reads
``input_.maturation_status``.
"""
from __future__ import annotations

from app.services.race.agents.analyst import RaceAnalystAgent
from app.services.race.schemas import AnalysisInput, LTADGroup


def _input(**over) -> AnalysisInput:
    base = dict(
        athlete_pseudonym="la deportista",
        age=13,
        ltad_group=LTADGroup.JUVENIL,
        progression_df_records=[],
        podium_context={},
        athlete_id=3,
        season=2026,
    )
    base.update(over)
    return AnalysisInput(**base)


def test_maturation_status_not_defaulted():
    agent = RaceAnalystAgent(prompt_version="race_analyst_v2")
    ctx = agent._build_v2_context(_input(maturation_status="Circa-PHV"), valida_num=4)
    assert ctx["maturation_status"] == "Circa-PHV"


def test_maturation_none_stays_none_even_with_podium_key():
    """The dead podium_context read must be gone: a stray key cannot resurrect it."""
    agent = RaceAnalystAgent(prompt_version="race_analyst_v2")
    ctx = agent._build_v2_context(
        _input(maturation_status=None, podium_context={"maturation_status": "Pre-PHV"}),
        valida_num=4,
    )
    assert ctx["maturation_status"] is None


def test_race_meta_threaded_from_input():
    agent = RaceAnalystAgent(prompt_version="race_analyst_v2")
    ctx = agent._build_v2_context(
        _input(race_meta="- Clima: Nublado"), valida_num=4
    )
    assert ctx["race_meta"] == "- Clima: Nublado"
