# Close-out gate — Phase 8 (feature 040, growth module redesign)

**Gate**: `engineering-lead` (opus) · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`
**Scope**: verification of the Phase 8 wave (T074–T079) plus a working-tree consistency pass over the whole feature.

---

## 1. Wave task verdicts

| Task | Status | Evidence (command + result) |
|---|---|---|
| **T074** — `docs/implementation-status.md` + `docs/technical-notes.md` | ✅ Done | `git diff docs/implementation-status.md` → new "Growth module redesign (specs/040-growth-module-redesign)" section, +74 lines: one row per phase (Setup, Foundational, US1–US5, Polish), a bundle-result paragraph (336.68 → 283.38 kB gzip entry, `GrowthTab-*.js` 17.42 kB gzip, −158.90 kB effective first paint) and an explicit "Deferred items" list. `git diff docs/technical-notes.md` → one dated 2026-09-04 entry covering the WHO switch, migration `2a8baa967cc6`, the idempotent recompute + id-only band-change report, the growth-summary contract, the lazy chunk with measured before/after numbers, and the removed components. Table structure and heading level match the neighbouring feature entries. |
| **T075** — superseded banners / cross-references | ✅ Done | `git diff docs/04-percentiles/workflow.md` → dated superseded banner at the top pointing to `docs/18` + `specs/040` + `docs/implementation-status.md`. `git diff docs/06-parents/workflow.md` → line 26 ("Clinical/family toggle mode in percentiles") struck through and closed with a US4 pointer. `git diff docs/README.md` → rows 04 and 18 updated with reciprocal pointers. |
| **T076** — CLAUDE.md managed block | ✅ Done | `git diff CLAUDE.md` → the `<!-- SPECKIT START/END -->` block now carries an "Active feature" paragraph (single reference standard, growth-summary endpoint, readable curve, family view, lazy chunk) naming the deferred items and the still-open close-out task. Edit is confined to the managed block; nothing outside it changed. |
| **T077** — `quickstart.md` §1–§6 walkthrough | ✅ Done | `specs/040-growth-module-redesign/checklists/quickstart-run.md` records every section. Gate re-ran the load-bearing legs independently: `cd backend && .venv/bin/python -m pytest tests/services/test_growth_seed.py tests/scripts/test_backfill_anthropometry.py tests/routers/test_anthropometry_bmi.py tests/routers/test_growth_summary.py tests/services/test_growth_summary.py -q` → **50 passed**; `cd frontend && npx vitest run src/components/athletes/growth src/lib/growth src/hooks/athletes/useGrowthSummary.test.tsx src/routes/athletes/__tests__ src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx` → **22 files / 317 passed**; `npm run typecheck` → clean. Live-stack legs (seed/backfill against a DB, coach-token `curl`, PDF regen, Playwright) are recorded as deferred with reasons — see §3. |
| **T078** — post-deploy smoke | ⏸️ **Deferred — cannot run before merge + deploy** | Steps verbatim from `tasks.md`: (1) confirm the Render startup log shows the WHO seed and the recompute summary (counts only); (2) smoke `GET /health`; (3) smoke `GET /api/athletes/{id}/growth-summary` with a coach token; (4) open the athlete page on a real Android device and confirm the growth chunk loads on tap; (5) hand the band-change report (ids only) to the coach for review before the next newsletter cycle. Owner: `release-manager`. Left unchecked in `tasks.md`. |
| **T079** — PR description | ✅ Done | `specs/040-growth-module-redesign/pr-description.md` (137 lines): Conventional Commits title `feat(growth-module): rediseña el módulo de crecimiento con OMS 2007 como referencia única`, body in español neutro, five user stories, recompute impact, measured bundle change, quality section, deferred list. `grep -niE "claude\|copilot\|chatgpt\|generated with\|ai-assisted\|anthropic"` → **no matches**. Gate fixed one stale bullet (see §2). |

## 2. Fixes applied by this gate

| # | Finding | Fix |
|---|---|---|
| 1 | `pr-description.md` §"Pendientes al cierre" listed **T074–T078** as pending Phase 8 work. T074–T077 completed in this same wave, after T079 was authored — the PR body would have under-reported the feature's own state to the reviewer. | Bullet rewritten: docs (T074–T076) and the quickstart run (T077) marked done with their artefact paths; only **T078** (post-deploy smoke) remains, with `release-manager` named as owner. `specs/040-growth-module-redesign/pr-description.md:109-114`. |

No other breakage found — no import, type, lint or test-expectation defect surfaced in this wave's files.

## 3. Deferred items carried out of the feature (accepted, with reasons)

All four are **environment/infrastructure gaps, not code defects**. None is new to this wave; each was already open and unchecked in `tasks.md` before it started.

| Task(s) | Reason accepted | Reopening steps |
|---|---|---|
| **T027** (real-MySQL `_test` migration + seed + recompute) | No `TEST_DATABASE_URL` in this environment; `pytest -m mysql` reports `7 skipped`. The only reachable stack is compose project `me`, which holds real club data and must never be written to by test tooling. | Export a `..._test`-suffixed `TEST_DATABASE_URL`, run `alembic upgrade head` + seed + backfill against it, then `pytest -m mysql`; record row counts (expect 336/336/120 WHO rows) and the id-only band-change summary in `checklists/reference-standard.md` §5. |
| **T028** (regenerate one family newsletter PDF on the dev stack) | Needs a seeded **synthetic** athlete on a non-production stack; none reachable. Partly de-risked already: the PDF caption's stale "CDC" string was found and fixed during US1 (`grep -rn "CDC" backend/templates/` → no matches), and the >10 y weight-chart omission is covered by `tests/services/training/test_growth_chart_builder.py` (both 120.5-month boundary cases). | `docker compose up` with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`, regenerate one PDF for a synthetic test athlete, confirm the "OMS 2007 · Res. 2465/2016" caption and the absent weight chart; note in `checklists/reference-standard.md`. |
| **T044**, **T054**, **T064**, and the Playwright leg of **T072** | The five specs are written and statically valid (`tsc --noEmit` clean) but were never executed green. The isolated e2e stack (`docker-compose.e2e.yml`, project `trocha-e2e`) cannot boot on a fresh volume — **confirmed independently by this gate**: `backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py:270` does an unguarded `from app.data.technique_catalog import EXERCISES, MATERIALS, SKILLS` inside `upgrade()`, reached whenever `technique_exercises` is empty (i.e. always on a fresh DB), and `ls backend/app/data/` confirms the module is gone (deleted by feature 038, commit `718d249`, per `d0e1f2a3b4c5_remove_technique_strength_catalog.py`). Two sibling migrations share the defect (`f1a2b3c4d5e6:54`, `a7b8c9d0e1f2`). **Pre-existing and outside feature 040** — it breaks any fresh database (new contributor, CI-from-scratch, disaster recovery), not just this feature's tests. Production and the developer's `me` volume are unaffected only because they already recorded the migration as applied. | Fix the three migrations (guard the import, or inline/restore the seed data), bring up `trocha-e2e`, then run `npx playwright test e2e/growth.spec.ts e2e/growth-parent.spec.ts e2e/history.spec.ts e2e/anthropometry.spec.ts e2e/target-size.spec.ts`. Owner: `database-architect`. Worth its own ticket regardless of this feature. |
| **T078** (post-deploy smoke) | Physically cannot run before the owner merges and Render deploys. | Steps listed in §1. Owner: `release-manager`. |

