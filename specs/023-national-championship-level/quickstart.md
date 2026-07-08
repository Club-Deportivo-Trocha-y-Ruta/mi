# Quickstart Validation — National Championship Support (Series Level)

**Feature**: 023-national-championship-level

End-to-end validation scenarios proving the feature works. See [data-model.md](data-model.md) for the schema delta and [contracts/api-delta.md](contracts/api-delta.md) for API changes.

## Prerequisites

```bash
# Backend venv + migration at head
source backend/.venv/bin/activate
cd backend && alembic upgrade head        # must apply d3e4f5a6b7c8

# Full stack (alternative)
docker compose up

# Seed dev credentials: entrenador@trochyruta.com / Coach2026!
```

## Scenario 1 — Register national championship before race day (US1 / SC-001)

1. Login as coach → Competitions → "Nueva competencia".
2. Choose type **Campeonato** → "Crear nueva serie": name `Campeonato Nacional MTB 2026`, organizer `Federación Colombiana de Ciclismo`, level **Nacional**.
3. Create the event: name, date `2026-07-18`, city **Pereira** (custom location).

**Expected**:
- No "Válida #" field shown.
- Series created with `level=national`, organizer NOT replaced by "Liga Vallecaucana de Ciclismo" (verify in `GET /api/race-analysis/race-series`).
- Competitions list shows the event labeled **Campeonato Nacional** (never "Departamental").
- Attempting a second event on the same series → 409 (INV-2).

API check:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -d '{"email":"entrenador@trochyruta.com","password":"Coach2026!"}' -H 'Content-Type: application/json' | jq -r .access_token)
curl -s localhost:8000/api/race-analysis/race-series?season=2026 -H "Authorization: Bearer $TOKEN" | jq '.items[] | {name, kind, level, organizer}'
```

## Scenario 2 — Ingest results + analytics labels (US2 / SC-002, SC-003)

1. From the competition detail → "Importar resultados" (competition-linked import, feature 015 flow).
2. Wizard shows locked identity (name/date/Pereira/Campeonato), NO "válida #" field.
3. Upload results file → dry-run → commit.
4. Open an athlete's race analysis → evolution chart.

**Expected**:
- Commit links results to the Pereira event.
- Evolution point + races picker show **"Cto. Nal. — Pereira"**.
- Departmental championship still shows **"Cto. Dep. — Ginebra"** (regression).

## Scenario 3 — Standings unchanged (SC-004)

```bash
# Capture standings BEFORE committing national results, commit, capture AFTER
curl -s "localhost:8000/api/race-analysis/standings?season=2026" -H "Authorization: Bearer $TOKEN" > /tmp/standings_before.json
# ... commit national results ...
curl -s "localhost:8000/api/race-analysis/standings?season=2026" -H "Authorization: Bearer $TOKEN" > /tmp/standings_after.json
diff /tmp/standings_before.json /tmp/standings_after.json   # expected: no diff
```

Season panorama must likewise exclude the national event.

## Scenario 4 — Notification label (US3 / FR-005)

1. Launch an AI insight for an athlete on the national championship event.
2. Inspect the generated notification (dev: `NOTIFICATION_LOG_BODIES=true` or DB `notifications` row).

**Expected**: body references **"Campeonato Nacional"**. Trigger the same for the departmental event → still "Campeonato Departamental".

## Scenario 5 — Monthly report grouping (FR-010)

1. Generate/regenerate the monthly technical report for July 2026.
2. Inspect the competition results section.

**Expected**: national championship appears as its own jornada group, marked as not awarding points ("no otorga puntos"), alongside any cup válidas of the month. No report-code changes involved — this validates the existing 022 grouping generalizes.

## Automated suites

```bash
cd backend && pytest                       # includes new label/router/import/dispatcher/standings tests
cd frontend && npx vitest run              # includes level select, label helper, axe checks
cd backend && ruff check . && mypy app     # constitution gate I
cd frontend && npx eslint src && npx tsc --noEmit
```

**Pass criteria**: all suites green; zero pre-023 test modified except deliberate label assertions; jest-axe zero violations on touched pages.
