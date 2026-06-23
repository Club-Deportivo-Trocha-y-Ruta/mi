"""Competitive Anxiety Assessment domain services (feature 017).

Pure-logic core for the CSAI-2R / SAS-2 / CSAI-2 instruments: instrument-key
loading, deterministic scoring, age-driven instrument selection, and the
rule-based interpretation fallback. These modules carry no DB or framework
dependency so they are unit-testable in isolation and reusable by the
LLM interpretation use case, the scoring endpoints, and the CSV importer.

Governed by Constitution Principle V (Youth Psychological Assessment
Safeguards): age-driven selection, wellbeing-not-diagnosis, baseline-anchored
interpretation, mastery climate, and a rule-based fallback that never depends
on the LLM.
"""
