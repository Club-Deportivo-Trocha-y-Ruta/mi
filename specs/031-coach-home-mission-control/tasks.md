# Tasks: Coach Home Mission Control

**Input**: Design documents from `/specs/031-coach-home-mission-control/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/coach-summary-endpoint.md`, `contracts/home-tiles.md`, `quickstart.md` (all present in this feature directory). **Cross-feature dependency**: `specs/028-frontend-design-foundation` MUST be merged first — this feature consumes `StatCard` (+ additive slots), `EmptyState`, `ErrorState` (incl. `isColdStart`), `StatusBadge`, the `--color-success/-warning/-danger` tokens, `frontend/e2e/target-size.spec.ts`, and the `useNewsletterStatusSummary` hook / `GET /api/training/athlete-newsletters/summary` endpoint as-is; none of these are (re)built by this feature.

**Tests**: Included throughout, not optional. Constitution II (Testing Standards, NON-NEGOTIABLE) requires backend `pytest` coverage (happy path, RBAC-negative, validation-negative, partial-failure isolation, query-count/no-N+1, privacy invariants) and frontend `vitest`+MSW coverage per tile/row state, plus `jest-axe` page coverage and an explicit `MeasurementAlerts` regression test (SC-006).

**Organization**: Tasks are grouped by user story (`spec.md` US1–US4) so each story is independently buildable and testable, in the order Setup → Foundational → US1 (P1) → US2 (P2) → US3 (P3) → US4 (P2) → Polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete sibling task)
- **[Story]**: Maps the task to `spec.md`'s US1/US2/US3/US4 — present only on story-phase tasks
- Every task names its exact file path

## Path Conventions

Existing web-application split, unchanged by this feature (`plan.md` Project Structure): `backend/app/`, `backend/tests/` (FastAPI + pytest) and `frontend/src/`, `frontend/e2e/` (React + vitest + Playwright). No new top-level directories.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new backend module locations for `GET /api/dashboard/coach-summary` and land the two incidental rule-of-three extractions `research.md` flags (R12, R13), before any real endpoint logic is written.

- [ ] T001 [P] Create the new dashboard router module `backend/app/routers/dashboard.py` with a module docstring and an empty `router = APIRouter()` (no endpoint yet — added in Foundational)
- [ ] T002 [P] Create `backend/app/schemas/dashboard.py` with `WeeklyLoadBandOut` (`age_band: Literal["10-12","13-15"]`, `planned_minutes: int`, `cap_minutes: int`, `athlete_count: int`) and `CoachSummaryOut` (`generated_at: datetime`, `consents_pending: int | None`, `insights_stale: int | None`, `weekly_load: list[WeeklyLoadBandOut] | None`) per `data-model.md` §1
- [ ] T003 [P] Extract the duplicated `_coach_club_ids(user)` helper (third occurrence, `research.md` R12) into `backend/app/services/permissions.py` as `coach_club_ids(user: User) -> set[int]`, then update `backend/app/routers/alerts.py` and `backend/app/routers/athletes.py` to import and call it in place of their own local copies, with zero behavior change to either router
- [ ] T004 [P] Extract the `count_selects` SQL-SELECT-counting async context manager (`research.md` R13) into new `backend/tests/helpers/query_counting.py`, sourced from the canonical implementation in `backend/tests/technique/test_perf_queries.py:79-118`

**Checkpoint**: Router/schema files exist (empty of business logic), the shared `coach_club_ids` helper is live with `alerts.py`/`athletes.py` tests still green, and a reusable query-counting test helper exists for Foundational's N+1 test.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the one new backend endpoint (`GET /api/dashboard/coach-summary`) end-to-end with its full test suite, plus the frontend data-fetching plumbing (`useCoachSummary`, MSW mocks, `persistAllowList` entry) every tile/row in US1–US4 will read from.

**⚠️ CRITICAL**: No user-story tile/row work (Phase 3+) may begin until this phase is complete.

### Backend — endpoint implementation

