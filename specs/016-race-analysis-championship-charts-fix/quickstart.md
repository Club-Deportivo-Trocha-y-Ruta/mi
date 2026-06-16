# Quickstart — Validate the Championship Charts Fix

Runnable validation for feature 016. Proves the Distribution and Evolution charts handle the
Departmental Championship with no error. See [contracts/](./contracts/) and [data-model.md](./data-model.md)
for shapes; this is a run/verify guide, not implementation.

## Prerequisites

- Backend venv + DB with feature-014 data (migration `b1c2d3e4f5a6` applied) and at least one athlete
  who competed in cup rounds **and** the Departmental Championship in season 2026.
- Frontend deps installed (`cd frontend && npm install`), Playwright browsers (`npx playwright install`).
- Dev credentials: coach `entrenador@trochyruta.com` / `Coach2026!`, parent `padre@trochayruta.com` / `Parent2026!`.

```bash
# Backend
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload
# Frontend (another shell)
cd frontend && npm run dev
```

## A. API smoke (backend) — championship no longer 500s

```bash
TOKEN=...   # coach JWT

# 1. Participation list — championship present with its own event_id + label
curl -s "$API/api/athletes/1/race-analysis/races?season=2026" -H "Authorization: Bearer $TOKEN" | jq
#   expect: items[] ordered by date; one entry series_kind="championship", label "Cto. Dep. — …"

# 2. Distribution by the championship's event_id — 200, not 500
curl -s -o /dev/null -w "%{http_code}\n" \
  "$API/api/athletes/1/race-analysis/distribution?event_id=21" -H "Authorization: Bearer $TOKEN"
#   expect: 200 (pre-fix: valida_num=99 → 500)

# 3. No-comparable-data race — still 200 with a valid payload (no category_id=0)
curl -s "$API/api/athletes/1/race-analysis/distribution?event_id=<dnf_event>" -H "Authorization: Bearer $TOKEN" \
  | jq '{category_id, athlete_time_ms, confidence}'
#   expect: category_id >= 1, athlete_time_ms null OK, confidence "low"

# 4. Non-participated event — clean 404 (not 500)
curl -s -o /dev/null -w "%{http_code}\n" \
  "$API/api/athletes/1/race-analysis/distribution?event_id=999999" -H "Authorization: Bearer $TOKEN"

# 5. Evolution — championship carries series_kind + label
curl -s "$API/api/athletes/1/race-analysis/evolution?season=2026&metric=podium_gap_ms" \
  -H "Authorization: Bearer $TOKEN" | jq '.series[] | {event_id, series_kind, label, event_date}'
#   expect: a championship point distinct from cup Válida I, ordered by date

# 6. Privacy — parent sees pseudonyms only
PTOKEN=...  # parent JWT (own child)
curl -s "$API/api/athletes/<child>/race-analysis/distribution?event_id=21" -H "Authorization: Bearer $PTOKEN" \
  | jq '[.points[].display_name] | unique'   # expect: [null]
```

## B. UI walkthrough (manual)

1. Log in as coach → athlete → **AI-analysis** → **Distribución**.
2. Open the race picker → every competed race listed once, labeled "Válida IV — Cali",
   "Cto. Dep. — Ginebra"; a "Temporada (todas)" entry is present.
3. Select **Cto. Dep.** → a distribution curve (or friendly "no data" state) renders — **no error**.
4. Select **Temporada (todas)** → calm informational message, no spinner, no error.
5. Open **Evolución** → the championship is one distinct point labeled "CD"/"Cto. Dep.", sitting in
   date order between the May and August rounds — not merged with Válida I.

## C. Automated gates

```bash
# Backend regression + RBAC + privacy
cd backend && pytest tests/ -k "distribution or evolution or races"

# Frontend unit + a11y
cd frontend && npm run test -- DistributionChart EvolutionChart useAthleteRaces
#   includes jest-axe (zero violations) on both charts

# E2E
cd frontend && npm run test:e2e -- race-analysis-championship

# Mutation gate (on-demand, scoped to the new modules)
cd frontend && npm run test:mutation
#   gate: score >= 70; zero surviving mutants on event_id identity,
#   championship label, and aggregate-sentinel branches
```

## Success criteria checklist

- [ ] SC-001/002 — every competed race incl. championship opens in Distribution with no error.
- [ ] SC-003 — championship is exactly one distinct, date-ordered point in Evolution.
- [ ] SC-004 — zero ambiguous picker options (each maps to one `event_id`).
- [ ] SC-005 — working races + the aggregate state show no regression.
- [ ] SC-006 — parent views show zero real competitor names.
