# Quickstart — 031 Coach Home Mission Control

Validation plan tied to `spec.md`'s Success Criteria (SC-001..SC-007). No new migration to run. Two shippable increments (per spec Assumptions): **Increment A** — hero tiles + pending rows on existing/reused data (no backend change); **Increment B** — `GET /api/dashboard/coach-summary` + the meter + the two new inbox rows. The checks below are grouped so Increment A can ship and be verified independently of Increment B.

## 1. Backend (pytest, `httpx.AsyncClient` + `aiosqlite`) — Increment B only

New file: `backend/tests/routers/test_dashboard_summary.py`.

- **Happy path**: seed a club with athletes in both age bands, some planned sessions this ISO week (club tz), a mix of current/outdated/missing consents, and at least one insight whose `agent_run.stale_since` is set. Assert `200`, correct `consents_pending`/`insights_stale` integers, and `weekly_load` entries matching the expected per-band sums and fixed caps (`600`/`780`).
- **Band attribution edge case**: seed one joint session with convocados in both bands; assert its `duration_min` is counted toward **both** bands' `planned_minutes` (research.md R3) — a regression here would silently under- or double-count.
- **Empty-band case**: seed a club with athletes only in one band; assert the other band is **omitted** from `weekly_load` (not present with zeros — `data-model.md` §1 null-vs-empty semantics).
- **Week-boundary case**: seed a session scheduled for the club-timezone Sunday night vs. the following Monday (near a UTC-day boundary); assert it lands in the correct ISO week — this is the concrete regression test for the "container may run in UTC, club is UTC-5" risk (research.md R3).
- **RBAC-negative**: parent role → 403. Coach from a different club passing another club's `club_id` → 403 (mirrors `alerts.py`'s existing check).
- **Validation-negative**: non-integer `club_id` → 422.
- **Partial-failure isolation**: monkeypatch/force one of the three sub-computations (e.g., the consents query) to raise; assert the response is still `200`, that field is `null`, and the other two fields are populated correctly — this is the regression test for FR-004's "must degrade gracefully" at the backend layer, not just the frontend's handling of an absent field.
- **No-N+1 / query-count**: mirror `backend/tests/routers/test_activities.py:865-891`'s `count_selects` pattern — seed a club with e.g. 15 athletes / 10 sessions / 5 insights and assert the endpoint issues ≤ a fixed ceiling (~12) of `SELECT` statements, independent of those seed counts. Per research.md R13, prefer extracting the duplicated `count_selects` helper (currently copy-pasted in 4 files) into `backend/tests/helpers/query_counting.py` as part of this test file's addition — a nice-to-have cleanup, not a hard requirement of this feature.
- **Privacy test**: assert no key in the JSON response matches an athlete-identifying shape (no `name`, `first_name`, `athlete_id`, `birth_date` anywhere in the payload) — mirrors the project's existing privacy-invariant test convention (Constitution II: "tests for code that handles minors' data MUST include explicit privacy invariants").
- **Regression guard**: assert `GET /api/athletes/alerts` and `MeasurementAlerts`'s consuming test (`frontend/src/components/dashboard/__tests__/MeasurementAlerts.test.tsx`) are untouched by this change — no shared code path should need modification (FR-006, SC-006). This is a documentation-and-diff-review check, not a new automated test (the point is: if the diff touches `alerts.py` or its schema, that is itself a regression signal to look at twice), **except** for the one intentional, additive extraction of `_coach_club_ids` into `services/permissions.py` (research.md R12) — that refactor must leave `alerts.py`'s and `athletes.py`'s own existing tests green unmodified, which the extraction's own test coverage should assert.

## 2. Frontend (vitest + Testing Library + MSW)

New/updated files: `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx` (extend), `DashboardPage.a11y.test.tsx` (extend), `DashboardClubScope.test.tsx` (verify unaffected), new `frontend/src/hooks/dashboard/__tests__/useCoachSummary.test.ts`, new component tests under `frontend/src/components/dashboard/__tests__/` for each new tile (`NextSessionTile`, `NextRaceTile`, `WeeklyLoadMeter`, `PendingInbox`). New MSW handler `frontend/src/test/msw/dashboardHandlers.ts` (mirrors the existing per-domain handler files, e.g. `raceEventsHandlers.ts`).

Per tile/row, exercise every state named in `contracts/home-tiles.md`:

