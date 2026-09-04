# Checklist — Phase 1 Setup (feature 040, growth module redesign)

**Wave**: Phase 1 — Setup · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`
**Gate**: `engineering-lead` (wave review) · **Workers**: `react-ui-engineer` (T002), `qa-engineer` (T003)

## Result

| Task | Owner | Status | Evidence (command → result) |
|---|---|---|---|
| T001 — branch + build baseline | engineering-lead | **Done** | `git rev-parse --abbrev-ref HEAD` → `feat/040-growth-module-redesign`. `checklists/build-baseline.md` exists with the R-08 numbers (entry 1,292.02 kB raw / 336.68 kB gzip; recharts chunk `useAthleteInsights-*.js` 367.65 kB / 107.39 kB gzip; WHO JSON inside entry). Cross-checked against the real `dist/`: `stat -f%z dist/assets/index-*.js` → 1,292.03 kB raw, `stat -f%z dist/assets/useAthleteInsights-*.js` → 367.66 kB raw (raw sizes match; the CLI `gzip -9` recompute gives 330.16 / 106.11 kB — ~2 % below Vite's reported gzip because of the different compression level, so Vite's reported numbers stay authoritative). |
| T002 — folder skeletons | react-ui-engineer | **Done** | `ls -la frontend/src/components/athletes/growth/` → `index.ts` (`export {}` barrel) + `__tests__/.gitkeep`. `cat backend/app/data/who_lms/README.md` → placeholder matching `contracts/who-lms-seed.md` (file list, provenance URL, "population constants only, no athlete data" note). `cd frontend && npm run typecheck` → **exit 0**, 0 errors (empty barrel does not break `tsc`). `npx vitest run src/lib/growth` → **2 files / 49 tests passed** (test discovery unaffected by the empty `__tests__/` dir). |
| T003 — build gate `check:chunks` | qa-engineer | **Done** | `cd frontend && bash scripts/check-chart-chunk.sh` → **exit 1** (expected red until Phase 7); reported all three conditions: `index.html` module-preloads `useAthleteInsights-DNKuU2NA.js`, entry `index-ldVWY3yi.js` statically imports it, entry contains `WHO 2007 Growth Reference`. Pass path verified independently by the gate: a temp copy of `dist/` with the modulepreload removed, the static import renamed and the WHO string redacted → **exit 0** (the gate is not a permanent red). `node -e "…package.json"` → `check:chunks = bash scripts/check-chart-chunk.sh`; `git diff frontend/package.json` → single added line. Script is cwd-independent (`bash frontend/scripts/check-chart-chunk.sh` from the repo root → same result). |

## Verification commands run by the gate

| Command | Result |
|---|---|
| `git rev-parse --abbrev-ref HEAD` | `feat/040-growth-module-redesign` |
| `cd frontend && npm run typecheck` | PASS — exit 0, 0 errors |
| `cd frontend && bash scripts/check-chart-chunk.sh` | FAIL — exit 1 (expected; 3/3 conditions still red until Phase 7 / T071) |
| gate pass-path sandbox (mutated copy of `dist/` in `/tmp`) | PASS — exit 0 |
| `cd frontend && npx vitest run src/lib/growth` | PASS — 2 files, 49 tests |
| `node -e "require('./frontend/package.json')"` | PASS — `check:chunks` script present, package.json valid |
| privacy grep over the three new files (`nombre|apellido|birth_date|fecha de nacimiento`) | PASS — no matches; the wave adds no fixtures and no athlete data |

## Deferred / not applicable in this wave

- None. No task of Phase 1 is blocked; nothing needed live MySQL, the dev stack or a deploy.
- `ruff check` not run for this wave: the only backend artifact added is `backend/app/data/who_lms/README.md` (Markdown), no Python touched.

## Notes for the next wave (Phase 2)

1. The gate is **intentionally red** and must stay red until T071. Do not "fix" it earlier by touching the script; the green condition is the lazy `GrowthTab` + dynamic WHO `import()`.
2. `dist/` in the working tree is the T001 baseline build. Re-run `npm run build` before trusting `check:chunks` after any bundling change.
3. Minor robustness note (not breakage, no action taken): `check-chart-chunk.sh` uses `find … | head -n 1` under `set -euo pipefail`; harmless with today's 113 asset files (output far below the pipe buffer), worth revisiting only if the assets directory grows by an order of magnitude.
4. Pre-existing repo state, unrelated to this wave: `.specify/feature.json`, `CLAUDE.md` and `docs/README.md` are modified by the earlier Spec Kit planning step; `docs/18-growth-module-redesign/` and `specs/040-growth-module-redesign/` are untracked planning artifacts.
5. Phase 2 entry conditions are met: skeleton folders exist for T038/T039 components, and the build gate is wired for T071.

**Signed**: engineering-lead (wave gate) — 2026-09-04. Phase 1 status: **pass** (T001, T002, T003 verified complete).
