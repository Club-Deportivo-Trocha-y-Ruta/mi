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

- [ ] T001 Install runtime deps `@tanstack/react-query-persist-client` and `@tanstack/query-async-storage-persister` (version-locked to `@tanstack/react-query` ^5.99) in frontend/package.json (Agent: react-ui-engineer)
- [ ] T002 [P] Install dev deps `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` and create frontend/stryker.config.json with `mutate` globs scoped to src/lib/queryPersister.ts, src/lib/persistAllowList.ts, src/store/serverWaking.store.ts and the US3 optimistic hooks (Agent: qa-engineer)
- [ ] T003 [P] Expose `APP_VERSION` build constant (package version or commit short-SHA) via `define` in frontend/vite.config.ts and declare its type in frontend/src/vite-env.d.ts (Agent: react-ui-engineer)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required — the three stories share only the Setup dependencies above and touch disjoint modules (research D1–D11). US1, US2, and US3 can start in parallel as soon as Phase 1 completes.

**Checkpoint**: Phase 1 merged → `engineering-lead` may spawn story teams in parallel

---

## Phase 3: User Story 1 — Instant return visits from device-stored content (Priority: P1) 🎯 MVP

**Goal**: Persist the allow-listed query cache to `localStorage` (`tyr:rq-cache:v1`) so reloads render within ~1 s with the server asleep; default-deny privacy allow-list, buster `APP_VERSION:userId`, full wipe on logout, ~24 h expiry, graceful degradation.

**Independent Test**: quickstart.md §P1 — view lists, stop backend, reload (<1 s render), logout (storage key gone), cross-account (no restore), >24 h timestamp (fresh load). Privacy: storage payload contains only allow-listed keys.

### Tests for User Story 1 (write first, must fail) ⚠️

- [ ] T004 [P] [US1] Unit tests for the allow-list predicate (accepts each allow-listed prefix, default-denies unknown keys, rejects non-success queries) in frontend/src/lib/__tests__/persistAllowList.test.ts (Agent: qa-engineer)
- [ ] T005 [P] [US1] Unit tests for persister factory: buster composition `APP_VERSION:userId`, wipe helper removes `tyr:rq-cache:v1`, storage read/write/parse failures degrade silently (INV-4) in frontend/src/lib/__tests__/queryPersister.test.ts (Agent: qa-engineer)
- [ ] T006 [P] [US1] Privacy-invariant integration test (constitution-mandated): exercise athlete-detail and parent flows with MSW, assert storage payload contains zero non-allow-listed keys (INV-1) and is empty after `logout()` (INV-2) in frontend/src/test/integration/persistence-privacy.test.tsx (Agent: qa-engineer)

### Implementation for User Story 1

- [ ] T007 [P] [US1] Create frontend/src/lib/persistAllowList.ts — readonly queryKey-prefix registry (calendar events, race events, standings, revision reasons, competition lists, session lists) + `shouldDehydrateQuery` predicate, with docstring documenting the FR-002 exclusions (Agent: react-ui-engineer)
- [ ] T008 [P] [US1] Create frontend/src/lib/queryPersister.ts — `createAsyncStoragePersister` on localStorage key `tyr:rq-cache:v1`, `buildBuster(userId)`, `wipePersistedCache()`, try/catch graceful degradation (Agent: react-ui-engineer)
- [ ] T009 [US1] Extend frontend/src/lib/queryClientHandle.ts with a persisted-cache wipe seam (mirrors the existing `queryClient.clear()` singleton pattern) so non-React modules can trigger the wipe; depends on T008 (Agent: react-ui-engineer)
- [ ] T010 [US1] Wire `logout()` in frontend/src/store/auth.store.ts to wipe the persisted cache via the T009 seam, and update frontend/src/store/auth.store.test.ts accordingly (Agent: react-ui-engineer)
- [ ] T011 [US1] Swap `QueryClientProvider` → `PersistQueryClientProvider` in frontend/src/App.tsx with `persistOptions` (persister, `maxAge` 24 h, buster, `dehydrateOptions.shouldDehydrateQuery`) and raise default `gcTime` to 24 h (Agent: react-ui-engineer)

### Merge gates for User Story 1

