# Tasks: Frontend Design Foundation & Everyday Reliability

**Input**: Design documents from `/specs/028-frontend-design-foundation/` (spec.md, plan.md, research.md, data-model.md, contracts/shared-components.md, contracts/newsletter-status-summary.md, quickstart.md)

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md (R1–R11 decisions), data-model.md, contracts/, `.specify/memory/constitution.md` v1.2.0

**Tests**: Constitution Principle II makes testing NON-NEGOTIABLE for this feature — vitest + Testing Library for branching components, jest-axe (zero violations) on every new/changed page- and dialog-level component, a regression test for every bug fix that fails on unfixed code and passes on the fix, pytest happy + negative paths for the one new backend endpoint, and a new Playwright `e2e/target-size.spec.ts`. Tests are included throughout, embedded in the task that produces the fix (per-task "done" criteria states the assertion).

**Organization**: Tasks are grouped by user story (US1–US4, priorities from spec.md) to enable independent implementation and testing of each story. Setup and Foundational phases precede all stories; Polish follows all stories.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task in the same phase)
- **[Story]**: US1/US2/US3/US4 — present only on Phase 3–6 tasks; Setup/Foundational/Polish carry no story label
- Every task names its exact file path(s); "done" is stated explicitly wherever it isn't obvious from the action alone

## Path Conventions

Existing web-app monorepo (per plan.md's Project Structure): `frontend/src/**` (React 19 + Vite + Tailwind v4 + shadcn/ui), `frontend/e2e/**` (Playwright), `backend/app/**` + `backend/tests/**` (FastAPI + SQLAlchemy 2 async). No new top-level directories are introduced. All new shared UI lives in `frontend/src/components/shared/` (the existing home of `PHVBadge.tsx`); new shadcn primitives land in `frontend/src/components/ui/` per `components.json` (`new-york`, `cssVariables: false`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install the missing dependencies and lay the token groundwork every later phase builds on. No story label — this is cross-cutting.

- [X] T001 Install the `@fontsource/cal-sans` runtime dependency: from `frontend/`, run `npm install @fontsource/cal-sans`, updating `frontend/package.json` and `frontend/package-lock.json`. No other file changes.
- [X] T002 Add the missing shadcn/ui primitives. **Deviation**: `npx shadcn@latest add ...` failed — `ui.shadcn.com:443` returns 403 from the org egress proxy (confirmed via `$HTTPS_PROXY/__agentproxy/status`: explicit `connect_rejected`/policy denial, not transient — matches research R1's flagged risk exactly). Per proxy policy, did not retry or route around it. Instead hand-authored all 11 primitives (`input.tsx`, `label.tsx`, `select.tsx`, `form.tsx`, `checkbox.tsx`, `radio-group.tsx`, `switch.tsx`, `alert.tsx`, `alert-dialog.tsx`, `separator.tsx`, `sonner.tsx`) matching the codebase's own established shadcn-adaptation convention (forwardRef, individual `@radix-ui/react-*` imports, project token vocabulary — the majority pattern in `button.tsx`/`dialog.tsx`/`badge.tsx`/`tooltip.tsx`, not the raw untouched oklch/dark-mode/`radix-ui`-umbrella style found in `toggle.tsx`/`toggle-group.tsx`, which the audit already flagged as drift). Installed the 4 missing Radix primitives as direct deps (`@radix-ui/react-checkbox`, `-switch`, `-alert-dialog`, `-slot` — all were already present transitively; `label`/`select`/`radio-group`/`separator` were already direct deps) plus `sonner`. `components.json`'s `"cssVariables": false` honored (literal Tailwind classes throughout, no CSS custom-property theme). Verified: `tsc --noEmit` zero errors; `vite build` succeeds.
- [X] T003 In `frontend/src/style.css`, register `--color-border-gray` inside the `@theme` block — added next to the other `--color-*` entries, generating the `border-border-gray` utility (verified present in built CSS output).
- [X] T004 In `frontend/src/style.css`, added the 4-tier semantic status scale to the `@theme` block: `--color-success: #0ca30c;`, `--color-warning: #fab219;`, `--color-danger: #d03b3b;` (neutral reuses existing grays).
- [X] T005 In `frontend/src/style.css`, wired up Cal Sans: `@import "@fontsource/cal-sans";` added at the top of the file, `@theme`'s `--font-display` changed to `"Cal Sans", system-ui, sans-serif`. Verified: built CSS contains the Cal Sans `@font-face` declaration (bundled by `@fontsource/cal-sans`'s `index.css`, all-subsets weight-400).
- [X] T006 In `frontend/src/style.css`, kept `@theme --shadow-card` and `@theme --shadow-ring` as the two survivors (unchanged). Added `/* deprecated: superseded by @theme --shadow-card — migrate call sites in feature 028 T068, then delete */` above `:root`'s `--shadow-ring-soft`, and a similar note above `--shadow-ring-only`. Did not delete them yet — `.shadow-ring-soft` utility still consumes `--shadow-ring-soft` until T068.
- **Note for T067 (US4)**: while registering tokens (T003/T004) in the shared `@theme` color block, also merged `--color-link-blue`'s value from the literal `#20b7c9` to `var(--color-primary)` (mechanical, idempotent, zero visual change — `:root`'s copy was left untouched). This is part of T067's originally-scoped work; when executing T067, skip the link-blue reassignment (already done) and only perform the lime-accent deletion.

**Checkpoint**: Dependencies installed, tokens registered — Foundational component work can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared component kit from `contracts/shared-components.md` — the frozen API that US1–US4 (and later features 029–033) consume. Each component ships with its own vitest + jest-axe test per constitution Principle II ("every page-level and dialog-level component").

**⚠️ CRITICAL**: No user-story work may begin until this phase is complete.

