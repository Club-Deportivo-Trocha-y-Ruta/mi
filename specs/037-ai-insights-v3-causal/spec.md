# Feature Specification: AI Insights v3 — causal, field-relative, prescriptive

**Feature**: `037-ai-insights-v3-causal` · **Created**: 2026-09-02 · **Status**: approved by coach (interview 2026-09-02)
**Supersedes the analytical contract of** `docs/10-race-results/spec-insights-per-valida-v2.md` §4 (3 markdown sections). Keeps its privacy, HITL and per-válida persistence decisions.

## Problem statement

The coach's verdict on the current per-athlete AI analysis: "muy básicos, no me están dando un valor agregado". Evidence gathered on 2026-09-02 against the local DB (aggregates only):

1. **The model only sees race rows.** Prompt context = position, time, gap to winner, podium times, finisher count, recorded conditions, age, LTAD group, maturation label, last 3 summaries. Data that already exists in the platform and never reaches the analysis: 277 attendance rows with RPE/rubrics (61 for the athlete in the screenshot), anthropometry with PHV offset (6 athletes), technical focus of every session, field size per race, gap to P3, cup vs championship series, 999 finished results of all clubs (basis for a field-strength reference).
2. **The prompt is ~80 % prohibitions and 0 % method.** No reasoning method, no worked example → generic LTAD boilerplate ("7-10 h/semana, 2 días de descanso, técnica PMBIA, hidratación") repeated across válidas with numbers swapped.
3. **Smallest model for both agents** (`gemini-3.1-flash-lite`, 1024 output tokens).
4. **Data bug**: `load_race_data._compacted_season_record` reads `sequence_number` from a `RaceResult` (the column lives on `RaceEvent`) → every historic row carries `valida_num=None` → critic ground truth finds no row → "no hay resultado registrado" → `must_block=true` → **every insight lands on "Confianza baja"**, and `season_comparative` is always empty.
5. **Season summary** reuses the per-válida prompt with `valida_num=0` and no season table → "primera referencia de la temporada" after 7 races; runs synchronously with no critic/HITL, `model` hardcoded.
6. **Recommendations never persist**: `_REC_BULLET_RE` rejects bullets ending with a period → `recommendations_json = []` on all 8 insights.
7. **Gender hardcoded** ("la deportista") for every athlete.
8. **Golden eval failing** (0.651 < 0.75), citations 0 across all cases.

## Coach decisions (interview 2026-09-02)

| Question | Decision |
|---|---|
| Value expected | All four: causes (training → race), field-relative performance, concrete catalog-linked prescription, questions/dialogue with the coach |
| Data allowed to reach the AI provider (anonymised) | Race + anthropometry + training (attendance, RPE, rubrics, coach session feedback) |
| Model/budget | Strong analyst on **Gemini** (free tier), cheap critic. Verified against the configured key on 2026-09-02: `gemini-3.8-flash` (analyst) and `gemini-3.1-flash-lite` (critic) are both available with a free tier |
| Output format | New structure: 1 headline finding + 2-4 evidence-backed observations + 2-3 catalog-linked actions + 1 question for the coach, as structured JSON rendered as cards |

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The insight explains *why*, not only *what* (P1)

As the coach, after a válida I open Insights IA and read one headline finding that connects the result to something I can act on (training window, maturation, field strength, conditions), followed by observations each backed by numbers that exist in the platform.

**Acceptance**
- AC-1.1 Every observation carries ≥1 evidence item and every number in the evidence exists in the context given to the model (deterministic grounding check; violation → critic issue `high`).
- AC-1.2 The 28-day training window before the race (attendance %, mean RPE, rubric means, technical foci, coach session feedback scrubbed) is part of the model context when the athlete has ≥1 attendance row in that window; otherwise the insight lists it under `data_gaps` instead of inventing it.
- AC-1.3 Maturation context = maturity offset, months from PHV, growth velocity (height only). Weight, BMI, nutritional status **never** reach the provider.
- AC-1.4 Two válidas of the same athlete never share a headline (exact match) nor >85 % token overlap in observations.

### User Story 2 — The result is read against the field (P1)

