---
description: "Task list for feature 037 — AI Insights v3 (causal, field-relative, prescriptive)"
---

# Tasks: AI Insights v3

**Input**: `spec.md`, `plan.md`, `data-model.md`. **Tests**: mandatory (Constitution II). Every backend task ships pytest (offline lane); every frontend task ships vitest (+ jest-axe on dialog/page components).

## Format: `[ID] [P?] [Story] Description`

## Wave 1 — data & fixes (parallel, disjoint files)

- [X] T101 [P] [US6] Fixes + model roles. `nodes/load_race_data.py`: populate `valida_num` via `events_by_id` (sequence_number) in `_compacted_season_record`; regression test asserting `valida_num` and that `_build_ground_truth` finds the row. `agents/analyst.py`: relax `_REC_BULLET_RE` (trailing `.`/`;`, optional `horizonte=…`, `catálogo=…`); `athlete_ref` from `athlete_sex` in `_build_v2_context` (v2 prompt uses `{{ athlete_ref }}`). `agents/_llm.py`: `build_chat_llm(role=…)`, `resolve_configured_model(role=…)`; `config.py`: `race_ai_analyst_model`, `race_ai_critic_model`, `race_ai_training_window_days`; `pricing.py`: add `gemini-3.8-flash`, `gemini-3.5-flash-lite`. `state.py`: add ALL new keys from plan §State keys. `routers/race_analysis.py`: inject `athlete_sex`, `analysis_kind` (new body field), keep `prompt_version` v2 for now (v3 switch in T204). Tests for each.
- [X] T102 [P] [US2] `app/services/race/field_metrics.py` + `nodes/compute_metrics.py` → `field_context`. Pure pandas per plan §Expected-vs-actual; fixtures with ≥3 events, one championship, DNF rows, <50 % coverage case. Unit tests for percentile, expected position, coverage rule, championship label.
- [X] T103 [P] [US1] `app/services/race/ai/athlete_context.py` + `nodes/load_athlete_context.py` + register in `graph.py` after `load_race_data`; `nodes/anonymize.py` scrubs `training_window.coach_feedback` with `club_forbidden_names`. Loaders per data-model.md; `age_band_from_age`; explicit eager loads (`selectinload`) for attendance→session→technique_exercises/strength_blocks/interval_structure. Tests with aiosqlite: window boundaries, None when no attendance, no weight/BMI keys ever present (assert), feedback scrubbed.
- [X] T104 [P] [US4] Migration `ai_insights_v3_columns` (down `463c1f0ccb38`), model columns, DTO fields (`headline`, `structured`, `coach_answer_*`, `coach_rating`), parent-mode server-side omission, `POST …/insights/{insight_id}/answer` (coach/admin; parent 403; other club 404), `nodes/recall_memory.py` → `coach_dialogue` (last 3 approved with structured_json). Tests: denied path, answer persisted + scrubbed, recall returns dialogue.

## Wave 2 — LLM layer + frontend contract (parallel)

- [X] T201 [US1,US3] `app/services/race/insight_v3.py` (InsightV3, render markdown, numeric tokens), prompts `race_analyst_v3.md` + `race_season_summary_v3.md` (method + few-shot), `agents/analyst.py::invoke_v3` (structured output, JSON-repair retry, concurrency 2), `nodes/analyst_agent.py` v3 branch (valida & season), `fallback.py::deterministic_fallback_v3`, `nodes/persist_insight.py` writes `structured_json` + rendered `summary_text` + parsed recommendations, `use_case` per kind. Tests with a fake LLM returning JSON; prompt renders with every data block absent/present; season prompt renders the season table.
- [X] T202 [US6] `app/services/race/ai/prechecks.py`, `prompts/race_critic_v3.md`, `agents/critic.py::invoke_v3`, `nodes/critic_agent.py` v3 branch (prechecks → LLM), `confidence.py` v3 rules (training/anthro completeness). Tests: number grounding tolerant formats, catalog ref unknown → med + dropped, LTAD rules, overlap rule, must_block only on privacy/ltad/high.
- [X] T203 [US4,US5] Routers: `POST /season-summary` launches graph run `analysis_kind="season"` (202 `{run_id,status}`), consent gate 451 on `start_run` and season, `hitl_gate_review` payload `structured_draft`, `agents/chat.py` athlete scope + `obtener_contexto_entrenamiento` tool. Tests: 451 path, season run launched with correct initial_state, chat tool returns aggregates only.
- [X] T204 [US6] Switch default `prompt_version` to `race_analyst_v3` in both launch routers; `RACE_AI_PROMPT_VERSION` env override (`v2` rollback). Update `tests/routers/*` expectations.
- [X] T205 [P] Frontend contract: `types/insightV3.types.ts`, extend `types/athleteRaceAnalysis.types.ts`, `api/athleteRaceAnalysis.ts` (`answerInsight`, `generateSeasonSummary` → run), `api/raceAnalysis.ts` chat `athlete_id`, hooks (`useAnswerInsight`, `useGenerateSeasonSummary` → returns run_id), MSW handlers + `fixtures/insightV3.ts` (5 distinct structured insights + season). Existing tests still green.