- [X] T007 Created `PageHeader` per contract. 10 tests, jest-axe 0 violations.
- [X] T008 Created `EmptyState` per contract, mirroring `CompetitionsListPage.tsx`'s empty-state visual. 10 tests, jest-axe 0 violations.
- [X] T009 Created `isColdStartError(err)` + `ErrorState` per contract, generalizing `CatalogGrid.tsx`'s heuristic (message-text keywords + duck-typed request-with-no-response fallback, excluding `ERR_CANCELED`). 30 tests, jest-axe 0 violations across default/custom/cold-start/retry variants.
- [X] T010 Created `StatCard` per contract over `ui/card.tsx` + `shadow-card`. 11 tests, jest-axe 0 violations (default/isLoading/href states).
- [X] T011 Created `ConfirmDialog` on `ui/alert-dialog.tsx`. Fixes the `ConfirmModal.tsx:66` autoFocus-on-confirm bug by construction (Cancel focused via `onOpenAutoFocus` when `tone="danger"`). 18 tests, jest-axe 0 violations (default/danger/isPending/errorMessage/description).
- [X] T012 Created `StatusBadge` per contract. **Correction applied during build**: computed real WCAG contrast for the T004 tokens against white — `text-success` (#0ca30c) ≈3.36:1 and `text-warning` (#fab219) ≈1.84:1 both fail 4.5:1 AA for 12px label text (invisible to jest-axe/jsdom, which doesn't resolve Tailwind classes to computed colors). Label renders in `text-charcoal`/`text-mid-gray` (always legible); the status color/token lives on `bg-{status}/10`, `border-{status}/30`, and the icon. 18 tests, jest-axe 0 violations across all 4 statuses.
- [X] T013 Created the unified `Stepper` merging `SessionStepper.tsx` and `ImportWizard.tsx`'s inline stepper (zero visual regression — `compact` replicates the existing circle/checkmark/arrow markup verbatim; `detailed` matches `OnboardingStepper`'s connector-line aesthetic). Step-focus management documented as a host-wizard responsibility (code comment: ref + `tabIndex={-1}` + `useEffect` keyed on `active`), consumed by US3 T050/T051. 12 tests, jest-axe 0 violations.
- [X] T014 Created `AthleteLink` per contract. Confirmed via `App.tsx` that `/athletes/:id` is `allowedRoles={[UserRole.coach]}` only. 14 tests, jest-axe 0 violations across coach/admin/unauthenticated.
- [X] T015 Mounted sonner's `<Toaster />` in `App.tsx` next to `TooltipProvider`.
- [X] T016 Created `RouteFallback` (adds `role="status"`/`aria-live="polite"` — absent from the original inline divs). 6 tests, jest-axe 0 violations.
- [X] T017 Adopted `RouteFallback` at 20 of 21 Suspense sites in `App.tsx`, copy preserved byte-exact. **1 site intentionally left as-is**: `/confirmar-correo` (`ConfirmEmailChangePage`) uses `min-h-screen` (not `min-h-[40vh]`) — the one public/unauthenticated route with no dashboard chrome, where full-viewport height is deliberate; swapping to `RouteFallback` would silently shrink it to 40vh. Flagged rather than guessed, per instruction.

**Independent verification (not just agent self-reports)**: `npx tsc --noEmit` — 0 errors repo-wide. `npx vitest run src/components/shared/` — 144/144 tests pass across 10 files (9 new + pre-existing `PHVBadge`). `npx vite build` — succeeds.

**Checkpoint**: The shared component kit exists and is tested. `contracts/shared-components.md` is now real code — features 029–033 may start consuming it. US1 and US2 (both P1) may now begin, in parallel with each other.

---

## Phase 3: User Story 1 - Field controls that work with gloves in the sun (Priority: P1) 🎯 MVP

**Goal**: The coach, on a tablet outdoors, can operate every daily control — above all the effort rubric — with gloved fingers and read every label in direct sunlight.

**Independent Test**: On a touch device (or emulation), record attendance and the full effort rubric (RPE, esfuerzo, actitud, técnica) for several athletes wearing gloves; measure every interactive target on a real rendering engine; check secondary text contrast against the project's stricter token.

- [ ] T018 [P] [US1] Rewrite `frontend/src/components/training/RubricSliders.tsx`: replace all 4 native `<input type="range">` sliders — RPE OMNI (0–10, 11 discrete steps, currently lines ~119-132) and Esfuerzo/Actitud/Técnica (1–5, 5 steps each, via the `RubricSlider` sub-component, lines ~39-90) — with `ToggleGroup`/`ToggleGroupItem` (`@/components/ui/toggle-group`, already installed) discrete steppers, each option ≥48×48px and wrapping to two rows below a 360px viewport; preserve the `RPE_LABELS`/`RPE_FACES`/`RUBRIC_LABELS` text and the existing `Controller`-based RHF autosave wiring untouched; delete the dead `text-light-gray-dark` class (line 78, resolves to no color — copy/typo of `mid-gray`); replace the "Comentario" textarea's inline `style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}` (line 165) with `className="shadow-ring"`. Mirror the in-repo `ToggleGroup` pattern already used for `session_kind` in `frontend/src/components/training/session-wizard/StepGeneral.tsx:190-210` and `surface_condition` in `frontend/src/components/competitions/import/ImportWizard.tsx:1155-1178`. Update/extend `frontend/src/components/training/RubricSliders.test.tsx` and `frontend/src/components/training/RubricSliders.a11y.test.tsx`: assert each of the 4 rubric groups renders as a `ToggleGroup` with discrete, accessibly-named options (not a range input), jest-axe zero violations, and that selecting an option still fires the existing autosave — must fail on the pre-rewrite range-input code.
- [ ] T019 [P] [US1] Update `frontend/src/components/training/DurationPicker.tsx`: add `min-h-[48px]` to the hours `<input>` (~line 105) and minutes `<select>` (~line 127) — currently styled via `inputClass`/`selectClass` (lines 24-28) with no minimum height, unlike the sibling `min-h-[48px]` input in `frontend/src/components/training/session-wizard/StepGeneral.tsx:16-17`; replace the 3 inline `boxShadow` usages (the `inputStyle` constant at line 26, applied at ~113 and ~132, plus the preset-button ternary at ~164-168) with `className="shadow-ring"`. Extend `frontend/src/components/training/DurationPicker.test.tsx` with a regression assertion that the hour input, minute select, and preset buttons each carry a ≥48px min-height class — must fail on unfixed code.
- [ ] T020 [US1] Adopt the stricter sunlight-contrast token on coach-facing small text (research R11): swap `text-mid-gray` → `text-text-disclaimer` (the utility auto-generated from the existing `--color-text-disclaimer` token, already used in 5 parent-facing files, e.g. `frontend/src/components/parents/MonthlyAveragesBanner.tsx:108`) on the rubric tick-mark/value labels in `frontend/src/components/training/RubricSliders.tsx` (post-T018), the timestamp cells in `frontend/src/components/training/SessionsTable.tsx`, and the "Total: X minutos" helper line in `frontend/src/components/training/DurationPicker.tsx` (post-T019). Depends on T018 and T019 (same files as those rewrites).
- [ ] T021 [P] [US1] Bump touch targets to ≥48×48px: change `min-h-[36px] min-w-[36px]` to `min-h-[48px] min-w-[48px]` on the note button in `frontend/src/components/competitions/results/ResultsTable.tsx` (~line 640); add `min-h-[48px] min-w-[48px]` to the button in `frontend/src/components/competitions/insights/AnalyzeAthleteButton.tsx` (~lines 181-186, currently no min-height class at all). Extend `frontend/src/components/competitions/results/__tests__/ResultsTable.test.tsx` (exists) and create `frontend/src/components/competitions/insights/__tests__/AnalyzeAthleteButton.test.tsx` (does not exist yet) with a regression assertion on the rendered class list — real pixel measurement is covered by T023's e2e spec.
- [ ] T022 [P] [US1] Add `capture="environment"` to the file `<input type="file">` in `frontend/src/components/training/MediaUploadZone.tsx` (~line 145) so tablets open the camera directly instead of the generic gallery picker. Extend `frontend/src/components/training/MediaUploadZone.test.tsx` with a regression test asserting the input carries `capture="environment"` — must fail on unfixed code.
- [ ] T023 [US1] Create `frontend/e2e/target-size.spec.ts` (Playwright, Chromium preinstalled — do NOT run `playwright install`): sweep the session-detail page (incl. the rubric from T018), the competitions results table (T021), the coach dashboard, and one representative list page; assert `boundingBox()` ≥48×48 for every `a`, `button`, `[role=button]`, and form input, with a documented allowlist for inline text links (research R7 — jest-axe in jsdom cannot measure rendered pixels). Depends on T018, T019, T020, T021, T022 (verifies their combined output on a real rendering engine).

