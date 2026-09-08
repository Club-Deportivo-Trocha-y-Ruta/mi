# Quickstart run — feature 040 (T077)

**Owner**: `qa-engineer` · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`
**Scope**: `quickstart.md` §1–§6, executed as far as the environment safely allows.

**Environment note (applies to every deferred item below)**: the only Docker stack reachable in this session is compose project `me` (`me-backend-1` / `me-mysql-1` / `me-mailhog-1`, ports 8000/3306/8025), which — per `checklists/e2e-stack.md` and this branch's standing convention — **holds real club data** and must never be mutated or queried by test tooling. Backend `Settings` (`backend/app/config.py`) loads `env_file=".env"` by default, so any bare `.venv/bin/python -m app.<script>` invocation from this shell would connect to that same real database. The isolated synthetic stack (`docker compose -p trocha-e2e`, ports 8001/3307/8026) is currently torn down (`docker ps -a --filter name=trocha-e2e` → empty) and, per `checklists/e2e-stack.md`, blocked from a clean bring-up by a pre-existing, feature-040-unrelated Alembic migration bug (`e1f2a3b4c5d6_technique_gymkhana_library.py` imports the deleted `app.data.technique_catalog`). Fixing that migration or restarting the isolated stack is outside this task's ownership (`checklists/quickstart-run.md` only) and outside "do not fix code" — so every step below that needs a live backend against non-production data is recorded as **deferred**, not skipped silently.

---

## §1 — Reference standard (US1)

| Command | Result |
|---|---|
| `cd backend && .venv/bin/python scripts/export_who_lms_csv.py` | Re-ran; **byte-identical** to the committed CSVs. SHA-256 unchanged: bmi `bd54748d…`, height `2deb948c…`, weight `5de34ff5…` (matches `checklists/reference-standard.md` §2). `git status --short app/data/who_lms` → clean. |
| `.venv/bin/python -m app.seed_growth_data` | ⏸️ **Deferred** — would connect to the real `me` MySQL via `backend/.env` (no `TEST_DATABASE_URL`/isolated stack available); not run. Idempotency and row counts already covered offline by T016. |
| `.venv/bin/python -m app.scripts.backfill_anthropometry` | ⏸️ **Deferred** — same reason; would recompute/write Z-scores on real athlete records. Covered offline by T017/T023. |
| `.venv/bin/python -m pytest tests/services/test_growth_seed.py tests/scripts/test_backfill_anthropometry.py tests/routers/test_anthropometry_bmi.py -q` | **20 passed** |

Manual check ("tile Z/percentile == curve hover == table row == family PDF value") — not re-verified live; already signed with file:line evidence in `checklists/reference-standard.md` §3 (SC-001, data-platform-lead, 2026-09-04). No code changed since then that would invalidate it.

## §2 — Growth summary endpoint (US2)

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest tests/routers/test_growth_summary.py -q` | **11 passed** (all 11 contract cases incl. 403 cross-parent and the privacy invariant) |
| `curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/athletes/2/growth-summary` | ⏸️ **Deferred** — no coach JWT available without either logging into the real `me` stack (real athlete id) or reading `.env` for credentials, both out of bounds. The full response contract is exercised offline by the 11 router tests above. |

## §3 — Coach tab (US2, US3, US5)

| Command | Result |
|---|---|
| `cd frontend && npx vitest run src/components/athletes/growth src/lib/growth src/hooks/athletes/useGrowthSummary.test.tsx` | **20 files / 311 passed** |
| `npm run typecheck` | Clean (`tsc --noEmit`, no errors) |
| `npm run build` | Succeeds; entry `dist/assets/index-*.js` 283.43 kB gzip (matches the 283.38 kB baseline in `checklists/build-baseline.md` within hash/minifier noise) |
| `bash scripts/check-chart-chunk.sh` (`npm run check:chunks`) | `OK — recharts chunk and WHO growth reference are not on the entry path.` |
| `npx playwright test e2e/growth.spec.ts e2e/history.spec.ts` | ⏸️ **Deferred** — needs a live backend with synthetic seed data; the isolated e2e stack is down and currently cannot boot cleanly (pre-existing migration blocker above), and Playwright must never target the `me` stack. Ties to open task **T044** (part 1, written not run) and the un-run part 2 under **T054**. |