- [ ] T012 [US1] Mandatory privacy audit (merge blocker): run `data-privacy-guard` against the P1 diff plus a storage dump captured after coach and parent flows; must confirm guarantees 1–4 of specs/012-perceived-performance-cache/contracts/persistence.md (Agent: data-privacy-guard)
- [ ] T013 [US1] Mutation-testing gate via temporary agent: ephemeral qa-engineer runs `npx stryker run` scoped to frontend/src/lib/persistAllowList.ts + frontend/src/lib/queryPersister.ts; require score ≥ 70 % and zero surviving mutants on the deny path and logout wipe; paste report into the PR (Agent: qa-engineer, temporary instance)

**Checkpoint**: US1 fully functional and independently testable — MVP shippable

---

## Phase 4: User Story 2 — Honest server wake-up experience (Priority: P2)

**Goal**: Warm-up `GET /health` on login/app-shell mount; "el servidor está despertando…" banner after 3 s of waiting, auto-clearing on response; localized error state when retries are exhausted.

**Independent Test**: quickstart.md §P2 — backend stopped: single `/health` ping on login mount (no auth header, no retries); any wait >3 s shows the amber banner; response clears it without user action.

### Tests for User Story 2 (write first, must fail) ⚠️

- [ ] T014 [P] [US2] Store unit tests with fake timers: IDLE→PENDING→WAKING at exactly 3 000 ms, settle clears to IDLE, multiple overlapping requests tracked via oldest-pending in frontend/src/store/__tests__/serverWaking.store.test.ts (Agent: qa-engineer)
- [ ] T015 [P] [US2] Banner component tests + jest-axe (zero violations): renders es-CO copy with diacritics, amber/attention tokens, clears when store resets in frontend/src/components/layout/__tests__/ServerWakingBanner.test.tsx (Agent: qa-engineer)
- [ ] T016 [P] [US2] Warm-up tests: fires at most once per app load, carries no Authorization header, swallows all errors (contracts/health-warmup.md rules 1–3) in frontend/src/routes/auth/__tests__/LoginPage.warmup.test.tsx (Agent: qa-engineer)

### Implementation for User Story 2

- [ ] T017 [P] [US2] Create frontend/src/store/serverWaking.store.ts — Zustand store with `pendingCount`, `oldestPendingSince`, `isWaking`, threshold constant 3 000 ms exported for tests/mutation gate (Agent: react-ui-engineer)
- [ ] T018 [US2] Wire the existing axios interceptors in frontend/src/api/client.ts to register request start/settle into the waking store, and add a deduplicated `warmUp()` helper (`GET /health`, fire-and-forget, no auth, no retries) per contracts/health-warmup.md (Agent: react-ui-engineer)
- [ ] T019 [US2] Create frontend/src/components/layout/ServerWakingBanner.tsx — shadcn/ui + Tailwind tokens (amber = attention), copy "El servidor está despertando…", 48 px touch targets on any affordance (Agent: react-ui-engineer)
- [ ] T020 [US2] Mount `ServerWakingBanner` and call `warmUp()` on mount in frontend/src/components/layout/AppShell.tsx (Agent: react-ui-engineer)
- [ ] T021 [US2] Call `warmUp()` and render the banner on frontend/src/routes/auth/LoginPage.tsx mount (pre-auth cold-start path) (Agent: react-ui-engineer)
- [ ] T022 [US2] Playwright cold-start smoke: delayed-first-response mock → banner appears at ≥3 s and clears on response; offline route mock after a cached visit → list renders from snapshot, in frontend/e2e/cold-start.spec.ts (Agent: qa-engineer)

### Merge gates for User Story 2

- [ ] T023 [US2] UX validation: `ux-researcher` reviews the waking-state flow in frontend/src/components/layout/ServerWakingBanner.tsx and frontend/src/routes/auth/LoginPage.tsx against coach-tablet and parent-3G personas (copy clarity, contrast/WCAG AA, no competition with per-surface error states) and files adjustments before merge (Agent: ux-researcher)
- [ ] T024 [US2] Mutation-testing gate via temporary agent: scoped Stryker run on frontend/src/store/serverWaking.store.ts; score ≥ 70 %, report into PR (Agent: qa-engineer, temporary instance)

**Checkpoint**: US1 and US2 both independently functional

---

## Phase 5: User Story 3 — Smooth navigation and instant field actions (Priority: P3)

**Goal**: `placeholderData: keepPreviousData` on paginated/filtered lists; intent-based prefetch (row hover/touch, post-login landing); optimistic attendance/roster mutations with rollback.

