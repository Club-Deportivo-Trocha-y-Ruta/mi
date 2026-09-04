# Quickstart — validating feature 040

## Prerequisites

- Backend venv: `cd backend && source .venv/bin/activate` (use `.venv/bin/python -m pytest` — the `pytest` shim on PATH is broken in this environment).
- Frontend: `cd frontend && npm ci`.
- For PDF/e2e scenarios: `docker compose up` (MySQL + backend + MailHog). WeasyPrint on macOS needs Pango: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

## 1. Reference standard (US1)

```bash
cd backend
.venv/bin/python scripts/export_who_lms_csv.py          # regenerates app/data/who_lms/*.csv (byte-identical)
.venv/bin/python -m app.seed_growth_data                 # CDC + WHO upsert, idempotent
.venv/bin/python -m app.scripts.backfill_anthropometry   # fills NULLs, then recomputes to WHO; prints summary
.venv/bin/python -m pytest tests/services/test_growth_seed.py tests/scripts/test_backfill_anthropometry.py tests/routers/test_anthropometry_bmi.py -q
```

Expected: WHO row counts 168/168/60 per sex; parity test passes; recompute report lists band changes by athlete id; second run reports `recomputed: 0`.

Manual: create a measurement via the UI → tile Z/percentile == curve hover == table row == family PDF value for the same record; caption "OMS 2007 · Res. 2465/2016".

## 2. Growth summary endpoint (US2)

```bash
.venv/bin/python -m pytest tests/routers/test_growth_summary.py -q
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/athletes/2/growth-summary | jq .
```

Expected: JSON per `contracts/growth-summary-api.md`; parent token for another athlete → 403.

## 3. Coach tab (US2, US3, US5)

```bash
cd frontend
npx vitest run src/components/athletes/growth src/lib/growth src/hooks/athletes/useGrowthSummary.test.tsx
npm run typecheck
npm run build && bash scripts/check-chart-chunk.sh      # fails if the entry chunk statically imports the recharts chunk
npx playwright test e2e/growth.spec.ts e2e/history.spec.ts
```

Manual on a 1024 px viewport: open `/athletes/:id?tab=growth` — stage, velocity, two bands and next measurement visible without scrolling; switch Talla → IMC; toggle Biológica; open Tabla; export PNG (file name has no name). On 390 px: same within one scroll.

Bundle expectation (baseline measured 2026-09-04): entry `index-*.js` 336.68 kB gzip statically importing a 107.39 kB gzip chunk that contains recharts; after the feature the entry must not import that chunk and must not contain the string `WHO 2007 Growth Reference`.

## 4. Family view (US4)

```bash
npx vitest run src/components/athletes/growth/GrowthTab.parent.test.tsx
npx playwright test e2e/growth-parent.spec.ts
```

Manual as parent: latest measurement drives the cards; page text contains no `Z=`/`P\d+`; no "Fuentes bibliográficas"; AI card read-only.

## 5. Accessibility and privacy gates

```bash
npx vitest run --reporter=verbose src/components/athletes/growth/GrowthTab.a11y.test.tsx
```

- `data-privacy-guard` audit checklist: `checklists/privacy.md` (created by the audit task).
- Grep gate: `grep -rn "first_name\|last_name\|birth_date" frontend/src/components/athletes/growth/` → only allowed in the family stage sentence helper input, never rendered inside growth components.

## 6. Family PDF (R-14)

```bash
cd backend && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest tests -k "newsletter and pdf" -q
```

Then regenerate one newsletter for a test athlete in the dev stack and confirm the growth chart labels "OMS 2007" and omits the weight chart above 10 y.

## 7. Post-deploy smoke

`GET /health` → 200; `GET /api/athletes/{id}/growth-summary` with a coach token → 200; open the athlete page on a real Android device: dashboard LCP within budget, growth tab loads its chunk on tap.
