# Quickstart: Cup vs Championship Series

**Feature**: 014-cup-vs-championship-series

How to exercise the feature end-to-end after implementation.

## Prerequisites

```bash
source backend/.venv/bin/activate
cd backend && alembic upgrade head        # applies the kind column + reclassifies event 15
cd backend && uvicorn app.main:app --reload
# frontend: cd frontend && npm run dev
```

Dev login (coach): `entrenador@trochyruta.com` / `Coach2026!`

## Scenario A — Register a championship (FR-001/002/003/005)

1. Go to **Competencias → Nueva competencia**.
2. In **Tipo de competencia**, choose **Campeonato**.
   - The **Válida #** field disappears.
   - The series picker offers/creates a championship series (e.g. "Campeonato
     Departamental 2026", organizer Liga Vallecaucana).
3. Fill name, date, venue → **Guardar**.
   - Expect: event created with no round number, `is_championship=true`.
4. Try to add a **second** event to the same championship series → expect a `409`
   with "un campeonato representa un único evento anual".

## Scenario B — Import results into a championship (FR-008)

1. **Competencias → Importar resultados**.
2. Choose **Tipo: Campeonato** → the **Válida #** input is hidden; no "Copa Valle"
   is pre-filled.
3. Upload the official results PDF/CSV → validate matches → commit.
   - Expect: results attached to the championship's single event; no round number.

## Scenario C — Import a cup round (regression, FR-002/008)

1. **Importar resultados**, **Tipo: Copa**, pick "Copa Valle", **Válida # = 6**.
2. Commit → expect the round imported exactly as before (no behavior change).

## Scenario D — Season ranking excludes championships (FR-010/011/013)

1. Open the season panorama for 2026.
2. Note a club athlete's cumulative points.
3. Confirm the Departmental Championship results are **not** included in the
   cumulative points/podiums (they are viewable on the event itself, but contribute
   zero to the season ranking).

## Scenario E — Existing data reclassified (FR-012)

1. Open the previously-misfiled **Departamental** competition.
2. Expect: it now belongs to "Campeonato Departamental 2026" (kind championship,
   Liga Vallecaucana), shows **no** round number, and **all** its results are intact.
3. The Copa Valle cumulative ranking no longer counts it.

## Automated checks

```bash
# Backend
cd backend && pytest tests/ -k "series_kind or championship or standings or season_panorama or migration_014"

# Frontend
cd frontend && npm run test -- competition  # wizard type selector, form round field, series picker, badges
cd frontend && npm run test -- a11y          # jest-axe on changed pages
```

## Rollback

```bash
cd backend && alembic downgrade -1   # repoints the event to Copa Valle (seq 99), drops kind column
```