**Acceptance**
- AC-2.1 For every finished result the system computes deterministically: field size, percentile rank, gap to P1 and P3, gap to category median time, laps behind, series kind/level.
- AC-2.2 "Expected vs actual": expected position derived from the prior performance index (season-to-date mean gap % of each finisher of that race, all clubs, ids only); the insight states whether the athlete finished above/below/at expectation and by how many places. When <50 % of finishers have a prior index, expected position is `null` and the insight says so.
- AC-2.3 Championships are labelled as such and never compared position-to-position with cup válidas; gap % and percentile are the comparable metrics.
- AC-2.4 No other minor is ever named, pseudonymised or ranked individually in the insight; only aggregates of the field.

### User Story 3 — Actions come from the club's own catalog (P1)

**Acceptance**
- AC-3.1 Each action has category, priority, horizon and an optional `catalog_ref` (`technique_skill` code, `strength_block` id or `interval_template` id) that exists in the DB; unknown refs → critic issue `med` and the ref is dropped.
- AC-3.2 LTAD guardrails remain deterministic: cadence ≥60 rpm, hours/week ≤ age, ≤5 days/week, no supplements, no structured intervals or HR-max test for <13, no medical diagnosis, no outcome goals ("podio", "ganar").
- AC-3.3 At least one action references the training window or the observation it derives from (no free-floating boilerplate).

### User Story 4 — The analyst asks, the coach answers, the next analysis remembers (P2)

**Acceptance**
- AC-4.1 Every insight ends with exactly one `coach_question` that only the coach can answer (e.g. "¿Hubo algo distinto en la semana previa: viaje, examen, molestia?").
- AC-4.2 The coach can answer inline (≤1000 chars) and rate the insight (👍/👎). Stored on the insight; the answer is scrubbed and injected into the next run's memory for that athlete.
- AC-4.3 The athlete tab exposes "Preguntar al analista": the existing race chat scoped to the athlete, with a new tool that returns the training-window aggregates.

### User Story 5 — Season summary is a real analysis (P2)

**Acceptance**
- AC-5.1 "Resumen temporada" runs through the same graph (`analysis_kind="season"`) with a dedicated prompt, the full season table with field metrics, the season training aggregates, the critic and HITL. Persisted as `valida_num=0`, `use_case="season_summary_v3"`.

### User Story 6 — Confidence and provenance are truthful (P2)

**Acceptance**
- AC-6.1 Bug-fix regression tests: `valida_num` populated for every history row; critic ground truth finds the row; recommendation bullets ending with `.` parse; gender reference follows `Athlete.sex`; persisted `model` = model actually used per role.
- AC-6.2 Confidence rules extended with training-window completeness; "Confianza baja" only when the critic blocks, the output is a fallback, or a grounding violation exists.

### User Story 7 — The eval guards the new contract (P3)

**Acceptance**
- AC-7.1 Golden set v3 (≥8 cases) with inputs carrying training window + anthropometry + field metrics; rule scorer checks schema validity, numeric grounding, catalog refs, forbidden terms, non-template headline, coach question present; judge v2 rubric adds "causal insight" and "field reading". Threshold stays 0.75.

## Success Criteria *(mandatory)*

- SC-1 On the current local dataset, regenerating the 5 cup válidas + championship of the screenshot athlete yields 6 distinct headlines, each observation grounded (0 grounding violations), ≥1 catalog-linked action per insight, confidence ≠ low on ≥5/6.
- SC-2 p95 per-válida latency ≤ 40 s with `gemini-3.8-flash`; cost ≤ USD 0.02/válida at paid rates (free tier in practice).
- SC-3 Golden eval v3 composite ≥ 0.75 in CI.
- SC-4 `data-privacy-guard` audit passes: no name, weight, BMI, nutritional status or third-party minor identifier in prompts, logs or persisted structured JSON.

## Out of scope

- Lap-split/pacing analysis (official PDFs carry only total time and "-N vueltas").
- Strava-derived load (0 activities in the DB today); the training window is attendance-based. Hook left in `training_window` for future `strava_load`.
- Parent-facing redesign beyond hiding coach-only blocks (expected-vs-actual, coach question, training feedback).
- AI-consent gate on `POST /runs` (tracked separately, as in 036).
