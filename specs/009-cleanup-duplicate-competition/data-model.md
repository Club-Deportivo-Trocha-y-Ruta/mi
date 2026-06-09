# Data Model: Cleanup Duplicate Competition

No new tables, columns, enums, or migrations. This feature operates on existing entities and their
existing relationships. Documented here for the deletion semantics only.

## Entities involved (existing)

### RaceEvent (`race_events`)
- The competition being removed. Relevant fields/relationships:
  - `id` (PK)
  - `calendar_event_id` → FK `calendar_events.id`, **`ON DELETE SET NULL`**, nullable (race-side of the
    1:1 link).
  - `results` → `race_results.event_id` (`ON DELETE CASCADE`); the **presence** of any row here marks the
    competition as authoritative → cleanup is refused (409).
- Removed in step 3 of the cleanup transaction.

### CalendarEvent (`calendar_events`)
- The linked calendar entry. Relevant:
  - `race_event_id` → FK `race_events.id`, **`ON DELETE RESTRICT`**, nullable; CHECK
    `ck_calendar_competition_race_event` forbids NULL when `event_type='competition'`.
  - `audiences` → `event_audiences.event_id` (`ON DELETE CASCADE`, ORM `delete-orphan`).
  - `attendances` → `event_attendances.event_id` (`ON DELETE CASCADE`, ORM `delete-orphan`).
- Removed in step 2 of the cleanup transaction (its audiences/attendances cascade).

### RaceResult (`race_results`)
- Read-only in this feature. Used solely to evaluate the "has results" guard. Never modified or deleted.

## State transition (cleanup of one no-results duplicate)

```
Precondition:  RaceEvent R exists, has NO race_results, optionally linked to CalendarEvent C.
Actor:         coach

Step 0 (guard): load R → 404 if missing; if EXISTS(race_results where event_id=R.id) → 409.
Step 1:         R.calendar_event_id = NULL ; flush          (release race-side FK)
Step 2 (if C):  delete C ; flush                            (cascades event_audiences/attendances)
Step 3:         delete R ; flush                            (no calendar_events references R → RESTRICT ok)
Commit:         single transaction via get_db.

Postcondition: R no longer in Competitions list; C (if any) no longer on the calendar; no results
               touched; if R had no calendar event, only R is removed.
```

## Invariants

- **INV-1 (results protected)**: a `RaceEvent` with ≥1 `race_results` row is never deleted by this flow.
- **INV-2 (atomicity)**: either both R and C are removed, or neither — never a half state. Enforced by a
  single transaction.
- **INV-3 (no orphans)**: removing C cascades its audiences/attendances; removing R leaves no dangling
  `calendar_events.race_event_id` (C is already gone). No third record is detached.
- **INV-4 (privacy)**: no athlete names/PII in responses or logs — IDs only.
