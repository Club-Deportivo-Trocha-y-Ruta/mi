# Quickstart: validating 045

> **Never validate against the local backend in its default configuration.** Local `.env` points at the production MySQL, so anything approved, committed or discarded there is real and visible to families. Use the offline test lanes below, or the isolated e2e stack (`docker compose` with a `_test` database).

## Offline lanes (must be green)

```bash
# Backend — the default lane (aiosqlite)
cd backend && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=. .venv/bin/python -m pytest \
  tests/services/race/test_field_metrics*.py tests/services/race/test_analytics_charts.py \
  tests/services/race/test_history*.py tests/routers/test_race_imports*.py \
  tests/routers/test_dashboard*.py tests/routers/test_athlete_race_analysis*.py \
  tests/services/notification/test_race_insight_dispatcher.py
ruff check <changed files>

# Frontend
cd frontend && npm run typecheck && npx vitest run
```

Pre-existing failures that are not caused by 045 (see research R-15):
- `tests/test_langchain_provider.py` (collection ImportError);
- `test_invariants_v2.py::test_resolve_age_*`;
- `SessionWizardRouteNotify.test.tsx`.

## Local test DB lane

Local `.env` points at production MySQL, so every run that can open a MySQL connection overrides the target to the local `trocha_ruta_test` database (docker compose `mysql` service, port 3306 on the host). Never pass credentials on the command line in a transcript — read them from the container's own environment.

```bash
# 1. Create the database once, using the container's root password (never echoed)
docker compose exec mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS trocha_ruta_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"'

# 2. Migrate it to head
cd backend && MYSQL_HOST=127.0.0.1 MYSQL_DB=trocha_ruta_test .venv/bin/alembic upgrade head

# 3. Full pytest with the same overrides (default lane stays aiosqlite; the overrides
#    guarantee nothing falls through to the production host)
MYSQL_HOST=127.0.0.1 MYSQL_DB=trocha_ruta_test PYTHONPATH=. \
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest

# 4. The mysql lane: TEST_DATABASE_URL must name a database ending in `_test`
#    (conftest refuses anything else); build it from the same local credentials.
MYSQL_HOST=127.0.0.1 MYSQL_DB=trocha_ruta_test TEST_DATABASE_URL="mysql+aiomysql://<user>:<pass>@127.0.0.1:3306/trocha_ruta_test" \
  PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest -m mysql
```

Invoke `python -m pytest`, not the `pytest` script: macOS SIP drops `DYLD_*` variables on the shebang re-exec and WeasyPrint then fails to load.

## Scenario checks (each one maps to a spec story)

1. **Metrics agree (US2, SC-002).** A backend consistency test builds one category with 6 timed finishers, one who lost laps and one DNF. It then asserts that the history, evolution, competition-results and analyst-context metrics are identical per athlete.
   - Time-based percentile: the fastest rider gets 100 and the slowest 0.
   - The rider who lost laps gets `null` for percentile and gaps, and is counted in Parrilla.
   - With 4 timed finishers, percentile and median gap are `null` everywhere.
2. **Family never sees winner or podium gaps (US4, SC-004).**
   - Backend: parent responses from the history, evolution, results and insight-detail endpoints contain none of `gap_to_winner_pct`, `gap_to_podium_pct`, `gap_to_podium_ms` or `gap_to_p3_hhmmss`; `metric=podium_gap_ms` returns 403.
   - Frontend: family renders of Progresión, the championship cards, the Análisis IA card and the family competition page show no such label.
   - Bitácora render: no «al P1» sublabel.
3. **Approval warning (FR-022).** A pending analysis whose family-visible text contains «gap 9.4% al líder» returns a non-empty `family_gap_mentions`, and the card shows the warning. Clean text returns an empty list, and no warning is shown.
4. **Identity gate per import (US3, SC-003).** Covered by the three `409`/`200` cases in `contracts/api.md`.
5. **Resumable import (US3).** Stage an import, leave the page, and open `?import=<id>`: the wizard resumes at the correct step. Discard it: the status becomes `discarded` and it leaves the inbox; discarding a committed import returns 409.
6. **Pending lands on its items (US5, SC-005).** Seed one analysis awaiting approval and one stale analysis, then follow each «Pendientes» row. The destination lists exactly those items. Dismissing the stale one removes it and writes an audit event.
7. **Merged tab and deep links (US1, US4, SC-006).**
   - Every address in `contracts/ui-routes.md` resolves as listed.
   - `?tab=ai_analysis&insight=<iid>` opens «Análisis IA» with that analysis expanded.
   - A family `view=comparar` falls back to Progresión.
8. **First paint (SC-007).** In a unit test, opening «Carreras» on Progresión fires only the history request; the insights and runs queries start only when «Análisis IA» opens. Deferred real-device check: LCP ≤ 3.5 s on a mid-tier Android over simulated 3G.
9. **Accessibility and targets (SC-010).** jest-axe reports zero violations on the merged tab, the inbox, «Temporada» and the approval card. Update the `target-size.spec.ts` sweep to the new views.

## Deferred real-infrastructure lanes (report explicitly if not run)

- `pytest -m mysql` — the `discarded` enum migration, upgrade and downgrade (`discarded` → `failed`).
- `pytest -m golden` — SC-008. The eval is insulated by its baked fixtures (research R-02), but run it before deploy if a race AI key is available.
- The Playwright specs listed in research R-15.
- A hands-on tablet check with the coach (SC-009).
