# Checklist — Phase 3 / User Story 1: one reference standard (WHO 2007)

**Wave gate**: `data-platform-lead` (opus)
**Date**: 2026-09-04
**Branch**: `feat/040-growth-module-redesign`
**Scope**: T016–T029

---

## 1. Task table

| Task | Status | Evidence (command → result) |
|---|---|---|
| **T016** — WHO seed tests (row counts, idempotency, 6-point L/M/S parity) | ✅ Done | `cd backend && .venv/bin/python -m pytest tests/services/test_growth_seed.py -q` → **7 passed** (4 pre-existing CDC + 3 new WHO). Counts asserted 168/168/60 per sex; parity vs `frontend/src/data/growth-reference-who.json` to 6 decimals. |
| **T017** — recompute tests (CDC→WHO switch, raw untouched, weight NULL > 120.5 m, idempotent, report shape, no PII in caplog) | ✅ Done | `cd backend && .venv/bin/python -m pytest tests/scripts/test_backfill_anthropometry.py -q` → **7 passed** (3 pre-existing + 4 new). |
| **T018** — POST stores `growth_source='WHO'`, hand-computed Z ±0.02, weight NULL for 14 y / populated for 8 y | ✅ Done | `cd backend && .venv/bin/python -m pytest tests/routers/test_anthropometry_bmi.py -q` → passing inside the 101-test group below. |
| **T019** — frontend `zScoreFromLMS` ↔ backend `calculate_z_score` parity | ✅ Done | `cd frontend && npx vitest run src/lib/growth` → **6/6** in `lms.parity.test.ts`; synthetic fixtures only. |
| **T020** — deterministic WHO CSV exporter + provenance README | ✅ Done | `cd backend && .venv/bin/python scripts/export_who_lms_csv.py` → `336 / 336 / 120` rows. Determinism proven by SHA-256 before/after a second export: **identical** (see §2). |
| **T021** — `seed_growth_data.py` WHO sources | ✅ Done | Covered by T016 (row counts + idempotency green). |
| **T022** — router computes with `GrowthSource.WHO`, nulls weight > 120.5 m, persists `growth_source` | ✅ Done | T018 tests green; `app/routers/anthropometry.py` uses `WEIGHT_AGE_MAX_MONTHS = 120.5`. |
| **T023** — `recompute_to_source(session, target=WHO)` wired into `run()` | ✅ Done | T017 tests green; report `./data/growth_band_changes_<YYYYMMDD>.json` carries ids only (§4). |
| **T024** — chart builder on WHO + weight chart omitted > 10 y | ✅ Done | `cd backend && .venv/bin/python -m pytest tests/services/training/test_growth_chart_builder.py -q` → green, incl. both 120.5-month boundary cases and `reason_no_data == "weight_over_10y"`. |
| **T025** — `useGrowthMetrics` trusts stored values only when `growth_source === "WHO"`, exposes `source` | ✅ Done | `cd frontend && npx vitest run src/hooks/athletes` → **21/21**. |
| **T026** — tooltip + sr-only table read stored Z/percentile; source caption in `NutritionalClassification` | ✅ Done | `cd frontend && npx vitest run src/components/athletes` → green; T011 characterization suite **16/16 unchanged**. Caption matches `contracts/band-vocabulary.md`. |
| **T027** — migration + seed + recompute on a real MySQL `_test` DB | ⏸️ **Deferred** | `TEST_DATABASE_URL` **not set** in this environment; `pytest -m mysql` → **7 skipped, 3922 deselected**. See §5. |
| **T028** — regenerate one family newsletter PDF on the dev stack | ⏸️ **Deferred** (partially pre-verified) | End-to-end PDF needs the dev stack + a seeded test athlete. Both assertions pre-verified offline — see §5. |
| **T029** — wave review, SC-001 signed | ✅ Done | See §3. |

**Result**: 12 of 14 tasks verified complete; T027 and T028 deferred with accepted infrastructure reasons.

---

## 2. Gate commands run by the wave gate

