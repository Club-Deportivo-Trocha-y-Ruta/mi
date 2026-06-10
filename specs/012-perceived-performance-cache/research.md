# Research: Perceived Performance — Frontend Cache & Cold-Start Experience

**Feature**: 012-perceived-performance-cache · **Date**: 2026-06-09

No `NEEDS CLARIFICATION` markers existed in the Technical Context (stack is
fixed by the constitution; the two product questions were owner-resolved during
specification). This document records the technology decisions and the
alternatives considered. Library behavior was verified against the TanStack
Query v5 documentation (persistQueryClient plugin) via context7 during the
preceding analysis.

## D1 — Persistence layer: TanStack first-party persist-client

- **Decision**: `@tanstack/react-query-persist-client` with
  `PersistQueryClientProvider` replacing `QueryClientProvider` in `App.tsx`,
  plus `@tanstack/query-async-storage-persister`.
- **Rationale**: First-party, version-locked to the installed
  `@tanstack/react-query` ^5.99; `PersistQueryClientProvider` specifically
  prevents the restore-vs-first-fetch race (queries stay idle until
  restoration completes); supports `maxAge`, `buster`, and
  `dehydrateOptions.shouldDehydrateQuery` — exactly the controls FR-001/002/
  005/006 need.
- **Alternatives considered**:
  - *Hand-rolled localStorage hydration of selected queries* — re-implements
    race handling and filtering; highest privacy-bug risk; rejected.
  - *Service worker (Workbox) HTTP cache* — solves a different layer, large
    update-lifecycle complexity; explicitly out of scope in the spec.
  - *Zustand-persisted view models* — duplicates server state outside the
    query cache, drifts from TanStack invalidation; rejected.

## D2 — Storage medium: localStorage (sync persister API via async wrapper)

- **Decision**: `window.localStorage`, single key `tyr:rq-cache:v1`, accessed
  through `createAsyncStoragePersister`.
- **Rationale**: The allow-list keeps payloads to a few hundred KB at most
  (lists only, no media, no per-athlete blobs) — far under the ~5 MB quota.
  localStorage is universally available on the target devices (mid-tier
  Android Chrome) and the project already standardizes on it (Zustand persist
  stores, session-wizard drafts use `tyr:` prefixed keys).
- **Alternatives considered**: IndexedDB via `idb-keyval` — better for large
  payloads and non-blocking writes, but adds a dependency and async failure
  modes we don't need at this payload size. Documented as the escalation path
  if the persisted snapshot ever approaches ~1 MB.

## D3 — What persists: default-deny allow-list of queryKey prefixes

- **Decision**: A single reviewable module `lib/persistAllowList.ts` exporting
  the allowed queryKey prefixes and a `shouldDehydrateQuery` predicate that
  (a) requires `query.state.status === 'success'` and (b) matches a prefix;
  everything else is rejected.
- **Audit amendment (2026-06-10, authoritative)**: the `data-privacy-guard`
  audit BLOCKED the draft list. Final allow-list: `["calendar","events"]`,
  `["calendar","race-events","available-for-calendar"]`, `["raceEvents"]`,
  `["revision-reasons"]`. Excluded relative to the draft: standings/results/
  competitors (`display_name` may be a minor), single calendar-event detail
  (`EventDataBirthday.athlete_first_name`), and training-session lists
  (`media[].athlete_ids` + free-text `coach_notes`; re-allow only behind a
  backend summary schema that strips those fields).
- **Rationale**: FR-002 demands default-deny with explicit exclusions; one
  module gives the `data-privacy-guard` audit a single review surface; prefix
  matching survives key params (filters, pagination) without enumerating them.
- **Alternatives considered**: per-hook `meta: { persist: true }` flags —
  more ergonomic but scatters the privacy decision across dozens of hooks and
  makes the audit surface diffuse; deny-list — unacceptable (fails default-
  deny; new sensitive queries would persist silently).

## D4 — Account scoping & invalidation: composite buster + logout wipe

- **Decision**: `buster = "{APP_VERSION}:{userId}"` (APP_VERSION injected at
  build time from `package.json` version / commit short-SHA via Vite `define`).
  On `logout()` in `auth.store.ts`, call the persister's `removeClient()` in
  addition to the existing `queryClient.clear()`, routed through the existing
  `lib/queryClientHandle.ts` singleton pattern.
- **Rationale**: A buster mismatch makes persist-client silently discard the
  stored snapshot — this single mechanism satisfies both FR-005 (different
  account ⇒ different buster ⇒ never restored) and FR-006 (new app version ⇒
  discarded). The explicit logout wipe (FR-004) removes data at rest rather
  than merely making it unrestorable, which is what the privacy clause
  requires on shared devices.
- **Alternatives considered**: per-user storage keys (`tyr:rq-cache:v1:{id}`)
  — leaves previous users' data at rest until expiry; rejected as the primary
  mechanism. Encrypting the snapshot — key would live in the same browser
  context, adds complexity without a real threat-model gain here.

## D5 — Freshness windows: maxAge 24 h, gcTime 24 h

