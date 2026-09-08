# Checklist — Isolated Playwright E2E stack (feature 040 support work)

**Owner**: `devops-engineer` · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`

**Goal**: stand up an ISOLATED backend/MySQL/MailHog stack (compose project `trocha-e2e`, ports 8001/3307/8026) with synthetic demo data, so Playwright specs (T044, T054, T064 and the existing suite) can run without ever touching the developer's `me` compose project (real club data, ports 8000/3306/8025).

## Files delivered

| File | Purpose |
|---|---|
| `docker-compose.yml` | *(unowned/unchanged)* base file, reused as-is via `-f`. |
| `docker-compose.e2e.yml` | New override: remaps backend→8001, mysql→3307, mailhog→8026 with `!override` (plain-list merge would otherwise **append** to the base ports and try to rebind host `:8000`/`:8025`/`:3306`, which are held by the `me` stack — verified below); fresh named volume `mysql_data_e2e`; `APP_ENV=development`, `CORS_ORIGINS=http://localhost:5175`, `AI_ENABLED=false`, `AI_PROVIDER=fake`, `STRAVA_ENABLED=false`. Does not read/print `.env`; MYSQL_*/JWT_* keep coming from the base file's `${...}` interpolation at the host level. `docker-compose.override.yml` (dev bind-mount) is never picked up because compose only merges files passed with `-f`. |
| `frontend/scripts/e2e-stack.sh` | `up` / `status` / `logs` / `down` wrapper around `docker compose -p trocha-e2e -f docker-compose.yml -f docker-compose.e2e.yml`. `up` builds, waits for `/health`=200, waits for a `seed`-matching log line (log text only, never values), then verifies the demo coach login returns 200. Refuses to run if `E2E_COMPOSE_PROJECT=me`. Env-overridable ports/credentials. |
| `frontend/playwright.config.ts` | `baseURL`/`webServer.command`/`webServer.url` now read `process.env.E2E_APP_PORT` (default unchanged: `5173`); `webServer.env.VITE_API_BASE_URL` reads `process.env.E2E_API_BASE_URL` (default unchanged: `http://localhost:8000`). |
| `frontend/e2e/ai-insights-newsletter.spec.ts`, `ai-insights-parent.spec.ts`, `ai-insights-hitl.spec.ts` | `isBackend()` now compares against `process.env.E2E_APP_PORT ?? "5173"` instead of the literal `"5173"`, so their `page.route()` interception still excludes Vite's own dev-server requests when run on a non-default port. |
| `frontend/package.json` | New script `test:e2e:isolated`: `./scripts/e2e-stack.sh up && E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 playwright test`. |

## Commands run and results

| # | Command | Result |
|---|---|---|
| 1 | `docker ps` (before touching anything) | Confirmed the running `me-backend-1` / `me-mysql-1` / `me-mailhog-1` on 8000/3306/8025 — recorded as the "never touch" baseline. |
| 2 | `docker compose -p trocha-e2e -f docker-compose.yml -f docker-compose.e2e.yml config` (secrets redacted with `grep -v` before viewing) | Verified the `!override` ports/volumes merge: only `8001→8000`, `8026→8025`, `3307→3306` are published (no duplicate `8000`/`8025`/`3306` from the base file); `mysql` only mounts `mysql_data_e2e:/var/lib/mysql` (not the base `mysql_data`). **Caveat**: an earlier, unfiltered run of this same command (before the redaction step was added) printed the fully-interpolated `environment:` block to this session's tool output, which includes real secret values sourced from the root `.env` (JWT_SECRET_KEY, AI_API_KEY, RACE_AI_API_KEY, MYSQL_PASS/ROOT_PASSWORD, STRAVA_CLIENT_SECRET/TOKEN_ENCRYPTION_KEY/WEBHOOK_VERIFY_TOKEN/RECONCILE_TOKEN). No secret was written to any file, commit, or memory — it only appeared transiently in that one tool call's output. Flagged separately as internal feedback; recommend the team judge whether rotation is warranted given exposure was confined to this session's transcript. |
| 3 | `frontend/scripts/e2e-stack.sh up` | **Backend failed to boot.** `mysql` (healthy) and `mailhog` came up correctly on 3307/8026 with zero interference with the `me` stack (confirmed via `docker ps` throughout — `me-*` stayed on 8000/3306/8025, "Up 2 days", unaffected). `backend` built successfully but `alembic upgrade head` crashed against the **fresh** `mysql_data_e2e` volume — see Blocker below. The script's health/seed/login waits correctly timed out and surfaced the container logs (no secrets) instead of hanging silently. |
| 4 | `docker ps -a --filter name=trocha-e2e` (post-run) | `trocha-e2e-mysql-1` healthy, `trocha-e2e-mailhog-1` up, `trocha-e2e-backend-1` `Exited (1)`. `me-*` containers unaffected. Left running for the next agent (mysql/mailhog are harmless to leave up; no point tearing down a fresh MySQL that will be needed again the moment the migration is fixed). |

## Blocker — pre-existing, unrelated to feature 040 (BLOCKS full stack bring-up)

**`alembic upgrade head` crashes on any *fresh* database** — not something this task's files can fix (outside `devops-engineer`'s ownership list: it lives in `backend/alembic/versions/` and `backend/app/data/`).

