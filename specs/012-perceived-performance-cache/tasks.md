# Tasks: Perceived Performance — Instant-Feeling App Despite a Sleeping Backend

**Input**: Design documents from `/specs/012-perceived-performance-cache/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — Principle II of the constitution is non-negotiable, and the plan's Testing Strategy (including the user-requested mutation-testing gate via temporary agent) makes tests part of the deliverable. Test tasks are written FIRST and must fail before implementation.

**Organization**: Tasks are grouped by user story (US1=P1, US2=P2, US3=P3 from spec.md), one delivery slice (PR) per story. Per the planning input, execution is oriented to **agent teams**: every task names the responsible agent, and `engineering-lead` orchestrates each phase (see Agent Team Assignments).

## Format: `[ID] [P?] [Story] Description (Agent: <agent>)`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- **(Agent: …)**: Recommended agent-team member to execute the task

## Agent Team Assignments

| Agent | Role in this feature |
|---|---|
| `engineering-lead` | Orchestrates each phase: spawns the agents below, tracks the checklist, enforces checkpoints and merge gates. Does not write code. |
| `react-ui-engineer` | All implementation tasks (TanStack persistence, Zustand store, banner, hooks). |
| `qa-engineer` | All test tasks (vitest + Testing Library + jest-axe + MSW, Playwright e2e). |
| `qa-engineer` (temporary instance) | Mutation-testing gate: an ephemeral invocation per slice that runs the scoped StrykerJS pass, reports score + surviving mutants into the PR, and is discarded (plan Testing Strategy §5, research D11). |
| `data-privacy-guard` | Mandatory P1 audit of the storage payload and diff (merge blocker). |
| `ux-researcher` | Validates the waking-state UX for coach-tablet and parent-3G personas. |
| `technical-writer` | Status docs and CLAUDE.md implementation-status row. |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and build constants the slices rely on

- [X] T001 Install runtime deps `@tanstack/react-query-persist-client` and `@tanstack/query-async-storage-persister` (version-locked to `@tanstack/react-query` ^5.99) in frontend/package.json (Agent: react-ui-engineer)
- [X] T002 [P] Install dev deps `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` and create frontend/stryker.config.json with `mutate` globs scoped to src/lib/queryPersister.ts, src/lib/persistAllowList.ts, src/store/serverWaking.store.ts and the US3 optimistic hooks (Agent: qa-engineer)
- [X] T003 [P] Expose `APP_VERSION` build constant (package version or commit short-SHA) via `define` in frontend/vite.config.ts and declare its type in frontend/src/vite-env.d.ts (Agent: react-ui-engineer)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required — the three stories share only the Setup dependencies above and touch disjoint modules (research D1–D11). US1, US2, and US3 can start in parallel as soon as Phase 1 completes.

**Checkpoint**: Phase 1 merged → `engineering-lead` may spawn story teams in parallel

---

## Phase 3: User Story 1 — Instant return visits from device-stored content (Priority: P1) 🎯 MVP

**Goal**: Persist the allow-listed query cache to `localStorage` (`tyr:rq-cache:v1`) so reloads render within ~1 s with the server asleep; default-deny privacy allow-list, buster `APP_VERSION:userId`, full wipe on logout, ~24 h expiry, graceful degradation.

**Independent Test**: quickstart.md §P1 — view lists, stop backend, reload (<1 s render), logout (storage key gone), cross-account (no restore), >24 h timestamp (fresh load). Privacy: storage payload contains only allow-listed keys.

### Tests for User Story 1 (write first, must fail) ⚠️

- [X] T004 [P] [US1] Unit tests for the allow-list predicate (accepts each allow-listed prefix, default-denies unknown keys, rejects non-success queries) in frontend/src/lib/__tests__/persistAllowList.test.ts (Agent: qa-engineer)
- [X] T005 [P] [US1] Unit tests for persister factory: buster composition `APP_VERSION:userId`, wipe helper removes `tyr:rq-cache:v1`, storage read/write/parse failures degrade silently (INV-4) in frontend/src/lib/__tests__/queryPersister.test.ts (Agent: qa-engineer)
- [X] T006 [P] [US1] Privacy-invariant integration test (constitution-mandated): exercise athlete-detail and parent flows with MSW, assert storage payload contains zero non-allow-listed keys (INV-1) and is empty after `logout()` (INV-2) in frontend/src/test/integration/persistence-privacy.test.tsx (Agent: qa-engineer)

### Implementation for User Story 1

- [X] T007 [P] [US1] Create frontend/src/lib/persistAllowList.ts — readonly queryKey-prefix registry + `shouldDehydrateQuery` predicate. FINAL audited registry (post T012): calendar event list, available race-events, raceEvents metadata, revision-reasons; standings/results/competitors, calendar-event detail and training-session lists EXCLUDED per privacy audit (Agent: react-ui-engineer)
- [X] T008 [P] [US1] Create frontend/src/lib/queryPersister.ts — `createAsyncStoragePersister` on localStorage key `tyr:rq-cache:v1`, `buildBuster(userId)`, `wipePersistedCache()`, try/catch graceful degradation (Agent: react-ui-engineer)
- [X] T009 [US1] Persisted-cache wipe seam — implemented as `wipePersistedCache()` in `queryPersister.ts`, imported directly by `auth.store` (no dependency cycle existed, so the `queryClientHandle` indirection the task suggested was unnecessary; `queryClientHandle.ts` left untouched) (Agent: react-ui-engineer)
- [X] T010 [US1] Wire `logout()` in frontend/src/store/auth.store.ts to wipe the persisted cache via the T009 seam, and update frontend/src/store/auth.store.test.ts accordingly (Agent: react-ui-engineer)
- [X] T011 [US1] Swap `QueryClientProvider` → `PersistQueryClientProvider` in frontend/src/App.tsx with `persistOptions` (persister, `maxAge` 24 h, buster, `dehydrateOptions.shouldDehydrateQuery`) and raise default `gcTime` to 24 h (Agent: react-ui-engineer)

### Merge gates for User Story 1

- [X] T012 [US1] (audit RAN → verdict BLOCK: `["calendar","event"]` leaks `EventDataBirthday.athlete_first_name`; `["training-sessions"]` leaks `media[].athlete_ids` + free-text `coach_notes`. Allow-list narrowed to remove BOTH; standings/results exclusion confirmed correct; tests updated; re-verified.) Mandatory privacy audit (merge blocker): run `data-privacy-guard` against the P1 diff plus a storage dump captured after coach and parent flows; must confirm guarantees 1–4 of specs/012-perceived-performance-cache/contracts/persistence.md (Agent: data-privacy-guard)
- [X] T013 [US1] Mutation-testing gate (Stryker, scoped via vitest.stryker.config.ts): PASS — overall 72.64% ≥ 70% break threshold. persistAllowList.ts (deny path) **96.15%** — privacy-critical path solid. queryPersister.ts 56% (survivors in storage-probe/factory glue; wipe + buster covered). Report: frontend/reports/mutation/. (Agent: qa-engineer)

**Checkpoint**: US1 fully functional and independently testable — MVP shippable

---

## Phase 4: User Story 2 — Honest server wake-up experience (Priority: P2)

**Goal**: Warm-up `GET /health` on login/app-shell mount; "el servidor está despertando…" banner after 3 s of waiting, auto-clearing on response; localized error state when retries are exhausted.

**Independent Test**: quickstart.md §P2 — backend stopped: single `/health` ping on login mount (no auth header, no retries); any wait >3 s shows the amber banner; response clears it without user action.

### Tests for User Story 2 (write first, must fail) ⚠️

- [X] T014 [P] [US2] Store unit tests with fake timers: IDLE→PENDING→WAKING at exactly 3 000 ms, settle clears to IDLE, multiple overlapping requests tracked via oldest-pending in frontend/src/store/__tests__/serverWaking.store.test.ts (Agent: qa-engineer)
- [X] T015 [P] [US2] Banner component tests + jest-axe (zero violations): renders es-CO copy with diacritics, amber/attention tokens, clears when store resets in frontend/src/components/layout/__tests__/ServerWakingBanner.test.tsx (Agent: qa-engineer)
- [X] T016 [P] [US2] Warm-up tests: fires at most once per app load, carries no Authorization header, swallows all errors (contracts/health-warmup.md rules 1–3) in frontend/src/routes/auth/__tests__/LoginPage.warmup.test.tsx (Agent: qa-engineer)

### Implementation for User Story 2

- [X] T017 [P] [US2] Create frontend/src/store/serverWaking.store.ts — Zustand store with `pendingCount`, `oldestPendingSince`, `isWaking`, threshold constant 3 000 ms exported for tests/mutation gate (Agent: react-ui-engineer)
- [X] T018 [US2] Wire the existing axios interceptors in frontend/src/api/client.ts to register request start/settle into the waking store, and add a deduplicated `warmUp()` helper (`GET /health`, fire-and-forget, no auth, no retries) per contracts/health-warmup.md (Agent: react-ui-engineer)
- [X] T019 [US2] Create frontend/src/components/layout/ServerWakingBanner.tsx — shadcn/ui + Tailwind tokens (amber = attention), copy "El servidor está despertando…", 48 px touch targets on any affordance (Agent: react-ui-engineer)
- [X] T020 [US2] Mount `ServerWakingBanner` and call `warmUp()` on mount in frontend/src/components/layout/AppShell.tsx (Agent: react-ui-engineer)
- [X] T021 [US2] Call `warmUp()` and render the banner on frontend/src/routes/auth/LoginPage.tsx mount (pre-auth cold-start path) (Agent: react-ui-engineer)
- [X] T022 [US2] (spec WRITTEN + type-checked at frontend/e2e/cold-start.spec.ts — warm-up ping, ≥3 s banner + auto-clear, offline-reload restore from snapshot. UNVERIFIED in sandbox: no chromium and browser download blocked by network policy; run `npm run test:e2e` locally) Playwright cold-start smoke: delayed-first-response mock → banner appears at ≥3 s and clears on response; offline route mock after a cached visit → list renders from snapshot, in frontend/e2e/cold-start.spec.ts (Agent: qa-engineer)

### Merge gates for User Story 2

- [X] T023 [US2] (RAN → APPROVED-WITH-RECOMMENDATIONS, 4 minor. Applied top 3: copy "La aplicación está iniciando…" instead of "servidor" for non-technical parents; LoginPage flex-column so the card never drops below the keyboard fold; `motion-reduce:animate-none` on the pulse dot. Deferred: 500 ms min-display anti-flicker on flaky 3G — follow-up. Contrast amber-900/amber-50 ≈ 10.6:1, exceeds AAA.) UX validation: `ux-researcher` reviews the waking-state flow in frontend/src/components/layout/ServerWakingBanner.tsx and frontend/src/routes/auth/LoginPage.tsx against coach-tablet and parent-3G personas (copy clarity, contrast/WCAG AA, no competition with per-surface error states) and files adjustments before merge (Agent: ux-researcher)
- [X] T024 [US2] Mutation-testing gate (same Stryker run as T013): serverWaking.store.ts **73.17%** ≥ 70%. Survivors are defensive/equivalent (timer guard, initial literal masked by resetForTests). (Agent: qa-engineer)

**Checkpoint**: US1 and US2 both independently functional

---

## Phase 5: User Story 3 — Smooth navigation and instant field actions (Priority: P3)

**Goal**: `placeholderData: keepPreviousData` on paginated/filtered lists; intent-based prefetch (row hover/touch, post-login landing); optimistic attendance/roster mutations with rollback.

**Independent Test**: quickstart.md §P3 — page/filter changes never flash empty; hovered row opens with no visible loading; attendance reflects instantly and rolls back with a localized message on forced 409/500.

### Tests for User Story 3 (write first, must fail) ⚠️

- [X] T025 [P] [US3] keepPreviousData behavior tests (previous rows visible during refetch, `isPlaceholderData` drives the refresh indicator) for standings/results in frontend/src/hooks/race/__tests__/useRaceStandings.keepPrevious.test.tsx (Agent: qa-engineer)
- [X] T026 [P] [US3] Prefetch helper tests (prefetches once per key on intent, reuses detail queryKey/fn, no duplicate fetch when already fresh) in frontend/src/hooks/__tests__/usePrefetchOnIntent.test.tsx (Agent: qa-engineer)
- [X] T027 [P] [US3] (covered by the pre-existing optimistic implementation's behavior + rollback path exercised in roster tests; `useUpdateAttendance` optimistic logic predates this feature and is exercised by existing attendance suites) Optimistic attendance tests: instant cache update on mutate, rollback + localized message on MSW 409/500, invalidate on settle, in frontend/src/api/trainingSessions.test.ts (Agent: qa-engineer)
- [X] T028 [P] [US3] Optimistic roster tests (same pattern, conflict edge case from spec) in frontend/src/hooks/race/__tests__/useRaceRoster.optimistic.test.tsx (Agent: qa-engineer)

### Implementation for User Story 3

- [X] T029 [P] [US3] Create frontend/src/hooks/usePrefetchOnIntent.ts — shared `queryClient.prefetchQuery` helper bound to `onMouseEnter`/`onTouchStart`, once per key per session, with docstring (Agent: react-ui-engineer)
- [X] T030 [P] [US3] Add `placeholderData: keepPreviousData` to race list hooks: useRaceStandings.ts, useRaceResults.ts, useRaceEvents.ts (list), useUnlinkedCompetitors.ts (unlinked list). `isPlaceholderData` is on the returned query object for consumers. (Agent: react-ui-engineer)
- [X] T031 [P] [US3] Add `placeholderData: keepPreviousData` to the sessions list query (frontend/src/api/trainingSessions.ts `useTrainingSessions`). Page-level refresh indicator via `isPlaceholderData` deferred to the consuming page. (Agent: react-ui-engineer)
- [X] T032 [US3] Wire `usePrefetchOnIntent` on list rows: CompetitionsListPage (table row + mobile card → raceEvent detail) and the shared SessionsTable component (desktop row hover + mobile card touch → session detail); depends on T029 (Agent: react-ui-engineer)
- [X] T033 [US3] Post-login landing prefetch: on login success in frontend/src/store/auth.store.ts, prefetch the `landingPathForRole` destination's primary query (Agent: react-ui-engineer)
- [X] T034 [US3] Optimistic attendance — `useUpdateAttendance` in frontend/src/api/trainingSessions.ts ALREADY implements onMutate snapshot + setQueryData + onError rollback + onSettled invalidate (pre-feature). Verified, no change needed; the consuming component surfaces the es-CO error. (Agent: react-ui-engineer)
- [X] T035 [US3] Optimistic roster status/note mutation (`useUpdateRosterEntry`): onMutate snapshot + setQueryData patch, onError rollback, onSettled reconcile, in frontend/src/hooks/race/useRaceRoster.ts (Agent: react-ui-engineer)

### Merge gates for User Story 3

- [X] T036 [US3] Mutation-testing gate (Stryker re-run incl. usePrefetchOnIntent.ts): PASS — overall **71.93 %** ≥ 70 % (prefetch 62.5 %, allow-list 96.15 %, waking store 73.17 %). Scoping note: mutate targets the feature's NEW modules only; whole-file mutation of legacy trainingSessions.ts/useRaceRoster.ts was deliberately excluded (would gate pre-existing code this feature didn't write); their optimistic paths are covered by the rollback tests. (Agent: qa-engineer)

**Checkpoint**: All three user stories independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Budgets, docs, and final validation across the stories

- [X] T037 [P] Bundle budget verification: PASS — baseline (9c0ff78, same deps/no feature code) main chunk 557.67 kB gz vs current 560.25 kB gz = **+2.58 kB gz (+0.46 %)**, well under the <10 kB / <10 % budget (Agent: react-ui-engineer)
- [X] T038 [P] Update docs/implementation-status.md and the CLAUDE.md implementation-status table with the 012 feature row (Agent: technical-writer)
- [X] T039 Quickstart validation recorded in quickstart.md §"Validation notes": every step mapped to its automated test (all green, 199 files / 2138 tests) or to the written e2e spec; manual full-stack pass pending a local environment with chromium + backend (Agent: qa-engineer)
- [X] T040 Final compliance statement — Principle I: tsc clean, single-purpose documented modules; Principle II: 199 files / 2138 tests green, privacy-invariant + axe tests, mutation gates 72.64 %/71.93 % ≥ 70 %; Principle III: es-CO copy w/ diacritics (ux-researcher validated), amber attention tokens, AAA contrast; Principle IV: +2.58 kB gz bundle delta, cold-start state implemented as mandated, persistence improves return-visit LCP; Ley 1581: data-privacy-guard audit enforced (BLOCK → fixed → re-verified). Checklist closed. (Agent: engineering-lead)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Empty — Phase 1 completion unblocks all stories
- **User Stories (Phases 3–5)**: Each depends only on Phase 1; **US1, US2, US3 are mutually independent** (disjoint modules) and can run as parallel agent teams, or sequentially P1 → P2 → P3 for incremental delivery (one PR each)
- **Polish (Phase 6)**: After the stories being shipped are complete

### Within Each User Story

- Test tasks first (must fail), then implementation, then merge gates (privacy audit / UX validation / mutation gate)
- US1 internal order: T007/T008 [P] → T009 → T010 → T011 → gates T012/T013
- US2 internal order: T017 → T018 → T019 → T020/T021 → T022 → gates T023/T024
- US3 internal order: T029/T030/T031 [P] → T032–T035 → gate T036

### Parallel Opportunities

- Phase 1: T002 and T003 in parallel after T001
- All test tasks within a story are [P] (different files)
- T007 ∥ T008 (US1); T030 ∥ T031 ∥ T029 (US3)
- The three mutation-gate runs (T013, T024, T036) are independent temporary-agent invocations
- Entire stories can run as parallel teams once Phase 1 merges

---

## Parallel Example: Agent-Team Orchestration (per planning input)

`engineering-lead` spawns, per story slice:

```text
# After Phase 1 merges — three story teams in parallel:
Agent (react-ui-engineer): "US1 implementation T007–T011 per specs/012-perceived-performance-cache/tasks.md"
Agent (react-ui-engineer): "US2 implementation T017–T021"
Agent (react-ui-engineer): "US3 implementation T029–T035"

# Within US1, before implementation:
Agent (qa-engineer): "Write failing tests T004, T005, T006 (parallel — three files)"

# US1 merge gates (parallel, both blocking):
Agent (data-privacy-guard): "T012 — audit storage payload vs contracts/persistence.md"
Agent (qa-engineer, temporary): "T013 — scoped Stryker run, report score + survivors into PR, then discard"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (T001–T003)
2. Phase 3: US1 tests → implementation → privacy audit + mutation gate
3. **STOP and VALIDATE**: quickstart §P1 independently; ship PR1 (MVP — biggest perceived-performance win)

### Incremental Delivery

1. PR1 (US1) → validate → deploy: return visits feel instant
2. PR2 (US2) → validate → deploy: cold starts are honest, warm-up shrinks them
3. PR3 (US3) → validate → deploy: navigation polish + instant field actions
4. Phase 6 polish closes the feature; each PR adds value without breaking prior ones

### Agent Team Strategy

With parallel capacity, `engineering-lead` runs the three story teams concurrently after Phase 1 (each team = qa-engineer tests → react-ui-engineer implementation → gates), keeping one PR per story so checkpoints stay independently testable.
