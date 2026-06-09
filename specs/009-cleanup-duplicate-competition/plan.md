# Implementation Plan: Cleanup Duplicate Competition

**Branch**: `009-cleanup-duplicate-competition` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-cleanup-duplicate-competition/spec.md`

## Summary

Give the coach a single, confirmed action — from the Competitions list (`/competitions`) and detail
view — that removes a **no-results** duplicate competition (`race_event`) together with its linked
calendar event, in one transaction, without admin involvement. The authoritative competition (the
one holding results) stays protected. This is the inverse of feature 008 (one-click associate to
calendar) plus a guarded delete.

Technical approach: a new **coach-only** endpoint
`DELETE /api/race-analysis/race-events/{id}/cleanup` backed by a new service function
`cleanup_duplicate_race_event(...)`. Because `calendar_events.race_event_id` uses `ON DELETE RESTRICT`
**and** the CHECK constraint `ck_calendar_competition_race_event` forbids a *competition* calendar
event from holding a `NULL` race_event_id, a pure "unlink" (set FK null) is impossible. The cleanup
therefore **deletes** the linked calendar event (cascading its audiences/attendances) and then deletes
the race_event. The existing admin-only `DELETE /{id}` and its guards are left untouched (FR-010). No
database migration is required — the existing schema and FK behaviors are sufficient.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Pydantic v2 (backend); React 19 +
Vite, TanStack Query, shadcn/ui + Tailwind, Zustand, Axios (frontend)

**Storage**: MySQL 8.4 (Hostinger prod); aiosqlite for tests. Tables touched (read/delete only):
`race_events`, `calendar_events`, `event_audiences`, `event_attendances`, `race_results` (read-only guard)

**Testing**: `pytest` + `httpx.AsyncClient` + aiosqlite (backend); `vitest` + Testing Library +
`jest-axe` (frontend)

**Target Platform**: Linux server (Render Free, Oregon) + SPA on Cloudflare Pages; coach on
desktop/tablet

**Project Type**: Web application (FastAPI backend + React SPA frontend)

**Performance Goals**: Transactional write p95 ≤ 1500 ms (Principle IV). The cleanup is a small,
bounded set of deletes by primary/foreign key on indexed columns — well within budget.

**Constraints**: No migration. Single DB transaction (atomic — never leave the competition deleted
but its calendar event dangling, or vice-versa). Logs emit IDs only (Ley 1581). Coach-only RBAC.

**Scale/Scope**: Tiny data volume (≤ ~10 competitions/season). One new endpoint, one service
function, one API client function, one hook, one new kebab action + reuse of the existing confirm
dialog.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Maintainability** — PASS. New behavior lives in a dedicated service function
  (`cleanup_duplicate_race_event`) rather than overloading `delete_race_event`, keeping both paths
  readable and single-purpose. The router stays thin. Public service function gets a docstring
  describing inputs/outputs/side-effects. No duplication introduced (reuses `delete_event_permanent`
  semantics conceptually; the cleanup orchestration is new and distinct).
- **II. Testing Standards (NON-NEGOTIABLE)** — PASS (planned). Backend: happy path (coach cleans a
  no-results competition WITH a linked calendar event → 204, competition + calendar event + audiences
  gone), happy path WITHOUT calendar event, and negative paths (has_results → 409; non-coach
  admin/parent → 403; missing → 404). Frontend: vitest for action visibility gating + confirm flow +
  hook invalidations; `jest-axe` on the (reused) dialog. Privacy invariant test: response/logs carry
  no athlete names.
- **III. User Experience Consistency** — PASS. Reuses `ConfirmDeleteDialog`, the existing kebab
  (`DropdownMenu`), shadcn/Tailwind tokens, 48×48 targets, focus-trapped dismissible dialog, and the
  red = destructive semantic. All copy in español neutro (Colombia). Loading/empty/error states reuse
  established patterns (`getRaceEventErrorMessage`).
- **IV. Performance Requirements** — PASS. A handful of indexed deletes in one transaction; no N+1, no
  new list queries, no bundle growth beyond a thin hook + action. Well under the 1500 ms write budget.

**Privacy / RBAC gate** — PASS. Coach-only via `require_role([UserRole.coach])`; competitions with
results cannot be removed; logs IDs-only. `data-privacy-guard` review applies (touches athlete-linked
results table only as a read-only guard; never returns names).

No violations → **Complexity Tracking table intentionally omitted** (nothing to justify).

## Project Structure

### Documentation (this feature)

```text
specs/009-cleanup-duplicate-competition/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cleanup-endpoint.md   # DELETE /{id}/cleanup contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (/speckit-specify output)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   └── race_events.py        # + DELETE /{race_event_id}/cleanup (coach-only)
│   └── services/
│       └── race_events.py        # + cleanup_duplicate_race_event(db, race_event_id)
└── tests/
    └── race/ (or routers/)       # + test_race_event_cleanup.py

frontend/
└── src/
    ├── api/
    │   └── raceEvents.ts          # + cleanupDuplicateRaceEvent(id)
    ├── hooks/race/
    │   └── useRaceEvents.ts       # + useCleanupDuplicateRaceEvent()
    └── routes/competitions/
        └── CompetitionsListPage.tsx  # + "Eliminar duplicado" kebab action (coach, !has_results)
        # CompetitionDetailPage.tsx may also surface the action (optional, same hook)
```

**Structure Decision**: Web application (Option 2). The feature is a thin, surgical addition over the
existing `race_events` router/service and the existing competitions list UI. It introduces no new
modules, models, schemas (beyond a trivial optional response), or migrations.

## Key Design Decisions

1. **Delete-not-unlink** for the calendar event. The DB makes a true unlink (set
   `calendar_events.race_event_id = NULL`) illegal for competition events
   (`ck_calendar_competition_race_event` + `ON DELETE RESTRICT`). Matching the user's choice
   ("calendar event always deleted"), cleanup deletes the calendar event. Its `event_audiences` /
   `event_attendances` rows cascade via `ON DELETE CASCADE`.
2. **Deletion order** (atomic, one transaction): (a) null the race-side FK
   `race_events.calendar_event_id` to release the 1:1 ring, (b) delete the `CalendarEvent`, (c) delete
   the `RaceEvent`. Because `race_events.calendar_event_id` is `ON DELETE SET NULL`, step (a) is also
   enforced by the DB, but we do it explicitly in the ORM to keep the session consistent. Step (c)
   succeeds only because no `calendar_events` row references the race_event anymore (RESTRICT
   satisfied).
3. **New endpoint, existing one untouched.** `delete_race_event` (admin-only, refuses when results or
   calendar link exist) is unchanged (FR-010). The new `cleanup_duplicate_race_event` is coach-only
   and is the only path that also removes the calendar event — and only for no-results competitions.
4. **Guard on results, re-checked at execution.** The service loads the event, refuses with 409 if any
   `race_results.event_id` rows exist (handles the "results imported between open and confirm" edge),
   and 404 if the event is already gone (stale list edge).
5. **RBAC = coach only**, mirroring feature 008's `create_calendar_event_for_race_event`
   (`require_role([UserRole.coach])`). Admin keeps its separate delete path. (Assumption: admin does
   not need this specific action; trivially extendable later if desired.)
6. **Frontend gating**: a new "Eliminar duplicado" destructive kebab item, shown when
   `user.role === coach && !item.has_results`. It opens the reused `ConfirmDeleteDialog` whose copy
   states that the competition **and** its calendar event will be permanently removed.

## Complexity Tracking

> No constitution violations — table intentionally omitted.
