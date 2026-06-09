# Phase 1 Data Model: One-click associate a competition to the calendar

**Feature**: 008-associate-competition-calendar
**Date**: 2026-06-09

> **No schema change. No Alembic migration.** This feature reuses two existing tables and their existing 1:1 relationship. This document records the fields the feature reads/writes and the invariants it must uphold.

## Entities (existing — unchanged)

### RaceEvent (válida) — `backend/app/models/race_event.py`

Fields relevant to this feature:

| Field | Type | Role in this feature |
|---|---|---|
| `id` | int (PK) | Path parameter for the new endpoint |
| `name` | str | Source for the calendar event `title` |
| `event_date` | date | Source for the all-day `start_at`/`end_at` |
| `location` | str \| None | Source for the calendar event `location` (and `event_data.city`) |
| `calendar_event_id` | int \| None (FK → CalendarEvent, SET NULL) | Read to detect "already linked"; set on association |
| `status` | enum | Must not be `cancelled` for association to be offered |

### CalendarEvent — `backend/app/models/calendar_event.py`

Fields written by this feature:

| Field | Type | Value on one-click association |
|---|---|---|
| `event_type` | enum | `competition` |
| `title` | str | válida `name` |
| `location` | str \| None | válida `location` |
| `all_day` | bool | **`True`** |
| `start_at` | datetime | válida `event_date` at 00:00 (America/Bogota) |
| `end_at` | datetime | válida `event_date` end-of-day (America/Bogota), `>= start_at` |
| `event_data` | JSON | competition payload (`city`, `race_category`, `is_departmental`) — as built today by `create_linked_calendar_event` |
| `race_event_id` | int (FK → RaceEvent, RESTRICT) | the válida's `id` |
| `status` | enum | `scheduled` |
| `created_by_user_id` | int | the acting coach |

Audience: one `all_club` audience row, as the existing create-time auto-link path creates.

## Relationship & invariants

- **Strict 1:1**: `race_events.calendar_event_id` ↔ `calendar_events.race_event_id`. Both sides set atomically in one transaction.
- **CHECK constraint** (existing): `event_type != 'competition' OR race_event_id IS NOT NULL` — satisfied because the auto-created event is `competition` and always carries `race_event_id`.
- **No duplicates (FR-009)**: if `race_event.calendar_event_id IS NOT NULL`, the new endpoint MUST NOT create a second event → return `409 Conflict`.
- **All-day (FR-003)**: `all_day = True`; `start_at`/`end_at` bound the válida's date.
- **Date required (edge case)**: a válida always has a non-null `event_date` (DB-required), so an all-day event can always be formed; no guard needed beyond normal validation.

## State transitions

```
Competition with no linked calendar event   (race_event.calendar_event_id IS NULL)
        │  POST /{id}/calendar-event  (coach)
        ▼
Competition linked to an all-day calendar event   (calendar_event_id set, has_calendar_event = true)
```

No reverse transition is in scope (un-linking / re-sync of already-linked events is a non-goal).

## Derived/read fields

- `has_calendar_event` (on `RaceEventRead` / `RaceEventListItem`): already derived server-side; flips to `true` after association and drives the frontend to hide the "associate" action and show the "En calendario" badge.
