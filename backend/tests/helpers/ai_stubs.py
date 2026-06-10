"""Reusable fake-LLM / agent stubs for race AI graph tests (feature 011, T002).

These let graph-level tests run without ``AI_API_KEY`` by injecting canned
analyst markdown and critic verdicts through the existing
``state["_analyst_agent"]`` / ``state["_critic_agent"]`` seams.
"""
from __future__ import annotations

from typing import Any

from app.services.race.schemas import (
    AnalysisOutput,
    CriticFeedback,
    CriticIssue,
    CriticIssueSeverity,
    RunMetrics,
)


def make_v2_output(pseudonym: str = "la deportista", markdown: str | None = None) -> AnalysisOutput:
    md = markdown or (
        "## Qué pasó en esta válida\n"
        "La deportista finalizó en la posición 2.\n\n"
        "## Recorrido hasta acá\n"
        "Participación consistente.\n\n"
        "## Hacia dónde va\n"
        "- Reforzar descensos técnicos (categoría=technique, prioridad=med) [1]\n"
    )
    return AnalysisOutput(
        pseudonym=pseudonym,
        sections={
            "what_happened": "La deportista finalizó en la posición 2.",
            "journey_so_far": "Participación consistente.",
            "next_steps": "- Reforzar descensos técnicos (categoría=technique, prioridad=med) [1]",
        },
        citations_used=["[1]"],
        recommendations=[],
        risk_flags=[],
        raw_markdown=md,
        word_count=len(md.split()),
    )


def _metrics(prompt_version: str) -> RunMetrics:
    return RunMetrics(
        tokens_in=10, tokens_out=20, latency_ms=5, cost_usd=0.0001,
        prompt_version=prompt_version,
    )


class StubCriticAgentV2:
    """Critic stub with a v2 path.

    Args:
        verdicts_by_call: optional list of CriticFeedback returned in order of
            ``invoke_v2`` calls. If exhausted/omitted, returns an approving
            verdict. ``captured_ground_truth`` records each prompt's ground
            truth so tests can assert it was threaded.
    """

    def __init__(self, verdicts: list[CriticFeedback] | None = None) -> None:
        self._verdicts = list(verdicts or [])
        self._i = 0
        self.captured_ground_truth: list[str] = []
        self.invoke_v2_calls = 0

    @staticmethod
    def is_enabled() -> bool:
        return True

    async def invoke(self, draft: AnalysisOutput):  # v1 compat
        return CriticFeedback(approved=True), _metrics("race_critic_v1")

    async def invoke_v2(self, draft: AnalysisOutput, ground_truth: str):
        self.invoke_v2_calls += 1
        self.captured_ground_truth.append(ground_truth)
        if self._i < len(self._verdicts):
            fb = self._verdicts[self._i]
            self._i += 1
        else:
            fb = CriticFeedback(approved=True, severity=CriticIssueSeverity.LOW)
        return fb, _metrics("race_critic_v2")


def contradiction_verdict() -> CriticFeedback:
    return CriticFeedback(
        approved=False,
        severity=CriticIssueSeverity.HIGH,
        issues=[
            CriticIssue(
                section="Qué pasó en esta válida",
                problem="Contradice el ground truth (pista seca vs Húmeda).",
                suggested_fix="Usar la superficie registrada (Húmeda).",
            )
        ],
        must_block=False,
    )
