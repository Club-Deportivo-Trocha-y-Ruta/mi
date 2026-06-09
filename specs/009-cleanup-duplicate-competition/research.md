# Research: Cleanup Duplicate Competition

Phase 0 output. All unknowns resolved against the live codebase (no remaining NEEDS CLARIFICATION).

## R1 — Can a competition be "unlinked" from its calendar event without deleting the event?

**Decision**: No — cleanup must **delete** the calendar event.

**Rationale**: `calendar_events.race_event_id` (backend/app/models/calendar_event.py:130) is a FK to
`race_events.id` with `ondelete="RESTRICT"`, and table CHECK `ck_calendar_competition_race_event`
(`event_type != 'competition' OR race_event_id IS NOT NULL`) forbids a competition-type calendar event
from having a NULL `race_event_id`. So setting the FK to NULL on a competition event is rejected by
MySQL 8 (the model comment cites error 3823 as the reason RESTRICT was chosen over SET NULL).
Therefore the only way to break a competition↔calendar 1:1 is to delete one of the two rows. The user
chose to always delete the calendar event, which aligns with this constraint.

**Alternatives considered**: (a) Convert the calendar event to a non-competition type and null the FK —
rejected: leaves an orphan, contradicts the user's "always delete" choice, and mutates unrelated data.
(b) Add a migration to relax the CHECK/FK — rejected: out of scope, riskier, and unnecessary given the
delete approach.

## R2 — What deletes when the calendar event is removed?

**Decision**: Deleting the `CalendarEvent` cascades its `event_audiences` and `event_attendances` rows
via `ON DELETE CASCADE` (calendar_event.py:200, :232) and the ORM `cascade="all, delete-orphan"`
relationships. The race-side FK `race_events.calendar_event_id` is `ON DELETE SET NULL`, so removing
the calendar event automatically clears it.

**Rationale**: Verified in the model. No manual cleanup of audiences/attendances needed.

**Alternatives considered**: Reusing `services/calendar/events.py::delete_event_permanent` — it deletes
the event and commits, but it also has training-session-specific branching and commits internally. We
need the delete to happen inside the larger cleanup transaction together with the race_event delete, so
the cleanup service issues `db.delete(cal)` directly (same effect for a competition event, which has no
training_session) and lets `get_db` commit once.

## R3 — Correct deletion order to satisfy all FKs in one transaction

**Decision**: (1) set `race_event.calendar_event_id = None` and flush; (2) `db.delete(calendar_event)`
and flush; (3) `db.delete(race_event)` and flush; (4) commit via `get_db`.

**Rationale**: The RESTRICT on `calendar_events.race_event_id` blocks deleting the **race_event** while a
calendar event still points to it — so the calendar event must go first. Nulling the race-side FK first
keeps the ORM identity map consistent (the DB would SET NULL it anyway when the calendar event is
deleted). After the calendar event is gone, nothing references the race_event, so its delete passes.

**Alternatives considered**: Deleting the race_event first — rejected: RESTRICT violation. Relying solely
on DB SET NULL without the explicit ORM null — works at the DB level but can leave a stale loaded
attribute in the session; explicit is safer and clearer.

## R4 — Endpoint shape and RBAC

**Decision**: `DELETE /api/race-analysis/race-events/{race_event_id}/cleanup`, `require_role([coach])`,
returns `204 No Content` on success.

**Rationale**: Mirrors the router's existing sub-resource verbs (`/{id}/calendar-link`,
`/{id}/calendar-event`, `/{id}/conditions`) and feature 008's coach-only
`create_calendar_event_for_race_event`. A distinct path keeps the admin-only `DELETE /{id}` untouched
(FR-010). 204 matches the existing delete and roster-delete endpoints.

**Alternatives considered**: `POST /{id}/cleanup` (rejected: the operation is a deletion, DELETE is the
correct verb); relaxing the existing `DELETE /{id}` to coach when no results (rejected: changes
established admin behavior and couples two concerns, violating FR-010).

## R5 — Status codes

**Decision**: 204 success; 404 event not found (stale list); 409 event has results (protected); 403
non-coach. 422 not applicable (no body).

**Rationale**: Consistent with `delete_race_event` (404/409) and the rest of the router. The 409 message
is in Spanish and explains the competition holds results.

## R6 — Frontend integration points

**Decision**: Add `cleanupDuplicateRaceEvent(id)` to `api/raceEvents.ts`, a
`useCleanupDuplicateRaceEvent()` mutation in `hooks/race/useRaceEvents.ts` (invalidating
`raceEventKeys.lists()` and the calendar tree via `calendarQueryRoot`/`invalidatePaired`), and a new
"Eliminar duplicado" item in the `ActionsKebab` of `CompetitionsListPage.tsx` gated by
`isCoach && !item.has_results`, reusing `ConfirmDeleteDialog`.

**Rationale**: Reuses every existing pattern (mutation + invalidation, kebab, confirm dialog, error
helper). The cleanup removes a calendar event, so the calendar query tree must be invalidated (unlike
the admin delete, which can never have a calendar event).

**Alternatives considered**: A brand-new dialog component — rejected: `ConfirmDeleteDialog` already
provides title/subject/description/confirm/pending/error props.