**Checkpoint**: US1 is independently functional and testable — every coach field control now meets the 48px/contrast bar. (Runs in parallel with US2 — see Dependencies.)

---

## Phase 4: User Story 2 - Never dead-ended (Priority: P1) 🎯 MVP

**Goal**: Whatever fails or wherever the coach or admin taps, there is always a way forward: failed loads offer retry, no visible link silently bounces, and small broken behaviors (calendar day tap, stale season, N+1 newsletter fan-out) are fixed.

**Independent Test**: As admin, click every athlete name on the dashboard, competition views, and newsletter detail — none may silently bounce. Throttle the network to fail loads on sessions, athletes, dashboard, and calendar — each shows a retry that recovers. Tap an empty calendar day — event creation opens with the date prefilled.

- [ ] T024 [P] [US2] Adopt `AthleteLink` (T014) in `frontend/src/components/dashboard/MeasurementAlerts.tsx` at its athlete-name render site(s) (today an unconditional link that silently 403-redirects admin sessions). Extend `frontend/src/components/dashboard/__tests__/MeasurementAlerts.test.tsx` with a regression test: an admin session renders a plain `<span>` (no navigation attempted), a coach session renders a working link — must fail on unfixed code.
- [ ] T025 [P] [US2] Adopt `AthleteLink` in `frontend/src/components/competitions/tabs/AthletesTab.tsx`. Extend `frontend/src/components/competitions/tabs/__tests__/AthletesTab.test.tsx` with the same admin-vs-coach regression assertion.
- [ ] T026 [P] [US2] Adopt `AthleteLink` in `frontend/src/components/competitions/tabs/InsightsTab.tsx`. Extend `frontend/src/components/competitions/tabs/__tests__/InsightsTab.test.tsx` with the same admin-vs-coach regression assertion.
- [ ] T027 [P] [US2] Adopt `AthleteLink` in `frontend/src/routes/training/AthleteNewsletterDetailPage.tsx`. Extend `frontend/src/routes/training/AthleteNewsletterDetailPage.test.tsx` with the same admin-vs-coach regression assertion.
- [ ] T028 [P] [US2] Adopt `ErrorState` (T009, with `onRetry`) in `frontend/src/routes/training/SessionsListPage.tsx` (~lines 70-74, replacing the static red-text paragraph with no retry). Extend `frontend/src/routes/training/SessionsListPage.test.tsx` with a regression test: on query error a "Reintentar" control renders and clicking it re-triggers the failed query — must fail on unfixed code.
- [ ] T029 [P] [US2] Adopt `ErrorState` in `frontend/src/routes/athletes/AthletesListPage.tsx` (~lines 143-147). Create `frontend/src/routes/athletes/AthletesListPage.test.tsx` (no test file exists today) with the same retry regression assertion.
- [ ] T030 [P] [US2] Adopt `ErrorState` in `frontend/src/routes/dashboard/DashboardPage.tsx` (~lines 18-22). Extend `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx` with the same retry regression assertion.
- [ ] T031 [US2] Adopt `ErrorState` (with `isColdStart` support) in `frontend/src/routes/calendar/CalendarPage.tsx` (lines 118-122, replacing the static "No se pudieron cargar los eventos" paragraph that has no retry). Extend `frontend/src/routes/calendar/CalendarPage.test.tsx` with a regression test for the retry affordance, plus an assertion that a cold-start-classified failure renders the "waking" copy rather than an error tone.
- [ ] T032 [US2] Fix `handleDateClick` in `frontend/src/routes/calendar/CalendarPage.tsx` (lines 55-57 — today an empty callback with only an aspirational comment): import `useNavigate` from `react-router-dom` and call `navigate(\`/calendar/events/new?date=${dateStr}\`)`; no receiving-side change is needed — `frontend/src/routes/calendar/EventFormPage.tsx:16` already reads `searchParams.get("date")` and prefills. Extend `frontend/src/routes/calendar/CalendarPage.test.tsx` with a regression test asserting a click on an empty day triggers navigation to `/calendar/events/new?date=<the clicked date>` — must fail on unfixed code (today's handler is a no-op). Same file as T031 — run after it.
- [ ] T033 [P] [US2] Add an exported `currentSeason()` helper to `frontend/src/lib/datetime.ts`, deriving the current year in `CLUB_TIMEZONE` (reuse the `Intl.DateTimeFormat("en-CA", {timeZone: CLUB_TIMEZONE})` extraction pattern already used inside `formatRelativeDay`, lines 168-190). Add a test in `frontend/src/lib/__tests__/datetime.test.ts` that mocks the system clock near a year boundary and asserts the helper tracks `CLUB_TIMEZONE` rather than a naive `new Date().getFullYear()`.
- [ ] T034 [US2] Replace the hardcoded `const CURRENT_SEASON = 2026;` in `frontend/src/routes/competitions/insights/InsightsHubPage.tsx` (line 18, consumed at lines 53, 74, 82) with `currentSeason()` imported from `lib/datetime.ts`. Extend `frontend/src/routes/competitions/insights/__tests__/InsightsHubPage.test.tsx` with a regression test that mocks the clock to a non-2026 year and asserts the rendered season link/text follows it — must fail on unfixed code. Depends on T033.
- [ ] T035 [US2] Add `NewsletterStatusSummaryItem` and `NewsletterStatusSummary` Pydantic schemas to `backend/app/schemas/athlete_newsletter.py` per `contracts/newsletter-status-summary.md`: item = `athlete_id: int`, `newsletter_id: int | None`, `status` restricted to `"none" | "draft" | "sent"`, `generated_at: datetime | None`, `sent_at: datetime | None`; summary = `year: int`, `month: int`, `items: list[NewsletterStatusSummaryItem]`.
- [ ] T036 [US2] Add `GET /api/training/athlete-newsletters/summary` to `backend/app/routers/athlete_monthly_newsletters.py`: create a new `training_router = APIRouter()` in the same file; validate `year` (2020–2100) and `month` (1–12) query params (422 on violation); RBAC via `Depends(require_role([UserRole.admin, UserRole.coach]))` (same dependency already imported from `app.dependencies` in this file); resolve the requesting coach's own club(s) using the pattern already established in `backend/app/routers/alerts.py`'s `_coach_club_ids(user)` (`user.club_memberships` filtered to `ClubRole.coach`; admin sees all / may pass no filter) rather than a path `club_id`; return exactly one item per **active** athlete in scope for the given period (`status: "none"` when no newsletter row exists) via a single grouped/left-joined query — no per-athlete queries. Register the router in `backend/app/main.py`: extend the existing import on line 17 to also import `training_router as newsletter_training_router`, and add `app.include_router(newsletter_training_router, prefix="/api/training", tags=["athlete-newsletters"])` near lines 89-90. Depends on T035.
- [ ] T037 [P] [US2] Create `backend/tests/routers/test_newsletter_status_summary_router.py`, following the `SimpleNamespace` + `app.dependency_overrides` + `httpx.AsyncClient` pattern in `backend/tests/routers/test_athlete_monthly_newsletters_router.py`: happy path (coach role, 200, one item per active club athlete including a `status: "none"` case), RBAC-negative (parent role → 403), validation-negative (`month=13` → 422), and an assertion (mock/spy call count on the DB session, or an equivalent query-count check) proving the endpoint issues a constant number of queries regardless of roster size. Depends on T036.
- [ ] T038 [US2] Create `frontend/src/hooks/training/useNewsletterStatusSummary.ts` — a TanStack Query hook calling `GET /api/training/athlete-newsletters/summary?year=&month=`, keyed `["newsletter-status-summary", userId, year, month]` (privacy pattern per `frontend/src/api/athleteNewsletters.ts:171-179` — userId first, for cache isolation). Migrate `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx` off the per-athlete `useNewsletterForAthlete`/`useAthleteNewsletters` fan-out (the local hook at lines ~71-84, invoked per card at ~line 720) onto this one hook; keep `useAthleteNewsletters` (`frontend/src/api/athleteNewsletters.ts:171`) for the athlete detail view only. Depends on T036 (endpoint must exist).
- [ ] T039 [US2] Add a regression test proving `AthleteNewslettersDashboardPage` issues exactly ONE newsletter-status HTTP request regardless of roster size — extend `frontend/src/routes/training/AthleteNewslettersDashboardPage.test.tsx` with an MSW request-count spy (per quickstart.md), seeded with e.g. 25 athletes; must fail against the pre-T038 code (today: N requests, one per athlete). Depends on T038 (same file).
- [ ] T040 [US2] Add a pending affordance (spinner + "Generando…") to the single-athlete "Generar" button in `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx` (~lines 189-200, today only toggles `disabled`), matching the `Loader2` + label-swap pattern already used in `frontend/src/routes/training/ReportDetailPage.tsx:487-489` / `SessionWizard.tsx:571`. Extend the same test file with a regression assertion that the spinner/"Generando…" label appears while `generateMutation.isPending`. Depends on T038/T039 (same file).

**Checkpoint**: US2 is independently functional and testable — no dead-end links, retry everywhere, correct calendar/season behavior, and a batched newsletter summary. Combined with US1, the MVP (Phase 1+2+US1+US2) is complete.

---

## Phase 5: User Story 3 - One consistent feedback language (Priority: P2)

**Goal**: Every action responds the same way everywhere: destructive actions use one confirmation dialog with safe defaults, long-running work shows progress on the triggering control, outcomes are confirmed with brief non-blocking notifications, and multi-step flows announce each step to assistive technology.

**Independent Test**: Trigger every destructive action (delete athlete, media, session cancellation with parent notification) and every long-running generation (report, newsletter, AI analysis): confirm one dialog pattern (safe default focus, Escape dismisses, focus returns), visible in-progress states, and consistent completion notifications; walk both wizards with a screen reader and verify step announcements.

- [ ] T041 [P] [US3] Migrate the `ConfirmModal` call sites to `ConfirmDialog` (T011, `tone="default"`) — fixes the `ConfirmModal.tsx:66` autoFocus-on-confirm bug by construction. Verified render sites: `frontend/src/routes/training/SessionsListPage.tsx`, `frontend/src/routes/training/AthleteNewsletterDetailPage.tsx`, `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx`, `frontend/src/components/competitions/insights/StaleAnalysisBadge.tsx`, `frontend/src/components/competitions/insights/AnalyzeAthleteButton.tsx`, `frontend/src/components/calendar/EventDrawer.tsx`. Before starting, re-run `grep -rn "<ConfirmModal" frontend/src` to confirm no additional site exists (research cites 9 render instances total — some files may render it more than once). Update each site's existing test to assert `ConfirmDialog` renders instead of `ConfirmModal`.
- [ ] T042 [P] [US3] Migrate the 5 `ConfirmDeleteDialog` call sites to `ConfirmDialog` (`tone="danger"`): `frontend/src/routes/parents/ParentDetailPage.tsx`, `frontend/src/routes/competitions/CompetitionsListPage.tsx`, `frontend/src/routes/competitions/CompetitionDetailPage.tsx`, `frontend/src/routes/athletes/AthleteDetailPage.tsx`, `frontend/src/routes/athletes/AthleteFormPage.tsx`. Update each site's existing test to assert the delete confirmation opens with Cancel focused.
- [ ] T043 [P] [US3] Replace `window.confirm(...)` in `frontend/src/components/training/MediaGallery.tsx` (~line 133, delete-media guard) with `ConfirmDialog` (`tone="danger"`). Create `frontend/src/components/training/MediaGallery.test.tsx` (no test file exists today) with a regression test asserting no `window.confirm` call occurs and the dialog renders instead — must fail on unfixed code.
- [ ] T044 [P] [US3] Replace `window.confirm(...)` in `frontend/src/routes/competitions/CompetitionFormPage.tsx` (~line 471, unsaved-changes guard on cancel) with `ConfirmDialog` (`tone="default"`). Create `frontend/src/routes/competitions/CompetitionFormPage.test.tsx` (no test file exists today) with the matching regression test.
- [ ] T045 [P] [US3] Rebuild `frontend/src/components/training/NotifyParentsDialog.tsx` on the Radix-backed `frontend/src/components/ui/dialog.tsx` primitive instead of the hand-rolled `<div role="alertdialog">` (lines 124-133 — no focus trap, no Escape-to-close, no focus restoration) — keep all 4 variant bodies (create/update/cancel/attendance, `variantCopy()`) as the dialog's content slot, gaining focus trap + Escape + focus-return by construction; keep this distinct from `ConfirmDialog` per research R3 (custom form body, not a plain yes/no confirm). Extend `frontend/src/components/training/NotifyParentsDialog.test.tsx` with a regression test asserting focus is trapped inside the dialog and Escape closes it — must fail against the pre-rebuild version.
- [ ] T046 [P] [US3] Migrate `frontend/src/components/consent/ConsentStatusPanel.tsx`'s hand-rolled toast (`successMessage` state + `setTimeout`, ~lines 276-281, "Estado de toast simple (sin librería externa)") to sonner's `toast.success(...)`; delete the local state and its rendered banner.
- [ ] T047 [P] [US3] Migrate `frontend/src/components/competitions/import/ImportWizard.tsx`'s `conditionsToast` banner (state at ~line 527, shown/auto-hidden via a 5s `setTimeout` at ~lines 640-650) to a `toast(...)` call fired at the same point (conditions left empty on advance); delete the local state and rendered banner. Verify the existing `frontend/src/components/competitions/import/__tests__/ImportWizard.conditions.test.tsx` still passes, updating its assertions from banner-presence to a sonner toast call/spy.
- [ ] T048 [US3] Migrate `frontend/src/routes/competitions/CompetitionDetailPage.tsx`'s local `ToastBanner` (definition ~line 726, usage ~line 617) to sonner; delete the component. Same file as T042 (`ConfirmDeleteDialog` migration) — run after it.
- [ ] T049 [P] [US3] Migrate `frontend/src/components/race/UnlinkedCompetitorsTab.tsx`'s local `ToastBanner` (~line 432, the pattern `CompetitionDetailPage.tsx`'s own comment cites as its source) to sonner; delete the component.
- [ ] T050 [P] [US3] Wire step-focus management into `frontend/src/components/training/session-wizard/SessionWizard.tsx`: replace its `SessionStepper` usage with the unified `Stepper` (T013); in `goNext()`/`goBack()` (lines ~234-260), move focus to the new step's heading via the `stepHeadingRef` contract on every successful step change, while preserving the existing `trigger(fields, {shouldFocus:true})` validation-failure focus behavior. Add a regression test (extend `frontend/src/components/training/session-wizard/SessionWizard.draftNotes.test.tsx` or add a focused new test file) asserting the new step's heading receives focus after `goNext()` — must fail on unfixed code (no `.focus()` call exists today).
- [ ] T051 [US3] Wire the same step-focus management into `frontend/src/components/competitions/import/ImportWizard.tsx`: replace the inline `function Stepper` (lines 209-243) with the unified `Stepper` (T013); add focus-on-step-change at each `setStep(...)` transition (e.g. ~lines 696, 792, 821). Add a regression test in one of the existing `frontend/src/components/competitions/import/__tests__/ImportWizard.*.test.tsx` files asserting heading focus on step change. Same file as T047 (toast migration) — run after it.