**Independent Test**: quickstart.md §P3 — page/filter changes never flash empty; hovered row opens with no visible loading; attendance reflects instantly and rolls back with a localized message on forced 409/500.

### Tests for User Story 3 (write first, must fail) ⚠️

- [ ] T025 [P] [US3] keepPreviousData behavior tests (previous rows visible during refetch, `isPlaceholderData` drives the refresh indicator) for standings/results in frontend/src/hooks/race/__tests__/useRaceStandings.keepPrevious.test.tsx (Agent: qa-engineer)
- [ ] T026 [P] [US3] Prefetch helper tests (prefetches once per key on intent, reuses detail queryKey/fn, no duplicate fetch when already fresh) in frontend/src/hooks/__tests__/usePrefetchOnIntent.test.tsx (Agent: qa-engineer)
- [ ] T027 [P] [US3] Optimistic attendance tests: instant cache update on mutate, rollback + localized message on MSW 409/500, invalidate on settle, in frontend/src/api/trainingSessions.test.ts (Agent: qa-engineer)
- [ ] T028 [P] [US3] Optimistic roster tests (same pattern, conflict edge case from spec) in frontend/src/hooks/race/__tests__/useRaceRoster.optimistic.test.tsx (Agent: qa-engineer)

### Implementation for User Story 3

- [ ] T029 [P] [US3] Create frontend/src/hooks/usePrefetchOnIntent.ts — shared `queryClient.prefetchQuery` helper bound to `onMouseEnter`/`onTouchStart`, once per key per session, with docstring (Agent: react-ui-engineer)
- [ ] T030 [P] [US3] Add `placeholderData: keepPreviousData` + `isPlaceholderData` exposure to race list hooks: frontend/src/hooks/race/useRaceStandings.ts, frontend/src/hooks/race/useRaceResults.ts, frontend/src/hooks/race/useRaceEvents.ts, frontend/src/hooks/race/useUnlinkedCompetitors.ts (Agent: react-ui-engineer)
- [ ] T031 [P] [US3] Add `placeholderData: keepPreviousData` + subtle refresh indicator to the sessions list (frontend/src/api/trainingSessions.ts query + frontend/src/routes/training/SessionsListPage.tsx) (Agent: react-ui-engineer)
- [ ] T032 [US3] Wire `usePrefetchOnIntent` on list rows of frontend/src/routes/competitions/CompetitionsListPage.tsx and frontend/src/routes/training/SessionsListPage.tsx; depends on T029 (Agent: react-ui-engineer)
- [ ] T033 [US3] Post-login landing prefetch: on login success in frontend/src/store/auth.store.ts, prefetch the `landingPathForRole` destination's primary query (Agent: react-ui-engineer)
- [ ] T034 [US3] Optimistic attendance mutations (`onMutate` snapshot + `setQueryData`, `onError` rollback + toast es-CO, `onSettled` invalidate) in frontend/src/api/trainingSessions.ts (Agent: react-ui-engineer)
- [ ] T035 [US3] Optimistic roster add/remove mutations, same pattern, in frontend/src/hooks/race/useRaceRoster.ts (Agent: react-ui-engineer)

### Merge gates for User Story 3

- [ ] T036 [US3] Mutation-testing gate via temporary agent: scoped Stryker run on frontend/src/hooks/usePrefetchOnIntent.ts + the optimistic mutation code in frontend/src/api/trainingSessions.ts and frontend/src/hooks/race/useRaceRoster.ts; score ≥ 70 %, report into PR (Agent: qa-engineer, temporary instance)

**Checkpoint**: All three user stories independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Budgets, docs, and final validation across the stories

- [ ] T037 [P] Bundle budget verification: `npm run build` before/after, confirm initial-route delta < 10 KB gzipped (< 10 % regression, Principle IV); record numbers in the PR (Agent: react-ui-engineer)
- [ ] T038 [P] Update docs/implementation-status.md and the CLAUDE.md implementation-status table with the 012 feature row (Agent: technical-writer)
- [ ] T039 Run the full quickstart.md validation end-to-end (P1 §1–6, P2 §1–2, P3 §1–3) against the local stack and record results in specs/012-perceived-performance-cache/quickstart.md notes (Agent: qa-engineer)
- [ ] T040 Final compliance statement: confirm Principles I–IV in each PR description and close out the orchestration checklist in specs/012-perceived-performance-cache/tasks.md (Agent: engineering-lead)

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
