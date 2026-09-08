# Resume notes — feature 040 implementation

**Status (2026-09-05)**: implementation complete. 78/79 tasks `[X]`; only **T078** (post-deploy smoke) stays open until the owner merges and Render deploys. No commit was made by the assistant; the owner commits.

## What closed on 2026-09-05 (after the workflow finished)

- Three historical migrations fixed so a fresh database migrates (`e1f2a3b4c5d6`, `f1a2b3c4d5e6`, `a7b8c9d0e1f2` — see `docs/technical-notes.md`).
- Isolated e2e stack operational (`frontend/scripts/e2e-stack.sh up`), demo seed extended with synthetic measurements.
- T027 (MySQL `_test`), T028 (PDF), T044/T054/T064 and the Playwright leg of T072 — evidence in `reference-standard.md` §5 and `frontend-gate.md`.
- Product fixes found by the e2e run: family history table no longer shows PHV offset/stage/age (FR-016); family PDF no longer draws an empty weight frame above 10 y (R-02).
- Pre-existing test fixes: `test_mysql_dialect.py` (`event_id=`), stale e2e assertions (Biblioteca, Bitácora heading, logout in user menu), `realTokens()` helper for the ten mocked specs.

## Open / owner decisions

- **T078** — steps verbatim in `tasks.md`; the production band-change report (ids only) is produced by the startup recompute.
- **target-size sweep** — feature 028 asserts ≥ 48 px, feature 033 design system uses 44 px rows; decide which one wins.
- **Older real-data e2e specs** (competitions, invitations, parents, cold-start…) need seed data or de-hard-coded ids to run on the isolated stack; per-spec causes in `frontend-gate.md`.
- **SC-002 in landscape** — at 1024 × 768 the growth tab needs one short scroll (header ≈ 610 px); top tiles duplicate the tab's status row.
- **Secrets incident** — a devops worker ran an unfiltered `docker compose config` on 2026-09-04 (values appeared in that agent's transcript only); consider rotating the affected keys.

## How to run the e2e again

```bash
frontend/scripts/e2e-stack.sh up
cd frontend && E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 npx playwright test e2e/growth.spec.ts e2e/growth-parent.spec.ts e2e/history.spec.ts e2e/anthropometry.spec.ts e2e/auth.spec.ts e2e/athletes.spec.ts --reporter=line
frontend/scripts/e2e-stack.sh down -v
```

Never target compose project `me` (ports 8000/3306/8025 — real club data).