- [ ] T005 Implement the `consents_pending` sub-aggregate (own `try/except`, returns `None` on failure) in new `backend/app/services/dashboard_summary.py`, per `research.md` R4 / `data-model.md` §1: club athlete count minus `COUNT(DISTINCT athlete_id)` from `parental_consents` where `withdrawn_at IS NULL AND policy_id = <active policy id>`, scoped to the requesting club's athlete ids
- [ ] T006 Implement the `insights_stale` sub-aggregate (own `try/except`) in `backend/app/services/dashboard_summary.py`, per `research.md` R5: count club athletes whose active insight (`athlete_ai_insights.is_active = 1`) joins to an `agent_runs` row with `stale_since IS NOT NULL`, scoped to the club's athlete ids (depends on T005 sharing the same file)
- [ ] T007 Implement the `weekly_load` sub-aggregate (own `try/except`) in `backend/app/services/dashboard_summary.py`, per `research.md` R3: bucket athletes into `"10-12"`/`"13-15"` via `compute_age_decimal` (`backend/app/services/category.py`), compute the current Monday–Sunday ISO week bounds from **"today" in `ZoneInfo("America/Bogota")"`** (not naive `date.today()`), run the one grouped `DISTINCT (session_id, band)` query summing `duration_min` for `status='planned'` sessions in that week, apply the fixed band-minimum-age caps (600 min for `"10-12"`, 780 min for `"13-15"`), and omit a band entirely when the club has zero athletes in it (depends on T005/T006 sharing the same file)
- [ ] T008 Implement the `GET /coach-summary` route handler in `backend/app/routers/dashboard.py` — `require_role([UserRole.admin, UserRole.coach])`, optional admin-only `club_id` query param with the same 403/scoping semantics as `backend/app/routers/alerts.py:37-65`, club scoping via T003's `coach_club_ids(current_user)`, calls the three T005–T007 sub-aggregates and assembles `CoachSummaryOut` (depends on T001, T002, T003, T005, T006, T007)
- [ ] T009 [P] Register the dashboard router in `backend/app/main.py` — add `dashboard` to the `from app.routers import ...` line and add `app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])` alongside the other coach-facing router registrations near `alerts`/`athletes` (`main.py:68-69`)

### Backend — endpoint tests (`backend/tests/routers/test_dashboard_summary.py`, new file)

