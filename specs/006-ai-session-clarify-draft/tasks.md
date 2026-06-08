---
description: "Task list for AI Session Clarify & Draft (006)"
---

# Tasks: AI Session Clarify & Draft

**Input**: Design documents from `specs/006-ai-session-clarify-draft/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/session-assistant.md

**Tests**: INCLUDED — Constitution Principle II (Testing) is NON-NEGOTIABLE for this codebase,
and this feature handles minors' data (privacy invariants required).

**Organization**: Grouped by user story (US1 P1, US2 P2, US3 P2) for independent delivery.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish carry no story label)
- Exact file paths included.

## Path Conventions
Web app: `backend/app/...` + `backend/tests/...`, `frontend/src/...` + `frontend/test/...`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm environment and scaffolding; no behavior yet.

- [ ] T001 Verify backend AI stack imports and `FakeLLMProvider` are available by running `cd backend && pytest tests/services/ai -q` (baseline green) and note the existing patterns reused (`BaseUseCase`, `PromptRegistry`, `Guardrails`).
- [ ] T002 [P] Confirm frontend builds and the session-wizard route renders: `cd frontend && npx tsc --noEmit && npx vitest run src/components/training/session-wizard -q`.
- [ ] T003 [P] Confirm `frontend/src/components/ui/toggle-group.tsx` supports `type="multiple"` (Radix prop) — no change expected; record findings inline in `aiSeededFields.ts` header comment when created.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared schemas, prompts, context builder, DI, router wiring, and frontend
scaffolding that ALL user stories depend on. No story is testable until this completes.

- [ ] T004 Create transient Pydantic schemas + enums in `backend/app/schemas/session_assistant.py` per data-model.md: `AthleteCallUpCriterion`, `SessionClarifyRequest`, `SessionAnswer`, `SessionDraftRequest`, `ClarifyOption`, `ClarifyQuestion`, `SessionClarifyResponse`, `SessionDraftResponse` (with field length/count validators).
- [ ] T005 [P] Add the two `PromptSpec` entries (`session_clarify`, `session_draft`) to `backend/app/services/ai/prompts/registry.py` with their `required_keys` (aggregate context keys from data-model.md §Aggregate context).
- [ ] T006 [P] Author Jinja prompt `backend/app/services/ai/prompts/session_clarify.j2` — instructs JSON-only output of 0–4 questions (2–4 options each), español neutro, references non-negotiables; consumes aggregate context only (no names).
- [ ] T007 [P] Author Jinja prompt `backend/app/services/ai/prompts/session_draft.j2` — instructs JSON-only editable draft (fields per data-model.md), español neutro, `athlete_call_up` as criterion only, structured warm-up/main/cool-down description.
- [ ] T008 Create `backend/app/services/training/session_assistant_context.py`: `build_aggregate_context(db, club_id, selected_athlete_ids)` → returns `age_mix` counts, `total_athletes`, `season_phase`, `days_to_next_race`, `next_race_priority`, `today`; reuses `app.services.category.compute_age_decimal` + age-group thresholds; **discards ids/names** after computing counts. Include `COPA_VALLE_2026` calendar constant here.
- [ ] T009 Create the use-case module `backend/app/services/ai/use_cases/session_assistant.py` with `SessionClarifyUseCase` and `SessionDraftUseCase` (subclass `BaseUseCase`, `template_id` set), each `run(...)`: render → `_ask` → strip fences → `json.loads` → guardrail-scrub strings → Pydantic-validate → return; raise `LLMSchemaError` on bad shape. (Behavior filled per story; structure here.)
- [ ] T010 Add DI providers `get_session_clarify_use_case` and `get_session_draft_use_case` in `backend/app/dependencies.py` (mirror `_get_monthly_report_blocks_use_case`: `Depends(get_llm_provider)` + `Depends(get_prompt_registry)`).
- [ ] T011 Create router skeleton `backend/app/routers/session_assistant.py` with `prefix="/api/clubs/{club_id}/session-assistant"`, both routes declared with `require_role([UserRole.admin, UserRole.coach])` + `user_club_role` access check (mirror `monthly_reports.py`); register it in `backend/app/main.py`.
- [ ] T012 [P] Create frontend types + API client `frontend/src/api/sessionAssistant.ts` (`clarify()`, `draft()` calling the two endpoints) matching contracts/session-assistant.md.
- [ ] T013 [P] Create TanStack hooks `frontend/src/hooks/training/useSessionAssistant.ts` (`useClarify`, `useDraft` mutations; map 503/422 to typed error states).
- [ ] T014 [P] Create Zod schema + draft→form mapper `frontend/src/schemas/sessionAssistant.schema.ts` (answers validation; `SessionDraftResponse` → `TrainingSessionFormValues`, resolving `athlete_call_up` against a passed roster).
- [ ] T015 Add the pre-wizard route `/training/sessions/assistant` in `frontend/src/App.tsx` (`ProtectedRoute allowedRoles={[coach, admin]}`) mounting a lazy `SessionAssistantPage`.
- [ ] T016 [P] Create MSW handlers `frontend/test/msw/sessionAssistantHandlers.ts` (clarify/draft happy + 503 + 422 fixtures).

**Checkpoint**: schemas/prompts/context/DI/router/frontend-scaffold exist; stories can build.

---

## Phase 3: User Story 1 — Clarify then draft from a short intent (Priority: P1) 🎯 MVP

**Goal**: Coach submits an intent, answers 2–4 chip questions (single/multi/"Otro"), gets an
editable draft that prefills the wizard; nothing auto-saved.

**Independent Test**: With AI enabled (or `FakeLLMProvider` canned fixture), open the
assistant, submit intent, answer questions, confirm the wizard opens pre-filled and editable
and no session is persisted until explicit save.

### Tests for US1
- [ ] T017 [P] [US1] Backend use-case test `backend/tests/services/ai/test_session_assistant_use_case.py`: clarify returns 2–4 questions w/ 2–4 options; draft maps all fields; fence-stripping + `json.loads` happy path via `FakeLLMProvider` fixture.
- [ ] T018 [P] [US1] Backend router test `backend/tests/routers/test_session_assistant.py`: `POST .../clarify` and `.../draft` happy paths (coach) return 200 with contract shapes; nothing written to DB.
- [ ] T019 [P] [US1] Frontend test `frontend/src/components/training/session-wizard/ai-assistant/SessionAssistantPanel.test.tsx`: renders questions, single-select keeps ≤1, multi-select keeps many, "Otro" reveals input; "Generar borrador" calls draft and hands values up.

### Implementation for US1
- [ ] T020 [US1] Implement `SessionClarifyUseCase.run()` body in `backend/app/services/ai/use_cases/session_assistant.py` (questions parse/validate/scrub) — depends on T009.
- [ ] T021 [US1] Implement `SessionDraftUseCase.run()` body in the same module (draft parse/validate/scrub, criterion enforcement) — depends on T009.
- [ ] T022 [US1] Implement the two endpoint bodies in `backend/app/routers/session_assistant.py`: build context (T008), call use cases, return contract responses — depends on T011, T020, T021.
- [ ] T023 [P] [US1] Build `frontend/src/components/training/session-wizard/ai-assistant/ClarifyQuestionCard.tsx` using `ToggleGroup` (`type="single"`/`"multiple"`, ≥48px) + "Otro" free-text (RHF+Zod).
- [ ] T024 [US1] Build `frontend/src/components/training/session-wizard/ai-assistant/SessionAssistantPanel.tsx`: intent textarea → `useClarify` → render `ClarifyQuestionCard`s → `useDraft` → emit mapped draft; lazy-loaded.
- [ ] T025 [US1] Build `frontend/src/routes/training/SessionAssistantPage.tsx` hosting the panel; on draft ready, navigate to the wizard handing off the mapped values (router state or store).
- [ ] T026 [US1] Edit `frontend/src/routes/training/SessionFormPage.tsx` + `SessionWizard.tsx` to accept an applied draft and prefill via `reset(values, { keepDirtyValues: true })` (Context7 pattern) — depends on T014, T025.

**Checkpoint**: MVP demoable end-to-end with AI enabled.

---

## Phase 4: User Story 2 — Smarter questions & drafts from club context (Priority: P2)

**Goal**: Questions/draft reflect age-mix and race proximity using aggregate context only.

**Independent Test**: For a 10–12 selection near an A-race, confirm no structured intervals
and taper-appropriate load; confirm no individual athlete is named anywhere.

### Tests for US2
- [ ] T027 [P] [US2] Backend test `backend/tests/services/training/test_session_assistant_context.py`: `build_aggregate_context` produces correct `age_mix` counts from athlete birth_dates and correct `days_to_next_race`/`priority` from `COPA_VALLE_2026`; asserts no names/ids in the returned dict.
- [ ] T028 [P] [US2] Backend test in `test_session_assistant_use_case.py`: given a 10–12-only age_mix near A-race, the (faked) prompt context carries the right signals and parsed output passes guardrails (no intervals language survives).

### Implementation for US2
- [ ] T029 [US2] Finalize `session_assistant_context.py`: age-mix computation, `season_phase` mapping, `days_to_next_race`/`next_race_priority` from `COPA_VALLE_2026` — depends on T008.
- [ ] T030 [US2] Condition both `.j2` prompts on the aggregate context (age-mix → group rules; race proximity → taper guidance), keeping español + non-negotiables — depends on T006, T007.
- [ ] T031 [P] [US2] Frontend: pass `selected_athlete_ids` (if any preselected) from the assistant page into `useClarify`/`useDraft`, and resolve `athlete_call_up` → ids via the roster in `sessionAssistant.schema.ts` — depends on T014, T024.

**Checkpoint**: Context-aware behavior verified; privacy of aggregate context asserted.

---

## Phase 5: User Story 3 — Safe, compliant output & graceful fallback (Priority: P2)

**Goal**: All output guardrail-clean; AI-disabled/timeout/malformed handled with clear UX and
no data loss; privacy invariants hold; single-round only.

**Independent Test**: Force AI off / malformed / timeout and confirm clear messages + manual
wizard works with no data loss; verify no name/id in context or logs.

### Tests for US3
- [ ] T032 [P] [US3] Backend privacy test `backend/tests/privacy/test_session_assistant_privacy.py`: prompt context (captured via fake provider) contains no athlete id/name; logs contain counts only; `ai_log_prompts` respected.
- [ ] T033 [P] [US3] Backend negative tests in `test_session_assistant.py`: parent → 403; AI disabled → 503; malformed JSON → 422; timeout → 503 (assert neutral español `detail`).
- [ ] T034 [P] [US3] Backend guardrail test in `test_session_assistant_use_case.py`: a fixture with a prohibited phrase (supplement / cadence <60 / power-meter <13) is scrubbed or raises `LLMSchemaError`.
- [ ] T035 [P] [US3] Frontend test `SessionAssistantPanel.test.tsx` (fallback): 503 shows "no disponible" + "continuar manualmente" (opens empty wizard, no data loss); timeout shows "pensando…"/"iniciando el servidor"; axe = 0 violations.
- [ ] T036 [P] [US3] Frontend test for per-field AI marker in `frontend/src/components/training/session-wizard/StepGeneral.test.tsx`: AI-seeded fields show marker; editing a field clears its marker.

### Implementation for US3
- [ ] T037 [US3] Wire guardrail scrubbing of every coach-visible string in both use cases and structural validators (counts, duration, session_kind, español) — depends on T020, T021.
- [ ] T038 [US3] Add error mapping in `backend/app/routers/session_assistant.py`: `asyncio.wait_for(ai_timeout_seconds)` → `SessionAssistantLLMTimeout`→503; `LLMSchemaError`→422; `settings.ai_enabled` false / Fake provider → 503 neutral message — depends on T022.
- [ ] T039 [P] [US3] Frontend fallback states in `SessionAssistantPanel.tsx`: loading ("pensando…"), cold-start ("iniciando el servidor"), 503/422 recoverable error + "continuar manualmente" → empty wizard — depends on T024.
- [ ] T040 [P] [US3] Implement `frontend/src/components/training/session-wizard/ai-assistant/aiSeededFields.ts` + per-field marker in `StepGeneral.tsx`: track AI-seeded field set, clear on `dirtyFields` change (FR-019) — depends on T026.

**Checkpoint**: Feature safe, private, and resilient; all acceptance scenarios covered.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T041 [P] Run `data-privacy-guard` audit over the feature (context builder, prompts, router, logs); resolve any finding before deploy.
- [ ] T042 [P] Lint/type gates green: `cd backend && ruff check . && mypy app/services/ai app/routers/session_assistant.py`; `cd frontend && npx tsc --noEmit && npx eslint src/...`.
- [ ] T043 [P] Docs: add `docs/09-training-planning/session-ai-assistant.md` (flow, privacy contract, endpoints) and update `docs/README.md`; add a CLAUDE.md implementation-status block for feature 006.
- [ ] T044 Full targeted suites green: backend `pytest tests/services/ai tests/routers/test_session_assistant.py tests/privacy/test_session_assistant_privacy.py tests/services/training/test_session_assistant_context.py -q`; frontend `npx vitest run src/components/training/session-wizard -q` (a11y 0 violations).
- [ ] T045 Update `specs/006-ai-session-clarify-draft/checklists/requirements.md` if any scope drifted; confirm spec ↔ implementation consistency for `/speckit-analyze`.

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** → **US1 (P3)** → **US2 (P4)** → **US3 (P5)** → **Polish (P6)**.
- US2 and US3 build on US1's use-case/endpoint bodies but are independently testable slices.
- Hard dependencies: T009 before T020/T021; T011 before T022; T014 before T026/T031; T026 before T040.

## Parallel Execution Examples
- Foundational: T005, T006, T007 (prompts/registry) ∥ T012, T013, T014, T016 (frontend scaffold).
- US1 tests: T017, T018, T019 in parallel before their implementations.
- US3: T032, T033, T034 (backend) ∥ T035, T036 (frontend) in parallel.

## Implementation Strategy
- **MVP = Phase 1 + 2 + US1 (T001–T026)**: a working clarify→draft→prefill flow with tests.
- Then layer **US2** (context smarts) and **US3** (safety/fallback/privacy), each shippable.
- Polish (P6) gates deploy: privacy audit + lint/type + docs + full suite.

**Total tasks**: 45 — Setup 3, Foundational 13, US1 10, US2 5, US3 9, Polish 5.