- **Próxima sesión**: loading skeleton; populated (name/relative-day/place, click navigates); empty (no planned session → CTA renders and links to `/training/sessions/new`); same-day-already-finished session is excluded (the concrete regression test for that Edge Case); error with retry; cold-start (skeleton, not error tone).
- **Próxima carrera**: loading; populated with each urgency tier (neutral/upcoming/in_window) — parametrized test across A/B/C/CD with `daysUntil` values crossing each threshold from `contracts/home-tiles.md`; season-over empty state (no future event); error/cold-start.
- **Carga semanal (meter)**: both bands comfortable; one band near-cap; one band over-cap (assert full-width bar + advisory, non-alarmist copy, not a clipped/overflowing bar); `weekly_load: null` → tile absent entirely (assert it does not render, and does not block the rest of the page from rendering); `weekly_load: []` → the "sin atletas 10-15" line; loading skeleton.
- **Pending inbox**: each of the 5 rows independently loading/populated/absent; all-clear state (only when every resolved row is zero, not while any are still loading — the specific regression case from `data-model.md` §2); degraded state with 1-2 rows `null` (assert the list still renders the remaining rows and no error banner appears — this is the direct test for US2 acceptance #2/FR-004); each row's click navigates to its documented link target.
- **Admin variant**: land as admin; assert every rendered tile/row/link is admin-openable (no dead `ProtectedRoute` bounce) — reuse the "click every link, assert no redirect to /dashboard" pattern the 028 `AthleteLink` tests establish, applied to this page's own tiles.
- **MeasurementAlerts regression**: re-run its existing test file unmodified against the new `DashboardPage` composition; assert byte-identical rendered output for a fixed fixture (SC-006).
- **Graceful degradation combinatorics**: at least one test with **all** Increment-B data absent (both `null` from a simulated 500/404 on `coach-summary`) verifying Increment A's tiles/rows still render fully — this is the direct test that the two increments are independently shippable, per spec Assumptions.

## 3. Accessibility (`jest-axe`)

Run on `DashboardPage` in each of: default populated state, all-clear state, degraded state (rows absent), cold-start/skeleton state, admin variant. Zero violations required (Constitution II). Specifically verify: meter fill/track color differences are not the only carrier of state (icon/text also present per the state's copy in `contracts/home-tiles.md`); every tile/row link ≥ 48×48 px (Constitution III — note per 028 R7, jest-axe/jsdom cannot verify rendered pixel size, so this specific check belongs to the Playwright pass below, not this one).

## 4. Playwright (`frontend/e2e/`)

- **LCP guard note**: this feature does not introduce a new Playwright perf spec by itself, but the existing/implied dashboard-route LCP budget (Constitution IV: ≤ 2.5 s dashboard route, simulated 3G, mid-tier Android) now covers a materially heavier landing page (6 fetches instead of 1-2) — re-run/extend whatever LCP measurement harness the project already uses (if none exists yet as a dedicated spec, that gap predates this feature and is out of scope to build from scratch here; flag it rather than silently skip verifying).
- **Target-size sweep**: extend `frontend/e2e/target-size.spec.ts` (028 R7) to include the new dashboard tiles/rows — this is exactly the class of bug (rendered pixel size) jsdom/axe cannot catch, and the harness already exists.
- **Link-through of each row**: one Playwright flow per pending-inbox row and both hero tiles, clicking through to the documented destination and asserting the URL/page landed on matches `contracts/home-tiles.md`.

## 5. Manual seeded scenarios (mapped to Success Criteria)

Seed via the dev Docker seed data (never production) per scenario, then verify manually against the criterion:

| Scenario | Seed | Verifies |
|---|---|---|
| Session today, race 6 days out (tier B window) | 1 planned session today (not yet finished), 1 tier-B race in 6 days | **SC-001**: both stated at a glance, no navigation; **SC-002**: session reachable in ≤ 2 taps |
| Taper-window states | Three race fixtures at `daysUntil` = 20 (neutral), 6 (tier-B warning), 3 (tier-B in-window) run in sequence | US1 acceptance #3 — urgency visibly changes as the window is entered |
| Zero-pending all-clear | No unimported results, no unlinked activities, no newsletters due, 0 consents pending, 0 stale insights | **US2 acceptance #3** — positive all-clear render, not blank space |
| Season rollover | Change system/test clock across Jan 1 (or seed `event_date`s spanning two seasons) | **FR-009** — race tile and any season-scoped row (results-to-import, insights-stale if season-scoped) follow the new year automatically, no hardcoded year |
| Resolve-and-return | From the inbox, resolve one pending item (e.g., import a race's results) on its destination screen, then navigate back to Inicio | **SC-003** — the row's count reflects the resolution without a manual reload (`refetchOnMount:"always"`, research.md R8) |
| Cold start | Let Render's free tier idle past ~15 min, then land | Edge Case — skeletons, not errors, across every tile while waking; existing "server waking" banner still shows |
| Admin walk-through | Log in as admin, click every visible element on Inicio | **SC-004** — 0 dead ends |
| Weekly-load bands | Seed sessions producing under/near/over-cap totals for each band independently | US3 acceptance #1/#2 — visual states + advisory (non-alarmist) copy on the over-cap band, with a working link to the sessions involved |

## 6. Definition of done for this feature

- All items above pass.
- `ruff` + `mypy` (backend), `eslint` + `tsc --noEmit` (frontend) clean.
- Constitution Check in `plan.md` re-verified post-design (Phase 1 gate) with no new violations.
- `docs/implementation-status.md` updated per the project's existing convention (not part of this plan's artifacts, but the natural next step after implementation).
