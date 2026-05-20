"""Eval framework para ``RaceAnalystAgent`` (Fase 7 race-results v2).

Módulos:

- :mod:`.scorer` — scorer rule-based determinístico (0.0–1.0).
- :mod:`.judge` — LLM-as-judge (Gemini Flash Lite, prompt ``judge_v1``).
- :func:`composite_score` — combina ambos: ``0.4 * rule + 0.6 * judge``.

Diseño:

- **Sin red en unit tests.** ``judge.llm_judge_score`` admite un
  ``llm_factory`` inyectable (mock en tests; default = factory real con
  ``AI_API_KEY``).
- **JSON Schema golden cases** documentado en
  :mod:`tests.evals.test_race_analyst_eval` y reflejado en cada
  ``evals/race_analyst/golden/case_NNN.json``.
- **Threshold CI:** 0.75 (workflow §7.7). Configurable vía variable
  de entorno ``RACE_EVAL_THRESHOLD`` para experimentación local.
"""

from __future__ import annotations

from app.services.race.eval.scorer import composite_score, rule_based_score

__all__ = [
    "composite_score",
    "rule_based_score",
]
