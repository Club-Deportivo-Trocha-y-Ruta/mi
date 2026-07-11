# Tasks: Structured Interval Training with Strava Correlation

**Input**: Design documents from `/specs/026-structured-interval-training/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: INCLUDED — Constitution Principle II (Testing NON-NEGOTIABLE) mandates happy + negative paths per router/service, jest-axe on new page/dialog components, and explicit privacy invariants. Write each story's tests first; confirm they fail before implementing.

**Organization**: Tasks grouped by user story (US1–US4 from spec.md) for independent implementation and testing.

**Agent assignment**: Per user request, every task carries a suggested specialized agent (from `.claude/agents/`) and model tier — `sonnet` default; `haiku` for mechanical/boilerplate; `fable` for the highest-judgment design tasks (matching engine, guardrail semantics).

## Format: `[ID] [P?] [Story] Description (Agente: X · Modelo: y)`

- **[P]**: parallelizable (different files, no pending dependencies)
- **[Story]**: US1–US4 traceability

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Models, migration, and schema surface every story depends on.

- [x] T001 [P] Create `backend/app/models/interval_structure.py` — enums `IntervalBlockType` (warmup/work/recovery/cooldown), `HRZone` (Z1–Z5), models `IntervalStructure`, `IntervalStructureBlock`, `IntervalTemplate`, `IntervalTemplateBlock` per data-model.md §1–4 (reuse `AgeBand` from `technique_exercise`, `values_callable` on all enums, UNIQUE constraints, relationships incl. `TrainingSession.interval_structure` back-ref in `backend/app/models/training_session.py`) (Agente: database-architect · Modelo: sonnet)
- [x] T002 [P] Create `backend/app/models/strava_activity_lap.py` — `StravaActivityLap` (no geo/name/cadence/watts columns, UNIQUE `(strava_activity_id, lap_index)`) + `IntervalMatchResult` (UNIQUE `(structure_id, strava_activity_id)`, `result_json`, `engine_version`, `triggered_by` enum `MatchTrigger`) per data-model.md §5–6, with the privacy doctrine docstring mirroring `strava_activity.py` (Agente: database-architect · Modelo: sonnet)
- [x] T003 Create Alembic migration `backend/alembic/versions/b5c6d7e8f9a0_interval_training.py` — `down_revision = "a4b5c6d7e8f9"`; creates the 6 tables + indexes/uniques; **reuses** existing `ageband` enum (does NOT create/drop it — same rule as migration `a7b8c9d0e1f2`); creates `intervalblocktype`, `hrzone`, `matchtrigger` enums; verify `alembic upgrade head` + `downgrade -1` round-trip on Docker MySQL (Agente: database-architect · Modelo: sonnet)
- [x] T004 [P] Create `backend/app/schemas/intervals.py` — `BlockIn/Out`, `StructureCreate/Update/Out` (incl. `age_gate_confirmed`, `total_planned_duration_s`), `TemplateCreate/Update/Out`, `TemplateAttachIn`, `MatchBlockOut`, `MatchDetailOut` (statuses `computed|no_activity|computing|failed`), `RecalculateIn/Out`, `LapOut` per contracts/api.md; result_json validated by a `MatchResultPayload` model before persist (Agente: fastapi-architect · Modelo: sonnet)
- [x] T005 [P] Create `frontend/src/types/intervals.types.ts` + `frontend/src/schemas/intervals.schema.ts` — Zod: cadence `min(60)` with localized message, `duration_s > 0`, repeat group consistency (`repeat_count >= 2`, identical within group), band enum; types mirror contracts (Agente: react-ui-engineer · Modelo: haiku)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Router shell, Strava laps capability, frontend API layer — no story can ship without these.

**⚠️ CRITICAL**: Complete before any user story phase.

- [x] T006 Create `backend/app/routers/intervals.py` skeleton — prefix `/api/intervals`, every route `Depends(require_role([UserRole.admin, UserRole.coach]))` + club scoping helper via `user_club_role` (copy `routers/strength.py` `_coach_or_admin`/`_coach_club_id` pattern); register router in `backend/app/main.py`; add `services/intervals/__init__.py` (Agente: fastapi-architect · Modelo: sonnet)
- [x] T007 [P] Add `get_activity_laps(activity_id: int) -> list[dict]` to `backend/app/services/strava/client.py` — `GET /activities/{id}/laps` through existing `_request()` (token refresh, 429 → `StravaRateLimited`, 404 → `StravaNotFoundError`); unit test with stubbed httpx in `backend/tests/services/test_strava_client_laps.py` (Agente: integration-engineer · Modelo: sonnet)
- [x] T008 [P] Create `frontend/src/api/intervals.ts` (API fns incl. `extractAgeGateError` mirroring `extractAgeBandGuardrail`, blob fn for instructivo) + `frontend/src/hooks/intervals/useIntervals.ts` (query-key factory `intervalKeys`, query/mutation hooks with invalidation per `api/strength.ts`/`useStrength.ts` conventions) (Agente: react-ui-engineer · Modelo: sonnet)

**Checkpoint**: Foundation ready — user stories can proceed (US1 first; US2–US4 parallelizable after US1).

---

## Phase 3: User Story 1 — Design an interval structure for a session (Priority: P1) 🎯 MVP

**Goal**: Coach builds warmup / repeatable work-recovery groups / cooldown with duration+zone+cadence, attached 1:1 to a session, with cadence and age-gate guardrails enforced server-side.

**Independent Test**: Create session → attach structure with one repeated group → save → reopen → persisted. Cadence 55 → rejected. Z3 on 10-12 → hard-blocked. Z1–Z2 on 10-12 → requires recorded confirmation. No Strava involved (quickstart Scenario 1).

### Tests for User Story 1 (write first, must fail)

- [x] T009 [P] [US1] Create `backend/tests/intervals/conftest.py` (club/coach/parent/session fixtures, mirrors `tests/strength/conftest.py`) + `backend/tests/intervals/test_structures.py` — create/get/put/delete happy paths, 1:1 conflict 409, repeat-group persistence, `invalid_repeat_group` 422, parent 403 (Agente: qa-engineer · Modelo: sonnet)
- [x] T010 [P] [US1] Create `backend/tests/intervals/test_guardrail.py` — `cadence_below_minimum` 422 any band incl. templates; `age_gate_z3_blocked` 422 hard (structure + template-save + attach paths); `age_gate_confirmation_required` 422 then success with `age_gate_confirmed=true` persisting user+timestamp; SC-002/SC-003 exhaustive (Agente: qa-engineer · Modelo: sonnet)

### Implementation for User Story 1

- [x] T011 [US1] Create `backend/app/services/intervals/structures.py` — CRUD + flattening helper `flatten_blocks()` (shared with matching/instructivo) + validation per research D2/D3 and contracts error codes; docstring with inputs/outputs/side effects (Constitution I) (Agente: fastapi-architect · Modelo: fable)
- [x] T012 [US1] Implement structure endpoints in `backend/app/routers/intervals.py` — `POST /structures`, `GET /sessions/{id}/structure`, `PUT /structures/{id}`, `DELETE /structures/{id}` per contracts/api.md; wire T009/T010 green (Agente: fastapi-architect · Modelo: sonnet)
- [x] T013 [P] [US1] Create `frontend/src/components/intervals/StructureEditor.tsx` + `BlockRow.tsx` — RHF+Zod, block list with add/remove/reorder, repeat-group UI (agrupar ×N), band selector, inline localized errors, 48px targets, español neutro copy (Agente: react-ui-engineer · Modelo: sonnet)
- [x] T014 [P] [US1] Create `frontend/src/components/intervals/AgeGateDialog.tsx` — mirrors `AgeBandGuardrailDialog.tsx` (focus trap, Escape, explicit close); on 422 `age_gate_confirmation_required` → confirm → resubmit `age_gate_confirmed: true`; hard `age_gate_z3_blocked` renders blocking explanation, no override CTA (Agente: react-ui-engineer · Modelo: sonnet)
- [x] T015 [US1] Integrate section "Estructura de intervalos" into `frontend/src/routes/training/SessionDetailPage.tsx` — empty/create state, view/edit, delete with confirm; lazy-load the editor (Agente: react-ui-engineer · Modelo: sonnet)
- [x] T016 [US1] Create `frontend/src/components/intervals/__tests__/StructureEditor.test.tsx` + `AgeGateDialog.test.tsx` — branching logic, error mapping, resubmit flow, jest-axe zero violations on the dialog and editor (Agente: qa-engineer · Modelo: sonnet)

**Checkpoint**: US1 fully functional standalone — richer session planning even with Strava disabled.

---

## Phase 4: User Story 2 — Plan-vs-actual compliance after Strava sync (Priority: P2)

**Goal**: Linking an activity to a structured session auto-computes lap↔block comparison (deferred); coach-only detail view with per-block compliance; manual recalculation.

**Independent Test**: Structure + linked activity with known laps → comparison appears with no coach action; fewer/more/zero laps degrade gracefully; edit structure → recalculate updates; parent gets 403 (quickstart Scenario 2).

### Tests for User Story 2 (write first, must fail)

- [x] T017 [P] [US2] Create `backend/tests/intervals/test_matching.py` — pure-engine unit tests: repeat-group flattening, `plan[i]↔lap[i]` pairing, ±30% boundary cases, `<10s` lap discard, fewer/more/zero laps → `sin_dato`/`extra`, `result_json` shape + summary counts (FR-016 exhaustive) (Agente: qa-engineer · Modelo: sonnet)
- [x] T018 [P] [US2] Create `backend/tests/intervals/test_match_flow.py` — link dispatch trigger (stubbed `get_activity_laps` + dispatcher), structure-change trigger, `GET /sessions/{id}/match` statuses (`computed|no_activity|computing|failed`), `POST /structures/{id}/recalculate` 202/409, laps replace-on-refetch, unlink deletes match row but preserves laps (Agente: qa-engineer · Modelo: sonnet)
- [x] T019 [P] [US2] Create `backend/tests/privacy/test_laps_privacy.py` — model has no geo/name/cadence/watts attrs; runner allow-list drops unexpected raw fields; match responses + `result_json` contain no coordinates; numeric-only log assertions (SC-007) (Agente: data-privacy-guard · Modelo: sonnet)

### Implementation for User Story 2

- [x] T020 [US2] Create `backend/app/services/intervals/matching.py` — pure function `compute_match(flattened_blocks, laps) -> MatchResultPayload` per research D5 (tolerance constant, discard rule, statuses, extra laps, engine `ENGINE_VERSION = 1`); no I/O, fully deterministic (Agente: fastapi-architect · Modelo: fable)
- [x] T021 [US2] Create `backend/app/services/intervals/match_runner.py` — deferred job: fetch laps via `get_activity_laps`, allow-list + replace-persist `StravaActivityLap` rows, compute, upsert `IntervalMatchResult` (`triggered_by`); own `AsyncSessionLocal` + commit (webhook dispatcher pattern); failure → `failed` state, numeric-only logs (Agente: integration-engineer · Modelo: sonnet)
- [x] T022 [US2] Wire triggers — edit `backend/app/routers/activities.py::link_activity` (dispatch on link when session has structure; delete match row on unlink) and `services/intervals/structures.py` (dispatch on create/update when a linked activity exists), both via `TaskDispatcher` (Agente: integration-engineer · Modelo: sonnet)
- [x] T023 [US2] Implement match endpoints in `backend/app/routers/intervals.py` — `GET /sessions/{id}/match`, `POST /structures/{id}/recalculate` per contracts; laps only ever serialized inside match detail (Agente: fastapi-architect · Modelo: sonnet)
- [x] T024 [US2] Create `frontend/src/components/intervals/PlanVsActualTable.tsx` + `frontend/src/routes/training/ActivityMatchPage.tsx` (lazy) + route `/training/sessions/:id/activity-match/:activityId` in `App.tsx` under `ProtectedRoute allowedRoles={[coach, admin]}`; badge semantics verde/ámbar/gris, states no_activity/computing/failed with retry, link from SessionDetailPage activity section (Agente: react-ui-engineer · Modelo: sonnet)
- [x] T025 [US2] Create `frontend/src/components/intervals/__tests__/PlanVsActualTable.test.tsx` + `ActivityMatchPage.test.tsx` — all four states, mismatch rendering, jest-axe on the page (Agente: qa-engineer · Modelo: sonnet)

**Checkpoint**: Core value proposition live — objective adherence evidence, coach-only.

---

## Phase 5: User Story 3 — Parent instructivo PDF (Priority: P3)

**Goal**: Brand-specific (iGPSport/Magene/Garmin) downloadable PDF from the structure; manual download only.

**Independent Test**: Structure → pick brand → PDF downloads with every block + brand steps + auto-lap warning; no structure → 404/disabled; no email/QR anywhere (quickstart Scenario 3).

### Tests for User Story 3 (write first, must fail)

- [x] T026 [P] [US3] Create `backend/tests/intervals/test_instructivo_pdf.py` — 200 + `application/pdf` + attachment filename per brand; rendered HTML contains flattened blocks, brand-specific steps, "desactivá la vuelta automática" in all three; 404 no structure; 422 unknown brand; parent 403 (PDF byte render needs pango/glib — assert via HTML context where env lacks it, same caveat as feature 024) (Agente: qa-engineer · Modelo: sonnet)

### Implementation for User Story 3

- [x] T027 [P] [US3] Create `backend/templates/documents/pdf/session_instructivo.html` — extends `base/layout.html` + `_brand_tokens.html`; session header, flattened block table (orden/tipo/duración/zona/cadencia), per-brand conditional steps per research D8, auto-lap warning block; español neutro; register new `DocumentTemplate` enum value + spec in the template registry (Agente: technical-writer · Modelo: sonnet)
- [x] T028 [US3] Create `backend/app/services/intervals/instructivo_pdf.py` (wrapper mirroring `athlete_newsletter_pdf.py`, reuses `flatten_blocks()`) + endpoint `GET /sessions/{id}/instructivo?brand=` in `routers/intervals.py` returning in-memory `Response` attachment per contracts (Agente: fastapi-architect · Modelo: sonnet)
- [x] T029 [US3] Create `frontend/src/components/intervals/InstructivoDownloadButton.tsx` — brand select (3 marcas), blob download via `triggerBlobDownload`, disabled sin estructura, loading/error states; integrate into SessionDetailPage section; test `__tests__/InstructivoDownloadButton.test.tsx` incl. jest-axe (Agente: react-ui-engineer · Modelo: sonnet)

**Checkpoint**: Plan actionable in the real world without device push.

---

## Phase 6: User Story 4 — Template library (Priority: P4)

**Goal**: Save structures as tagged templates (banda/fase/proximidad); browse/filter; copy-on-attach.

**Independent Test**: Save template → filter by each tag → attach to second session → blocks cloned; edit template afterward → sessions untouched (quickstart Scenario 4).

### Tests for User Story 4 (write first, must fail)

- [x] T030 [P] [US4] Create `backend/tests/intervals/test_templates.py` — CRUD + archive; tag filters; attach clones (independent copy proven by mutating both sides); Z3+ on 10-12 template rejected at save; attach onto 10-12 requires confirmation; 409 session already structured; parent 403 (Agente: qa-engineer · Modelo: sonnet)

### Implementation for User Story 4

- [x] T031 [US4] Create `backend/app/services/intervals/templates.py` — CRUD + `attach_template()` copy-on-attach reusing the full structure validation from `structures.py` (research D3, spec edge case) (Agente: fastapi-architect · Modelo: sonnet)
- [x] T032 [US4] Implement template endpoints in `backend/app/routers/intervals.py` — `POST/GET/PUT /templates`, `PATCH /templates/{id}/archive`, `POST /templates/{id}/attach` per contracts; list with `selectinload` on blocks (Agente: fastapi-architect · Modelo: sonnet)
- [x] T033 [US4] Create `frontend/src/components/intervals/TemplatePicker.tsx` (browse/filter by 3 tags + attach w/ AgeGateDialog reuse) + `frontend/src/routes/intervals/TemplateLibraryPage.tsx` (lazy route `/intervals/templates`, coach/admin) + "Guardar como plantilla" action in StructureEditor (Agente: react-ui-engineer · Modelo: sonnet)
- [x] T034 [US4] Create `frontend/src/components/intervals/__tests__/TemplatePicker.test.tsx` + `TemplateLibraryPage.test.tsx` — filters, attach flow incl. confirmation path, jest-axe on the page (Agente: qa-engineer · Modelo: sonnet)

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T035 [P] Run `data-privacy-guard` audit over the full feature surface (models, runner, responses, logs, PDF output) — mandatory constitution gate for athlete-linked data; fix findings (Agente: data-privacy-guard · Modelo: fable)
- [x] T036 [P] Add query-count/eager-load assertions for structure+template list endpoints in `backend/tests/intervals/test_perf_queries.py` (mirrors `tests/strength/test_perf_queries.py`; Constitution IV N+1 rule) (Agente: performance-engineer · Modelo: sonnet)
- [ ] T037 Execute quickstart.md end-to-end on Docker (all 4 scenarios + privacy audit section) + full `pytest` / `vitest` regression; verify new lazy routes stay ≤150 KB gzip (`npm run build` output) (Agente: qa-engineer · Modelo: sonnet)
- [x] T038 [P] Update `docs/implementation-status.md` + add feature row to `CLAUDE.md` status table (deploy pending note: run migration `b5c6d7e8f9a0` on Render) (Agente: technical-writer · Modelo: haiku)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Ph1)**: none — T001/T002/T004/T005 parallel; T003 after T001+T002
- **Foundational (Ph2)**: after Setup — T006/T007/T008 parallel; **blocks all stories**
- **US1 (Ph3)**: after Ph2 — blocks US2/US3/US4 only at the service-reuse points noted below
- **US2 (Ph4)**: needs T011 (`flatten_blocks`) + T007; otherwise independent of US3/US4
- **US3 (Ph5)**: needs T011 (`flatten_blocks`); independent of US2/US4
- **US4 (Ph6)**: needs T011 (validation reuse); independent of US2/US3
- **Polish (Ph7)**: after desired stories complete

### Key task-level dependencies

- T003 ← T001, T002 · T011 ← T004, T009, T010 · T012 ← T011 · T020 ← T017 · T021 ← T020, T007 · T022 ← T021 · T023 ← T021 · T028 ← T027, T011 · T031 ← T011, T030 · T024 ← T023, T008 · T033 ← T032, T008

### Parallel Opportunities

- Ph1: T001 ∥ T002 ∥ T004 ∥ T005 → then T003
- Ph2: T006 ∥ T007 ∥ T008
- After T011 lands: **US2, US3, US4 backend tracks can run in parallel** (different files); frontend tracks parallel per story after T008
- Test-first tasks within each story ([P] pairs) run together
- Ph7: T035 ∥ T036 ∥ T038

## Parallel Example: after Foundational + T011

```bash
# Three specialized agents in parallel, one story each:
Task (fastapi-architect/fable):  "T020 matching.py pure engine"
Task (technical-writer/sonnet):  "T027 session_instructivo.html template"
Task (fastapi-architect/sonnet): "T031 templates.py copy-on-attach"
```

## Implementation Strategy

**MVP = Phase 1 + 2 + US1** (T001–T016): coach designs guarded interval structures — already valuable with Strava off. **STOP & VALIDATE** with quickstart Scenario 1, then increments: US2 (core value: matching) → US3 (instructivo) → US4 (templates) → Polish. Each checkpoint independently deployable; migration ships with MVP.

## Notes

- Every task above follows checklist format: checkbox + ID + [P]? + [Story]? + file path + (Agente · Modelo)
- Commit per task or logical group (Conventional Commits, descripción en español)
- Constitution gates recap: tests per surface (II), español neutro copy (III), deferred Strava call + selectinload + lazy routes (IV), no-geo laps + numeric logs + privacy audit (Ley 1581)
