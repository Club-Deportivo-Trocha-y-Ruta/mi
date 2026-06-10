# Quickstart: Perceived Performance — Frontend Cache & Cold-Start Experience

**Feature**: 012-perceived-performance-cache

## Setup

```bash
cd frontend

# Runtime deps (version-locked to installed @tanstack/react-query ^5.99)
npm install @tanstack/react-query-persist-client @tanstack/query-async-storage-persister

# Dev-only: mutation-testing gate
npm install -D @stryker-mutator/core @stryker-mutator/vitest-runner

npm run dev
```

Backend for local verification: `docker compose up` (or none at all — a dead
backend is the most faithful cold-start simulation).

## Verifying each slice

### P1 — Persistence (instant return visits)

1. Log in as coach (`entrenador@trochyruta.com`), open Competencias and the
   calendar.
2. DevTools → Application → Local Storage → check `tyr:rq-cache:v1` exists and
   contains **only** allow-listed keys (no athlete personal data anywhere in
   the payload).
3. Stop the backend (`docker compose stop backend`). Reload the page: lists
   render from the snapshot within ~1 s.
4. Restart the backend; confirm content refreshes in the background.
5. Log out → the storage key is gone. Log in as another user → nothing from
   the previous account is restored (buster mismatch).
6. Edit the stored `timestamp` to >24 h ago → reload behaves as a first visit.

### P2 — Warm-up + waking banner

1. With the backend stopped, open the login page — confirm a single
   `GET /health` fires in the Network tab (no retries, no auth header).
2. DevTools → Network → throttle or keep backend stopped; trigger any data
   load: after ~3 s the amber "la aplicación está iniciando…" banner appears;
   when a response arrives it clears without user action.

### P3 — Navigation polish

1. Standings/sessions/competitions: switch pages/filters — previous rows stay
   visible with a subtle refresh indicator; never an empty flash.
2. Hover (desktop) or touch-start (tablet) a row, then open it — detail
   renders with no visible loading state on a warm server.
3. Record attendance with the network throttled — UI updates instantly; force
   a 409/500 (MSW or backend down) — change rolls back with a localized
   message.

## Tests

```bash
cd frontend
npm run test            # vitest suite (incl. privacy invariants + axe)
npm run test:e2e        # Playwright cold-start smoke (P2)
```

## Mutation-testing gate (temporary agent)

Run after the suite is green for the slice under review. The temporary QA
agent (ephemeral `qa-engineer` invocation) executes:

```bash
cd frontend
npx stryker run         # scoped by stryker.config.json `mutate` globs
```

`stryker.config.json` scopes mutation to this feature's modules:
`src/lib/queryPersister.ts`, `src/lib/persistAllowList.ts`,
`src/store/serverWaking.store.ts`, and the optimistic-mutation hooks (P3).

**Gate**: mutation score ≥ 70 % on scoped files; any surviving mutant on the
allow-list deny path or the logout wipe blocks merge. The agent pastes the
score and surviving-mutant summary into the PR description, then is discarded.

## Privacy audit (mandatory before P1 merge)

Run the `data-privacy-guard` agent against the P1 diff + a storage dump
captured after exercising coach and parent flows; it must confirm contract
guarantees 1–4 in `contracts/persistence.md`.

## Validation notes (T039 — 2026-06-10, sandbox run)

Recorded against the implementation as merged on `claude/frontend-cache-render-perf-qpnyw1`.

| Quickstart step | How validated | Result |
|---|---|---|
| P1 §2 storage contains only allow-listed keys | Automated: `src/test/integration/persistence-privacy.test.tsx` (INV-1, incl. birthday + session-media vectors) + `persistAllowList.test.ts` | ✅ Green |
| P1 §5 logout wipe / cross-account buster | Automated: `auth.store.persist-wipe.test.ts`, `queryPersister.test.ts` | ✅ Green |
| P1 §3–4, §6 reload-with-dead-backend, 24 h expiry | E2E-012-3 in `e2e/cold-start.spec.ts` (offline reload restore); expiry covered by persist-client `maxAge` config + unit constant test | ⚠️ e2e written, needs local `npm run test:e2e` (no chromium in sandbox — download blocked by network policy) |
| P2 §1 single `/health` ping, no auth, no retries | Automated: `client.warmup.test.ts`, `LoginPage.warmup.test.tsx`; E2E-012-1 | ✅ Green (e2e pending local) |
| P2 §2 banner ≥3 s, auto-clear | Automated: `serverWaking.store.test.ts` (fake timers), banner tests + jest-axe; E2E-012-2 | ✅ Green (e2e pending local) |
| P3 §1 no empty flash on filter/page change | Automated: `useRaceStandings.keepPrevious.test.tsx` | ✅ Green |
| P3 §2 hover/touch prefetch | Automated: `usePrefetchOnIntent.test.tsx` (dedupe, fresh-skip) | ✅ Green |
| P3 §3 optimistic + rollback | Automated: `useRaceRoster.optimistic.test.tsx`; attendance pre-existing optimistic path | ✅ Green |

Note: the banner copy was changed to **"La aplicación está iniciando…"** after the
ux-researcher validation (T023) — "aplicación" instead of "servidor" for
non-technical parents. Spec FR-008 was amended accordingly.