## 4. Working-tree consistency checks (whole feature, run by the gate)

| Command | Result |
|---|---|
| `ls specs/040-growth-module-redesign/checklists` | 15 files — every wave signed: `setup`, `foundational`, `reference-standard`, `build-baseline`, `coach-tab`, `family-copy`, `family-view`, `privacy`, `frontend-gate`, `integration-review`, `e2e-stack`, `quickstart-run`, `requirements`, `resume-notes`, plus this `close-out`. |
| `git status --short \| wc -l` | **57** before this gate (43 modified, 14 untracked) — all within the feature's ownership: `docs/*`, `CLAUDE.md`, `backend/app/services/ai/prompts/*`, `backend/tests/test_ai_router.py`, `frontend/src/**` growth surface, `specs/040-*`, plus the e2e-stack scaffolding (`docker-compose.e2e.yml`, `frontend/scripts/e2e-stack.sh`). No stray file outside the feature. |
| `cd frontend && npm run typecheck` | **Clean** (`tsc --noEmit`, no errors). |
| `cd frontend && npx vitest run` (full suite) | **327/329 files, 3950/3952 tests passed**. The 2 failures are pre-existing and unrelated — see §5. |
| `cd backend && ruff check` scoped to all 23 files feature 040 creates or touches | **All checks passed!** (The repo-wide `ruff check app tests` reports 329 findings, every one of them in files this feature never touched — pre-existing debt, left alone.) |
| `cd backend && .venv/bin/python -m pytest tests/services/test_growth_seed.py tests/scripts/test_backfill_anthropometry.py tests/routers/test_anthropometry_bmi.py tests/routers/test_growth_summary.py tests/services/test_growth_summary.py -q` | **50 passed** in 0.35 s (offline lane). |
| `grep -rn "#[0-9a-fA-F]\{6\}" frontend/src/components/athletes/growth/` (excluding `__tests__`) | **No matches** — design tokens only, no raw hex in new frontend files. |
| `grep -rn "Cronologica\|Biologica\|tecnicos" frontend/src` | 3 hits, all **pre-existing and outside this feature** (`focos_tecnicos` data key / `focos-tecnicos` test id in `newsletterHandlers.ts` and `MonthlyMetricsTable.tsx`+test; `git diff --name-only main...HEAD` → not touched by this branch). No display copy is affected; the T053 gate on user-visible strings holds. |
| `grep -rn "first_name\|last_name\|birth_date" frontend/src/components/athletes/growth/` | 16 hits, all allowed: `birth_date` only as a prop input to the bio-age/family-stage helpers (never rendered); `first_name`/`last_name` only in `__tests__/` fixtures with fictitious names. `grep -rn "athlete\.first_name\|athlete\.last_name"` in the growth folder → no matches. |
| Secret scan of `checklists/e2e-stack.md` (untracked file, flagged by the T079 worker) | **No literal secret values present.** The only match for the secret variable names is the line documenting that `docker compose config` was run *with* `grep -v` redaction. See §6. |