Manual viewport check (1024 px / 390 px, chart toggle, PNG export) — not re-verified live for the same reason; covered by the automated component tests above and the SC-008 sign-off in `checklists/coach-tab.md` (T055).

## §4 — Family view (US4)

| Command | Result |
|---|---|
| `npx vitest run src/components/athletes/growth/GrowthTab.parent.test.tsx` | Ran at its actual path, `src/components/athletes/growth/__tests__/GrowthTab.parent.test.tsx` (quickstart's path predates the `__tests__/` co-location used by the shipped suite) → **15 passed** |
| `npx playwright test e2e/growth-parent.spec.ts` | ⏸️ **Deferred** — same isolated-stack blocker as §3. Ties to open task **T064**. |

Manual parent-view check (latest measurement drives cards, no `Z=`/`P\d+` text, no bibliography, read-only AI card) — not re-verified live; the same assertions are encoded in the vitest file above (15/15 green) and in `checklists/privacy.md` (T065).

## §5 — Accessibility and privacy gates

| Command | Result |
|---|---|
| `npx vitest run --reporter=verbose src/components/athletes/growth/__tests__/GrowthTab.a11y.test.tsx` | **2 passed** — 0 axe violations (coach mode, with and without records) |
| `grep -rn "first_name\|last_name\|birth_date" frontend/src/components/athletes/growth/` | 16 hits, all allowed: `birth_date` appears only as a prop input (`birthDate={athlete.birth_date}` in `GrowthCurveSection.tsx`, feeding the bio-age/family-stage helpers, never rendered as text); `first_name`/`last_name` appear only in test fixtures under `__tests__/` using fictitious names ("Atleta Ficticia/Prueba", "Persona Ficticia"). Confirmed no component renders `athlete.first_name`/`.last_name` (`grep -rn "athlete\.first_name\|athlete\.last_name" frontend/src/components/athletes/growth/` → no matches). |

`checklists/privacy.md` (T065, `data-privacy-guard`) already signed for this feature — not re-run here.

## §6 — Family PDF (R-14)

| Command | Result |
|---|---|
| `cd backend && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest tests -k "newsletter and pdf" -q` | **23 passed**, 3949 deselected — no WeasyPrint native-lib errors with the fallback path set |
| Manual: regenerate one newsletter PDF for a test athlete in the dev stack, confirm "OMS 2007" caption and no weight chart above 10 y | ⏸️ **Deferred** — needs a seeded test athlete in a non-production stack; the isolated stack is down (blocker above). The two assertions are already pinned by unit/integration tests: the caption fix is recorded in `checklists/reference-standard.md` §6 (`grep -rn "CDC" backend/templates/` → no matches), and the >10 y weight-chart omission is covered by `tests/services/training/test_growth_chart_builder.py` (both 120.5-month boundary cases) included in the 23 passed above. |

---

## Summary

| Category | Status |
|---|---|
| Offline pytest (§1, §2, §6) | **54 passed**, 0 failed |
| Frontend vitest (§3, §4, §5) | **333 passed**, 0 failed, 0 a11y violations |
| `npm run typecheck` | Clean |
| `npm run build` + `check:chunks` | Green, entry 283.43 kB gzip, recharts/WHO reference off the entry path |
| Privacy grep gate | Pass (no rendered PII) |
| Playwright e2e (§3, §4) | Deferred — isolated stack down (pre-existing migration bug, unrelated to feature 040), `me` stack off-limits |
| Live-stack manual checks (§1 curl, §2 curl, §6 PDF regen) | Deferred — same real-data / isolated-stack constraints |

**No code was changed by this task.** Everything reachable offline is green; every deferral is an environment/infrastructure gap already documented elsewhere on this branch (`checklists/e2e-stack.md`, `checklists/reference-standard.md`), not a new finding. Remaining gaps (T044, T054, T064, T072 e2e runs; T027/T028 live-DB runs) require either fixing the unrelated Alembic migration bug or standing up the isolated e2e stack — both out of this task's scope.
