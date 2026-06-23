# Competitive Anxiety Assessment — Module Workflow (feature 017)

Coach-facing module to administer, score, and interpret **state** competitive-anxiety
questionnaires for youth XCO athletes (10–15), anchored to each athlete's own
baseline and framed in a **mastery climate**. Wellbeing, never diagnosis
(Constitution Principle V).

## Instruments & selection

| Instrument | Items | Age band | Scoring |
|---|---|---|---|
| **CSAI-2R** | 17 | 13–15 (default) | subscale = (Σ/n)×10, range 10–40 |
| **SAS-2** | 15 | 10–12 (default) | subscale = Σ (somatic 5–20, cognitive = worry + concentration disruption); **no self-confidence** (N/A) |
| **CSAI-2** | 27 | import-only | subscale = Σ, range 9–36 |

Selection is age-driven (`services/anxiety/selection.py`). Applying an adult
anxiety instrument (CSAI-2/2R) to an under-13 athlete is allowed **only** as an
explicit override and returns a warning (HTTP 422 until `override=true`).
Item *text* is provisioned from the licensed source — never invented; only the
item→subscale map + reverse flags + ranges live in `app/data/anxiety_keys/*.json`.

## End-to-end flow

1. **Configure** (`POST /api/anxiety/assessments` or `/batch`) — coach picks the
   athlete(s) + optional calendar event. The age-driven instrument is resolved,
   the **guardian-consent gate** is enforced (active `parental_consents` row with
   `psychological_assessment=true`, else 409), and a **single-use answer token**
   is issued (raw value returned once; only its SHA-256 hash is stored).
2. **Answer** (`GET/POST /api/anxiety/answer/{token}`) — UNauthenticated, token-gated.
   One item at a time, 1–4 scale, español, encouraging-only message. Submitting
   computes scores, seeds the baseline if first, and consumes the token (410 thereafter).
3. **Score** — deterministic from the loaded key + stored item answers
   (`services/anxiety/scoring.py`); always recomputable (`POST .../recompute`).
   Self-confidence is a positive dimension and is **never** inverted.
4. **Interpret** (`POST .../interpret`, on-demand, cached) — LLM use case
   (`services/ai/use_cases/anxiety_interpretation.py` + `prompts/anxiety_interpretation_v1.j2`)
   returns the fixed JSON schema, scrubbed by `Guardrails`; on any failure it falls
   back to the **rule-based interpreter** producing the same schema (FR-016).
   Pseudonyms only — no real athlete name reaches the provider.
5. **Dashboards** — individual series vs. baseline (`GET .../athletes/{id}/series`)
   and group triage by dominant pattern for warm-up/huddle
   (`GET .../groups/by-event/{event_id}`: somatic_high / cognitive_high /
   confidence_low / favorable + alert flags).
6. **Import/Export** — historical CSV (item-by-item) scored + baselined retroactively
   (`POST .../import`); CSV/JSON export (`GET .../export`).

## Safeguards (Constitution Principle V)

- Age-driven selection + under-13 warning.
- Wellbeing-not-diagnosis enforced in prompt + guardrails + rule fallback.
- Baseline-anchored (per athlete + subscale + instrument family; families are
  non-comparable — no stitched trend across an instrument change, FR-022).
- Mastery climate; human-in-the-loop (no auto-messaging to families).
- Alert flag (individual conversation / professional referral) on sustained
  high anxiety + low confidence.
- Guardian consent gate + coach/admin RBAC; minors privacy (pseudonyms in AI,
  no PII in logs, `AI_LOG_PROMPTS=false` in prod).

## Data model

New tables (migration `c2d3e4f5a6b7`): `anxiety_instruments`,
`anxiety_assessments`, `anxiety_response_tokens`, `anxiety_baselines`. Reuses
`athletes`, `race_events`, `users`, `parental_consents` (new
`psychological_assessment` boolean). All enums via `values_callable`.

## Runbook notes

- **Migration**: `alembic upgrade head` applies `c2d3e4f5a6b7`. Seed at least one
  active `anxiety_instruments` row per instrument type before creating assessments
  (the scoring key JSON is stored in `scoring_key_json`).
- **AI env**: reuses the standard `AI_*` settings + `get_llm_provider` factory
  (google/anthropic/fake). Interpretation always succeeds via rule fallback even
  with `AI_ENABLED=false`.
- **Tests**: `pytest tests/anxiety` (in-memory SQLite, no MySQL needed).
