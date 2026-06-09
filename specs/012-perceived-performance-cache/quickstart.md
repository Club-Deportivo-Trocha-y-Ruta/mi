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
   load: after ~3 s the amber "el servidor está despertando…" banner appears;
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
