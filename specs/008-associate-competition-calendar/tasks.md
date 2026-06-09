---
description: "Task list for 008-associate-competition-calendar"
---

# Tasks: One-click associate a competition to the calendar

**Input**: Design documents from `/specs/008-associate-competition-calendar/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/create-calendar-event-for-race-event.md, quickstart.md

**Tests**: INCLUDED — the project Constitution (Principle II, NON-NEGOTIABLE) requires backend `pytest` and frontend `vitest`/`jest-axe` coverage for routers, services, permissions, and branching UI. Test tasks are therefore mandatory here even though the spec did not request TDD.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 (one-click associate, P1) or US2 (edit details first, P2)
- Web app paths: `backend/`, `frontend/`

## Path Conventions

Web application. Backend under `backend/app/**` + `backend/tests/**`; frontend under `frontend/src/**`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project, dependency, or migration. Verify the ground truth the design relies on.

- [X] T001 Confirm `services/race/calendar_sync.py::create_linked_calendar_event` builds a valid `competition` `CalendarEvent` (title, location, `event_data` with `city`/`race_category`/`is_departmental`, `all_club` audience, both FK sides) and currently hardcodes start 07:00 + 5h, in `backend/app/services/race/calendar_sync.py`. Record the exact signature and `event_data` construction for reuse.
- [X] T002 Confirm there is no existing migration touching `race_events`/`calendar_events` needed (this feature adds none) and that `has_calendar_event` is derived in `backend/app/routers/race_events.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend the shared creation service so the US1 endpoint can produce an all-day event without forking logic. Blocks US1.

- [X] T003 Add an `all_day: bool = False` parameter to `create_linked_calendar_event` in `backend/app/services/race/calendar_sync.py`. When `True`: set `all_day=True`, `start_at = event_date` 00:00 and `end_at = event_date` end-of-day in `America/Bogota`; when `False`: preserve current 07:00 + 5h behavior. Update the function docstring (inputs/outputs/side effects) per Constitution Principle I.
- [X] T004 [P] Add/extend service test `backend/tests/services/test_calendar_sync_all_day.py`: assert `all_day=True` yields an all-day event bounding `event_date`; assert default (`all_day=False`) still yields 07:00 + 5h (regression for the create-competition flow).

**Checkpoint**: `create_linked_calendar_event(..., all_day=True)` works and the existing flow is unchanged.

---

## Phase 3: User Story 1 — One-click associate (Priority: P1) 🎯 MVP

**Goal**: From a competition with no linked calendar event, a coach creates and links an all-day calendar event in a single action, reusing the válida's name/date/location, with zero re-entry.

**Independent Test**: Coach opens an unlinked válida, clicks the one-click action → all-day event created and linked, "En calendario" badge appears, no form shown. (quickstart Scenario A.)

### Backend (US1)

- [X] T005 [US1] Add response schema for the new endpoint in `backend/app/schemas/race_event.py` — reuse/extend `CalendarLinkRead` to `{ race_event_id, calendar_event_id, has_calendar_event: true }` (name it e.g. `CalendarAutoCreateRead`).
- [X] T006 [US1] Add endpoint `POST /api/race-analysis/race-events/{race_event_id}/calendar-event` in `backend/app/routers/race_events.py`, guarded by `require_role([UserRole.coach])` (coach-only per FR-008). Load válida (404 if missing); if `calendar_event_id` already set → `409`; else delegate to `create_linked_calendar_event(db, race_event, user, all_day=True)`, commit, return `201` with the Phase-3 schema.
- [X] T007 [P] [US1] Backend tests in `backend/tests/routers/test_race_event_calendar_autocreate.py` covering contract scenarios: happy path (201, all-day, title/location match, both FKs set, `has_calendar_event` true); already-linked → 409 (no duplicate); non-coach (admin & parent) → 403; unknown id → 404.

### Frontend (US1)

- [X] T008 [P] [US1] Add `createCalendarEventForRaceEvent(raceEventId): Promise<...>` to `frontend/src/api/raceEvents.ts` (POST the new endpoint) and the response type to `frontend/src/types/raceEvents.types.ts`.
- [X] T009 [US1] Add `useCreateCalendarEventForRaceEvent()` mutation hook in `frontend/src/hooks/race/useRaceEvents.ts` that invalidates the `useRaceEvent(id)` query on success so `has_calendar_event` flips.
- [X] T010 [US1] In `frontend/src/routes/competitions/CompetitionDetailPage.tsx`, replace the plain "Asociar a calendario" `Link` with a primary one-click action wired to the mutation: disabled/loading state during the request, success toast then badge "En calendario" appears and the action disappears, error toast (no raw exception text) with retry on failure. Keep the action hidden when `has_calendar_event` or cancelled. Copy in español neutro; ≥48×48 px target.
- [X] T011 [P] [US1] Frontend tests in `frontend/src/routes/competitions/__tests__/CompetitionDetailPage.associate.test.tsx`: one-click fires the new API and refetches; success hides the action and shows the badge; failure shows an error toast and keeps the action; `jest-axe` passes on the page.

**Checkpoint**: US1 is independently shippable — solves the coach's stated pain on its own.

---

## Phase 4: User Story 2 — Edit details first (Priority: P2)

**Goal**: A coach can open the calendar event form pre-filled with the válida's name/date/location (all-day on, válida preselected) to review/adjust before saving.

**Independent Test**: From an unlinked válida, choose "Editar detalles primero" → form opens pre-filled; edit title and save → event created and linked with the edit. (quickstart Scenario B.)

- [X] T012 [US2] Extend `frontend/src/components/calendar/EventForm.tsx` to accept prefill props `prefillTitle?`, `prefillStartDate?`, `prefillLocation?`, and `prefillAllDay?`, seeding the corresponding RHF defaults (in addition to the existing `prefillRaceEventId`). Do not alter behavior when props are absent.
- [X] T013 [US2] In `frontend/src/routes/calendar/EventFormPage.tsx`, when `prefillRaceEventId` is present, fetch the válida via `useRaceEvent` and pass `prefillTitle=name`, `prefillStartDate=event_date`, `prefillLocation=location`, `prefillAllDay=true` into `EventForm`. Handle loading/error states (no unbounded spinner).
- [X] T014 [US2] In `frontend/src/routes/competitions/CompetitionDetailPage.tsx`, add the secondary "Editar detalles primero" affordance alongside the one-click action (e.g., split button / dropdown using existing shadcn primitives) that navigates to `/calendar/events/new?race_event_id=N`. Ensure focus handling and Escape-dismiss if a menu/dialog is used.
- [X] T015 [P] [US2] Frontend tests in `frontend/src/routes/calendar/__tests__/EventFormPage.prefill.test.tsx`: with `race_event_id` query param, the form renders pre-filled title/date/location, event type Competencia, all-day on; submitting persists; `jest-axe` passes.

**Checkpoint**: US2 enhances US1 without changing the one-click path.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T016 [P] Run `backend/` `ruff` + `mypy` and `frontend/` `eslint` + `tsc --noEmit`; fix any new findings (Constitution Principle I gate).
- [X] T017 [P] Update `docs/implementation-status.md` and the CLAUDE.md status table row to record feature 008 as built (deploy pending), keeping the SPECKIT block intact.
- [ ] T018 Execute `specs/008-associate-competition-calendar/quickstart.md` Scenarios A–D against the dev stack as the coach; confirm SC-001..SC-005. _(Manual step — not run by the implementation workflow; automated pytest/vitest coverage passed.)_

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational, T003-T004)** → **Phase 3 (US1)** → **Phase 4 (US2)** → **Phase 5 (Polish)**.
- US1 depends on T003 (the `all_day` service param). US2 is independent of the US1 backend endpoint (it uses the existing calendar create), but T014 shares the detail-page file with T010, so sequence T010 before T014.
- Backend (T005-T007) and frontend (T008-T011) within US1 can proceed in parallel once T003 lands; T008→T009→T010 are sequential (api → hook → page), T007 and T011 are parallel test tasks.

## Parallel Opportunities

- T004 ∥ (after T003).
- US1: T007 ∥ T008 (then T009 → T010), T011 after T010.
- US2: T012 → T013, T014 after T010; T015 after T013.
- Polish: T016 ∥ T017 (T018 last).

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**. This alone resolves the coach's pain (one-click, zero re-entry) and is independently shippable.
- **Increment 2 = Phase 4 (US2)** adds the "edit details first" escape hatch.
- **Increment 3 = Phase 5** polish, docs, and manual verification before deploy.
