# Notes — 010-competitions-ai-insights

## T001 baseline (2026-06-09)
- Backend: 2564 tests collected; pre-existing failures on `main` (verified via clean `HEAD` worktree): 25 failed + errors across `test_training_session_router.py`, `test_training_session_notifications.py`, `test_parent_athletes.py`, `test_calendar_models.py`, `test_calendar_audiences.py`, `test_notification_changes.py`, and the two Alembic-text tests in `tests/models/test_race_import_*`. None are touched by this feature.
- Frontend: full vitest run has a small set of pre-existing failures (e.g. `StandingsTable` 26-category rendering timeout) present before this feature; all feature-scoped suites green.
- The repo has **no ESLint config** (no `eslint.config.*` / `.eslintrc*`) — the constitution's frontend gate is effectively `tsc --noEmit` + vitest.

## T027 privacy audit (data-privacy-guard, 2026-06-09)
- Verdict: **APPROVED** (after fix). 7/7 items PASS.
- One HIGH finding: `group_launch.py` logged `athlete_id` in a `logger.exception` — fixed to log the opaque `run_id` instead (consistent with the file's other log sites).
- Confirmed: anonymizer node untouched; `season_comparative` carries no identity fields; chat event scoping adds only event label (venue/date) to LLM context; `AI_LOG_PROMPTS` paths unchanged; new endpoints coach/admin-gated; no third-party calls from frontend; chat history in React state only.

## T028 quality gates (2026-06-09)
- `ruff check` clean on all feature-touched backend files (auto-fixed 9 unused imports in touched test files). Whole-tree `ruff check app` has extensive pre-existing violations in untouched files — out of scope.
- Backend feature suites: 87 passed (test_race_analysis.py 43 incl. 5 new chat-scope, test_race_event_runs.py 19, test_race_analysis_privacy.py 4, test_compute_metrics_season.py 21).
- One regression caught and fixed during gates: `test_race_analysis_privacy.py` stub agent needed the new `race_event_id`/`event_scope` kwargs.
- Frontend: `tsc --noEmit` clean; final full vitest run **188 files / 2091 tests, all passed**. (An earlier full run showed 12 timeout failures — reproduced as flakes only under heavy machine load while the backend suite ran concurrently; all pass on a quiet run, including the previously flaky StandingsTable rendering test.)
