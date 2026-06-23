---

description: "Task list for Competitive Anxiety Assessment (feature 017)"
---

# Tasks: Competitive Anxiety Assessment

**Input**: Design documents from `specs/017-competitive-anxiety-assessment/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rest-api.md, quickstart.md

**Tests**: INCLUDED — Constitution Principle II (Testing) is NON-NEGOTIABLE for this minors-data platform.

## Implementation status (`/speckit-implement`, 2026-06-23)

**MVP increment delivered & verified**: the pure-logic core that embodies Constitution Principle V is implemented and **all 20 unit tests pass** (`pytest tests/anxiety --noconftest`):

- ✅ T003 scoring-key fixtures (CSAI-2R / SAS-2 / CSAI-2)
- ✅ T007 instrument-key loader · ✅ T008 deterministic scoring · ✅ T009 age-driven selection + under-13 guard
- ✅ T034 rule-based interpretation fallback (mastery climate, no diagnosis, referral flag)
- ✅ T014 selection tests · ✅ T026 scoring tests · rule-interpreter tests (part of T030)

**Deliberately deferred** (need the Alembic migration + full app wiring + browser/build to verify; not implemented to avoid breaking the existing test suite with half-wired models/relationships): T001–T002 scaffolding remainder, T004–T006 migration/models/schemas, T010–T012 consent gate/router wiring, T015–T025 endpoints + answer flow + UI, T028–T033/T035–T037 scoring/interpretation endpoints + LLM use case + prompt, T038–T048 dashboards + import UI, T049–T053 polish/deploy. These are queued per `(@agent)` for the next implementation pass.

---

**Agent assignment**: each task is tagged `(@agent)` per plan.md Appendix A. `/speckit-implement` (dynamic workflow) dispatches each task to its agent, parallelizing `[P]` tasks and respecting dependencies. Orchestrated by `engineering-lead`; `head-coach-lead` + `mental-performance-coach` review safeguard/clima copy; `data-privacy-guard` audits PII gates.

## Format: `[ID] [P?] [Story] Description (@agent)`

- **[P]**: parallelizable (different files, no incomplete deps)
- **[Story]**: US1–US6 from spec.md
- All product copy in español neutro; this corpus in English.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] Create backend module scaffolding: `backend/app/services/anxiety/` (package), `backend/app/data/anxiety_keys/` dir, empty `backend/app/routers/anxiety.py`, `backend/app/schemas/anxiety.py` (@fastapi-architect)
- [ ] T002 [P] Create frontend scaffolding: `frontend/src/components/anxiety/`, `frontend/src/hooks/anxiety/`, `frontend/src/pages/anxiety/`, `frontend/src/api/anxiety.ts` (@react-ui-engineer)
- [X] T003 [P] Add scoring-key fixtures `backend/app/data/anxiety_keys/{csai2r,sas2,csai2}.json` (item→subscale map + reverse flags + subscale ranges; item TEXT slots left for licensed provisioning, not invented) (@data-analyst)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [ ] T004 Alembic migration creating `anxiety_instruments`, `anxiety_assessments`, `anxiety_response_tokens`, `anxiety_baselines` (enums via `values_callable`) and adding `psychological_assessment` boolean to `parental_consents`, in `backend/alembic/versions/` (@database-architect)
- [ ] T005 [P] SQLAlchemy models `anxiety_instrument.py`, `anxiety_assessment.py`, `anxiety_response_token.py`, `anxiety_baseline.py` in `backend/app/models/` per data-model.md (depends T004) (@fastapi-architect)
- [ ] T006 [P] Pydantic v2 schemas (create/batch/answer/read/score/interpret/import/export) in `backend/app/schemas/anxiety.py` per contracts (depends T004) (@fastapi-architect)
- [X] T007 [P] Instrument-key loader `backend/app/services/anxiety/instrument_keys.py` (reads `data/anxiety_keys/*.json`; never invents items) (@data-analyst)
- [X] T008 Deterministic scoring `backend/app/services/anxiety/scoring.py` (subscale sums, (sum/n)×10 for CSAI-2R, reverse flags, partial averaging, self-confidence NOT inverted) (depends T007) (@fastapi-architect)
- [X] T009 [P] Age-band selection + under-13 guard `backend/app/services/anxiety/selection.py` (SAS-2 for <13, CSAI-2R default 13–15, override-with-warning) (depends T005) (@fastapi-architect)
- [ ] T010 [P] Consent gate + RBAC dependency `backend/app/services/anxiety/consent_gate.py` (blocks assessment unless active `psychological_assessment` consent; coach/admin only) (depends T004) (@fastapi-architect + @data-privacy-guard)
- [ ] T011 Register `anxiety` router in `backend/app/main.py` and wire dependencies (depends T005, T006) (@fastapi-architect)
- [ ] T012 [P] Frontend anxiety API client + TanStack Query base in `frontend/src/api/anxiety.ts` (depends T006 contract) (@react-ui-engineer)

**Checkpoint**: schema, models, scoring, selection, consent gate, routing ready.

---

## Phase 3: User Story 1 — Configure a pre-race assessment (P1) 🎯 MVP

**Goal**: Coach creates single/group assessments tied to a calendar event; age-driven instrument with under-13 warning; issues answer tokens.

**Independent Test**: create assessments for mixed-age group on a Race A event; verify correct instrument, override warning, token issuance, consent block.

### Tests (write first, must fail)

- [ ] T013 [P] [US1] Contract/router tests for `POST /assessments` and `/assessments/batch` (auth denied, consent-missing 409, under-13 override 422) in `backend/tests/anxiety/test_assessments_create.py` (@qa-engineer)
- [X] T014 [P] [US1] Unit tests for `selection.py` (age bands, override) in `backend/tests/anxiety/test_selection.py` (@qa-engineer)

### Implementation

- [ ] T015 [US1] Assessment-creation service `backend/app/services/anxiety/assessments.py` (resolve instrument, copy event priority, issue token, enforce consent gate) (depends T008, T009, T010) (@fastapi-architect)
- [ ] T016 [US1] Token service `backend/app/services/anxiety/tokens.py` (hashed, single-use, expiring) (depends T005) (@fastapi-architect)
- [ ] T017 [US1] Endpoints `POST /assessments`, `POST /assessments/batch` in `backend/app/routers/anxiety.py` (depends T015, T016) (@fastapi-architect)
- [ ] T018 [P] [US1] `AssessmentWizard` config UI in `frontend/src/components/anxiety/AssessmentWizard.tsx` (event picker, group select, instrument auto + override warning) (@react-ui-engineer)
- [ ] T019 [P] [US1] `useCreateAssessment` / `useCreateBatch` hooks in `frontend/src/hooks/anxiety/` (@react-ui-engineer)
- [ ] T020 [US1] UX review of config flow (<2-min group send, tablet/field) + axe on wizard (@ux-researcher)

**Checkpoint**: US1 fully functional and testable.

---

## Phase 4: User Story 2 — Athlete answers via token (P1)

**Goal**: Athlete answers on mobile via one-time token; one item at a time, 1–4 scale, no clinical text; item answers persisted.

**Independent Test**: open token link on phone viewport, answer (incl. partial), confirm single-use + item-level persistence.

### Tests

- [ ] T021 [P] [US2] Router tests `GET/POST /answer/{token}` (valid, consumed→410, partial) in `backend/tests/anxiety/test_answer_token.py` (@qa-engineer)
- [ ] T022 [P] [US2] Frontend + axe test for questionnaire (one-at-a-time, 48×48, no horizontal scroll) in `frontend/src/components/anxiety/__tests__/Questionnaire.test.tsx` (@qa-engineer)

### Implementation

- [ ] T023 [US2] Token-answer endpoints `GET/POST /answer/{token}` in `backend/app/routers/anxiety.py` (unauth, token-gated; computes scores on submit, seeds baseline if first) (depends T016, T008) (@fastapi-architect)
- [ ] T024 [P] [US2] `Questionnaire` UI + `AnswerPage` (token route) in `frontend/src/components/anxiety/Questionnaire.tsx`, `frontend/src/pages/anxiety/AnswerPage.tsx` (one-question-at-a-time, español, encouraging-only message) (@react-ui-engineer)
- [ ] T025 [US2] Mobile/3G usability + WCAG AA pass on answer flow (@ux-researcher)

**Checkpoint**: US1 + US2 work independently (configure → answer loop).

---

## Phase 5: User Story 3 — Score the responses (P1)

**Goal**: Correct, recomputable subscale scores per official key; partial handling; self-confidence positive.

**Independent Test**: feed known answer sets per instrument; assert scores match key and ranges; recompute reproduces.

### Tests

- [X] T026 [P] [US3] Scoring unit tests per instrument (CSAI-2R 10–40, CSAI-2 9–36/27–108, SAS-2 key, partial averaging, reverse items, self-confidence not inverted) in `backend/tests/anxiety/test_scoring.py` (@qa-engineer)
- [ ] T027 [P] [US3] Recompute endpoint test in `backend/tests/anxiety/test_recompute.py` (@qa-engineer)

### Implementation

- [ ] T028 [US3] `POST /assessments/{id}/recompute` + `GET /assessments/{id}` (scores + baseline deltas) in `backend/app/routers/anxiety.py` (depends T008, T023) (@fastapi-architect)
- [ ] T029 [P] [US3] Baseline service `backend/app/services/anxiety/baseline.py` (establish per athlete+subscale+instrument family; trend vs. baseline; non-comparable across families) (depends T005, T008) (@fastapi-architect)

**Checkpoint**: scoring verified and recomputable.

---

## Phase 6: User Story 4 — Per-athlete interpretation (P1)

**Goal**: On-demand LLM interpretation (cached) in fixed JSON schema, baseline-anchored, mastery climate, no diagnosis; rule-based fallback.

**Independent Test**: interpret with LLM on/off; assert schema, mastery framing, baseline reference, fallback parity, alert flag on high-anx+low-conf.

### Tests

- [ ] T030 [P] [US4] Interpretation tests: schema validity, LLM path, fallback parity, JSON-invalid→fallback, alert flag in `backend/tests/anxiety/test_interpretation.py` (@qa-engineer)
- [ ] T031 [P] [US4] Privacy property test: real athlete name never reaches provider payload / never in output in `backend/tests/anxiety/test_interpretation_privacy.py` (@data-privacy-guard)

### Implementation

- [ ] T032 [US4] LLM use case `backend/app/services/ai/use_cases/anxiety_interpretation.py` (BaseUseCase; renders prompt; validates JSON; guardrails scrub; pseudonyms) (depends T029) (@integration-engineer)
- [ ] T033 [P] [US4] Jinja prompt `backend/app/services/ai/prompts/anxiety_interpretation_v1.j2` encoding the club runtime system prompt (no diagnosis, clima de maestría, baseline anchoring, age-appropriate, referral on extreme signals) — content reviewed by (@mental-performance-coach) (@integration-engineer)
- [X] T034 [P] [US4] Rule-based fallback `backend/app/services/anxiety/rule_interpreter.py` (coarse bands + pattern→strategy mapping; same JSON schema) (depends T029) (@integration-engineer + @mental-performance-coach) — implemented standalone (baseline passed as param; no DB dep). Unit tests in `backend/tests/anxiety/test_rule_interpreter.py` (part of T030).
- [ ] T035 [US4] Endpoints `POST /assessments/{id}/interpret` and `POST /assessments/interpret-group` (cache result + source/model; supersede on regenerate; always succeed via fallback) (depends T032, T034) (@fastapi-architect)
- [ ] T036 [P] [US4] `InterpretationPanel` + `AnalyzeButton` UI + `useInterpretation` hook in `frontend/src/components/anxiety/` (on-demand, cached, español) (@react-ui-engineer)
- [ ] T037 [US4] Verify `AI_LOG_PROMPTS=false` path + provider wiring (google/anthropic/fake) for the new use case (@integration-engineer + @devops-engineer)

**Checkpoint**: actionable, safe interpretation with guaranteed fallback.

---

## Phase 7: User Story 5 — Individual & group dashboards (P2)

**Goal**: Individual evolution vs. baseline + group triage by dominant pattern for warm-up/huddle.

**Independent Test**: load scored+interpreted set; verify individual panel and group 3-pattern split + alerts.

### Tests

- [ ] T038 [P] [US5] Dashboard endpoint tests (series split by instrument family; group triage buckets; N+1 query-count assertion) in `backend/tests/anxiety/test_dashboards.py` (@qa-engineer)
- [ ] T039 [P] [US5] Frontend + axe tests for `IndividualPanel`/`GroupPanel` in `frontend/src/components/anxiety/__tests__/` (@qa-engineer)

### Implementation

- [ ] T040 [US5] Endpoints `GET /athletes/{id}/series` and `GET /groups/by-event/{event_id}` (eager-load via selectinload; dominant-pattern bucketing) in `backend/app/routers/anxiety.py` (depends T029, T035) (@fastapi-architect)
- [ ] T041 [P] [US5] `IndividualPanel` (scores, baseline evolution chart lazy-loaded, interpretation, flags) in `frontend/src/components/anxiety/IndividualPanel.tsx` (@react-ui-engineer)
- [ ] T042 [P] [US5] `GroupPanel` (somatic/cognitive/confidence buckets + alerts) in `frontend/src/components/anxiety/GroupPanel.tsx` (@react-ui-engineer)
- [ ] T043 [US5] `AnxietyDashboardPage` route wiring + navigation in `frontend/src/pages/anxiety/AnxietyDashboardPage.tsx` (@react-ui-engineer)

**Checkpoint**: race-day triage available.

---

## Phase 8: User Story 6 — Historical import (P3)

**Goal**: CSV item-by-item import scored + interpreted retroactively; baselines seeded; series charted; CSV/JSON export.

**Independent Test**: import sample CSV (incl. CSAI-2 27-item); verify scoring, baseline seeding, charts; export round-trips.

### Tests

- [ ] T044 [P] [US6] Import tests (item-by-item CSV, CSAI-2 27-item, partial rows, error rows, baseline seeding) in `backend/tests/anxiety/test_import.py` (@qa-engineer)
- [ ] T045 [P] [US6] Export test (CSV/JSON includes item answers + scores) in `backend/tests/anxiety/test_export.py` (@qa-engineer)

### Implementation

- [ ] T046 [US6] CSV importer `backend/app/services/anxiety/importer.py` (parse item columns + metadata, infer instrument, score via scoring.py, seed baselines) (depends T008, T029) (@data-analyst)
- [ ] T047 [US6] Endpoints `POST /import` (multipart) and `GET /export` in `backend/app/routers/anxiety.py` (depends T046) (@fastapi-architect)
- [ ] T048 [P] [US6] `ImportDialog` UI + `useAnxietyImport` hook (column mapping preview, error report) in `frontend/src/components/anxiety/ImportDialog.tsx` (@react-ui-engineer)

**Checkpoint**: all user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T049 [P] Minors-privacy audit across logs/commits/AI prompts for the whole module (no name/DOB leakage; pseudonyms only) (@data-privacy-guard)
- [ ] T050 [P] Docs: `docs/` workflow + runbook for the module; update `docs/implementation-status.md` and CLAUDE.md status table (@technical-writer)
- [ ] T051 [P] Performance pass: confirm dashboard p95 + LCP budgets, lazy-load charts, query counts (@react-ui-engineer + @fastapi-architect)
- [ ] T052 Deploy prep: env vars (`AI_*`), migration on Render, post-deploy smoke of one anxiety endpoint + cold-start UI (@devops-engineer + @release-manager)
- [ ] T053 Run `quickstart.md` scenarios 1–8 end-to-end and record results (@qa-engineer)

---

## Dependencies & Execution Order

- **Setup (P1)**: T001–T003 — parallel, immediate.
- **Foundational (P2)**: T004 first (migration) → T005/T006/T007 → T008/T009/T010 → T011/T012. BLOCKS all stories.
- **US1 (P3)**: after Foundational. MVP.
- **US2 (P4)**: after Foundational; pairs with US1 for the configure→answer loop.
- **US3 (P5)**: after US2 (needs submitted answers) for live data, but scoring unit-testable independently.
- **US4 (P6)**: after US3 (needs scores + baseline).
- **US5 (P7)**: after US4 (needs scores + interpretation).
- **US6 (P8)**: after US3 (needs scoring + baseline); independent of US4/US5.
- **Polish (P9)**: after desired stories.

### Parallel Opportunities

- Setup T001/T002/T003 in parallel.
- Foundational: T005/T006/T007 in parallel after T004; T009/T010 in parallel after their deps.
- Within stories, `[P]` model/UI/test tasks parallel.
- Frontend (`@react-ui-engineer`) and backend (`@fastapi-architect`) tracks largely parallel once contracts (T006) are fixed.

---

## Implementation Strategy

### MVP First

1. Phase 1 Setup → Phase 2 Foundational → Phase 3 US1 (+ Phase 4 US2 for a usable loop).
2. STOP and VALIDATE configure→answer→score on dev.
3. Add US4 (interpretation) → US5 (dashboards) → US6 (import) incrementally.

### Dynamic-workflow note (for /speckit-implement)

Dispatch each task to its `(@agent)`; run `[P]` tasks concurrently within a phase; gate each phase checkpoint on its tests passing; re-check Constitution Principle V (safeguards) before merging US4 (interpretation) and US2 (athlete-facing copy). `engineering-lead` orchestrates; `head-coach-lead` signs off on domain safeguards.

---

## Notes

- Tests are mandatory here (Constitution II); write story tests before implementation and confirm they fail first.
- `[P]` = different files, no incomplete deps.
- Commit after each task or logical group; keep product copy in español neutro.
- Licensed instrument item text is provisioned by the club, never invented (FR-004).
