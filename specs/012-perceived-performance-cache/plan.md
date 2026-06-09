# Implementation Plan: Perceived Performance — Instant-Feeling App Despite a Sleeping Backend

**Branch**: `012-perceived-performance-cache` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-perceived-performance-cache/spec.md`

## Summary

Frontend-only feature in three independently shippable slices: (P1) persist an
explicit allow-list of non-sensitive TanStack Query data to device storage so
return visits render within ~1 s even while the Render Free backend wakes
(~50 s), with full wipe on logout, ~24 h expiry, and invalidation per app
version and account; (P2) proactively warm the backend via the existing
`GET /health` endpoint on login/app-shell mount and surface an explicit
"el servidor está despertando…" state after ~3 s of waiting; (P3) navigation
polish — `placeholderData: keepPreviousData` on paginated/filtered lists,
intent-based prefetching, and optimistic updates for attendance/roster
mutations. No backend or database change. Testing includes a mutation-testing
gate (StrykerJS) executed by a temporary QA agent, per the planning input.

## Technical Context

**Language/Version**: TypeScript ~6.0, React 19.2, Vite 8 (frontend SPA only — backend untouched)

**Primary Dependencies**: `@tanstack/react-query` ^5.99 (existing). **New runtime**: `@tanstack/react-query-persist-client`, `@tanstack/query-async-storage-persister` (version-locked to the installed react-query). **New dev-only**: `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` (mutation-testing gate).

**Storage**: `window.localStorage` under a single namespaced key (`tyr:rq-cache:v1`) via the async-storage persister; default-deny allow-list decides what is dehydrated (see research.md D2/D3)

**Testing**: vitest + Testing Library + jest-axe + MSW (existing stack); Playwright for one cold-start e2e smoke; StrykerJS mutation testing scoped to the new cache/waking modules, executed by a temporary QA agent during the testing step (see Testing Strategy)

**Target Platform**: Web — mid-tier Android Chrome over intermittent 3G/4G (parents), Chrome on tablet (coach in the field); backend remains FastAPI on Render Free (Oregon)

**Project Type**: Web application — frontend feature within existing `frontend/` workspace

**Performance Goals**: restored content visible <1 s on reload with server asleep (SC-001); waking state at exactly the 3 s threshold (SC-002); added initial-bundle weight <10 KB gzipped (persist-client + persister are ~3 KB combined)

**Constraints**: zero backend/DB changes; Ley 1581 minors privacy — only allow-listed non-personal lists persisted, full wipe on logout, per-account scoping via buster, ~24 h `maxAge`; copy in español neutro (Colombia); WCAG 2.1 AA for the new banner state

**Scale/Scope**: ~5 new frontend modules, ~10 existing hooks/pages touched, 3 delivery slices (one PR each); no new routes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | New modules (`queryPersister`, `persistAllowList`, `serverWaking.store`) are small, named for what they produce, with docstrings (shared-lib requirement). `eslint` + `tsc --noEmit` gate every slice. No duplication: persistence config lives in one module consumed by `App.tsx`. | ✅ PASS |
| II. Testing (NON-NEGOTIABLE) | Each slice ships with vitest + Testing Library tests (hooks and branching components), jest-axe on the new `ServerWakingBanner` and any touched page, and **explicit privacy-invariant tests**: non-allow-listed keys never reach storage; storage emptied on logout; foreign-account data never restored. Mutation-testing gate (temporary agent) validates test-suite strength on the new modules. MSW keeps suites deterministic. | ✅ PASS |
| III. UX Consistency | Banner uses existing shadcn/ui + Tailwind tokens (amber = attention while waking, red only on final failure); copy in español neutro with diacritics; no new component pattern (banner lives under `components/layout/`); loading/empty/error states defined for every async surface touched; 48 px touch targets on retry affordances. | ✅ PASS |
| IV. Performance | Directly implements the constitution's mandate to surface a "starting the server" state instead of a generic spinner. Bundle delta <10 KB gz (<10% regression). Persistence improves LCP on return visits toward the ≤2.5 s budget. No heavy static imports; no lazy-route changes. | ✅ PASS |
| Privacy gate (Ley 1581) | Allow-list is default-deny and curated in one reviewable module; `data-privacy-guard` audit is a mandatory task before merging P1. No minor PII in logs/commits; storage inspected in tests (SC-004/SC-005). | ✅ PASS |
| Stack discipline | Two new runtime deps are first-party TanStack companions of the already-agreed TanStack Query — written justification in Complexity Tracking. Stryker is dev-only. | ✅ PASS |

**Post-design re-check (after Phase 1)**: no design artifact introduced new
surface area beyond the table above — still PASS. No Complexity Tracking
violations; the dependency justification below is informational, not a gate
exception.

## Project Structure

### Documentation (this feature)

```text
specs/012-perceived-performance-cache/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── persistence.md   # Device-storage contract (key, schema, invariants)
│   └── health-warmup.md # GET /health warm-up usage contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── App.tsx                          # MOD: PersistQueryClientProvider, gcTime 24 h
│   ├── lib/
│   │   ├── queryPersister.ts            # NEW: persister factory, buster, wipe helper
│   │   ├── persistAllowList.ts          # NEW: default-deny queryKey-prefix registry
│   │   └── queryClientHandle.ts         # MOD: expose persisted-cache wipe for stores
│   ├── store/
│   │   ├── auth.store.ts                # MOD: logout() also wipes persisted cache
│   │   └── serverWaking.store.ts        # NEW: pending-request tracking, 3 s threshold
│   ├── api/
│   │   └── client.ts                    # MOD: interceptors feed waking store; warmUp()
│   ├── components/layout/
│   │   ├── AppShell.tsx                 # MOD: mounts ServerWakingBanner
│   │   └── ServerWakingBanner.tsx       # NEW: "el servidor está despertando…" state
│   ├── routes/auth/LoginPage.tsx        # MOD: fire warm-up ping on mount
│   └── hooks/                           # MOD (P3): keepPreviousData on list hooks,
│       │                                #   prefetch-on-intent helpers,
│       │                                #   optimistic attendance/roster mutations
│       └── …
├── stryker.config.json                  # NEW (dev): scoped mutation-testing config
└── src/**/__tests__/                    # NEW/MOD: tests per Testing Strategy
```

**Structure Decision**: Web-application layout, frontend workspace only. All new
code lands in the existing `frontend/src` module folders (`lib/`, `store/`,
`components/layout/`); no new top-level structure, no backend paths touched.

## Delivery Slices

| Slice | Spec story | Scope | Ships independently |
|---|---|---|---|
| PR1 | US1 (P1) | persist-client provider, allow-list, buster (appVersion+userId), logout wipe, graceful degradation | Yes — value even alone |
| PR2 | US2 (P2) | warm-up ping, serverWaking store + banner, retry-exhausted error state | Yes |
| PR3 | US3 (P3) | keepPreviousData on lists, hover/touch + post-login prefetch, optimistic attendance/roster | Yes |

## Testing Strategy

Per Principle II plus the planning input ("Include mutation test with temporal
agent, in the step for testing"):

1. **Unit/component (every slice)** — vitest + Testing Library: allow-list
   filtering (`shouldDehydrateQuery` accepts allow-listed keys, rejects
   everything else by default), buster composition, logout wipe, waking-store
   threshold transitions (fake timers), banner render/clear, keepPreviousData
   behavior, optimistic rollback on mutation error (MSW 409/500).
2. **Privacy invariants (P1, mandatory)** — tests that exercise athlete-detail
   and parent flows, then assert the storage payload contains zero
   non-allow-listed keys and is empty after `logout()`. These double as the
   regression tests required by the constitution for minors-data code.
3. **Accessibility** — jest-axe on `ServerWakingBanner` (within AppShell) and
   every touched page-level component; zero violations to merge.
4. **E2E smoke (P2)** — Playwright: simulate delayed first response, assert
   banner appears ≥3 s and clears on response; reload with route mocking
   offline, assert cached list renders.
5. **Mutation-testing gate (temporary agent)** — after each slice's suite is
   green, a temporary QA agent (ephemeral `qa-engineer` invocation, discarded
   after the run) executes StrykerJS with the vitest runner **scoped to that
   slice's new modules** (`lib/queryPersister.ts`, `lib/persistAllowList.ts`,
   `store/serverWaking.store.ts`, optimistic-mutation hooks). Acceptance:
   **mutation score ≥ 70 %** on scoped files; surviving mutants in privacy-
   critical branches (allow-list deny path, logout wipe) are merge blockers
   regardless of score. The gate runs on demand in the testing step — not in
   CI — because of its runtime cost; the agent reports score + surviving
   mutants back into the PR description. Config lives in
   `frontend/stryker.config.json` (see quickstart.md).

## Complexity Tracking

No constitutional violations. Recorded here: the written justification that
Stack Discipline requires for new runtime dependencies.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `@tanstack/react-query-persist-client` + `@tanstack/query-async-storage-persister` (runtime, ~3 KB gz combined) | First-party persistence layer for the already-agreed TanStack Query: restore-before-fetch semantics, `maxAge`/`buster`, `shouldDehydrateQuery` filtering | Hand-rolled localStorage (de)hydration of the query cache — duplicates battle-tested race-condition handling (restore vs. mount fetch), easy to get privacy filtering wrong, more code to maintain |
| `@stryker-mutator/*` (dev-only) | Requested mutation-testing gate to validate test strength on privacy-critical cache code | Coverage % alone — measures execution, not assertion strength; a wipe-on-logout test that asserts nothing still shows 100 % coverage |
