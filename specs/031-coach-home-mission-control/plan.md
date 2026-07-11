# Implementation Plan: Coach Home Mission Control

**Branch**: `claude/coach-profile-ux-analysis-kaar7d` (shared program branch for specs 028-033, per `spec.md`'s declared Feature Branch) | **Date**: 2026-07-11 | **Spec**: `specs/031-coach-home-mission-control/spec.md`

**Input**: Feature specification from `/specs/031-coach-home-mission-control/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Replace `DashboardPage`'s three static, linkless stat cards (`frontend/src/routes/dashboard/DashboardPage.tsx:28-66`) with a "what's next / what's pending" mission-control layout: two hero stat tiles (next planned session; next Copa Valle race with taper-window urgency), one weekly-load meter (planned minutes per age band vs. the club's "hours ≤ age" cap), and a five-row pending-work inbox (results to import, activities to link, newsletters due, consents pending, stale AI insights) — while leaving `MeasurementAlerts` byte-identical (FR-006). Technical approach, grounded in reading the actual hooks/models rather than assumed: **three of five inbox rows and both hero tiles need zero backend work** (existing `useTrainingSessions`/`useRaceEventsList`/`useActivityReview`(count-only)/028's newsletter summary already carry the data); **exactly one new backend endpoint**, `GET /api/dashboard/coach-summary`, covers the two genuinely-new counts (consents pending, stale insights) plus the weekly-load aggregate — deliberately not bundling the other three rows into it, since that would double-fetch data the hero tiles already load (`research.md` R2). The meter and tiles are plain HTML/CSS (no charting library), designed against the `dataviz` skill's meter/stat-tile/status-color rules (`research.md` R0, R6, R7). Ships in two independently-verifiable increments per the spec's own Assumptions: existing-data tiles first, the one new endpoint second.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5 + React 19 (frontend) — unchanged, per CLAUDE.md stack.

**Primary Dependencies**: Backend — FastAPI, SQLAlchemy 2 async, Pydantic v2 (all existing; **no new runtime dependency**). Frontend — TanStack Query, shadcn/ui (028's `StatCard` with additive slots, `EmptyState`, `ErrorState`, `StatusBadge`), Tailwind v4 (all existing; **no new runtime dependency** — `recharts` v3.8.1 is already in `package.json` but is deliberately **not** imported into this route, see Constitution IV below).

**Storage**: MySQL 8.4 (existing). Read-only aggregates over existing tables (`training_sessions`, `session_attendances`, `athletes`, `parental_consents`, `athlete_ai_insights`, `agent_runs`). **No new tables, columns, or Alembic migration.**

**Testing**: `pytest` + `httpx.AsyncClient` + `aiosqlite` (backend, existing convention); `vitest` + Testing Library + MSW (frontend, existing convention, new `dashboardHandlers.ts`); `jest-axe`; Playwright (existing `e2e/` infra, extended — `target-size.spec.ts`). Full obligations in `quickstart.md`.

**Target Platform**: Render (Oregon, Docker, free tier, ~50 s cold start) for the backend; coach-facing tablet/desktop browser for the frontend (this page is coach/admin-only — the parent-facing 3G/Android budget from Constitution IV does not directly apply here, but the *dashboard-route* LCP budget explicitly does, see Performance Goals).

**Project Type**: Web application (existing `backend/` + `frontend/` split; no new top-level structure).

**Performance Goals**: LCP ≤ 2.5 s on the dashboard route (Constitution IV's explicit per-route budget); new endpoint p95 ≤ 500 ms (Constitution IV general API budget); **O(1) HTTP request count independent of club size** (SC-005/FR-008) — 6 fixed-shape requests total on landing (`research.md` R2's accounting), none scaling with athlete/session/event count.

**Constraints**: No schema/migration changes; no changes to AI pipelines, scoring, or stored data (spec Assumptions boundary); `MeasurementAlerts` behavior must stay byte-identical (FR-006/SC-006); no minor PII beyond ids used server-side (FR-010); must degrade gracefully (never error) whenever the two Increment-B-only sub-aggregates, or the Strava-dependent activities count, are unavailable (FR-004).

**Scale/Scope**: One production club (~20-40 athletes) today; 1 new backend endpoint + router + schema + service module; ~5 new frontend components (2 hero tiles, 1 meter, 1 inbox card, 1 new hook) plus a `DashboardPage` rewrite; `MeasurementAlerts` untouched.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — no new violations introduced by the data-model/contracts.*

| Principle | Status | Evidence |
|---|---|---|
| **I. Code Quality & Maintainability** | **PASS** | New backend service is a flat, single-purpose module (`app/services/dashboard_summary.py`), matching the existing `services/measurement_alerts.py` precedent rather than a new sub-package. The plan explicitly extracts `_coach_club_ids` (duplicated in `alerts.py`/`athletes.py`) into `services/permissions.py` on its third occurrence rather than adding a third inline copy (`research.md` R12) — the rule-of-three applied, not deferred. No new abstraction beyond what three call sites justify. Public service functions get docstrings per the existing convention (`run_staleness.py`, `measurement_alerts.py` as models). |
| **II. Testing (NON-NEGOTIABLE)** | **PASS**, gated on `quickstart.md` | Backend: happy path, RBAC-negative (parent → 403, cross-club coach → 403), validation-negative (bad `club_id` → 422), **partial-failure isolation** test (one sub-aggregate forced to fail → still 200, only that field null), and a **query-count regression test** (mirrors `test_activities.py:865-891`'s `count_selects` pattern) protecting the new endpoint from N+1 as club size grows. Frontend: every tile/row state (loading/empty/error/cold-start) per `contracts/home-tiles.md`, the admin variant, and an explicit **graceful-degradation combinatorics test** (all Increment-B data absent → Increment-A tiles still fully render). **Regression test for `MeasurementAlerts`**: its existing test suite re-run unmodified against the new `DashboardPage` composition, asserting byte-identical output (SC-006) — this is the concrete, automated form of "leave it exactly as it is." `jest-axe` on 5 distinct page states (populated/all-clear/degraded/cold-start/admin). |
| **III. User Experience Consistency** | **PASS** | Loading/empty/error states designed per tile/row (`contracts/home-tiles.md`, no tile/row skips a state). Status semantics: `--color-success/-warning/-danger` (028 tokens, already validated against this exact dataviz palette) reused for the meter's warning/danger steps; the comfortable state deliberately uses the brand accent rather than status-green, explicitly justified against the skill's own literal meter spec and the collision-avoidance rationale (`research.md` R6) — a documented, cited exception, not an ad hoc color choice. All interactive rows/tiles ≥ 48×48 px, verified by extending the existing `target-size.spec.ts` Playwright harness (028 R7) rather than relying on `jest-axe`/jsdom, which structurally cannot measure rendered size. Built entirely on shadcn/ui + the 028 shared-component kit (`StatCard` additive slots, `EmptyState`, `ErrorState`, `StatusBadge`) — no new component pattern introduced without one already existing to extend. |
| **IV. Performance Requirements** | **PASS** | **No `recharts` import into this route** — justified, not just declared: per the dataviz skill's own "Is it even a chart?" heuristic, a single ratio against a limit is a **meter** (plain divs/CSS), not a chart, so pulling a charting library into the highest-traffic route in the app would be pure bundle cost with no rendering benefit; `recharts` stays confined to the athlete-analysis routes that already lazy-load it. New endpoint's p95 ≤ 500 ms is justified by query shape, not aspiration: every sub-aggregate is bounded by the requesting club's roster size (~20-40 rows), never a global scan, and none fan out per-athlete (query-count test enforces this going forward). Request count is **O(1)** in club size — 6 fixed requests total, accounted for explicitly in `research.md` R2 (not "however many it turns out to be"). |
| **V. Youth Psychological Assessment Safeguards** | **N/A** | This page displays no psychological-instrument content (the anxiety module is untouched). Noted for completeness: `consents_pending` is a bare count with no per-athlete or per-consent-type (e.g., `psychological_assessment`) breakdown, keeping this page consistent with Principle V's data-minimization spirit even though it isn't gated by Principle V directly. |

**Quality Gates**: No PII beyond ids in the new payload — verified by a dedicated privacy test (`quickstart.md` §1), consistent with FR-010 and `research.md` R10. Structured logs on the new endpoint carry ids/counts only (matches `run_staleness.py`'s existing logging convention).

## Project Structure

### Documentation (this feature)

```text
specs/031-coach-home-mission-control/
├── plan.md              # This file
├── research.md           # Phase 0 — tile sourcing, endpoint consolidation, weekly-load rule, meter design, refresh/cold-start/privacy decisions
├── data-model.md         # Phase 1 — CoachSummary read-model + frontend CoachHomeViewModel composition
├── quickstart.md         # Phase 1 — validation plan tied to SC-001..SC-007
├── contracts/
│   ├── coach-summary-endpoint.md   # GET /api/dashboard/coach-summary — full contract
│   └── home-tiles.md               # Per-tile/row UI contract (states, urgency, meter thresholds)
└── checklists/
    └── requirements.md   # Pre-existing, all-pass
```

### Source Code (repository root)

**Structure Decision**: Existing web-application split (`backend/` + `frontend/`, per CLAUDE.md's documented architecture) — no new top-level directories. This feature adds one new backend router/schema/service triad and one new frontend hook/tile set, following each layer's existing per-domain-module convention exactly (e.g., `alerts.py`+`schemas/alerts.py`+`services/measurement_alerts.py` is the direct precedent this plan mirrors).

```text
backend/
├── app/
│   ├── routers/
│   │   └── dashboard.py                 # NEW — GET /api/dashboard/coach-summary; require_role([admin, coach])
│   ├── schemas/
│   │   └── dashboard.py                 # NEW — CoachSummaryOut, WeeklyLoadBandOut
│   ├── services/
│   │   ├── dashboard_summary.py         # NEW — 3 independent try/except sub-aggregates (consents, stale insights, weekly load)
│   │   └── permissions.py               # EXTENDED — extract shared coach_club_ids() (3rd dup, research.md R12); no behavior change for alerts.py/athletes.py
│   └── main.py                          # EXTENDED — app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
└── tests/
    ├── routers/
    │   └── test_dashboard_summary.py    # NEW — happy/RBAC/validation/partial-failure/query-count/privacy (quickstart.md §1)
    └── helpers/
        └── query_counting.py            # NEW (recommended) — extracted count_selects, 5th consumer triggers the rule-of-three

frontend/
├── src/
│   ├── routes/dashboard/
│   │   ├── DashboardPage.tsx            # REWRITTEN — hero strip + inbox card + <MeasurementAlerts /> (unchanged import)
│   │   └── __tests__/                   # EXTENDED — DashboardPage.test.tsx, DashboardPage.a11y.test.tsx; DashboardClubScope.test.tsx verified unaffected
│   ├── components/dashboard/
│   │   ├── MeasurementAlerts.tsx        # UNCHANGED (FR-006)
│   │   ├── NextSessionTile.tsx          # NEW
│   │   ├── NextRaceTile.tsx             # NEW (incl. taper-guidance lookup, research.md R7)
│   │   ├── WeeklyLoadMeter.tsx          # NEW (2 small-multiple meters, plain divs)
│   │   ├── PendingInbox.tsx             # NEW (5 rows + all-clear/degraded states)
│   │   └── __tests__/                   # NEW — one file per new component, MeasurementAlerts.test.tsx unmodified
│   ├── hooks/dashboard/
│   │   ├── useCoachSummary.ts           # NEW — staleTime 60s, refetchOnMount:"always" (research.md R8)
│   │   └── __tests__/useCoachSummary.test.ts   # NEW
│   ├── api/
│   │   └── dashboard.ts                 # NEW — fetchCoachSummary(), mirrors api/trainingSessions.ts conventions
│   ├── types/
│   │   └── dashboard.types.ts           # NEW — CoachSummary, WeeklyLoadBand
│   ├── lib/
│   │   ├── datetime.ts                  # EXTENDED — small "en N días" helper alongside formatRelativeDay (contracts/home-tiles.md, Tile 1)
│   │   └── persistAllowList.ts          # EXTENDED (recommended) — add ["dashboard","coach-summary"] prefix, pending data-privacy-guard review (research.md R9)
│   └── test/msw/
│       └── dashboardHandlers.ts         # NEW
└── e2e/
    └── target-size.spec.ts              # EXTENDED — new dashboard tiles/rows added to the existing sweep
```

## Complexity Tracking

*No entries — the Constitution Check above records zero violations. The one new endpoint, one new router/schema/service triad, and reuse-first tile sourcing are the minimal surface identified in Phase 0 research; nothing here required a justified exception.*