**Checkpoint**: US3 is independently functional and testable — one dialog pattern, one toast standard, both wizards announce steps.

---

## Phase 6: User Story 4 - Recognizably one product on every screen (Priority: P3)

**Goal**: Headers, empty states, error states, status labels, cards, and headings look and behave identically wherever the coach goes, and the documented brand heading font finally renders.

**Independent Test**: Visual sweep across all coach modules: page headers, empty states, error states, and status labels are visibly uniform; headings render in the brand display font from one central definition; no per-screen font or shadow one-offs remain.

> **Scope note**: the file lists below deliberately exclude files already rewritten in US1/US3 (`RubricSliders.tsx`, `DurationPicker.tsx`, `NotifyParentsDialog.tsx`, `ConfirmModal.tsx`, `ConfirmDeleteDialog.tsx` — the last two are retired outright in Polish/T071) and the 9 pages folded into the `PageHeader` rollout (T063/T064), which also absorb those pages' own leftover shadow literals. This keeps every file touched by exactly one US4 task.

### Shadow-literal adoption (177 inline occurrences → `shadow-ring`/`shadow-card` tokens, grouped by directory)

- [ ] T052 [P] [US4] Adopt `shadow-ring` (swap `style={{boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px"}}` → `className="shadow-ring"`) in: `frontend/src/routes/training/ProjectProfilePage.tsx`, `frontend/src/routes/training/ReportDetailPage.tsx`, `frontend/src/routes/training/ReportsListPage.tsx`, `frontend/src/routes/training/SessionAssistantPage.tsx`, `frontend/src/routes/training/AthleteNewsletterDetailPage.tsx`, `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx`, `frontend/src/routes/training/ActivityMatchPage.tsx`, `frontend/src/routes/profile/ProfilePage.tsx`, `frontend/src/routes/profile/ConfirmEmailChangePage.tsx`.
- [ ] T053 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/routes/parents/training/ParentMonthlyOverviewPage.tsx`, `frontend/src/routes/parents/training/ParentSessionsPage.tsx`, `frontend/src/routes/parents/competitions/ParentCompetitionResultsPage.tsx`, `frontend/src/routes/parents/calendar/ParentCalendarPage.tsx`, `frontend/src/routes/parents/MyAthleteDetailPage.tsx`, `frontend/src/routes/parents/ParentDetailPage.tsx`, `frontend/src/routes/parents/ParentsListPage.tsx`.
- [ ] T054 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/routes/competitions/insights/ClubInsightsPage.tsx`, `frontend/src/routes/competitions/insights/SeasonInsightsPage.tsx`, `frontend/src/routes/competitions/CompetitionFormPage.tsx`, `frontend/src/routes/calendar/EventFormPage.tsx`, `frontend/src/routes/activities/ActivityReviewPage.tsx`, `frontend/src/routes/admin/AIHealthPage.tsx`, `frontend/src/routes/NotFoundPage.tsx`, `frontend/src/routes/GonePage.tsx`.
- [ ] T055 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/routes/auth/LoginPage.tsx`, `frontend/src/routes/auth/OnboardingPage.tsx`, `frontend/src/routes/auth/ParentRegisterPage.tsx`, `frontend/src/routes/auth/ResetPasswordPage.tsx`, `frontend/src/routes/auth/ForgotPasswordPage.tsx`.
- [ ] T056 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/training/session-wizard/ai-assistant/SessionAssistantPanel.tsx`, `frontend/src/components/training/session-wizard/ai-assistant/ClarifyQuestionCard.tsx`, `frontend/src/components/training/session-wizard/SessionWizard.tsx`, `frontend/src/components/training/session-wizard/StepGeneral.tsx`, `frontend/src/components/training/session-wizard/StepReview.tsx`, `frontend/src/components/training/session-wizard/StepRouteNotes.tsx`, `frontend/src/components/training/RouteFileDropzone.tsx`, `frontend/src/components/training/SessionFiltersBar.tsx`, `frontend/src/components/training/SessionsTable.tsx`, `frontend/src/components/training/AthleteNewslettersTabPanel.tsx`, `frontend/src/components/training/AthletesMultiSelect.tsx`, `frontend/src/components/training/AttendanceTable.tsx`, `frontend/src/components/training/MediaUploadZone.tsx`, `frontend/src/components/training/MonthlyMetricsTable.tsx`.
- [ ] T057 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/athletes/NutritionalClassification.tsx`, `frontend/src/components/athletes/PercentileCurves.tsx`, `frontend/src/components/athletes/ResearchReferences.tsx`, `frontend/src/components/athletes/TrainingReadiness.tsx`, `frontend/src/components/athletes/AthleteForm.tsx`, `frontend/src/components/athletes/AthleteInfoCard.tsx`, `frontend/src/components/athletes/AthletesTable.tsx`, `frontend/src/components/athletes/GrowthCharts.tsx`, `frontend/src/components/athletes/LinkedParentsCard.tsx`, `frontend/src/components/athletes/MorphologyCard.tsx`, `frontend/src/components/athletes/AnthropometryForm.tsx`, `frontend/src/components/athletes/AnthropometryHistory.tsx`.
- [ ] T058 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/athletes/ai/LaunchAnalysisForm.tsx`, `frontend/src/components/athletes/ai/MiniSparkline.tsx`, `frontend/src/components/athletes/ai/PanoramaView.tsx`, `frontend/src/components/athletes/ai/ComparatorPanel.tsx`, `frontend/src/components/athletes/ai/DistributionChart.tsx`, `frontend/src/components/athletes/ai/EvolutionChart.tsx`, `frontend/src/components/athletes/ai/HeroLastInsightCard.tsx`, `frontend/src/components/athletes/ai/InsightsTimeline.tsx`, `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx`.
- [ ] T059 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/competitions/tabs/InsightsTab.tsx`, `frontend/src/components/competitions/tabs/ResultsTab.tsx`, `frontend/src/components/competitions/tabs/StandingsTab.tsx`, `frontend/src/components/competitions/tabs/AthletesTab.tsx`, `frontend/src/components/competitions/roster/RosterPanel.tsx`, `frontend/src/components/competitions/insights/GroupAnalysisPanel.tsx`, `frontend/src/components/competitions/import/ImportWizard.tsx`, `frontend/src/components/race/EditResultNoteDialog.tsx`, `frontend/src/components/race/UnlinkedCompetitorsTab.tsx`, `frontend/src/components/race/EditConditionsDialog.tsx`.
- [ ] T060 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/parents/ParentContactInfo.tsx`, `frontend/src/components/parents/ParentFormDialog.tsx`, `frontend/src/components/parents/ParentInviteManager.tsx`, `frontend/src/components/parents/ParentsTable.tsx`, `frontend/src/components/parents/ParentAthleteAssignment.tsx`, `frontend/src/components/consent/ConsentRenewalModal.tsx`, `frontend/src/components/consent/ConsentStatusPanel.tsx`, `frontend/src/components/consent/RevokeConsentDialog.tsx`, `frontend/src/components/dashboard/MeasurementAlerts.tsx`.
- [ ] T061 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/onboarding/steps/ConfirmStep.tsx`, `frontend/src/components/onboarding/steps/ConsentStep.tsx`, `frontend/src/components/onboarding/steps/ParentProfileStep.tsx`, `frontend/src/components/onboarding/OnboardingSuccess.tsx`, `frontend/src/components/onboarding/OnboardingWizard.tsx`, `frontend/src/components/onboarding/steps/AccountStep.tsx`, `frontend/src/components/calendar/EventDrawer.tsx`, `frontend/src/components/calendar/EventForm.tsx`, `frontend/src/components/calendar/FiltersBar.tsx`, `frontend/src/components/calendar/AudienceSelector.tsx`, `frontend/src/components/calendar/CalendarShell.module.css`, `frontend/src/components/technique/ExerciseForm.tsx`.
- [ ] T062 [P] [US4] Same `shadow-ring` adoption in: `frontend/src/components/layout/AppShell.tsx`, `frontend/src/components/ai/AthleteCombobox.tsx`, `frontend/src/components/ai/HITLApprovalCard.tsx`, `frontend/src/components/activities/ActivityCard.tsx`, `frontend/src/components/activities/LinkSessionDialog.tsx`, `frontend/src/components/ui/textarea.tsx`.

### Cal Sans / PageHeader rollout (program decision D3 — ship the font; 59 hand-rolled `<h1>` blocks; 115 dead inline font references)

- [ ] T063 [P] [US4] Adopt `PageHeader` (T007) on 4 highest-traffic pages, replacing each hand-rolled `<h1 style={{fontFamily:"'Cal Sans'...}}>` block: `frontend/src/routes/dashboard/DashboardPage.tsx` (also swap its 3 duplicated stat-card inline `boxShadow` strings, ~lines 32,42,56, to `shadow-card`/`StatCard` (T010) while in the file), `frontend/src/routes/training/SessionsListPage.tsx`, `frontend/src/routes/athletes/AthletesListPage.tsx`, `frontend/src/routes/competitions/CompetitionsListPage.tsx` (swap any remaining inline `boxShadow` in these files to `shadow-ring`/`shadow-card` as encountered — they were intentionally left out of T052-T062).
- [ ] T064 [P] [US4] Adopt `PageHeader` on 5 more pages, same treatment: `frontend/src/routes/calendar/CalendarPage.tsx`, `frontend/src/routes/athletes/AthleteDetailPage.tsx` (inline font at lines ~481,681,733,752), `frontend/src/routes/training/SessionDetailPage.tsx` (~line 561), `frontend/src/routes/competitions/CompetitionDetailPage.tsx` (~line 443), `frontend/src/routes/competitions/insights/InsightsHubPage.tsx` (~lines 40,68,103) — swap any remaining inline `boxShadow` in these files to `shadow-ring`/`shadow-card` as encountered.
- [ ] T065 [US4] Remove the remaining inline Cal Sans `style={{fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600}}` objects not covered by T063/T064 — start with the primitive itself, `frontend/src/components/ui/dialog.tsx`'s `DialogTitle` (~lines 99-106, baked into every dialog in the app), then the remaining call sites (e.g. `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx:228`, `frontend/src/components/competitions/insights/GroupAnalysisPanel.tsx:134`, `frontend/src/components/competitions/chat/CompetitionChatPanel.tsx:233`, `frontend/src/routes/training/SessionAssistantPage.tsx:89`, and the rest of the ~84 files cited in `docs/17-coach-ux-redesign/agent-reports/02-component-architecture.md` item 9) — replace each with the `font-display` utility class. Re-grep `fontFamily: "'Cal Sans'` across `frontend/src` before finishing to confirm zero remain. Run after T063, T064 (heavy file overlap with the whole app).

### Token integrity, remaining fixes, documentation

- [ ] T066 [P] [US4] Fix the 7 broken semantic-token classes (Tailwind v4 cannot generate a utility for an undefined `@theme` color, so these are silent no-ops): in `frontend/src/components/onboarding/OnboardingStepper.tsx`, replace `border-muted-foreground/30 bg-muted text-muted-foreground` (incomplete-step styling), the two `text-muted-foreground/60` occurrences, the two `text-foreground` occurrences, and the `bg-muted` progress-bar occurrence with real project vocabulary (e.g. `border-mid-gray/30 bg-light-gray text-mid-gray`, `text-charcoal`, as fits each spot); in `frontend/src/components/ai/AnthropometricRecordExplanationCard.tsx` (line 100), delete the dead `text-muted-foreground` class from `className="mt-3 text-[13px] text-muted-foreground text-mid-gray"`, leaving the already-functioning `text-mid-gray`.
- [ ] T067 [P] [US4] In `frontend/src/style.css`, delete the dead lime-accent block (`--color-accent`, `--color-accent-dark`, `--color-accent-light` — confirmed zero usages outside `style.css` itself) from both the `:root` and `@theme` blocks; change `--color-link-blue`'s value in both blocks from the repeated literal `#20b7c9` to `var(--color-primary)` so there is one source of truth. Do NOT rename any `text-link-blue`/`bg-link-blue`/`ring-link-blue`/`border-link-blue` call sites (30+ files) — that app-wide color-semantics rename is explicitly deferred to feature 033 per spec.md's Assumptions.
- [ ] T068 [US4] Migrate the 16 `.shadow-ring-soft` call sites to the canonical `shadow-card` utility (decided in T006), then delete the now-unused `.shadow-ring-soft` utility class (`frontend/src/style.css` lines 205-211) and the deprecated `--shadow-ring-soft` custom property: `frontend/src/components/ui/card.tsx`, `frontend/src/components/technique/CatalogGrid.tsx`, `frontend/src/components/strength/CatalogGrid.tsx`, `frontend/src/components/parents/portal/ChildCard.tsx`, `frontend/src/components/parents/ParentSessionCard.tsx`, `frontend/src/components/parents/ReadOnlyAttendanceRow.tsx`, `frontend/src/components/parents/MonthlyAveragesBanner.tsx`, `frontend/src/components/layout/AppShell.tsx`, `frontend/src/components/intervals/TemplatePicker.tsx`, `frontend/src/components/competitions/chat/CompetitionChatPanel.tsx`, `frontend/src/routes/parents/training/ParentMonthlyOverviewPage.tsx`, `frontend/src/routes/parents/training/ParentSessionDetailPage.tsx`, `frontend/src/routes/parents/training/ParentSessionsPage.tsx`, `frontend/src/routes/parents/competitions/ParentCompetitionResultsPage.tsx`, `frontend/src/routes/parents/calendar/ParentCalendarPage.tsx`, `frontend/src/routes/parents/calendar/ParentEventDetailPage.tsx`. Run after T053, T062, and T067 (all touch `AppShell.tsx`, the parent route files, or `style.css`).
- [ ] T069 [US4] Adopt `EmptyState` (T008) on the "sin resultados" branches of `frontend/src/routes/training/SessionsListPage.tsx`, `frontend/src/routes/athletes/AthletesListPage.tsx`, `frontend/src/routes/competitions/CompetitionsListPage.tsx` (use its existing icon+copy pattern as the reference — report04 calls it the most polished empty state in the app today), and `frontend/src/routes/calendar/CalendarPage.tsx`, replacing each page's duplicated ad hoc empty-state block. Run after T063, T064 (same files).
- [ ] T070 [P] [US4] Update `docs/05-design-system/design.md` to match shipped reality: §3 Typography (lines 54-90) — Cal Sans is now actually self-hosted and loading; §2 Color Palette (lines 21-53) — document the real hex values from `style.css` (charcoal `#2f2f2f`, mid-gray `#717171`, teal `--color-primary`/`--color-link-blue` merged per T067) and the 4-tier semantic status scale added in T004; remove the lime-accent mention (retired in T067); §6 Depth & Elevation (lines 158-181) — document `shadow-card`/`shadow-ring` as the two canonical, Tailwind-auto-generated shadow utilities (`.shadow-ring-soft` retired in T068).

**Checkpoint**: All four user stories are independently functional. The coach experience is visually and behaviorally consistent app-wide.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Folder hygiene, final documentation cross-check, and the full validation gate before this feature is considered done and 029 begins.

- [ ] T071 [P] Delete `frontend/src/components/common/ConfirmModal.tsx` and `frontend/src/components/common/ConfirmDeleteDialog.tsx` (fully superseded by `ConfirmDialog`, T011, once every call site migrated in T041/T042) and remove the now-empty `frontend/src/components/common/` directory. Depends on T041, T042.
- [ ] T072 [P] Move `frontend/src/components/shared/PHVBadge.tsx` (and its test `frontend/src/components/shared/PHVBadge.test.tsx`) to `frontend/src/components/athletes/PHVBadge.tsx` (test alongside, matching that directory's convention); update its 5 importers: `frontend/src/components/athletes/AthleteInfoCard.tsx`, `frontend/src/components/athletes/AthletesTable.tsx`, `frontend/src/components/athletes/AnthropometryForm.tsx`, `frontend/src/components/athletes/AnthropometryHistory.tsx`, `frontend/src/components/ai/AIGeneratedContent.tsx`.
- [ ] T073 Run the full frontend validation suite per quickstart.md: `cd frontend && npm run typecheck && npm test` — confirm zero jest-axe violations across every new/changed page- and dialog-level component (Foundational kit + US1-US4 rewrites) and that every regression test introduced in T018-T053/T065 passes.
- [ ] T074 Run the full backend validation suite: `cd backend && source .venv/bin/activate && pytest` — confirm `test_newsletter_status_summary_router.py` (T037) passes alongside the full existing suite with no regressions from the schema/router/`main.py` changes (T035/T036).
- [ ] T075 Run the Playwright e2e suite (Chromium preinstalled — do NOT run `playwright install`): `cd frontend && npm run test:e2e`, with particular attention to `e2e/target-size.spec.ts` (T023) and the existing `e2e/cold-start.spec.ts` (must still pass after the `ErrorState`/`isColdStart` changes in T009/T028-T031).
- [ ] T076 Verify the performance guards (constitution IV, SC-009): run `cd frontend && npm run build` and compare route-bundle sizes against the pre-028 baseline (flag any route regressing ≥10%, per the `sonner`/`@fontsource/cal-sans` budget analysis in plan.md's Constitution Check); run a Lighthouse pass (mid-tier mobile profile, simulated slow 4G/3G) against `/dashboard` and `/athletes`, confirming LCP ≤2.5s.

**Checkpoint**: Feature 028 complete. `contracts/shared-components.md` is a stable, validated API — features 029–033 may build on it.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. All tasks touch shared config (`package.json`, `style.css`) — sequential within the phase, no `[P]`.
- **Foundational (Phase 2)**: Depends on Setup (needs the shadcn primitives and tokens from T002-T005). **BLOCKS all user stories.**
- **US1 (Phase 3) and US2 (Phase 4)**: Both P1. Depend only on Foundational. Their file sets are fully disjoint (verified) — **run in parallel** per the priority-order rule "both P1, parallelizable after Foundational."
- **US3 (Phase 5)**: Depends on Foundational (`ConfirmDialog` T011, `Stepper` T013). Sequenced after US1+US2 complete — several US3 files (`SessionsListPage.tsx`, `AthleteNewsletterDetailPage.tsx`, `AthleteNewslettersDashboardPage.tsx`, `CompetitionDetailPage.tsx`, `CalendarPage.tsx`'s sibling files) are also touched by US1/US2 tasks, so starting only after both P1 stories land avoids rebase churn.
- **US4 (Phase 6)**: Depends on Foundational; sequenced after US3 — US4's `PageHeader`/shadow sweep touches dozens of files across the whole app (including several US3 retired/rebuilt files: `NotifyParentsDialog.tsx`, the two `ConfirmModal`/`ConfirmDeleteDialog` source files, `ImportWizard.tsx`, `CompetitionDetailPage.tsx`), so it must run last among the stories.
- **Polish (Phase 7)**: Depends on all stories — T071 needs US3's dialog migrations done; T073-T076 are whole-suite gates that only make sense once every other phase is complete.
- **Downstream**: Features 029-033 consume `contracts/shared-components.md` as a **frozen API** — once Foundational (T007-T017) ships, those features may start building against `PageHeader`/`EmptyState`/`ErrorState`/`StatCard`/`ConfirmDialog`/`StatusBadge`/`Stepper`/`AthleteLink` without waiting for US1-US4/Polish, as long as no later 028 task changes those props (only additive extensions are permitted, per the contract's own header).

### User Story Dependencies

- **US1 (P1)**: No dependency on US2/US3/US4. Independently testable per its Independent Test above.
- **US2 (P1)**: No dependency on US1/US3/US4. Independently testable per its Independent Test above.
- **US3 (P2)**: Functionally independent of US1/US2 (no shared files), but sequenced after them per priority order.
- **US4 (P3)**: Functionally independent of US1/US2/US3 in outcome (visual consistency), but sequenced last because it touches the largest number of files and several US3-retired components.

### Within Each Phase

- Foundational: all 8 shared components (T007-T014) plus `RouteFallback` (T016) can be built in parallel; `Toaster` mount (T015) and its Suspense adoption (T017) are sequential (same file, `App.tsx`).
- US1: the 4 independent fixes (T018, T019, T021, T022) run in parallel; the contrast pass (T020) and the e2e spec (T023) are sequential gates over the rest.
- US2: the 4 `AthleteLink` sites and 3 of the 4 `ErrorState` sites are parallel; `CalendarPage.tsx`'s two fixes (T031→T032) are sequential (same file); the backend trio (T035→T036→T037) and the frontend trio (T038→T039→T040) are each sequential (schema-before-endpoint-before-tests; hook-before-migration-before-polish).
- US3: 9 of 11 tasks are parallel (disjoint files); T048 waits on T042 and T051 waits on T047 (same files).
- US4: the 11 shadow-sweep tasks (T052-T062) and the 2 `PageHeader` batches (T063-T064) are all mutually parallel (disjoint files by construction); T065 (broad font sweep), T068 (`.shadow-ring-soft` migration) and T069 (`EmptyState` rollout) each wait on the tasks that share their files.

### Parallel Opportunities

- All Setup tasks touch shared config files — no meaningful within-phase parallelism, but the phase itself is short.
- Once Foundational completes, US1 and US2 can be staffed by two different people/agents simultaneously.
- Within Foundational and within US4, the majority of tasks are `[P]` and disjoint — these are the two best phases to split across multiple agents at once.

---

## Parallel Execution Examples

```bash
# Set 1 — Foundational component builds (after Setup, T001-T006 done):
Task: "T007 Create PageHeader in frontend/src/components/shared/PageHeader.tsx + test"
Task: "T008 Create EmptyState in frontend/src/components/shared/EmptyState.tsx + test"
Task: "T009 Create ErrorState + isColdStartError in frontend/src/components/shared/ErrorState.tsx + test"
Task: "T010 Create StatCard in frontend/src/components/shared/StatCard.tsx + test"
Task: "T011 Create ConfirmDialog in frontend/src/components/shared/ConfirmDialog.tsx + test"
Task: "T012 Create StatusBadge in frontend/src/components/shared/StatusBadge.tsx + test"
Task: "T013 Create Stepper in frontend/src/components/shared/Stepper.tsx + test"
Task: "T014 Create AthleteLink in frontend/src/components/shared/AthleteLink.tsx + test"
Task: "T016 Create RouteFallback in frontend/src/components/shared/RouteFallback.tsx + test"

# Set 2 — US1 + US2 running together (after Foundational, both P1):
Task: "T018 Rewrite RubricSliders.tsx to ToggleGroup steppers"          # US1
Task: "T024 Adopt AthleteLink in MeasurementAlerts.tsx"                  # US2
Task: "T028 Adopt ErrorState in SessionsListPage.tsx"                    # US2
Task: "T033 Add currentSeason() helper to lib/datetime.ts"               # US2

# Set 3 — US4 shadow-literal sweep (after US3, all directory-disjoint):
Task: "T052 shadow-ring sweep: routes/training remnant + routes/profile"
Task: "T053 shadow-ring sweep: routes/parents"
Task: "T056 shadow-ring sweep: components/training remnant"
Task: "T057 shadow-ring sweep: components/athletes core"
Task: "T058 shadow-ring sweep: components/athletes/ai"
Task: "T059 shadow-ring sweep: components/competitions + race"
```

---

## Implementation Strategy

### MVP First (Phase 1 + Phase 2 + US1 + US2 — T001-T040)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) — the shared component kit and token groundwork.
2. Complete Phase 3 (US1) and Phase 4 (US2) in parallel — these are the two confirmed-defect, P1 stories: glove-friendly ≥48px controls everywhere, zero dead-end links, retry-on-failure everywhere, a working calendar day-tap, a self-correcting season, and a batched newsletter summary (kills the N+1 fan-out).
3. **STOP and VALIDATE**: run quickstart.md's automated + manual validation for US1/US2 (target-size e2e, dead-end sweep, calendar prefill). This alone satisfies SC-001 through SC-004 and SC-007.
4. Deploy/demo if ready — this is the "reliability wins" milestone the coach will feel immediately.

### Incremental Delivery

1. Setup + Foundational → foundation ready; features 029-033 may start consuming the contract.
2. US1 + US2 → MVP, test independently, deploy/demo.
3. US3 → one consistent feedback language (SC-005, SC-006); test independently (screen-reader wizard walk, dialog audit); deploy/demo.
4. US4 → visual consistency + shipped brand font (SC-008); can itself be delivered in slices, since the 11 shadow-sweep tasks (T052-T062) are independent of the 2 `PageHeader` batches (T063-T064), which are independent of the token-integrity fixes (T066-T067); deploy/demo incrementally.
5. Polish → folder hygiene, full-suite validation, performance guard — the final gate before 029 begins.

### Parallel Team Strategy

With multiple agents/developers available:

1. Complete Setup + Foundational together (short, mostly sequential).
2. Once Foundational is done: Agent/Dev A takes US1, Agent/Dev B takes US2 — fully disjoint files.
3. Once both land: proceed to US3 as a single stream (its tasks are mostly parallel internally but the story as a whole is best kept coherent given it touches many of the same dialog/toast patterns).
4. US4's 19 tasks are the best-suited for splitting across 3-4 agents at once (11 shadow-sweep + 2 PageHeader + 6 fix/doc tasks, almost all `[P]`).
5. Polish is a single stream (validation gates must run after everything else).

---

## Notes

- `[P]` tasks touch different files and have no unresolved dependency within their phase — verified file-by-file during generation (see the Phase 6 scope note for how overlaps with earlier phases were resolved).
- `[Story]` labels (US1-US4) map every phase-3-through-6 task to its spec.md user story for traceability; Setup/Foundational/Polish carry no label because they are cross-cutting.
- Every bug-fix task states its own regression test and the "must fail on unfixed code" condition, per constitution Principle II.
- Commit after each task or logical group; stop at any phase checkpoint to validate independently.
- Avoid: vague tasks, silent same-file conflicts, cross-story dependencies that would break US1/US2 independence.
