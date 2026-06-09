# Tasks: Faithful, Grounded AI Insights for Competitions

**Input**: Design documents from `/specs/011-ai-insights-grounding/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — Constitution Principle II (NON-NEGOTIABLE) requires every bug fix to land with a regression test that fails on unfixed code, plus privacy invariants for minors' data. Write each story's tests first and confirm they fail before implementing.

**Organization**: Tasks are grouped by user story (US1–US6 from spec.md) so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)

## Path Conventions

Web app: `backend/app/...` + `backend/tests/...` and `frontend/src/...` (per plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared test fixtures every story's regression tests will use. No project init or new dependencies are needed (Constitution: stack unchanged).

- [ ] T001 [P] Add shared pytest fixtures in backend/tests/conftest.py (or a new backend/tests/fixtures/race_grounding.py imported from conftest): a completed `RaceEvent` with full recorded conditions (surface=Húmeda, climate=Nublado, 25.0 °C, 1000 msnm, weather_notes con un nombre prohibido para tests de privacidad), a completed `RaceEvent` with all condition fields NULL, an athlete with a latest `AnthropometricRecord` (maturation Circa-PHV) and one athlete with zero anthropometric records
- [ ] T002 [P] Add a reusable fake-LLM/critic stub helper in backend/tests/helpers/ai_stubs.py that returns canned analyst markdown and critic verdict JSON (so graph-level tests run without `AI_API_KEY`), following the existing `_analyst_agent`/`_critic_agent` state-injection seams

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Typed contract changes that US1 and US2 both build on. MUST be complete before any user story phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Add `race_meta: str | None = None` and `maturation_status: str | None = None` fields to `AnalysisInput` in backend/app/services/race/schemas.py (keep `extra="forbid"`; document the per-válida semantics from contracts/graph-state.md in the docstring)
- [ ] T004 Add `fetch_event_conditions(db, season, valida_nums) -> dict[int, dict]` to backend/app/services/race/queries.py returning the five condition fields per valida_num (reuse `load_events`/`load_series` caches; an event with all-NULL conditions still yields an entry with all-None values, per contracts/graph-state.md)

**Checkpoint**: Foundation ready — user story phases can begin.

---

## Phase 3: User Story 1 — Race conditions match what was recorded (Priority: P1) 🎯 MVP

**Goal**: Every analysis states only the recorded conditions of its event; events without recorded conditions produce analyses that never mention clima/pista, with an explicit anti-fabrication veto in the prompt.

**Independent Test**: quickstart.md §1–§2 — re-run the canonical case (athlete 3, Válida 4, Cali: Húmeda/Nublado/25 °C) and an event without conditions; verify faithful statement vs. complete omission.

### Tests for User Story 1 (write FIRST, confirm they FAIL)

- [ ] T005 [P] [US1] Regression test `test_load_race_data_emits_event_conditions` (per launched válida; all-None entry for unrecorded event) in backend/tests/services/race/ai/test_load_race_data_conditions.py
- [ ] T006 [P] [US1] Regression tests `test_race_meta_populated_from_event_conditions` and `test_race_meta_none_when_unrecorded` (AnalysisInput built per válida; `format_race_meta` returns None on all-None, never empty string) in backend/tests/services/race/test_analyst_race_meta.py
- [ ] T007 [P] [US1] Prompt-rendering regression tests: with `race_meta` → "## Condiciones de carrera" present with exact recorded values; with `race_meta=None` → no conditions section AND the veto text present AND Sección-1 instruction no longer demands conditions, in backend/tests/services/race/test_prompt_v2_conditions.py
- [ ] T008 [P] [US1] Privacy property test `test_weather_notes_scrubbed_before_prompt` — forbidden name seeded in `weather_notes` never appears in the assembled prompt context (Constitution privacy gate) in backend/tests/services/race/ai/test_anonymize_conditions.py
- [ ] T009 [P] [US1] Deterministic guardrail test: when `race_meta is None` and the (stubbed) model output mentions clima/pista/terreno terms, the guardrail flags/strips it, in backend/tests/services/race/test_guardrails_conditions_veto.py

### Implementation for User Story 1

- [ ] T010 [US1] Extend `load_race_data` node to call `fetch_event_conditions` and emit `state["event_conditions"]` keyed by valida_num in backend/app/services/race/ai/nodes/load_race_data.py
- [ ] T011 [US1] Extend `anonymize` node to scrub `event_conditions[*].weather_notes` with the existing forbidden-names scrubbing in backend/app/services/race/ai/nodes/anonymize.py
- [ ] T012 [US1] Add `format_race_meta(conditions) -> str | None` helper and wire `_build_v2_context` to read `input_.race_meta` (delete the dead `podium_context.get("race_meta")` read) in backend/app/services/race/agents/analyst.py
- [ ] T013 [US1] Thread per-válida `race_meta` into each `AnalysisInput` in `_build_input`/`_analyst_agent_v2` in backend/app/services/race/ai/nodes/analyst_agent.py
- [ ] T014 [US1] Edit prompt backend/app/services/race/prompts/race_analyst_v2.md: make the Sección-1 "SÍ incluir … condiciones" instruction conditional on `race_meta`, and add the hard veto block ("PROHIBIDO mencionar clima, pista o terreno si no se proveen datos de condiciones") rendered when `race_meta` is falsy (copy in español neutro)
- [ ] T015 [US1] Add the deterministic conditions-veto scan (climate/track term list checked only when `race_meta is None`) to the existing guardrails post-generation pass in backend/app/services/ai/guardrails.py (or the race-specific guardrail call site in backend/app/services/race/agents/analyst.py — keep it where `scrub_with_report` runs)

**Checkpoint**: US1 fully functional — T005–T009 pass; quickstart §1–§2 verifiable end to end.

---

## Phase 4: User Story 2 — Real maturation status and age/LTAD group (Priority: P1)

**Goal**: Analyses use the athlete's real maturation (from anthropometric records) and real LTAD group; never the Pre-PHV/Bambino defaults; no maturation claim when no records exist.

**Independent Test**: quickstart.md §3 — athlete 3 (Circa-PHV, +0.7) is analyzed as Circa-PHV; a 13–15 athlete gets the juvenil block; an athlete without records gets no maturation claim.

### Tests for User Story 2 (write FIRST, confirm they FAIL)

- [ ] T016 [P] [US2] Regression test `test_initial_state_injects_ltad_and_maturation` for both launch routers (per-athlete v2 and global) asserting `initial_state["ltad_group"]` matches the age mapping and `maturation_status` comes from the latest anthropometric record (None when no records) in backend/tests/routers/test_launch_state_injection.py
- [ ] T017 [P] [US2] Regression test `test_maturation_status_not_defaulted` — `_build_v2_context` uses `input_.maturation_status`; the dead `podium_context.get("maturation_status", "Pre-PHV")` read is gone; Circa-PHV athlete renders "Circa-PHV" in prompt context — in backend/tests/services/race/test_analyst_maturation.py
- [ ] T018 [P] [US2] Prompt-rendering test: `maturation_status=None` → no "Fase madurativa" line and an explicit no-maturation-claims instruction; `ltad_group="juvenil"` → 13–15 differentiation block rendered (not the 10–12 block) in backend/tests/services/race/test_prompt_v2_maturation_ltad.py

### Implementation for User Story 2

- [ ] T019 [P] [US2] Inject `ltad_group` (reusing the existing age→group mapping at lines ~776-794) and `maturation_status` (latest anthropometric record query, None-safe) into `initial_state` in backend/app/routers/athlete_race_analysis.py
- [ ] T020 [P] [US2] Same injection for the global launch path's `initial_state` in backend/app/routers/race_analysis.py
- [ ] T021 [US2] Read `input_.maturation_status` in `_build_v2_context` (remove the dead podium_context read; keep a logged exceptional fallback in `_resolve_ltad` per contracts/graph-state.md) in backend/app/services/race/agents/analyst.py and backend/app/services/race/ai/nodes/analyst_agent.py
- [ ] T022 [US2] Edit backend/app/services/race/prompts/race_analyst_v2.md: render the "Fase madurativa" context line only when `maturation_status` is provided; when absent, instruct the model to make no maturation-phase claim (depends on T014 — same file, sequence after US1's prompt edit)

**Checkpoint**: US1 + US2 — the two P1 defects (fabricated conditions, wrong maturation/group) are fixed and regression-tested.

---

## Phase 5: User Story 3 — Every draft reviewed, with ground truth (Priority: P2)

**Goal**: The critic validates the v2 section structure, reviews all N drafts of a batch, and receives per-draft ground truth so contradictions with recorded data are flagged.

**Independent Test**: quickstart.md §4 — group run of N≥2 válidas yields N verdicts; a seeded contradictory draft is flagged.

### Tests for User Story 3 (write FIRST, confirm they FAIL)

- [ ] T023 [P] [US3] Regression test `test_critic_reviews_all_drafts` — graph state with 3 `per_valida_drafts` produces `per_valida_verdicts` with 3 entries (stubbed critic LLM) in backend/tests/services/race/ai/test_critic_coverage.py
- [ ] T024 [P] [US3] Regression test `test_critic_v2_accepts_v2_sections` — a well-formed v2 draft ("Qué pasó…", "Recorrido…", "Hacia dónde…") is not penalized for missing v1 sections (prompt-render assertion: critic v2 prompt lists v2 headings, not "## Evolución" etc.) in backend/tests/services/race/test_critic_v2_prompt.py
- [ ] T025 [P] [US3] Test `test_critic_prompt_includes_ground_truth` — the rendered critic v2 prompt contains the válida's recorded conditions (or "sin condiciones registradas"), the athlete's result row, and podium times, in backend/tests/services/race/test_critic_v2_prompt.py
- [ ] T026 [P] [US3] Test `test_persist_stores_per_valida_verdicts` — each persisted insight row carries its own `metrics_snapshot_json["critic_verdict"]` and `["grounding"]` keys (additive; old snapshots stay valid) in backend/tests/services/race/ai/test_persist_grounding_snapshot.py

### Implementation for User Story 3

- [ ] T027 [P] [US3] Create prompt backend/app/services/race/prompts/race_critic_v2.md per contracts/prompt-variables.md: v2 expected sections, `ground_truth` block, contradiction rules (severity high; clima/pista mention with unrecorded conditions = issue), identical JSON verdict schema (copy in español neutro)
- [ ] T028 [US3] Extend `RaceCriticAgent` in backend/app/services/race/agents/critic.py with a v2 invoke path that renders race_critic_v2.md with `draft_analysis` + formatted `ground_truth` (reuse existing JSON parsing/retry)
- [ ] T029 [US3] Rework the `critic_agent` node to iterate `per_valida_drafts` (bounded, cap=4), build each draft's ground truth from `state["event_conditions"]` + `raw_data`/`podium_context`, and emit `state["per_valida_verdicts"]` (keep singular `critic_feedback` = first válida for v1 compat) in backend/app/services/race/ai/nodes/critic_agent.py
- [ ] T030 [US3] Update `hitl_gate_review` to consider per-válida verdicts (must_block on any blocked draft; only the affected draft is withheld per spec edge case) in backend/app/services/race/ai/nodes/hitl_gate_review.py
- [ ] T031 [US3] Persist per-row `critic_verdict` and `grounding` keys into `metrics_snapshot_json` in backend/app/services/race/ai/nodes/persist_insight.py (additive keys per data-model.md)

**Checkpoint**: All drafts in a batch are reviewed against real data before delivery.

---

## Phase 6: User Story 4 — Computed confidence (Priority: P2)

**Goal**: The persisted/displayed confidence reflects the actual run (critic verdict + data completeness) instead of the hardcoded `medium`.

**Independent Test**: quickstart.md §4 step 3 — clean/full-data run shows alta; run with issues or missing data shows media/baja; the badge demonstrably varies.

### Tests for User Story 4 (write FIRST, confirm they FAIL)

- [ ] T032 [P] [US4] Unit tests for `compute_confidence` covering every rule branch of data-model.md (fallback/must_block/high→low; med issue or no verdict→medium; missing conditions/maturation or N=1 cap→medium; clean+complete→high) in backend/tests/services/race/ai/test_confidence.py
- [ ] T033 [P] [US4] Regression test `test_confidence_varies_with_inputs` — two graph runs (clean+complete vs. flagged/missing-data) persist different `AthleteAiInsight.confidence` values (fails on unfixed code where both are `medium`) in backend/tests/services/race/ai/test_persist_confidence.py

### Implementation for User Story 4

- [ ] T034 [P] [US4] Create `compute_confidence(verdict, completeness) -> InsightConfidence` (pure, deterministic) in backend/app/services/race/ai/confidence.py
- [ ] T035 [US4] Wire per-válida confidence into the graph: compute after the critic (in critic_agent node output or persist preamble) as `state["confidence"]: dict[int, InsightConfidence]`, and make `persist_insight` read the per-válida value (constant default remains only for v1 runs) in backend/app/services/race/ai/nodes/critic_agent.py and backend/app/services/race/ai/nodes/persist_insight.py (depends on T029/T031)

**Checkpoint**: The "Confianza" badge is a real signal (frontend already renders the enum — no UI change required).

---

## Phase 7: User Story 5 — Chat held to the same grounding rule (Priority: P3)

**Goal**: The competition chat answers condition questions only from recorded data and says "no quedó registrado" when absent.

**Independent Test**: quickstart.md §5 — ask «¿cómo estaban la pista y el clima?» for a recorded and an unrecorded event.

### Tests for User Story 5 (write FIRST, confirm they FAIL)

- [ ] T036 [P] [US5] Tool tests: `obtener_condiciones_evento` returns recorded conditions JSON for the recorded event and `{"registro": false}` for the all-NULL event (db_factory-injected, no LLM) in backend/tests/services/race/test_chat_conditions_tool.py
- [ ] T037 [P] [US5] Prompt test: race_chat_v1.md contains the grounding rule (tool-derived answers; "no quedó registrado" on absence; inventing PROHIBIDO) and the tool is registered in the agent's tool list, in backend/tests/services/race/test_chat_grounding_prompt.py

### Implementation for User Story 5

- [ ] T038 [US5] Add `_build_obtener_condiciones_evento_tool(db_factory, ...)` factory (same pattern as the two existing tools) and register it in the chat agent loop in backend/app/services/race/agents/chat.py
- [ ] T039 [US5] Edit backend/app/services/race/prompts/race_chat_v1.md adding the grounding rule per contracts/prompt-variables.md (copy in español neutro)

**Checkpoint**: Chat can no longer fabricate event conditions.

---

## Phase 8: User Story 6 — Re-generate stored fabricated analyses (Priority: P3)

**Goal**: The coach replaces a stored fabricated insight with a faithful one in a single action; a failed re-generation never removes the existing insight.

**Independent Test**: quickstart.md §1 step 3 — re-launch Válida 4 for athlete 3; the old insight is deprecated and the new grounded one becomes active; simulate failure and verify the old one survives.

### Tests for User Story 6 (write FIRST, confirm they FAIL)

- [ ] T040 [P] [US6] Regression test `test_failed_regeneration_keeps_previous_insight_active` — a graph run that errors before/at persist leaves the prior active row `is_active=1`; an approved run deprecates it via `deprecate_previous_active` in backend/tests/services/race/ai/test_regenerate_replace.py
- [ ] T041 [P] [US6] Frontend tests for the Regenerar action in frontend/src/components/athletes/ai/__tests__/InsightsTimeline.regenerate.test.tsx: action visible on insight rows, triggers the per-válida launch mutation with the row's (season, valida_num), shows error state on failure (vitest + Testing Library), and jest-axe passes on the row with the new control

### Implementation for User Story 6

- [ ] T042 [US6] Add the "Regenerar" affordance (button/menu item, copy en español neutro, target táctil ≥48px) to the insight row that re-launches the existing per-válida analysis endpoint scoped to that válida, with loading/error states per Constitution III, in frontend/src/components/athletes/ai/InsightsTimeline.tsx (reuse the existing launch mutation from LaunchAnalysisForm/TanStack Query hooks)

**Checkpoint**: All six user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T043 [P] Run the data-privacy-guard audit over the changed surfaces (conditions → prompt, maturation → prompt, chat tool output, snapshot JSON) and record the result in the PR description (Constitution privacy gate)
- [ ] T044 [P] Update docs/implementation-status.md (new module row) and the CLAUDE.md "Implementation status" table with feature 011
- [ ] T045 Full quality gate: `cd backend && pytest` (all suites), `ruff` + `mypy`, `cd frontend && npm test` + `eslint` + `tsc --noEmit`; fix any fallout
- [ ] T046 Execute quickstart.md manually end to end (canonical Válida 4 case, omission case, maturation case, chat questions) and check token growth of the v2 prompt stays within `AI_MAX_TOKENS=8192`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately
- **Foundational (Phase 2)**: after Setup — BLOCKS all stories (T003 blocks US1/US2 input wiring; T004 blocks US1/US3/US5 data access)
- **US1 (Phase 3)** and **US2 (Phase 4)**: after Phase 2; mostly independent, EXCEPT both edit `race_analyst_v2.md` and `analyst.py` → do US1 first, then US2 (T022 depends on T014; T021 touches the same function as T012)
- **US3 (Phase 5)**: after Phase 2; consumes `event_conditions` (T010) for ground truth → run after US1
- **US4 (Phase 6)**: T034 is independent; T035 depends on US3 (T029, T031)
- **US5 (Phase 7)**: only needs T004 — can run in parallel with US1–US4
- **US6 (Phase 8)**: backend test T040 independent; frontend T041/T042 deliver most value after US1/US2 (so the regenerated insight is actually faithful)
- **Polish (Phase 9)**: after all desired stories

### Parallel Opportunities

- T001 ∥ T002 (Setup); T003 ∥ T004 within reason (different files)
- All test-first tasks within a story are [P] (different test files)
- T019 ∥ T020 (different routers); T027 ∥ T028 prep; T034 ∥ T033's test authoring
- **US5 in parallel with US1–US4** (different modules: chat vs. graph)
- T043 ∥ T044 in Polish

### Parallel Example: User Story 1

```bash
# Write all US1 regression tests together (different files):
Task: T005 backend/tests/services/race/ai/test_load_race_data_conditions.py
Task: T006 backend/tests/services/race/test_analyst_race_meta.py
Task: T007 backend/tests/services/race/test_prompt_v2_conditions.py
Task: T008 backend/tests/services/race/ai/test_anonymize_conditions.py
Task: T009 backend/tests/services/race/test_guardrails_conditions_veto.py
# Then implement sequentially: T010 → T011 → T012 → T013 → T014 → T015
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 + Phase 2 (fixtures + typed contract + conditions query)
2. Phase 3 (US1) → **STOP and VALIDATE** against the canonical Válida 4 / Cali case
3. This alone closes the reported bug: no more fabricated conditions

### Incremental Delivery

1. US1 → validate → deploy (reported bug fixed)
2. US2 → validate → deploy (P1 sports-safety fix: real maturation/LTAD)
3. US3 → US4 (review coverage, then real confidence — US4 builds on US3's verdicts)
4. US5 (chat) any time after Phase 2; US6 (regenerate UI) last, once outputs are faithful
5. Polish: privacy audit, docs, full gates, manual quickstart

---

## Notes

- No Alembic migration in any task — verify none is generated accidentally (`alembic revision --autogenerate` should produce an empty diff)
- Both prompts edited here carry product-facing copy → español neutro (Colombia); test/code identifiers in English
- Commit per task or logical group (Conventional Commits: type in English, description en español latino, no AI references)