- [ ] T010 Write happy-path tests for `GET /api/dashboard/coach-summary` in new `backend/tests/routers/test_dashboard_summary.py`: seed a club with athletes in both age bands and a mix of current/outdated/missing consents and stale/fresh insights; assert `200` and correct `consents_pending`/`insights_stale`/`weekly_load` values; plus the **band-attribution edge case** (one joint session with convocados in both bands counts its `duration_min` toward both bands), the **empty-band case** (a band with zero athletes is omitted, not zeroed), and the **week-boundary case** (a session scheduled near the Sunday-night/Monday `America/Bogota` boundary lands in the correct ISO week) (depends on T008, T009)
- [ ] T011 Add RBAC-negative (parent role → 403; coach passing another club's `club_id` → 403) and validation-negative (non-integer `club_id` → 422) tests to `backend/tests/routers/test_dashboard_summary.py`
- [ ] T012 Add the partial-failure isolation test to `backend/tests/routers/test_dashboard_summary.py`: monkeypatch one sub-aggregate (e.g. consents) to raise, assert the response is still `200`, that field is `null`, and the other two fields are populated correctly
- [ ] T013 Add the query-count/no-N+1 regression test to `backend/tests/routers/test_dashboard_summary.py`, using T004's `backend/tests/helpers/query_counting.py::count_selects`: seed ~15 athletes / 10 sessions / 5 insights and assert the endpoint issues ≤ 12 `SELECT` statements, independent of those seed counts
- [ ] T014 Add the privacy-invariant test to `backend/tests/routers/test_dashboard_summary.py`: assert no athlete-identifying key (`name`, `first_name`, `athlete_id`, `birth_date`, etc.) appears anywhere in the JSON response

### Frontend — data-fetching plumbing

- [ ] T015 [P] Create `frontend/src/types/dashboard.types.ts` with `CoachSummary` and `WeeklyLoadBand` types matching `data-model.md` §1
- [ ] T016 Create `frontend/src/api/dashboard.ts` with `fetchCoachSummary()`, mirroring the conventions in `frontend/src/api/trainingSessions.ts` (depends on T015)
- [ ] T017 Create `frontend/src/hooks/dashboard/useCoachSummary.ts` — TanStack Query, key `["dashboard","coach-summary"]`, `staleTime: 60_000`, `refetchOnMount: "always"` per `research.md` R8 (depends on T016)
- [ ] T018 Create `frontend/src/hooks/dashboard/__tests__/useCoachSummary.test.ts` (depends on T017)
- [ ] T019 [P] Create `frontend/src/test/msw/dashboardHandlers.ts` with MSW handlers for `GET /api/dashboard/coach-summary` (success with all fields populated, success with one field `null`, 403 RBAC), mirroring the structure of the existing per-domain handler files (e.g. `frontend/src/test/msw/raceEventsHandlers.ts`)
- [ ] T020 [P] Extend `frontend/src/lib/persistAllowList.ts` — add the `["dashboard","coach-summary"]` prefix to `PERSIST_ALLOWLIST_PREFIXES` per `research.md` R9 (counts-only payload, no PII, `data-privacy-guard`-reviewable)
- [ ] T021 Extend `frontend/src/lib/__tests__/persistAllowList.test.ts` with a case asserting `["dashboard","coach-summary"]` is allow-listed (depends on T020)

**Checkpoint**: `GET /api/dashboard/coach-summary` is live, fully tested (happy/RBAC/validation/partial-failure/query-count/privacy), and `useCoachSummary()` can fetch it from the frontend with MSW coverage and cold-start-safe persistence. All four of the page's independent data sources (existing sessions/race/activities/newsletter hooks, plus this new one) are ready for tile/row work to begin.

---

## Phase 3: User Story 1 - "What's next" at a glance (Priority: P1) 🎯 MVP

**Goal**: The landing shows the next planned session (name, relative day, place; tap to open) and the next Copa Valle race (days remaining, class-based taper guidance, urgency-differentiated), each with a purposeful empty state, per `spec.md` US1.

**Independent Test**: Seed data for each state (session today / in N days / none planned; race inside and outside its taper window; season finished) and verify each tile's content, link target, urgency treatment, and empty state, per `spec.md`'s Independent Test for US1.

- [ ] T022 [P] [US1] Add a "en N días" relative-day helper to `frontend/src/lib/datetime.ts`, reusing `formatRelativeDay`'s (`datetime.ts:164-199`) club-timezone day-diff math, returning `"en N días"` for `diffDays > 1` (contracts/home-tiles.md, Tile 1)
- [ ] T023 [US1] Extend `frontend/src/lib/__tests__/datetime.test.ts` with cases for the new "en N días" helper (0/1/>1-day boundaries, club-timezone correctness) (depends on T022)
- [ ] T024 [P] [US1] Add the `TaperGuidance` lookup map (label + `taperDays` + urgency thresholds per tier A/B/C/CD, per `research.md` R7 and the exact copy in `frontend/src/components/calendar/EventForm.tsx:71-75`) to `frontend/src/lib/insights.ts`, keyed by `getCarreraTier`'s (`insights.ts:163-173`) tier values
- [ ] T025 [US1] Extend `frontend/src/lib/__tests__/insights.test.ts` with cases for the new `TaperGuidance` map (label/taperDays per tier A/B/C/CD; `null` for a date not in `CARRERA_TIER`) (depends on T024)
- [ ] T026 [P] [US1] Create `NextSessionTile` in `frontend/src/components/dashboard/NextSessionTile.tsx` — consumes `useTrainingSessions({from_date: today, to_date: today+14d, status: "planned"})` (`api/trainingSessions.ts:80-94`), selects the earliest session not yet finished by time (same-day exclusion: combine `scheduled_date` + `scheduled_start_time` in `America/Bogota`, exclude if `+ duration_min` has already elapsed), renders on `StatCard` (value = session title matching `SessionsListPage`'s row-title convention, hint = relative day via T022 + time + `location`, href = `/training/sessions/{id}`), `EmptyState` ("Sin sesiones planificadas" + "+ Planificar" → `/training/sessions/new`) when none, `ErrorState`/skeleton per the cold-start rule (depends on T022)
- [ ] T027 [P] [US1] Create `NextRaceTile` in `frontend/src/components/dashboard/NextRaceTile.tsx` — consumes `useRaceEventsList({season: currentSeason()})` (`hooks/race/useRaceEvents.ts:101-112`), selects the earliest event with `event_date >= today`, renders on `StatCard` with the three urgency states (neutral / upcoming / in_window) driven by `getCarreraTier(event.event_date)` + T024's `TaperGuidance` + `daysUntil` against the exact per-tier thresholds in `contracts/home-tiles.md` (A/CD: warning ≤10d, danger ≤7d; B: warning ≤6d, danger ≤4d; C: always neutral), season-over empty state ("Temporada finalizada — sin próximas carreras") when no future event exists, `ErrorState`/skeleton (depends on T022, T024)
- [ ] T028 [P] [US1] Create `frontend/src/components/dashboard/__tests__/NextSessionTile.test.tsx` covering: loading skeleton; populated (name/relative-day/place, click navigates to `/training/sessions/{id}`); empty state renders the "+ Planificar" CTA linking to `/training/sessions/new`; same-day-already-finished session is excluded (regression test for the Edge Case); error state with retry; cold-start renders a skeleton, never an error tone (depends on T026)
- [ ] T029 [P] [US1] Create `frontend/src/components/dashboard/__tests__/NextRaceTile.test.tsx` covering: loading; populated for each urgency tier, parametrized across A/B/C/CD at `daysUntil` values crossing each threshold from `contracts/home-tiles.md`; season-over empty state; error/cold-start (depends on T027)
- [ ] T030 [US1] Integrate `NextSessionTile` and `NextRaceTile` into `frontend/src/routes/dashboard/DashboardPage.tsx`, replacing two of the three existing static stat cards (`DashboardPage.tsx:28-66`), keeping the existing `<MeasurementAlerts />` import and render untouched (depends on T026, T027)
- [ ] T031 [US1] Extend `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx` asserting the hero strip renders `NextSessionTile`'s and `NextRaceTile`'s content and that each links to its documented target (depends on T030)

**Checkpoint**: A coach landing on `/dashboard` can now answer "what's next?" (session and race, with taper guidance) without navigating anywhere, reaching today's session in ≤2 interactions (SC-001/SC-002) — independently verifiable via T028/T029/T031 before any other story exists.

---

## Phase 4: User Story 2 - "What's pending" as an actionable inbox (Priority: P2)

**Goal**: The landing shows a five-row pending-work inbox (results to import, activities to link, newsletters due, consents pending, stale AI insights), each with a count and a link to its resolution screen, degrading gracefully when a row's data is unavailable, per `spec.md` US2.

**Independent Test**: Seed pending work of each kind and verify each row's count and link; disable the aggregate-backed rows and verify the list renders without them (no errors, no empty placeholders), per `spec.md`'s Independent Test for US2.

- [ ] T032 [US2] Create the `PendingInbox` shell in `frontend/src/components/dashboard/PendingInbox.tsx` — fixed 5-row order (resultados por importar, actividades sin enlazar, boletines pendientes, consentimientos pendientes, insights IA desactualizados), `RowState` handling per `data-model.md` §2 (omit the row when `null`, render a skeleton row when `undefined`), row layout (icon + count + short label + chevron, ≥48 px tap target)
- [ ] T033 [US2] Wire the "Resultados por importar" row in `PendingInbox.tsx` from the **same** `useRaceEventsList({season: currentSeason()})` result `NextRaceTile` already fetches, filtered client-side `!has_results && event_date < today` (zero extra requests, `research.md` R2), linking to the competitions list's existing needs-results filtered view (depends on T032)
- [ ] T034 [US2] Wire the "Actividades sin enlazar" row in `PendingInbox.tsx` from `useActivityReview({linked: "false", page: 1, page_size: 1}).total` (`hooks/activities/useActivityReview.ts:28-34`), linking to `/activities` pre-filtered `linked=false` (depends on T032)
- [ ] T035 [US2] Wire the "Boletines pendientes del mes" row in `PendingInbox.tsx` from 028's `useNewsletterStatusSummary(currentYear, currentMonth)`, counting items where `status !== "sent"`, linking to `/training/athlete-newsletters` (depends on T032)
- [ ] T036 [US2] Wire the "Consentimientos pendientes" and "Insights IA desactualizados" rows in `PendingInbox.tsx` from `useCoachSummary().consents_pending` / `.insights_stale` (T017), linking to the existing consent-management and season-panorama/competitions-insights screens per `contracts/home-tiles.md` (depends on T032)
- [ ] T037 [P] [US2] Add the all-clear state to `PendingInbox.tsx`: render the positive "Todo al día — sin pendientes esta semana" state only when every row that has resolved (i.e., not `undefined`) reports `count === 0` **and** at least one row has actually resolved (depends on T033, T034, T035, T036)
- [ ] T038 [P] [US2] Create `frontend/src/components/dashboard/__tests__/PendingInbox.test.tsx` covering each of the 5 rows independently loading/populated/omitted-when-`null`, and each row's correct link target (depends on T033, T034, T035, T036)
- [ ] T039 [US2] Extend `PendingInbox.test.tsx` with the all-clear-state test (renders when every resolved row is `0`; does **not** render while any row is still `undefined`/loading) (depends on T037, T038)
- [ ] T040 [P] [US2] Add absent-block MSW scenario handlers (`coach-summary` error/500, activities-count-only error) to `frontend/src/test/msw/dashboardHandlers.ts`
- [ ] T041 [US2] Extend `PendingInbox.test.tsx` with the degraded-state test using T040's handlers: 1-2 rows forced `null`/unavailable, assert the remaining rows still render and no error banner appears (US2 acceptance #2, FR-004) (depends on T038, T040)
- [ ] T042 [US2] Integrate `PendingInbox` into `frontend/src/routes/dashboard/DashboardPage.tsx` as Row 2, below the hero strip (depends on T032, T033, T034, T035, T036, T037)
- [ ] T043 [US2] Add the refetch-on-return test in `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx`: simulate resolving one pending item then remounting `DashboardPage`, assert the row's count refreshes via `refetchOnMount:"always"` without a manual reload (SC-003) (depends on T042)

**Checkpoint**: The inbox independently surfaces all five kinds of pending work with accurate counts and working links, shows a positive all-clear when nothing is pending, and degrades silently (never erroring) when the two aggregate-backed rows are unavailable — verifiable via T038/T039/T041/T043 without US1 or US3 existing.

---

## Phase 5: User Story 3 - Load planning against the club's own rule (Priority: P3)

**Goal**: The landing shows this week's planned training load per age band against the "weekly hours ≤ athlete age" cap, with comfortable/near-cap/over-cap visual states and advisory, never-alarmist wording, per `spec.md` US3.

**Independent Test**: Seed planned sessions producing under-cap, near-cap, and over-cap weekly totals per age band and verify the meter's states and wording, per `spec.md`'s Independent Test for US3.

- [ ] T044 [P] [US3] Create `WeeklyLoadMeter` in `frontend/src/components/dashboard/WeeklyLoadMeter.tsx` — two independent small-multiple meters (one per `age_band` present in `useCoachSummary().weekly_load`), plain divs/CSS fill+track pairs per the comfortable (≤80%, `--color-primary`) / near-cap (>80–100%, `--color-warning`) / over-cap (>100%, `--color-danger`) state table in `contracts/home-tiles.md`, value-leads headline (planned hours/minutes) + band/cap caption, over-cap renders a full-width bar with advisory non-alarmist copy (never clipped/overflowing), a "Ver sesiones de esta semana" link to `/training/sessions` with the current week's `from_date`/`to_date` pre-applied via the existing `useTrainingFiltersStore` query-param convention (`store/trainingFiltersStore.ts`)
- [ ] T045 [P] [US3] Add the absent (`weekly_load: null` → tile omitted entirely, never an error tone) and empty (`weekly_load: []` → "Sin atletas en edad de seguimiento (10-15 años)" neutral line) states to `WeeklyLoadMeter.tsx` (depends on T044)
- [ ] T046 [P] [US3] Create `frontend/src/components/dashboard/__tests__/WeeklyLoadMeter.test.tsx` covering: both bands comfortable; one band near-cap; one band over-cap (assert full-width bar + advisory, non-alarmist copy, never a clipped/overflowing bar); loading skeleton (depends on T044)
- [ ] T047 [US3] Extend `WeeklyLoadMeter.test.tsx` with the `weekly_load: null` case (tile absent, rest of the page unaffected) and the `weekly_load: []` case (the "sin atletas 10-15" line) (depends on T045, T046)
- [ ] T048 [US3] Integrate `WeeklyLoadMeter` into `frontend/src/routes/dashboard/DashboardPage.tsx` as the hero strip's third tile, replacing the last remaining static stat card (depends on T044, T045)

**Checkpoint**: The weekly-load meter independently shows comfortable/near-cap/over-cap states with advisory copy and a working link, and disappears cleanly (never blocking the rest of the home) when its aggregate is unavailable — verifiable via T046/T047 without US1, US2, or US4.

---

## Phase 6: User Story 4 - A home that respects roles and existing alerts (Priority: P2)

**Goal**: The admin landing shows only admin-openable content (no dead links into coach-only screens), and the existing measurement alerts remain behaviorally unchanged, per `spec.md` US4.

**Independent Test**: Land as admin and verify every visible element opens; land as coach and verify measurement alerts behave identically to before the redesign, per `spec.md`'s Independent Test for US4.

> Requires US1's and US2's `DashboardPage` integrations (T030, T042) to already exist — this story verifies and, where needed, gates the *assembled* page, per `research.md` R11's finding that no admin-specific branching is expected to be needed on the two hero tiles or any of the five inbox rows (none deep-link to `/athletes/:id`).

- [ ] T049 [US4] Add the admin-variant test in `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx`: land as admin, assert every rendered tile/row link resolves to an admin-openable route (no `ProtectedRoute` bounce back to `/dashboard`), reusing the 028 `AthleteLink` "click every link" test pattern (depends on T030, T042)
- [ ] T050 [US4] Contingency task — if T049 surfaces a tile/row whose link target is not admin-openable, apply an `AthleteLink`-equivalent role gate (plain text instead of a dead link) to that specific component's file; `research.md` R11 expects this task to be a no-op, confirmed at implementation time (depends on T049)
- [ ] T051 [P] [US4] Add the `MeasurementAlerts` regression test: re-run `frontend/src/components/dashboard/__tests__/MeasurementAlerts.test.tsx` unmodified against the new `DashboardPage` composition, asserting byte-identical rendered output for a fixed fixture (FR-006/SC-006) (depends on T030, T042)
- [ ] T052 [US4] Add the cold-start skeleton behavior test in `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx`: simulate the cold-start condition across all tiles/rows, assert skeletons render (never an error tone) alongside the existing "server waking" notice (depends on T030, T042)
- [ ] T053 [US4] Add the graceful-degradation combinatorics test in `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx`: simulate **all** Increment-B data absent (`coach-summary` request errors) and assert Increment A's tiles/rows (session, race, results-to-import, activities, newsletters) still render fully (depends on T030, T042)

**Checkpoint**: 0 role dead-ends for admin (SC-004), `MeasurementAlerts` is provably unchanged (SC-006), and the page never shows an error tone during cold start or partial-aggregate outages — verifiable now that US1 and US2 are both integrated into `DashboardPage`.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final page-level layout, and the cross-cutting accessibility/performance/e2e/manual validation that spans all four stories together.

- [ ] T054 [P] Finalize the responsive layout of `frontend/src/routes/dashboard/DashboardPage.tsx` — Row 1 hero strip (3 tiles: session, race, weekly-load), Row 2 `PendingInbox` card, Row 3 `MeasurementAlerts`, per the page order fixed in `contracts/home-tiles.md`
- [ ] T055 Extend `frontend/src/routes/dashboard/__tests__/DashboardPage.a11y.test.tsx` with `jest-axe` runs across the 5 required page states (populated, all-clear, degraded, cold-start/skeleton, admin variant) — zero violations required (Constitution II) (depends on T054)
- [ ] T056 [P] Verify `frontend/src/routes/dashboard/__tests__/DashboardClubScope.test.tsx` still passes unmodified against the rewritten `DashboardPage` (no club-scoping regression)
- [ ] T057 [P] Extend `frontend/e2e/target-size.spec.ts` (028) with the new dashboard tiles/rows, verifying ≥48×48 px interactive targets — the class of bug `jest-axe`/jsdom cannot catch
- [ ] T058 [P] Add Playwright link-through flows in new `frontend/e2e/dashboard-coach.spec.ts` — one flow per pending-inbox row and both hero tiles, clicking through and asserting the landed URL/page matches `contracts/home-tiles.md`
- [ ] T059 Record the LCP guard note per `quickstart.md` §4 in `docs/implementation-status.md`'s entry for this feature: the dashboard-route LCP budget (≤2.5 s, Constitution IV) now covers a heavier 6-fetch landing page; run or extend the project's existing Lighthouse/manual measurement step against it (flag the gap explicitly if no such harness exists yet — do not silently skip)
- [ ] T060 Run the full `quickstart.md` §5 manual seeded-scenario sweep (session-today + race-6-days-out; taper-window states across daysUntil=20/6/3; zero-pending all-clear; season rollover; resolve-and-return; cold start; admin walk-through; weekly-load bands) against a dev-seeded environment and record pass/fail against SC-001 through SC-007
- [ ] T061 Run `ruff` + `mypy` (backend) and `eslint` + `tsc --noEmit` (frontend), fixing any violation introduced by this feature, per `quickstart.md` §6 Definition of Done

**Checkpoint**: The fully assembled coach home ships — hero strip, inbox, meter, and unchanged measurement alerts — passing lint/type-check, `jest-axe`, target-size, and the full manual SC sweep.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately (T001–T004).
- **Foundational (Phase 2)**: Depends on Setup completion. **BLOCKS all of US1–US4** — no tile/row work may start before `GET /api/dashboard/coach-summary` and `useCoachSummary` exist and are tested (T005–T021).
- **US1 (Phase 3, P1)**: Depends only on Foundational. No dependency on US2/US3/US4 (T022–T031).
- **US2 (Phase 4, P2)**: Depends only on Foundational. Independent of US1/US3's own files — its "resultados por importar" row reuses `useRaceEventsList`'s **query cache**, not US1's code, so no build-order dependency on US1 exists even though both consume the same TanStack Query key (T032–T043).
- **US3 (Phase 5, P3)**: Depends only on Foundational (specifically `useCoachSummary`, T017). Independent of US1/US2 (T044–T048).
- **US4 (Phase 6, P2)**: Depends on Foundational **and** on US1's (T030) and US2's (T042) `DashboardPage` integrations — US4's admin-variant, regression, and cold-start tests exercise the *assembled* page produced by those two integration tasks. Does **not** require US3 (T044–T048) to be complete first — the weekly-load meter is untouched by any US4 test (T049–T053).
- **Polish (Final Phase)**: Depends on US1, US2, US3, and US4 all being complete — its layout pass and 5-state `jest-axe` sweep (including the admin variant) exercise the fully assembled page (T054–T061).

### Cross-Feature Dependency

This entire feature assumes `specs/028-frontend-design-foundation` is merged: `StatCard` (+ additive slots), `EmptyState`, `ErrorState` (incl. `isColdStart`), `StatusBadge`, the status-color tokens, `frontend/e2e/target-size.spec.ts`, and `useNewsletterStatusSummary` / `GET /api/training/athlete-newsletters/summary` are consumed as-is (T026, T027, T035, T057) and are out of scope to build here.

### User Story Dependencies (summary)

| Story | Depends on | Independent of |
|---|---|---|
| US1 (P1) | Foundational | US2, US3, US4 |
| US2 (P2) | Foundational | US1, US3, US4 |
| US3 (P3) | Foundational | US1, US2, US4 |
| US4 (P2) | Foundational, US1, US2 | US3 |

### Within Each Story

- Shared lib helpers (T022, T024) before the tile components that consume them (T026, T027).
- A component before its own test file (T026→T028, T027→T029, T044→T046).
- All of a story's components/logic before that story's `DashboardPage.tsx` integration task (last task in US1/US2/US3).
- US4's contingency task (T050) only executes if its trigger test (T049) fails.

### Parallel Opportunities

- All Setup tasks (T001–T004) — different files.
- Within Foundational: T015, T019, T020 — different files, no interdependency.
- Once Foundational completes: US1 (T022), US2 (T032), US3 (T044) can all start at once — different files, no cross-story dependency.
- Within US1: T022 ∥ T024 (different lib files); then T026 ∥ T027 (different tile files); then T028 ∥ T029 (different test files).
- Within US2: T037 ∥ T038 (once T033–T036 land); T040 is independent of the whole `PendingInbox.tsx` chain.
- Within US3: T044 → then T045 ∥ T046 (different files, both only need T044).
- Within US4: T051 (different file — `MeasurementAlerts.test.tsx`) is independent of T049/T052/T053 (all three edit `DashboardPage.test.tsx` sequentially).

---

## Parallel Example: Setup

```bash
Task: "Create the new dashboard router module backend/app/routers/dashboard.py"
Task: "Create backend/app/schemas/dashboard.py with WeeklyLoadBandOut and CoachSummaryOut"
Task: "Extract coach_club_ids into backend/app/services/permissions.py; update alerts.py/athletes.py"
Task: "Extract count_selects into backend/tests/helpers/query_counting.py"
```

## Parallel Example: Foundational (frontend scaffolding)

```bash
Task: "Create frontend/src/types/dashboard.types.ts"
Task: "Create frontend/src/test/msw/dashboardHandlers.ts"
Task: "Extend frontend/src/lib/persistAllowList.ts with the dashboard prefix"
```

## Parallel Example: Kicking off all three independent stories at once

```bash
Task: "[US1] Add en-N-días helper to frontend/src/lib/datetime.ts"          # T022
Task: "[US2] Create PendingInbox shell in frontend/src/components/dashboard/PendingInbox.tsx"   # T032
Task: "[US3] Create WeeklyLoadMeter in frontend/src/components/dashboard/WeeklyLoadMeter.tsx"    # T044
```

## Parallel Example: User Story 1 tiles

```bash
Task: "[US1] Create NextSessionTile in frontend/src/components/dashboard/NextSessionTile.tsx"   # T026
Task: "[US1] Create NextRaceTile in frontend/src/components/dashboard/NextRaceTile.tsx"          # T027

# then, once each tile exists:
Task: "[US1] Create NextSessionTile.test.tsx"   # T028
Task: "[US1] Create NextRaceTile.test.tsx"       # T029
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1 + US4's role guard)

1. Complete Phase 1: Setup (T001–T004).
2. Complete Phase 2: Foundational (T005–T021) — **critical**, blocks every story.
3. Complete Phase 3: User Story 1 (T022–T031).
4. Take the **role-guard slice** of US4 — run T049 scoped to just the two hero tiles landed in step 3 (skip T051/T052/T053, which need US2's inbox to be meaningful) — confirming 0 admin dead-ends on what exists so far.
5. **STOP and VALIDATE**: seed the states in US1's Independent Test and confirm SC-001/SC-002 by hand.
6. Deploy/demo if ready — this is the smallest slice that gives the coach a working "what's next" landing with no admin dead-clicks.

### Two-Increment Delivery (per spec.md's Assumptions)

The feature is explicitly designed to ship in two increments; task ranges map to them directly:

- **Increment A — existing-data tiles, zero new backend work**: T022–T031 (US1, both hero tiles), plus T032–T035 + T037–T039 + T042–T043 (US2's three non-aggregate rows: results-to-import, activities-unlinked, newsletters-due, and their all-clear/refetch behavior). None of these tasks read `useCoachSummary`.
- **Increment B — the one new endpoint and everything it powers**: T005–T021 (the `coach-summary` endpoint + `useCoachSummary`, listed in Foundational for a single clean gate in this document, but deployable independently since Increment A never calls it), T036 + T040–T041 (US2's two aggregate-backed rows), and all of US3 (T044–T048, the weekly-load meter, which has no other data source).
- US4 (T049–T053) and Polish (T054–T061) naturally follow whichever increment(s) have shipped; the graceful-degradation test (T053) is exactly the automated proof that Increment A keeps working if Increment B is delayed.

### Incremental Delivery (full)

1. Setup + Foundational → foundation ready (backend endpoint + frontend hooks, fully tested).
2. Add US1 → validate independently → deploy/demo (MVP).
3. Add US2 → validate independently → deploy/demo.
4. Add US3 → validate independently → deploy/demo.
5. Add US4 → validate role/regression/cold-start behavior against the now-assembled page → deploy/demo.
6. Polish → final layout, full-page a11y/perf/e2e sweep, manual SC validation → ship.

### Parallel Team Strategy

With multiple developers/agents available after Foundational:

- Developer/Agent A: US1 (T022–T031).
- Developer/Agent B: US2 (T032–T043).
- Developer/Agent C: US3 (T044–T048).
- US4 (T049–T053) starts once A and B both reach their `DashboardPage` integration tasks (T030, T042).
- Polish (T054–T061) starts once A, B, C, and the US4 owner have all finished.

---

## Notes

- `[P]` tasks touch different files with no unfinished-sibling dependency; same-file edits within a component (e.g., the four `PendingInbox.tsx` wiring tasks T033–T036) are intentionally sequential.
- `[Story]` labels map every story-phase task back to `spec.md`'s US1–US4 for traceability; Setup/Foundational/Polish carry no story label by design (they are cross-cutting).
- Verify each new/changed test fails against the pre-task code and passes after, per Constitution II.
- Stop at any story's Checkpoint to validate it independently before moving on — none of US1/US2/US3 breaks if the others are skipped or delayed.
- Avoid: editing `MeasurementAlerts.tsx` itself (FR-006 forbids it), adding a `recharts` import to this route (Constitution IV / `research.md` R0), and bundling `results_to_import`/`activities_unlinked`/`newsletters_due` into the new endpoint (would double-fetch data the hero tiles already load, per `research.md` R2).