| Command | Result |
|---|---|
| `cd backend && ruff check app tests scripts` | 344 errors repo-wide, **all pre-existing**; exactly **1** was in a wave-touched file (unused `model_validator` import in `app/schemas/anthropometry.py`, present at `HEAD`) → **fixed**. Re-run limited to the 11 wave files: **All checks passed**. |
| `cd backend && .venv/bin/python -m pytest tests/services/test_growth_seed.py tests/scripts/test_backfill_anthropometry.py tests/routers/test_anthropometry_bmi.py tests/test_growth_service.py -q` | **101 passed** |
| `cd backend && .venv/bin/python -m pytest tests -k "growth_chart or newsletter" -q` | **311 passed**, 3618 deselected — no WeasyPrint failures in this selection |
| `cd backend && .venv/bin/python scripts/export_who_lms_csv.py && git status --short backend/app/data/who_lms` | Re-export byte-identical. SHA-256 stable across two runs: bmi `bd54748d…`, height `2deb948c…`, weight `5de34ff5…`. `git status` shows only `?? backend/app/data/who_lms/` (directory never staged yet — not a re-export diff). |
| `cd frontend && npm run typecheck` | **Clean** (`tsc --noEmit`) |
| `cd frontend && npx vitest run src/lib/growth src/hooks/athletes src/components/athletes` | **54 files / 726 tests passed** |
| `cd frontend && npx vitest run src/routes/parents` | **13 files / 114 tests passed** (after the fixture fix in §6) |
| `cd backend && .venv/bin/python -m pytest -q` (full offline lane) | 3656 passed / **225 failed** / 30 skipped — all 225 pre-existing and environmental (§7) |
| `cd frontend && npx vitest run` (full suite) | 3775 passed / **1 failed** — the pre-existing `datetime.test.ts` timezone flake (§7) |

---

## 3. SC-001 sign-off (T029)

**Claim**: for one record, the tile, the curve hover and the table show the same Z / percentile / band, taken from the same stored record.

Verified by reading the three resolution paths — they are semantically identical:

1. **Tile / classification** — `frontend/src/hooks/athletes/useGrowthMetrics.ts:211`
   `const canUseStored = backendZ !== null && record.growth_source === "WHO";`
   then `percentile = backendZ.percentile ?? percentileFromZ(zScore)`, `band = classifyBand(indicator, zScore)`.
2. **Curve hover (tooltip)** — `frontend/src/components/athletes/PercentileCurves.tsx:463-470`
   `if (row.storedZScore != null) { zScore = row.storedZScore; percentile = row.storedPercentile ?? percentileFromZ(zScore); }` … `band = classifyBand(indicator, zScore)`.
3. **sr-only table** — `frontend/src/components/athletes/PercentileCurves.tsx:890-894`
   `const z = row.storedZScore ?? zScoreFromLMS(...); const p = row.storedPercentile ?? percentileFromZ(z);`

`storedZScore` is populated by `extractStoredZ` (`PercentileCurves.tsx:262-281`), whose gate is the **same** predicate — `if (record.growth_source !== "WHO") return null;` — over the same per-indicator column pair. The null-percentile fallback (`?? percentileFromZ(z)`) and the band function (`classifyBand(indicator, z)`) are identical across all three. Legacy rows (`growth_source` `null`/`CDC`) fall back to client LMS **consistently in all three surfaces**, so the tile can never disagree with the hover or the table.

The helper is deliberately duplicated rather than imported (to keep the hook mockable in the a11y/characterization suites). **Noted as a divergence risk** for Phase 5: `PercentileChart.tsx`/`PercentileTable.tsx` must reuse one shared helper — recorded as a follow-up for T050/T051.

**PDF leg of SC-001**: see §4 — the template caption was stale and has been corrected.

**Signed**: data-platform-lead — 2026-09-04.

---

## 4. Privacy check (recompute report + PDF)

- Band-change report entries carry **ids only**: `athlete_id`, `record_id`, `indicator`, `previous`, `current` (`app/scripts/backfill_anthropometry.py:306-326`). No name, no birth date. `birth_date` is read in memory to compute age and never written out.
- Logging is aggregate-only; T017 asserts `caplog` contains no `first_name` / `birth_date`.
- Seed CSVs are population constants only — no athlete data (`app/data/who_lms/README.md`).
- No minor data appears in this checklist.

---

## 5. Deferred tasks

