# Contract: Create-and-link an all-day calendar event for a competition

**Feature**: 008-associate-competition-calendar
**Endpoint**: `POST /api/race-analysis/race-events/{race_event_id}/calendar-event`

Creates a new **all-day** `competition` calendar event from the válida's own data and links it 1:1. This is the backend for the frontend "one-click associate" action (User Story 1).

## Auth

- **Roles**: `coach` only (per spec FR-008). Other roles → `403 Forbidden`.
- **Auth scheme**: JWT bearer (existing).

## Request

- **Path param**: `race_event_id: int` — the válida to associate.
- **Body**: none. The event is built entirely from the válida's stored `name`, `event_date`, and `location`. (No re-entry — that is the point of the feature.)

## Behavior

1. Load the válida by `race_event_id`. If not found → `404`.
2. If `race_event.calendar_event_id IS NOT NULL` (already linked) → `409 Conflict`.
3. Delegate to `services/race/calendar_sync.py::create_linked_calendar_event(db, race_event, user, all_day=True)`:
   - `event_type = competition`, `title = name`, `location = location`.
   - `all_day = True`; `start_at` = `event_date` 00:00, `end_at` = `event_date` end-of-day (America/Bogota).
   - `event_data` = competition payload as built today (`city`/`race_category`/`is_departmental`).
   - one `all_club` audience.
   - both FK sides set atomically.
4. Commit. Return the link result.

## Responses

| Status | When | Body |
|---|---|---|
| `201 Created` | Event created and linked | `{ "race_event_id": int, "calendar_event_id": int, "has_calendar_event": true }` |
| `403 Forbidden` | Caller is not a coach | standard error envelope |
| `404 Not Found` | `race_event_id` does not exist | standard error envelope |
| `409 Conflict` | Válida already linked to a calendar event | `{ "detail": "La válida id=X ya está vinculada al evento de calendario id=Y" }` |

> Response shape may reuse the existing `CalendarLinkRead` schema (`race_event_id`, `calendar_event_id`) extended with `has_calendar_event`, or return `EventRead`. Final choice in `/speckit-tasks`; either MUST let the frontend flip `has_calendar_event` without a hard refetch (though a `useRaceEvent` invalidation is acceptable).

## Test scenarios (backend)

1. **Happy path** — coach POSTs for an unlinked válida → `201`; a `competition` `CalendarEvent` exists with `all_day=True`, `title==name`, `location==location`, `start_at`/`end_at` bounding `event_date`; both FK sides set; `has_calendar_event` now `true`.
2. **Already linked** — válida with `calendar_event_id` set → `409`; no second event created.
3. **Non-coach** — admin or parent token → `403`.
4. **Not found** — unknown `race_event_id` → `404`.
5. **All-day branch isolation** — the existing create-time auto-link path (`all_day` default `False`) still produces the 07:00 + 5h event (regression).

## Out of scope (non-goals — see spec)

- Re-syncing or editing an already-linked válida (no two-way sync here).
- The create-competition `create_calendar_event` checkbox flow (unchanged).
- Any specific start time / duration on the auto-created event.