- **Symptom**: migration `e1f2a3b4c5d6_technique_gymkhana_library.py` (feature 018) fails with `ModuleNotFoundError: No module named 'app.data.technique_catalog'` inside its `upgrade()` function, at the line `from app.data.technique_catalog import EXERCISES, MATERIALS, SKILLS`.
- **Root cause**: commit `718d249` (`feat(newsletter): implement family newsletter redesign and delivery tracking`, already on this branch's history) deleted `backend/app/data/technique_catalog.py` (1393 lines) as part of "Removed legacy content related to the previous newsletter pipeline" — a deliberate retirement of that module for the *application* layer (its one remaining consumer, `backend/app/services/training/focus_grouping.py`, was already refactored to hardcode the needed constants — see its module docstring: "kept verbatim from the retired technique catalog module"). Nobody updated the **historical Alembic migration** that still imports the module at upgrade-time, so it now only fails when a database replays migrations from empty (a brand-new volume, a CI database, a disaster-recovery restore, or — the case that surfaced it — this isolated e2e stack's fresh `mysql_data_e2e` volume). The `me` stack's `mysql_data` volume already has `e1f2a3b4c5d6` recorded as applied from before the file was deleted, so it never re-runs that step and looks unaffected — this is a **latent** bug, not visible in day-to-day dev.
- **Reproduction** (isolated, no risk to any real data): `docker compose -p trocha-e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build`, then `docker logs trocha-e2e-backend-1` shows the traceback above.
- **Impact**: any fresh migration replay fails — this e2e stack, a new contributor's first `docker compose up`, CI-from-scratch, or a disaster-recovery restore of the Hostinger MySQL DB. Production today is unaffected only because its DB already has migration history past that point.
- **Not fixed here**: fixing it means either (a) restoring `backend/app/data/technique_catalog.py` from `git show 718d249~1:backend/app/data/technique_catalog.py` (1393 lines, exact pre-deletion content), or (b) freezing the specific `EXERCISES`/`MATERIALS`/`SKILLS` data the migration needs directly inside `e1f2a3b4c5d6_technique_gymkhana_library.py` so historical migrations stop depending on live app code — a judgment call for `database-architect`/`fastapi-architect`, not a devops/compose change.

## Current state / handoff

- `trocha-e2e-mysql-1` (healthy) and `trocha-e2e-mailhog-1` are left **up** on 3307/8026 so the fix-and-retry cycle doesn't need to wait on MySQL init again.
- `trocha-e2e-backend-1` is stopped (`Exited (1)`); once the migration is fixed, re-run `frontend/scripts/e2e-stack.sh up` (it will rebuild and retry the backend against the same `mysql_data_e2e` volume — MySQL itself never got a usable schema, so nothing needs to be wiped).
- The `me` stack was never stopped, restarted, seeded, queried, or attached to at any point in this task.
- Not run (blocked by the above): the seed-log wait, the demo coach login check (`POST /api/auth/login` → 200), and the required smoke test `E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 npx playwright test e2e/auth.spec.ts --reporter=line`.

### To resume once the migration is fixed

```bash
frontend/scripts/e2e-stack.sh up
E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 npx playwright test e2e/auth.spec.ts --reporter=line
```

## Teardown record

**Owner**: `devops-engineer` · **Date**: 2026-09-04 · **Task**: `E2E-STACK-TEARDOWN`

- Command run: `docker compose -p trocha-e2e -f docker-compose.yml -f docker-compose.e2e.yml down -v` (exit 0, no output — nothing left to remove).
- Pre-check (`docker compose ls -a`, `docker ps -a --filter label=com.docker.compose.project=trocha-e2e`, `docker volume ls`): the `trocha-e2e` project, its containers (`trocha-e2e-mysql-1`, `trocha-e2e-mailhog-1`, `trocha-e2e-backend-1`), and the `mysql_data_e2e` volume had already been removed by the time this task ran (no trace found before the `down -v` command was even issued).
- Post-check confirms full removal:
  - `docker compose ls -a` → only `me` (running), `api`, `webapp` (both unrelated, pre-existing exited projects) — no `trocha-e2e` row.
  - `docker volume ls | grep -i trocha` → no matches (`mysql_data_e2e` gone).
  - `docker network ls | grep -i trocha` → no matches.
  - `docker ps -a | grep -i trocha` → no matches.
- `me` stack confirmed untouched and healthy throughout: `me-backend-1` (Up 2 days, 0.0.0.0:8000), `me-mysql-1` (Up 2 days, healthy, 0.0.0.0:3306), `me-mailhog-1` (Up 2 days, 0.0.0.0:8025) — never stopped, restarted, or queried by this task.
- No secrets were read, printed, or written during teardown.

## Blocker resolved — stack operational (2026-09-05)

- **Migration fix**: `e1f2a3b4c5d6`, `f1a2b3c4d5e6` and `a7b8c9d0e1f2` now `try/except ModuleNotFoundError` around the catalog imports and return early (the tables are dropped by `d0e1f2a3b4c5`). `alembic upgrade head` replays from an empty MySQL 8.4 volume; verified twice (`down -v` + `up`).
- **Demo seed**: `scripts/seed.py` adds three synthetic anthropometry records to the demo athlete (`seed_demo_anthropometry`) so the growth tab, curve, family view and PDF annex have data. Log line: `Mediciones demo: 3 creadas`.
- **Bring-up**: `frontend/scripts/e2e-stack.sh up` → backend healthy on :8001, seed complete, demo coach login 200. `me` stack untouched throughout.
- **Also on this MySQL**: database `trocha_ruta_test` (created for T027; disappears with `down -v`).
- **Helpers added for the specs**: `e2e/helpers/demo-athlete.ts` (resolve the seeded athlete by API), `e2e/helpers/session.ts` (`realTokens(role)` for specs that inject the session via `addInitScript` — see `frontend-gate.md` for why).
- **Run**: `cd frontend && E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 npx playwright test [specs] --reporter=line` (or `npm run test:e2e:isolated`).
- **Teardown**: `frontend/scripts/e2e-stack.sh down -v`.
