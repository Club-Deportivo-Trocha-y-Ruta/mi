"""T057 (feature 036, Wave 3 / US2): ``is_first_in_season`` reaches the

actual text sent to the LLM, not just the ``invoke_per_valida`` call kwargs.

Diagnostic finding for T057
----------------------------
``is_first_in_season`` is computed by ``load_race_data`` from real
chronological season history (see ``test_load_race_data.py::
test_full_season_context_includes_prior_validas``, which launches Válida 3
alone with Válidas 1-2 as real priors and asserts ``is_first_in_season is
False``) and is propagated through ``_analyst_agent_v2`` independently of
the launched set's size — already fixed and regression-tested prior to this
feature as "Task #22" (``test_analyst_agent_v2_uses_full_season.py``) and
"Task #20" (``test_guardrails_race_v2_n1.py``). Those tests stop at the
``invoke_per_valida``/``Guardrails`` call-kwargs boundary; none of them
inspects the text the LLM actually receives.

This module closes that gap end to end: state -> ``AnalysisInput`` ->
``RaceAnalystAgent._build_v2_context`` -> rendered prompt. A silent
regression in the ``full_season_records`` -> ``season_progression``
rename, or in the ``state["season_comparative"]`` -> ``AnalysisInput.
season_comparative`` wiring, would fail a test here instead of only
showing up as a missing comparison on a coach's screen.

Conclusion: no bug found in the flag itself. The zero-comparison samples
quoted in spec.md for a mid-season válida analysed alone are not explained
by a wrongly-true ``is_first_in_season`` — they are explained by the
Section 1 checklist prompt (T054) and the mandated lap fabrication (T055),
which is what this wave's prompt rewrite targets instead.
"""
from __future__ import annotations

import app.services.race.agents.analyst as analyst_mod
from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V2,
    RaceAnalystAgent,
)
from app.services.race.schemas import AnalysisInput, LTADGroup


class _FakeLLMCallResult:
    """Mimics ``LLMCallResult`` — enough for ``_invoke_single_v2``."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens_in = 10
        self.tokens_out = 20
        self.latency_ms = 5
        self.cost_usd = 0.0


_NON_N1_OUTPUT = (
    "## Qué pasó en esta válida\n"
    "La deportista finalizó en la posición 3.\n\n"
    "## Recorrido hasta acá\n"
    "El gap frente al líder se redujo respecto a válidas previas.\n\n"
    "## Hacia dónde va\n"
    "- Reforzar técnica de curvas (categoría=technique, prioridad=med) [1]\n"
)

_N1_OUTPUT = (
    "## Qué pasó en esta válida\n"
    "La deportista completó la prueba y registró un tiempo competitivo.\n\n"
    "## Recorrido hasta acá\n"
    "Con una sola válida disputada aún no es posible establecer una "
    "tendencia de progresión.\n\n"
    "## Hacia dónde va\n"
    "- Reforzar transferencia de peso en bermas (categoría=technique, "
    "prioridad=med) [1]\n"
)


def _make_input(**over) -> AnalysisInput:
    base: dict = dict(
        athlete_pseudonym="AzulZorro",
        age=13,
        ltad_group=LTADGroup.JUVENIL,
        progression_df_records=[
            {"valida_num": 4, "position": 3, "race_time_ms": 2_050_000},
        ],
        podium_context={},
        athlete_id=42,
        season=2026,
    )
    base.update(over)
    return AnalysisInput(**base)


async def test_prompt_carries_season_comparative_when_not_first_in_season(monkeypatch):
    """Launch of V4 alone, with V1-V3 as real priors (state shaped exactly
    like ``_analyst_agent_v2`` would build it from ``load_race_data`` +
    ``compute_metrics`` output): the rendered prompt must carry the
    mandatory comparison instructions and must NOT fall back to the N=1
    override — there IS a season to compare against.
    """
    captured_prompts: list[str] = []

    async def _fake_call_llm(llm, prompt):
        captured_prompts.append(prompt)
        return _FakeLLMCallResult(_NON_N1_OUTPUT)

    monkeypatch.setattr(analyst_mod, "call_llm", _fake_call_llm)
    monkeypatch.setattr(analyst_mod, "build_chat_llm", lambda: None)

    agent = RaceAnalystAgent(prompt_version=PROMPT_VERSION_ANALYST_V2)
    inp = _make_input(
        season_comparative=[
            {
                "valida_num": 3,
                "event_label": "Válida 3",
                "position": 5,
                "race_time_ms": 2_200_000,
                "field_size": None,
                "delta_position": -2,
                "delta_time_ms": -150_000,
            },
        ],
        progression_assessment="improving",
    )
    full_season_records = [
        {"valida_num": 1, "position": 7, "race_time_ms": 2_400_000,
         "gap_to_winner_ms": 400_000, "gap_pct": 20.0},
        {"valida_num": 2, "position": 6, "race_time_ms": 2_300_000,
         "gap_to_winner_ms": 300_000, "gap_pct": 15.0},
        {"valida_num": 3, "position": 5, "race_time_ms": 2_200_000,
         "gap_to_winner_ms": 200_000, "gap_pct": 10.0},
        {"valida_num": 4, "position": 3, "race_time_ms": 2_050_000,
         "gap_to_winner_ms": 50_000, "gap_pct": 2.4},
    ]

    await agent.invoke_per_valida(
        [(4, inp)],
        forbidden_names=[],
        is_first_in_season=False,
        full_season_records=full_season_records,
        athlete_age=13,
    )

    assert len(captured_prompts) == 1, (
        "Se esperaba una sola llamada al LLM (sin veto duro/retry) — si "
        "esto falla, el texto de ejemplo del test gatilló un veto."
    )
    prompt = captured_prompts[0]
    # T014 comparative block (compute_metrics.season_comparative): mandatory.
    assert "Dirección de progresión calculada" in prompt
    assert "Datos de válidas previas" in prompt
    # full_season_results -> season_progression block: per-válida gap trend.
    assert "numérico de CADA válida del histórico" in prompt
    # The N=1 override must NOT fire — there IS a season to compare against.
    assert "REGLA N=1" not in prompt
    assert "REGLA ANTI-FABRICACIÓN" not in prompt


async def test_prompt_falls_back_to_n1_rule_when_truly_first(monkeypatch):
    """A genuinely single-válida season must render the N=1 override and
    must NOT claim a season history that does not exist.
    """
    captured_prompts: list[str] = []

    async def _fake_call_llm(llm, prompt):
        captured_prompts.append(prompt)
        return _FakeLLMCallResult(_N1_OUTPUT)

    monkeypatch.setattr(analyst_mod, "call_llm", _fake_call_llm)
    monkeypatch.setattr(analyst_mod, "build_chat_llm", lambda: None)

    agent = RaceAnalystAgent(prompt_version=PROMPT_VERSION_ANALYST_V2)
    inp = _make_input(
        progression_df_records=[
            {"valida_num": 1, "position": 5, "race_time_ms": 2_400_000},
        ],
    )

    await agent.invoke_per_valida(
        [(1, inp)],
        forbidden_names=[],
        is_first_in_season=True,
        full_season_records=[],
        athlete_age=13,
    )

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "REGLA N=1" in prompt
    assert "REGLA ANTI-FABRICACIÓN" in prompt
    assert "Datos de válidas previas" not in prompt
    assert "numérico de CADA válida del histórico" not in prompt
