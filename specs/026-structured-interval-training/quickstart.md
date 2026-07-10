# Quickstart Validation: Structured Interval Training

**Feature**: `026-structured-interval-training` · Proves the feature end-to-end. Contracts: [contracts/api.md](./contracts/api.md) · Model: [data-model.md](./data-model.md)

## Prerequisites

```bash
# Full stack (runs migrations + seed automatically)
docker compose up
# — or local backend —
source backend/.venv/bin/activate
cd backend && alembic upgrade head && uvicorn app.main:app --reload
# Frontend
cd frontend && npm run dev
```

- Migration `b5c6d7e8f9a0` applied (check: `alembic current` shows it as head).
- Login as coach (`entrenador@trochyruta.com` / `Coach2026!`, dev seed).
- For US2 only: a seeded/linked Strava activity, or the MSW/pytest fixtures below — no real Strava account needed for automated validation.

## Scenario 1 — Create a structure with guardrails (US1)

1. Open an existing training session → section **Estructura de intervalos** → *Crear estructura*.
2. Band `13-15`; add: calentamiento 5 min Z1 @70 rpm; grupo repetido ×2 (trabajo 2 min Z2 @75 + recuperación 1 min Z1 @65); vuelta a la calma 5 min Z1.
3. Save → reload the session → structure persists with the repeat group intact. ✅ SC-001 (time the flow: < 5 min).
4. Negative: set a cadence of 55 rpm → inline Zod error + server `422 cadence_below_minimum` if forced. ✅ SC-003.
5. Negative: switch band to `10-12`, add a Z3 block → save hard-blocked (`age_gate_z3_blocked`), no override offered. ✅ SC-002.
6. Band `10-12` with only Z1–Z2 → confirmation dialog appears; confirm → saves; DB row has `age_gate_confirmed=true` + user + timestamp.

```bash
cd backend && pytest tests/intervals/test_structures.py tests/intervals/test_guardrail.py -q
```

## Scenario 2 — Plan-vs-actual matching (US2)

1. With the Scenario-1 structure saved, link a Strava activity to the session (existing `LinkSessionDialog` flow). Expected: link responds fast (no Strava call inline); match computes deferred.
2. Open **Ver comparación** → detail view shows each planned block paired to its lap with badges (verde=cumplido / ámbar=fuera de tolerancia / gris=sin dato) and extra laps listed, not discarded.
3. Fewer laps than blocks → trailing blocks `sin dato`, view intact. More laps → `extra` rows. Zero laps → all `sin dato` + explicit message.
4. Edit the structure → *Recalcular* → comparison reflects the edit. ✅ SC-004.
5. Access control: parent token on `GET /api/intervals/sessions/{id}/match` → `403`. ✅ SC-008.

```bash
cd backend && pytest tests/intervals/test_matching.py tests/intervals/test_rbac.py -q
```

(`test_matching.py` unit-tests the pure engine — flattening, ±30% tolerance, <10 s lap discard, fewer/more/zero laps — without network; the runner is tested with a stubbed `get_activity_laps`.)

## Scenario 3 — Instructivo PDF (US3)

1. Session with structure → **Descargar instructivo** → pick each brand (Garmin / Magene / iGPSport) → PDF downloads (< 1 min ✅ SC-005).
2. Verify content: every block appears; brand steps differ (Garmin: `Rest → Type → Open`; Magene: duraciones fijas + lap manual; iGPSport: hoja de referencia); "desactivá la vuelta automática" present in all three; copy in español neutro.
3. Session without structure → button disabled; direct `GET .../instructivo?brand=garmin` → `404`.
4. Delivery check: no email sent, no public URL created (FR-011).

```bash
cd backend && pytest tests/intervals/test_instructivo_pdf.py -q
# Nota: el render PDF real requiere pango/glib — pasa en Docker/Render (mismo caveat que feature 024).
```

## Scenario 4 — Template library (US4)

1. Save Scenario-1 structure as template with tags (banda, fase, proximidad) → appears in `/intervals/templates`.
2. Filter by each tag → template found. Attach to a second session → blocks cloned. ✅ SC-006 (faster than from scratch).
3. Edit the template afterward → first and second sessions unchanged (copy-on-attach).
4. Attach a `10-12` template to a session → confirmation required (sub-Z3) exactly as manual build; Z3+ can't even be saved on a `10-12` template.

```bash
cd backend && pytest tests/intervals/test_templates.py -q
```

## Privacy audit (SC-007 — mandatory before merge)

```bash
cd backend && pytest tests/privacy/test_laps_privacy.py -q
```

Asserts: `StravaActivityLap` has no geo/name/cadence/watts attributes; match responses and `result_json` contain no coordinates; runner allow-list drops unexpected raw fields; logs numeric-only. Then run the `data-privacy-guard` agent audit per constitution quality gate.

## Full regression

```bash
cd backend && pytest
cd frontend && npx vitest run   # includes components/intervals/__tests__ + jest-axe on new views
```

## Expected outcomes summary

| Check | Expected |
|---|---|
| Structure CRUD + repeat groups | Persist/reload intact (US1) |
| Cadence <60 anywhere | Always 422, every band (SC-003) |
| Z3+ on 10-12 (structure, template, attach) | Always hard-blocked (SC-002) |
| 10-12 sub-Z3 save | Requires recorded confirmation |
| Link → comparison | Automatic, deferred, no coach action (SC-004) |
| Laps mismatch (fewer/more/zero) | Graceful `sin_dato`/`extra`, never an error (FR-016) |
| Recalculate | Reflects structure/lap changes (FR-015) |
| Instructivo | Per-brand PDF, manual download only (SC-005, FR-011) |
| Parent/athlete access | 403 everywhere (SC-008) |
| Geo/cadence/watts in laps or outputs | Zero instances (SC-007) |
