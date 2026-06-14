# Tasks: Coach Per-Athlete Qualitative Notes on Competition Results

**Feature**: 013-race-result-athlete-notes | **Branch**: `claude/athlete-notes-race-results-zjdesm`
**Input**: spec.md, plan.md, research.md, data-model.md, contracts/coach-note.md, quickstart.md

Each task is annotated with the **responsible specialized agent** in brackets after the labels. Tests are
included because the project constitution makes them NON-NEGOTIABLE (incl. privacy-invariant tests for
minors' data).

**Agent legend**: `[database-architect]` `[fastapi-architect]` `[integration-engineer]`
`[react-ui-engineer]` `[qa-engineer]` `[data-privacy-guard]`

---

## Phase 1: Setup

- [ ] T001 Confirm working branch `claude/athlete-notes-race-results-zjdesm`, backend venv, and frontend deps; baseline `cd backend && pytest -q` and `cd frontend && npx vitest run` are green before changes. {no agent — orchestrator}

## Phase 2: Foundational (BLOCKING — all user stories depend on persistence)

- [ ] T002 [database-architect] Add `coach_note: Mapped[Optional[str]]` (`String(500)`), `coach_note_author_id: Mapped[Optional[int]]` (FK `users.id`, `ondelete="SET NULL"`), and `coach_note_updated_at: Mapped[Optional[datetime]]` (plus optional read-only `coach_note_author` relationship) to `class RaceResult` in `backend/app/models/race_result.py`. Leave the legacy importer `notes` column untouched.
- [ ] T003 [database-architect] Generate Alembic migration in `backend/alembic/versions/` revising head `f9a0b1c2d3e4`: add the three columns + FK `fk_race_results_coach_note_author`; downgrade drops FK then columns; no data backfill.
- [ ] T004 [database-architect] Run `cd backend && alembic upgrade head` against a scratch DB and confirm columns/FK exist and `alembic downgrade -1` is clean.

**Checkpoint**: schema ready; the importer `notes` column is unchanged.

---

## Phase 3: User Story 1 — Record a qualitative observation per athlete (Priority: P1) 🎯 MVP

**Goal**: Coach/admin can add/edit/clear a short free-text note for a club rider in a válida, from the
Results view, persisted to that rider+válida.

**Independent test**: Open a válida's results, write a note on one club rider, save, confirm it persists
tied to that rider+válida and is editable; parent role sees no affordance.

### Backend (US1)

- [ ] T005 [P] [US1] [fastapi-architect] In `backend/app/schemas/race_results.py`: add `result_id: int`, `coach_note: str | None = None`, `coach_note_updated_at: datetime | None = None` to `ResultRow`; add `CoachNoteUpdate` schema with a `field_validator` that strips and enforces `1 ≤ len ≤ 500` (reject whitespace-only).
- [ ] T006 [US1] [fastapi-architect] In `backend/app/routers/race_events.py` add `PUT /race-analysis/race-results/{result_id}/coach-note` (mirror `update_race_event_conditions`): load row (404 if missing/soft-deleted), reject when `athlete_id is None` (4xx), set `coach_note`/`coach_note_author_id=current_user.id`/`coach_note_updated_at=now()`, commit, return `ResultRow`. Guard with `require_role([UserRole.coach, UserRole.admin])`.
- [ ] T007 [US1] [fastapi-architect] In the same router add `DELETE /race-analysis/race-results/{result_id}/coach-note`: null the three fields, commit, return `ResultRow`; same RBAC guard; idempotent when already absent.
- [ ] T008 [US1] [fastapi-architect] Ensure the results-row builder used by `GET .../results` populates `result_id`, `coach_note`, `coach_note_updated_at` so the read path round-trips the new fields.

### Frontend (US1)

- [ ] T009 [P] [US1] [react-ui-engineer] In `frontend/src/types/raceResults.types.ts` add `result_id: number`, `coach_note: string | null`, `coach_note_updated_at: string | null` to `RaceResultRow`.
- [ ] T010 [P] [US1] [react-ui-engineer] In `frontend/src/api/raceResults.ts` add `setResultCoachNote(resultId, { coach_note }, opts)` (PUT) and `clearResultCoachNote(resultId, opts)` (DELETE) per `contracts/coach-note.md`.
- [ ] T011 [US1] [react-ui-engineer] In `frontend/src/hooks/race/useRaceResults.ts` add `useSetResultCoachNote` and `useClearResultCoachNote` (`useMutation`) with optimistic `onMutate` (`cancelQueries` + snapshot + `setQueryData` patching the row), `onError` rollback, and `onSettled` returning `invalidateQueries(raceResultsKeys.byEventFiltered)`.
- [ ] T012 [US1] [react-ui-engineer] Create `frontend/src/components/race/EditResultNoteDialog.tsx` (mirror `EditConditionsDialog.tsx`): shadcn `Sheet`/Dialog + `Textarea`, React Hook Form + `zodResolver`, Zod schema (strip, `max(500)`, localized español messages), explicit saving/error/save-failure states, focus trap + Escape dismiss, 48×48px targets.
- [ ] T013 [US1] [react-ui-engineer] Wire the note affordance into `frontend/src/components/competitions/results/ResultsTable.tsx` for club rows (coach/admin only): add/edit icon opening `EditResultNoteDialog`; hidden entirely for parent role.

### Tests (US1)

- [ ] T014 [P] [US1] [qa-engineer] Create `backend/tests/routers/test_race_result_coach_note.py` (mirror `test_race_results_read.py`): PUT sets (200 + subsequent GET shows note), PUT replaces (no duplicate), DELETE clears; 422 empty/whitespace + >500; 403 parent and athlete; 4xx note on non-club row (`athlete_id is None`); 404 missing/soft-deleted row.
- [ ] T015 [P] [US1] [qa-engineer] Create `frontend/src/components/race/__tests__/EditResultNoteDialog.test.tsx` (mirror `EditConditionsDialog.test.tsx`): renders for coach, hidden for parent; Zod localized validation (empty / >500); optimistic update + rollback on mutation failure; `jest-axe` zero violations on the dialog.

**Checkpoint**: US1 independently shippable — notes can be captured/edited/cleared from the results view.

---

## Phase 4: User Story 2 — Review past notes when reopening a válida (Priority: P2)

**Goal**: Reopening a past válida shows each rider's saved note; edits/deletes persist.

**Independent test**: Write notes for two riders, navigate away, reopen the válida, verify both notes
appear with their riders; edit one and delete the other, reopen, verify state.

- [ ] T016 [US2] [react-ui-engineer] In `ResultsTable.tsx`, render the existing `coach_note` per club row (truncated preview + tooltip/expand) and prefill `EditResultNoteDialog` with the current note text when editing; show the add affordance when `coach_note` is null (no placeholder noise).
- [ ] T017 [P] [US2] [qa-engineer] Backend test: persistence across reopen — set note, re-fetch `GET .../results`, assert note present; edit replaces; DELETE leaves row with `coach_note=null` and other fields intact. (Add to `test_race_result_coach_note.py`.)
- [ ] T018 [P] [US2] [qa-engineer] Frontend test: `ResultsTable` shows saved note for coach on re-render, prefills dialog on edit, shows add affordance when null, hidden for parent.

**Checkpoint**: US1 + US2 deliver the full coach observation log.

---

## Phase 5: User Story 3 — Notes enrich the per-athlete insight and coach-only chat (Priority: P2)

**Goal**: The (scrubbed) note feeds BOTH the automatic per-athlete/per-válida insight AND the coach-only
competition chat; absent note → unchanged behaviour.

**Independent test**: Write a distinctive note, run the rider's insight and ask the competition chat about
that rider — both reflect the observation; remove the note — both revert to numbers-only; no real name
ever appears in prompts/logs.

- [ ] T019 [US3] [integration-engineer] In `backend/app/services/race/ai/nodes/load_race_data.py::_serialize_result` add `"coach_note": r.coach_note` to the per-athlete dict (raw at load time).
- [ ] T020 [US3] [integration-engineer] In `backend/app/services/race/ai/nodes/anonymize.py` scrub `coach_note` against the forbidden-real-name list using the same logic as `_scrub_event_conditions` / `load_forbidden_names`; when null, omit. Pseudonymization preserved.
- [ ] T021 [US3] [integration-engineer] In `backend/app/services/race/ai/nodes/analyst_agent.py` include the scrubbed `coach_note` in the per-athlete prompt context (alongside event_conditions/podium); when null, change nothing (FR-009).
- [ ] T022 [US3] [integration-engineer] Extend the coach-only competition chat per-athlete tool (race chat tools) to return the scrubbed `coach_note` so chat answers incorporate it; never the raw text or real names.
- [ ] T023 [P] [US3] [qa-engineer] AI tests (extend `test_race_analysis*.py`): `_serialize_result` includes note when present and omits when absent; analyst prompt + chat tool carry the scrubbed note; null note → context identical to baseline (regression).
- [ ] T024 [US3] [data-privacy-guard] Privacy-invariant audit + tests (extend `test_race_analysis_privacy.py`): note is scrubbed of real names before any prompt; raw note and real names never appear in prompts or logs (`AI_LOG_PROMPTS=false`); `coach_note` appears in zero parent/athlete-facing responses.

**Checkpoint**: All three user stories complete; AI reasons about the "why".

---

## Phase 6: Polish & Cross-Cutting

- [ ] T025 [P] [qa-engineer] Run full gates: `cd backend && ruff check . && mypy app && pytest -q`; `cd frontend && npx tsc --noEmit && npx eslint src && npx vitest run`. Fix any failure (blocker, not follow-up).
- [ ] T026 [P] [fastapi-architect] Update `docs/implementation-status.md` and the CLAUDE.md status table with feature 013 (deploy pending; `AI_MAX_TOKENS`/scrub notes unchanged).
- [ ] T027 Run the `quickstart.md` manual smoke (capture → reopen → insight → chat → clear → parent sees nothing) and record the result. {no agent — orchestrator}

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational, BLOCKING)** → Phases 3-5 (user stories) → Phase 6 (Polish).
- **US1 (P1)** depends only on Foundational; it is the MVP and independently shippable.
- **US2 (P2)** depends on US1 (read embedding + editor exist).
- **US3 (P2)** depends on Foundational (the column) and is otherwise independent of US1/US2 UI — backend AI
  work can proceed in parallel with frontend US1/US2 once T002-T004 land.

### Parallel opportunities

- After Foundational: backend US1 (T005-T008) and frontend US1 (T009-T013) run in parallel (different
  files); test tasks T014/T015 in parallel.
- US3 backend AI (T019-T022, integration-engineer) can run in parallel with frontend US1/US2
  (react-ui-engineer) — disjoint files.
- `[P]`-marked tasks within a phase touch different files and can be dispatched concurrently.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: coach can capture/edit/clear notes from the results view.
- Increment 2: add **US2** (review on reopen) — small frontend + test delta.
- Increment 3: add **US3** (AI insight + chat) — backend AI + privacy audit.
- Each increment is independently testable and shippable.

## Format validation

All tasks use `- [ ] T### [P?] [US#?] [agent] description + file path`. Setup/Foundational/Polish tasks
carry no story label; user-story tasks carry `[US1]`/`[US2]`/`[US3]`.