- **Decision**: `maxAge: 24 h` on the persister; raise the QueryClient default
  `gcTime` to 24 h (persistence only includes what GC hasn't evicted —
  today's 5 min default would make restore useless). `staleTime` defaults
  stay as-is (5 min global, per-hook overrides), so restored data is treated
  as stale and revalidates immediately on mount — the
  stale-while-revalidate behavior FR-003 requires.
- **Rationale**: 24 h bounds shared-device exposure (spec edge case) while
  covering the typical "check again later the same day / next morning"
  pattern. Memory impact of a 24 h gcTime is modest (small list payloads).
- **Alternatives considered**: `gcTime` raised only on allow-listed hooks —
  precision without much benefit since dehydration already filters; revisit
  if memory profiling ever flags it.

## D6 — Waking-server detection: interceptor-fed store with 3 s threshold

- **Decision**: A small `store/serverWaking.store.ts` (Zustand, in keeping
  with global-UI-state conventions). The existing axios interceptors in
  `api/client.ts` register request start/settle; a 3 s timer flips
  `isWaking: true` if the oldest in-flight request is still pending; settling
  clears it. `ServerWakingBanner.tsx` (mounted in `AppShell` and on the login
  page) renders the state.
- **Rationale**: Centralized at the HTTP layer ⇒ FR-008's "any request"
  guarantee holds without touching every hook; reuses the existing
  interceptor seam; Zustand matches the stack rule. Threshold owner-confirmed
  at ~3 s.
- **Alternatives considered**: per-query `isLoading` timers in components —
  misses mutations and duplicates logic; TanStack `onSettled` global
  callbacks — miss non-query axios calls (login itself, which is exactly the
  cold-start path).

## D7 — Warm-up ping: existing GET /health on mount

- **Decision**: Fire-and-forget `GET {API}/health` (no auth, exists at
  `backend/app/main.py:71`) once per app load, triggered from `LoginPage`
  mount and the authenticated `AppShell` mount; no retries, errors swallowed.
- **Rationale**: FR-009; wakes Render while the user types credentials. No
  backend change. Single ping per load avoids burning Render free-tier hours
  (an external cron pinger was rejected for ToS/quota reasons in the
  analysis).

## D8 — List smoothness: placeholderData keepPreviousData

- **Decision**: `placeholderData: keepPreviousData` (v5 idiom) on the
  paginated/filtered list hooks: standings, race results, sessions list,
  competitions list, unlinked competitors; subtle refreshing indicator driven
  by `isPlaceholderData`.
- **Rationale**: FR-010; v5 replaced the v4 `keepPreviousData` boolean with
  this composable; zero schema impact.

## D9 — Prefetch on intent

- **Decision**: Shared helper using `queryClient.prefetchQuery` with the same
  queryKey/fn as the detail hooks; wired to `onMouseEnter`/`onTouchStart`
  (once per row per session) on list rows, and post-login prefetch of the
  role landing data inside the existing login success path
  (`landingPathForRole` already determines the destination).
- **Rationale**: FR-011; prefetched data lands in the normal cache, so RBAC
  is untouched (FR-013) — the prefetch uses the same authenticated endpoints
  the user could already call.

## D10 — Optimistic updates: attendance & roster mutations

- **Decision**: Standard TanStack optimistic pattern (`onMutate` → snapshot +
  `setQueryData`; `onError` → rollback + localized toast; `onSettled` →
  invalidate) on attendance recording and roster add/remove mutations only.
- **Rationale**: FR-012 limits scope to the field-critical writes; server
  remains source of truth (spec edge case on conflicts).
- **Alternatives considered**: offline mutation queue (persisted mutations +
  `resumePausedMutations`) — powerful but belongs to the out-of-scope
  offline-first step.

## D11 — Mutation-testing gate via temporary agent (planning input)

- **Decision**: StrykerJS (`@stryker-mutator/core` + `@stryker-mutator/vitest-runner`,
  dev-only) with `frontend/stryker.config.json` scoped via `mutate` globs to
  the new modules (`lib/queryPersister.ts`, `lib/persistAllowList.ts`,
  `store/serverWaking.store.ts`, optimistic-mutation hooks). Executed in the
  testing step of each slice by a **temporary QA agent** — an ephemeral
  `qa-engineer` agent invocation that runs the scoped Stryker pass, reports
  mutation score and surviving mutants into the PR, and is then discarded.
  Gate: score ≥ 70 % on scoped files; any surviving mutant on the allow-list
  deny path or the logout wipe is a merge blocker.
- **Rationale**: Requested in the planning input. Mutation testing directly
  measures assertion strength on privacy-critical branches where line
  coverage is misleading. Running it agent-driven and on demand (not CI)
  keeps CI fast and free-tier friendly.
- **Alternatives considered**: full-codebase Stryker run — minutes-to-hours
  of runtime for code this feature doesn't touch; coverage thresholds alone —
  rejected (measures execution, not assertions); wiring Stryker into CI —
  revisit if the club moves off free tiers.