### T027 — real MySQL `_test` database
**Reason**: `TEST_DATABASE_URL` is not set in this environment. A socket probe (no credentials printed) found `127.0.0.1:3306` open and `mysql:3306` unresolvable (docker-compose-only hostname), but without `TEST_DATABASE_URL` there is no `_test` database name or credentials to connect with, and reading `.env*` is forbidden.
**Evidence**: `cd backend && .venv/bin/python -m pytest -m mysql -q` → `7 skipped, 3922 deselected`.
**To close**: export `TEST_DATABASE_URL=mysql+aiomysql://…/<name>_test`, then run `alembic upgrade head`, the seed, `python -m app.scripts.backfill_anthropometry`, and `pytest -m mysql`; record row counts (expect 336/336/120 WHO rows) and the band-change summary (ids only) here.
**Owner**: `database-architect`.

### T028 — family newsletter PDF on the dev stack
**Reason**: needs `docker compose up` plus a seeded test athlete. The docker daemon is running, but the app database is not reachable for this session (same blocker as T027).
**Partially pre-verified offline**, so the residual risk is low:
- WeasyPrint native libs work locally with the documented fallback: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` → `WeasyPrint import: OK 68.1`, and `pytest tests/services/notification/test_stage_log_pdf.py` → **15 passed** (vs 13 failures without the variable — an env-var issue, not a code defect).
- "Weight chart absent above 10 y" is pinned by unit tests at the builder level, including both 120.5-month boundary cases.
- "Label reads OMS 2007" **was not true before this review** — see §6.
**To close**: bring up the dev stack, regenerate one PDF for a test athlete, confirm visually.
**Owner**: `qa-engineer`.

---

## 6. Fixes applied by the wave gate

1. **`backend/templates/documents/pdf/athlete_stage_log.html`** — the family PDF still captioned the percentile annex as CDC while the builder had switched to WHO (T024), i.e. a direct SC-001 violation on the PDF surface that only the deferred T028 would have caught:
   - `"Comparación con población de referencia CDC."` → `"… de referencia OMS 2007."`
   - `"Fuente: tablas CDC 2000 (5-19 años). De acuerdo con Res. 2465/2016 MinSalud Colombia."` → `"Fuente: OMS 2007 · Res. 2465/2016 — MinSalud Colombia (referencia 5-19 años; peso para la edad solo hasta los 10 años)."`
   - annex intro `"Referencias OMS/CDC adaptadas"` → `"Referencias OMS 2007 adaptadas"`
   `grep -rn "CDC" backend/templates/` now returns nothing. Tests after the edit: **32 passed**.
2. **`frontend/src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx`** — `makeRecord()` fixtures set stored Z but no `growth_source`, so T025's WHO gating made the hook recompute client-side and the T004 regression test stopped detecting the record-ordering bug it guards. Added `growth_source: "WHO"` to the fixture defaults with a comment explaining why. Suite back to **114/114**.
3. **`backend/app/schemas/anthropometry.py`** — removed the unused `model_validator` import (pre-existing at `HEAD`, but the only ruff error in a wave-touched file).

---

## 7. Pre-existing failures (not attributable to this wave)

| Symptom | Count | Cause |
|---|---|---|
| `OperationalError: Can't connect to MySQL server on 'mysql'` | ~211 | Tests that exercise the real `app.main.app` / DB and need the docker network. Spread over `test_users.py`, `test_training_session_router.py`, `test_athletes.py`, `test_clubs.py`, `test_auth.py`, etc. **None** in a file this wave touched. |
| `OSError: cannot load library 'libgobject-2.0-0'` | 13 | WeasyPrint native libs; passes with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`. |
| `test_ai_factory.py` — `DID NOT RAISE LLMConfigError` | 1 | Environment-dependent AI provider config. |
| `frontend src/lib/__tests__/datetime.test.ts` — `currentSeason` | 1 | Pre-existing wall-clock/timezone flake; file untouched. |
| `ruff check app tests scripts` | 343 remaining | Repo-wide lint debt; the project has no clean ruff baseline. None in wave-touched files. |

---

## 8. Follow-ups for later phases

- **Phase 5 (T050/T051)**: `PercentileChart.tsx` and `PercentileTable.tsx` must consume a single shared stored-value helper instead of re-duplicating `extractStoredZ`, to keep SC-001 structurally guaranteed after `PercentileCurves.tsx` is deleted in T052.
- **`frontend/src/components/athletes/ResearchReferences.tsx`** still lists "CDC — Growth Charts Data Files" as a bibliography entry. Legitimate as a citation, but confirm during Phase 7 that it is not read as the app's active standard.
- T027 and T028 must be closed before the US1 deploy is called done.
