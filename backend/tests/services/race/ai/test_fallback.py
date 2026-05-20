"""Tests del fallback determinista del analyst."""
from __future__ import annotations

from app.services.race.ai.fallback import deterministic_fallback
from app.services.race.schemas import AnalysisOutput


def test_fallback_returns_valid_output():
    out = deterministic_fallback("AzulZorro")
    assert isinstance(out, AnalysisOutput)
    assert out.pseudonym == "AzulZorro"
    assert "no disponible" in out.raw_markdown.lower()
    assert out.recommendations == []
    assert out.risk_flags == []
    assert out.sections == {}
    assert out.word_count > 0


def test_fallback_word_count_is_consistent():
    out = deterministic_fallback("VerdePuma")
    # Conteo de palabras debe coincidir con split simple del raw_markdown.
    assert out.word_count == len(out.raw_markdown.split())