## Status 2026-09-02

Waves 1 and 2 done and integrated (backend race+routers green, ruff clean on touched files, `npm run typecheck` clean, vitest green except the pre-existing `datetime.test.ts` timezone case). Waves 3 and 4 done 2026-09-02 (second workflow run); Gate 3 and final gate green with only the known pre-existing failures. Post-workflow fix: `grounding_numbers` now excludes the few-shot example of the v3 prompts (`grounding_source_text`). Only T404 (SC-1 real regeneration) remains. Integration fixes applied by the orchestrator after the workflow: duplicate keys removed from `RaceAnalystState`; `SeasonSummaryButton` moved to the 202 `{run_id}` contract (`onRunStarted`), full run-timeline wiring stays in T302.

Known gaps carried into Wave 3/4 (from agent reports): `start_athlete_run` in `routers/athlete_race_analysis.py` still lacks the 451 consent gate (only `start_run` and season have it); `chat.py` does not pass `role="chat"` (harmless, same default); `ActionCategory.tactics` degrades to `technique` in the compat `AnalysisOutput`; HITL payload exposes `structured_draft` only for the lowest válida of a multi-válida run; the v3 season prompt has no N=1 hard veto equivalent (relies on `trend="first_reference"` instruction + prechecks); critic model provenance is not persisted (single `model` column).

## Wave 3 — UI (parallel)

- [X] T301 [US1,US2,US3] `InsightV3Card.tsx` (+ sub-blocks), `InsightsTimeline.tsx` (preview = headline; drawer → card), `HeroLastInsightCard.tsx` (headline + first action), `HITLApprovalCard.tsx` (structured draft view, edit falls back to markdown), parent mode gating. Tests: render all blocks, parent hides coach-only blocks, a11y zero violations, preview shows headline.
- [X] T302 [US4,US5] `CoachAnswerForm.tsx` (textarea ≤1000 + 👍/👎, optimistic), mounted in drawer slot prop `footer` of `InsightV3Card`; `AthleteAnalystChatPanel.tsx` in the tab ("Preguntar al analista", coach only); `SeasonSummaryButton.tsx` starts run + shows `AnalysisRunTimeline`. Tests: answer posts and updates cache; chat sends athlete_id; season button → run timeline.

## Wave 4 — quality

- [X] T401 [US7] Eval v3: `evals/race_analyst/golden_v3/case_001..008.json` (inputs incl. training window, anthro, field metrics; fictional), `eval/scorer_v3.py`, `eval/prompts/judge_v2.md`, `tests/evals/test_race_analyst_eval.py` v3 path (`RACE_EVAL_VERSION`, default v3). Threshold 0.75.
- [X] T402 Privacy audit (`data-privacy-guard`): prompts, logs, persisted JSON, parent DTO omission.
- [X] T403 Docs: `docs/10-race-results/spec-insights-v3.md`, `docs/implementation-status.md`, `docs/technical-notes.md` (dated entry), CLAUDE.md model line.
- [X] T405 Backend gaps: 451 consent gate on `start_athlete_run`, `role="chat"` in `chat.py`, `structured_drafts` (plural) in the HITL payload. Done 2026-09-02.
- [ ] T404 Verification: `pytest`, `ruff check`, `npm run typecheck`, `npm test`; SC-1 regeneration of the screenshot athlete's 6 races on the local DB (aggregate report only).