## 5. Pre-existing failures (not counted against this wave)

| Failure | Attribution |
|---|---|
| `frontend/src/lib/__tests__/datetime.test.ts` → `currentSeason` timezone assertion | Known pre-existing timezone assumption; file untouched by this branch. |
| `frontend/src/hooks/ai/useRaceRun.test.ts` → "un run que sí llega a estado terminal…" | Timer-sensitive flake under full-suite load. **Passes in isolation** (`npx vitest run src/hooks/ai/useRaceRun.test.ts` → 21/21). `git diff --name-only main...HEAD` → file not touched by this branch; last modified by commit `5af8e41` (feature 037). |
| Backend `pytest -q` MySQL `OperationalError`s | No local MySQL reachable; documented in `docs/technical-notes.md`. |
| Backend WeasyPrint `libgobject-2.0-0` failures | Missing native libs unless `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` is set. |
| `TaskDispatcher.dispatch()` fire-and-forget assertions in `test_training_session_notifications.py` | Latent pre-existing bug, attributed in feature 038's close note. |
| Repo-wide `ruff check app tests` — 329 findings | All in files outside this feature's diff. |

## 6. Advisory for the owner (not a gate failure)

`checklists/e2e-stack.md` records that, during this feature's e2e-stack setup, an **unfiltered `docker compose config` run transiently printed real secret values** (`JWT_SECRET_KEY`, `AI_API_KEY`, `RACE_AI_API_KEY`, `MYSQL_PASS` / `MYSQL_ROOT_PASSWORD`, Strava secrets) into that session's tool output. This gate verified that **no secret value was persisted**: the checklist itself contains none (redaction-scan above), and `.env*` remains gitignored. The exposure was ephemeral transcript output only. Whether to rotate those credentials before merge is the owner's call — flagged here so the decision is deliberate rather than implicit.

---

## Verdict

**PASS.** Every Phase 8 task is either verified complete (T074, T075, T076, T077, T079 — marked `[X]` in `tasks.md`) or explicitly deferred with an accepted infrastructure reason recorded above (T078, plus the carried-over T027/T028/T044/T054/T064 and T072's Playwright leg, all left unchecked). Typecheck clean, feature-scoped lint clean, 50 backend and 3950 frontend tests green, token/diacritics/privacy grep gates green, no raw hex, no minor-identifiable data in any new file.

The feature is **ready to merge**, with two follow-ups that outlive it: the fresh-database migration bug (`database-architect`, worth its own ticket — it blocks any from-scratch deploy, not just this feature's e2e) and the post-deploy smoke T078 (`release-manager`).

**Signed**: `engineering-lead` (wave gate) — 2026-09-04
