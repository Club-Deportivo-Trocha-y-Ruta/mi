# Quickstart Validation: Interval Block Duration Usability (034)

Runnable scenarios proving the feature end-to-end. References: [data-model.md](./data-model.md), [contracts/api-delta.md](./contracts/api-delta.md).

## Prerequisites

```bash
# Backend
source backend/.venv/bin/activate
cd backend && alembic upgrade head        # applies c7d8e9f0a1b2
uvicorn app.main:app --reload

# Frontend
cd frontend && pnpm dev

# Login as coach: entrenador@trochyruta.com / Coach2026!
```

## Scenario 1 — mm:ss entry (US1, P1)

1. Open a training session → Plan → "Crear estructura de intervalos".
2. Add a block; duration entry shows **Min** and **Seg** fields (no "Duración (segundos)").
3. Enter 5 min 00 s → total shows `5:00`. Enter 1 min 30 s in a second block → total `6:30`.
4. Try 0 min 0 s → inline error, save blocked. Try 75 in Seg → field constrained to 0–59.
5. Save; reopen editor → durations hydrate back as `5:00` / `1:30`.

**Expected**: no raw-seconds integer visible anywhere; stored values are exact seconds (300, 90).

## Scenario 2 — open-ended warmup (US2, P2)

1. In a warmup block, select duration type **"Libre — hasta botón de vuelta"** → duration fields disappear; zone + cadence remain required.
2. Verify a `work` block does NOT offer the open option.
3. Toggle "Parte de un grupo repetido" on an open block → blocked with explanatory message (and vice-versa order).
4. Save structure with open warmup + 20:00 of fixed blocks → total reads **"20:00 + calentamiento libre"**.
5. Band 10–12 + open block Z3 → hard block (age gate unchanged).

**API check**:

```bash
# 422 cases (see contracts/api-delta.md): open work block, open inside repeat group, open with duration_s
curl -s -X POST .../structures -d '{"blocks":[{"position":1,"block_type":"work","duration_type":"open_lap",...}]}' | jq .detail
```

## Scenario 3 — plan-vs-actual with open block (US3, P3)

1. Structure: open warmup + 2 fixed blocks. Link a Strava activity with 3 laps (test fixture / seeded laps).
2. Comparison table: row 1 status **"Libre"** (neutral badge), planned cell "Libre", actual = lap elapsed; rows 2–3 judged with ±30% as before.
3. Fixture without first lap → open block row shows "sin_dato".
4. A comparison stored before this feature renders unchanged (engine_version 1 payload untouched).

**Backend unit check**: `pytest backend/tests/test_interval_matching.py -k libre` — open+lap→`libre`, open no-lap→`sin_dato`, open never `fuera_tolerancia`, `ENGINE_VERSION == 2`.

## Scenario 4 — PDF + templates (US4, P3)

1. Generate instructivo (any brand) for the Scenario-2 structure → warmup row: **"Libre — hasta botón de vuelta"** + zone + cadence; fixed rows keep "X min Y s".
2. Save structure as template; attach template to another session → open type preserved.

## Test suites

```bash
cd backend && pytest tests/test_interval_structures.py tests/test_interval_matching.py tests/test_interval_instructivo.py
cd frontend && pnpm vitest run src/components/intervals src/schemas
```

**Expected**: all green, including jest-axe (editor + comparison table) and regression: pre-existing fixtures (all-fixed structures) produce byte-identical outputs.

## Deploy note

Render: automatic `alembic upgrade head` via `entrypoint.sh` on deploy; migration is additive (server_default) — no manual step, no seed impact.
