# Quickstart: Strength Training Exercise Library (021)

Validation guide — proves the feature end-to-end. Contracts: [contracts/strength-api.md](./contracts/strength-api.md) · Entities: [data-model.md](./data-model.md).

## Prerequisites

```bash
# Backend + DB (runs migrations incl. 021 schema+seed, then dev seed)
docker compose up
# — or —
source backend/.venv/bin/activate
cd backend && alembic upgrade head && uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev
```

Login as coach: `entrenador@trochyruta.com` / `Coach2026!` (dev seed).

## Scenario 1 — Catalog browse & filter (US1 / SC-001)

1. Navigate to `/strength`.
2. Filter `equipo = sin equipo`, `banda = 10-12` → only bodyweight 10-12 exercises; every card opens a detail with ASCII illustration (`role="img"`), execution steps, common errors. Zero photos anywhere.
3. Search `q = "plancha"` → matching results, filters still applied.
4. Filter `equipo = equipo gym`, `banda = 10-12` → **empty state message** (club rule), not an error.

API check: `curl -H "Authorization: Bearer $TOK" "localhost:8000/api/strength/exercises?equipment=sin_equipo&age_band=10-12"` → `{items, total}`, all items contain `"10-12"` in `age_bands`.

## Scenario 2 — Block assembly + 30-min indicator (US2 / SC-005)

1. `/strength/blocks/new`, target band `13-15`.
2. Add exercises until total = 28 min → indicator **within** (green). Add one to hit exactly 30 → **at** (amber). One more → **over** (red? per token semantics: amber=attention for at, red only if design says blocking — it never blocks; verify copy says target, not clinical limit).
3. Save → block persists; reopen → entries + totals intact.

## Scenario 3 — Age guardrail + recorded override (US3 / SC-004)

1. New block, target band `10-12`.
2. Attempt to add a `13-15`-only exercise (e.g., dumbbell entry) → warning dialog in Spanish explaining why; **Cancelar** leaves block unchanged.
3. Retry and confirm override → entry added flagged; API response entry has `is_age_override: true`.

API check: `POST /api/strength/blocks` with a 13-15-only exercise in a 10-12 block **without** `is_age_override` → **422** with `AGE_BAND_GUARDRAIL` detail; **with** `is_age_override: true` → **201**.

## Scenario 4 — Attach to training session (US2 / SC-002)

1. From block detail: **Añadir a sesión** → pick an existing training session → confirm.
2. Open that session in the Training Sessions module → strength block visible in the plan.
3. Attach same block to a second session → allowed (reusable). Re-attach to the same one → **409**.
4. Delete the session → block still exists under `/strength/blocks` (RESTRICT survives).

## Scenario 5 — Progress notes, coach-only, no comparison (US4 / SC-006)

1. `/strength/athletes/{id}/progress` → record `en progreso` + note for one athlete/exercise → persists; latest status shown.
2. Verify: no route/screen anywhere lists two athletes' strength progress side by side.
3. Log in as parent (`padre@trochayruta.com`) → all `/api/strength/*` return **403**; frontend routes redirect.

## Test suites

```bash
# Backend — mirrors tests/technique/ layout
cd backend && pytest tests/strength/ -v
# Expected coverage: catalog filters+search, block CRUD, guardrail 422/override,
# attach 201/409/RESTRICT, progress privacy (no PII), RBAC negatives, query-count (no N+1)

# Frontend
cd frontend && npx vitest run src/components/strength src/routes/strength
# Expected: FilterBar, BlockAssembler duration boundaries (29/30/31 min),
# AgeBandGuardrailDialog flow, ProgressNotesBoard, jest-axe on all pages
```

## Deploy validation (Render)

Migration `a7b8c9d0e1f2` runs via `entrypoint.sh` on deploy (seed included — SC-007 day-one catalog). Post-deploy: `GET /health`, then authenticated `GET /api/strength/exercises` returns seeded total ≥ 20.
