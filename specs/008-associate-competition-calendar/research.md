# Phase 0 Research: One-click associate a competition to the calendar

**Feature**: 008-associate-competition-calendar
**Date**: 2026-06-09

The Technical Context has no `NEEDS CLARIFICATION` markers — all four high-impact decisions were resolved with the coach during spec authoring. This document records the codebase findings that shape the implementation and the design decisions derived from them.

## Codebase findings (grounding)

- **Models**: `RaceEvent` (`backend/app/models/race_event.py`) has `name`, `event_date`, `location`, and `calendar_event_id` (FK, SET NULL). `CalendarEvent` (`backend/app/models/calendar_event.py`) has `title`, `start_at`, `end_at`, `all_day` (default `False`), `location`, `event_type`, `event_data`, and `race_event_id` (FK, RESTRICT). A CHECK constraint enforces `event_type != 'competition' OR race_event_id IS NOT NULL`. The link is strict 1:1.
- **Existing service**: `services/race/calendar_sync.py::create_linked_calendar_event(db, race_event, user)` already builds a `competition` `CalendarEvent` from the válida, sets both FK sides, and attaches an `all_club` audience. **Today it hardcodes start = 07:00 and duration = 5h (`all_day=False`).** It is invoked at válida-creation time when `RaceEventCreate.create_calendar_event` is `True`.
- **Existing endpoints**: `POST /{id}/calendar-link` links an *already-existing* calendar event; `create_calendar_event` on the calendar router requires `race_event_id` for competition events. There is **no** endpoint that, given an existing unlinked válida, creates-and-links a fresh event from the válida's own data.
- **`has_calendar_event`**: derived in the race-events router via an EXISTS/COUNT subquery; surfaced on `RaceEventRead` / `RaceEventListItem` and consumed by the frontend.
- **Frontend pain point**: `CompetitionDetailPage.tsx` shows the "Asociar a calendario" button when `has_calendar_event === false`. It is a plain `Link` to `/calendar/events/new?race_event_id=N`. `EventFormPage.tsx` reads `prefillRaceEventId` from the query param and `EventForm.tsx` only pre-selects `event_type=competition` + `race_event_id`. **Title, date, and location are NOT prefilled** — hence the re-typing.

## Decision 1 — One-click via a new endpoint vs. reusing `/calendar-link`

**Decision**: Add `POST /api/race-analysis/race-events/{id}/calendar-event` that creates a new all-day competition `CalendarEvent` from the válida and links it, by delegating to `create_linked_calendar_event(..., all_day=True)`.

**Rationale**: `/calendar-link` requires a *pre-existing* calendar event id — it solves a different problem. The one-click flow must *create* the event. Delegating to the existing `create_linked_calendar_event` keeps a single source of truth for how a competition event is constructed (audience, event_data, FK wiring), satisfying the rule-of-three / no-duplication principle. We extend that function with an `all_day` parameter rather than forking it.

**Alternatives considered**:
- *Reuse the calendar router's generic `create_calendar_event`*: rejected — it expects the full `EventCreate` payload (title, start_at, end_at, event_data, audiences) assembled client-side, which is exactly the manual entry we are eliminating, and it duplicates the construction logic already in `calendar_sync`.
- *Add a `create_calendar_event` re-trigger on the PATCH update endpoint*: rejected — conflates "edit válida" with "associate", and the update path already only *propagates* to an existing linked event.

## Decision 2 — All-day handling in `create_linked_calendar_event`

**Decision**: Add an `all_day: bool = False` parameter. When `True`, set `all_day=True` and set `start_at`/`end_at` to the válida's `event_date` at 00:00 → end-of-day (same date) in the `America/Bogota` timezone, instead of the 07:00 + 5h block. Preserve current behavior (`all_day=False`, 07:00 + 5h) for the existing válida-creation call site so that flow is unchanged.

**Rationale**: The coach chose all-day because a válida stores only a date. Defaulting the new parameter to `False` makes the change additive and leaves the create-competition checkbox flow (explicitly out of scope) untouched.

**Alternatives considered**:
- *Make all competition events all-day*: rejected — out of scope; would change the create-competition flow's existing behavior and its tests.

## Decision 3 — "Edit details first" prefill

**Decision**: When `EventFormPage` has a `prefillRaceEventId`, fetch the válida (`useRaceEvent`) and pass `title = name`, `start_date = event_date`, `location = location`, and `all_day = true` as prefill props into `EventForm`, in addition to the existing `race_event_id` preselect. The coach reviews/edits, then submits through the existing calendar create flow.

**Rationale**: Reuses the existing form and its Zod validation; the only change is seeding initial values from the válida. This delivers User Story 2 without a parallel form.

**Alternatives considered**:
- *A bespoke mini-form in a dialog on the detail page*: rejected — duplicates `EventForm`'s validation and event_data handling, violating UX-consistency and rule-of-three.

## Decision 4 — Permissions: coach-only vs. coach + admin

**Decision**: The new one-click endpoint and the UI action are **coach-only** (`require_role([UserRole.coach])`), per spec FR-008.

**Rationale**: The coach explicitly chose coach-only. The decision is recorded here because adjacent endpoints (`/calendar-link`, calendar create, válida CRUD) currently allow `admin + coach`. This is an intentional, documented narrowing for *this* action only; it does not change any existing endpoint's RBAC. If the coach later wants parity, widening to `[admin, coach]` is a one-line change.

**Alternatives considered**:
- *Match the surrounding `[admin, coach]`*: rejected for now to honor the explicit answer; flagged so the reviewer is aware of the inconsistency and can confirm.

## Decision 5 — `event_data` for the auto-created competition event

**Decision**: Reuse whatever `create_linked_calendar_event` already builds for `event_data` (competition payload: `city`, `race_category`, `is_departmental`), deriving `city` from the válida `location` (or a sensible default) and `race_category`/`is_departmental` from existing válida fields where available, exactly as the create-competition flow does today.

**Rationale**: Keeps the one-click path behaviorally identical to the proven create-time auto-link path, minus the time-of-day. No new mapping logic to maintain.

**Open item for implementation**: confirm during `/speckit-tasks` that `create_linked_calendar_event` already populates a valid `event_data` for competition (it must, since the create-competition flow relies on it) and that the all-day branch does not break that payload.
