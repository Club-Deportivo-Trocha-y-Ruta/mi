# Implementation Plan: One-click associate a competition to the calendar

**Branch**: `008-associate-competition-calendar` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-associate-competition-calendar/spec.md`

## Summary

A coach viewing a competition (`RaceEvent` / Copa Valle válida) with no linked calendar event must be able to put it on the club calendar with **one click**, reusing the competition's existing `name`, `event_date`, and `location` and creating the entry as an **all-day** `CalendarEvent` — with zero manual re-entry. A secondary "edit details first" path opens the existing calendar event form **pre-filled** with those same values for review/adjustment before saving.

Technical approach: the backend already auto-creates a linked competition `CalendarEvent` at válida-creation time via `services/race/calendar_sync.py::create_linked_calendar_event()`. We (1) extend that service to support an all-day event and expose it through a new coach-only endpoint `POST /api/race-analysis/race-events/{id}/calendar-event` that creates-and-links from the válida's own data; (2) replace the frontend "Asociar a calendario" link with a split action — primary one-click call to the new endpoint, secondary "Editar detalles primero" that navigates to the existing `EventForm` now pre-filled with the válida's title/date/location (not just `race_event_id`). No new data model; no migration.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Pydantic v2 (backend); React 19, Vite, shadcn/ui, Tailwind v4, TanStack Query, React Hook Form + Zod (frontend)

**Storage**: MySQL 8.4 (async via aiomysql). Existing tables `race_events` and `calendar_events` — **no schema change, no migration**.

**Testing**: `pytest` + `httpx.AsyncClient` + `aiosqlite` (backend); `vitest` + Testing Library + `jest-axe` (frontend)

**Target Platform**: Web — coach on tablet (primary), desktop. Backend on Render free tier (Oregon).

**Project Type**: Web application (FastAPI backend + React SPA frontend)

**Performance Goals**: One-click associate is a single transactional write → must meet Principle IV write budget (p95 ≤ 1500 ms). No new list/read endpoints, so no N+1 surface introduced.

**Constraints**: Coach-only action (per spec FR-008). All-day event (no start time/duration). Strict 1:1 link must not be duplicated. UI copy in español neutro (Colombia). WCAG 2.1 AA; 48×48 px touch targets.

**Scale/Scope**: ~7 competitions per season. Tiny scale; the value is friction reduction, not throughput.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Maintainability**: PASS. Reuses the existing `calendar_sync` service rather than introducing a parallel creation path (avoids a third copy of competition-event construction). New endpoint and frontend action are named for what they produce (`create_calendar_event_for_race_event`, "Asociar a calendario"). Service function gets a docstring covering the new `all_day` behavior. No new runtime dependency.
- **II. Testing Standards (NON-NEGOTIABLE)**: PASS (planned). Backend: new endpoint gets happy-path (creates all-day linked event) + negative paths (already linked → 409; non-coach → 403; missing date → 4xx). Service test for the `all_day` branch of `create_linked_calendar_event`. Frontend: `vitest` tests for the split action (one-click mutation fires the new API; "edit details first" navigates with prefill) and `jest-axe` on the detail page / any dialog. No minor PII involved, so privacy invariants are limited to confirming no athlete data is touched.
- **III. User Experience Consistency**: PASS. Uses shadcn/ui button + (if a confirm/menu is needed) existing dialog/dropdown primitives. All new copy in español neutro. Loading/disabled state on the one-click button during the mutation; success and error toasts (no raw exception text); the "associate" affordance disappears and the "En calendario" badge appears on success. 48×48 px targets; focus handling on any menu/dialog.
- **IV. Performance Requirements**: PASS. Single write per association; no bundle growth of note (reuses existing `EventForm`, adds one mutation hook). No heavy component added. Cold-start state already handled globally.

**Result**: PASS — no violations. Complexity Tracking not required.

One deliberate decision to record (not a violation): the new one-click endpoint and UI action are **coach-only** per the spec, whereas the adjacent existing endpoints (`/calendar-link`, calendar create) are `admin + coach`. See research.md Decision 4.

## Project Structure

### Documentation (this feature)

```text
specs/008-associate-competition-calendar/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (no schema change; documents reused entities)
├── quickstart.md        # Phase 1 output (manual verification)
├── contracts/           # Phase 1 output (new endpoint contract)
│   └── create-calendar-event-for-race-event.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   └── race_events.py            # ADD: POST /{id}/calendar-event (coach-only, one-click)
│   ├── services/
│   │   └── race/
│   │       └── calendar_sync.py      # EDIT: create_linked_calendar_event(..., all_day: bool)
│   └── schemas/
│       └── race_event.py             # ADD: response schema for the new endpoint (reuse CalendarLinkRead or EventRead-lite)
└── tests/
    ├── routers/
    │   └── test_race_event_calendar_autocreate.py   # NEW
    └── services/
        └── test_calendar_sync_all_day.py            # NEW (or extend existing calendar_sync tests)

frontend/
├── src/
│   ├── routes/
│   │   ├── competitions/
│   │   │   └── CompetitionDetailPage.tsx   # EDIT: replace link with split action (one-click + edit-first)
│   │   └── calendar/
│   │       └── EventFormPage.tsx           # EDIT: when prefillRaceEventId set, fetch válida & pass title/date/location
│   ├── components/
│   │   └── calendar/
│   │       └── EventForm.tsx               # EDIT: accept prefill title/start_date/location/all_day
│   ├── api/
│   │   └── raceEvents.ts                   # ADD: createCalendarEventForRaceEvent(id)
│   ├── hooks/race/
│   │   └── useRaceEvents.ts                # ADD: useCreateCalendarEventForRaceEvent()
│   └── types/
│       └── raceEvents.types.ts             # ADD: response type for the new endpoint
└── src/routes/competitions/__tests__/
    └── CompetitionDetailPage.associate.test.tsx     # NEW (extend existing detail test)
```

**Structure Decision**: Web application (Option 2). Changes are confined to the existing competitions and calendar slices on both tiers. No new modules, no migration.

## Complexity Tracking

> No constitution violations — table intentionally empty.
