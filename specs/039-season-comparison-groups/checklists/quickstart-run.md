# Quickstart run — feature 039 (season comparison groups)

Executed 2026-09-03 on `feat/039-season-comparison-groups`, from `backend/.venv` (no Docker), against `quickstart.md`. One line per section; commands run verbatim from the quickstart unless noted.

| # | Command | Result | Notes |
|---|---|---|---|
| 1 | `pytest tests/services/race/test_comparison_groups.py tests/services/race/test_analytics.py tests/services/race/test_analytics_charts.py tests/routers/test_athlete_race_analysis_evolution_groups.py tests/services/training/test_newsletter_builder.py tests/test_newsletter_builder_024.py tests/services/race/ai/nodes/test_compute_metrics.py tests/services/test_compute_metrics_season.py -q` | PASS — 141 passed | All key assertions listed in quickstart §1 (split_progression grouping, build_evolution filtering/groups/confidence, parent-cross-athlete denial, newsletter charts_context totals, championship field_size/percentile/gap_pct/DNF nulls, season comparative first_reference/same-series priors) are covered by these files and pass. |
| 1 | `ruff check` (repo-wide, as literally written in quickstart) | FAIL — 349 pre-existing errors, 0 introduced by 039 | Scoped to only the files feature 039 touched: clean (see T047). The 349 are repo-wide pre-existing debt — confirmed via `git stash`: baseline (039 changes stashed) has 351, i.e. 039 nets *fewer* errors (fixed a stray `gap` unused-var in `newsletter_builder.py` and a `call_count_holder` NameError in a test, both fixed either by the feature itself or by T047). Not 039's responsibility to clean the other 349. |
| 2 | `TEST_DATABASE_URL=… pytest -m mysql tests/services/race/test_mysql_dialect.py -q` | SKIPPED — 7 skipped | `TEST_DATABASE_URL` intentionally left unset per instructions; `mysql_engine` fixture self-skips the whole file. Lane not exercised this run. |
| 3 | Newsletter PDF with real data (SC-1 style) | DONE (wave 2) | `tasks.md` T015 is checked off: real-dataset regeneration (athlete with CD+CN, athlete without championships) was already performed and PDFs reviewed in wave 2 — not repeated in this pass. |
| 4 | `npm run typecheck` | PASS — clean | `tsc --noEmit`, no errors. |
| 4 | `npx vitest run src/components/athletes/ai/__tests__/EvolutionChart.test.tsx src/components/athletes/ai/__tests__/MiniSparkline.test.tsx src/components/athletes/ai/__tests__/a11y.v2.test.tsx` | PASS — 44 passed (3 files) | Includes the jest-axe zero-violations checks in `a11y.v2.test.tsx`. Manual `npm run dev` cross-check (switch groups on CD+CN athlete, Panorama sparkline cup-only) not performed in this pass — no live coach session available; covered functionally by the automated specs above. |
| 5 | `pytest tests/services/race/ai -q` (offline, FakeLLM) | PASS — 357 passed, 11 xfailed, 6 xpassed | |
| 5 | `RACE_AI_API_KEY=… pytest -m golden -q` (blocking gate) | OPEN — not re-run this pass | Per known state: run earlier today with the real Gemini key, cases 001–002 scored 0.840/0.820, then Gemini free-tier quota was exhausted (HTTP 429 `RESOURCE_EXHAUSTED` on `gemini-3.8-flash`); cases 003–009 fell back to the deterministic path and were not measured. Scoreboard file was restored to its pre-run version. T040 remains open until quota resets and the gate is re-run in full — not repeated here to avoid burning more quota against an already-known-inconclusive state. |
| 6 | Post-deploy smoke (`/health` + authenticated evolution endpoint against Render) | PENDING | Feature not yet deployed (`docs/implementation-status.md`: Deploy step ⏳ Pending). Not applicable until after merge + deploy. |

## Summary

- Sections exercised and green: 1 (offline tests), 4 (frontend), 5-offline.
- Section 1's bare `ruff check` "fails" only due to pre-existing, out-of-scope repo debt — 039's own files are ruff-clean (see T047 report).
- Section 2 skipped by design (no `TEST_DATABASE_URL`).
- Section 3 already completed in wave 2 (T015).
- Section 5's golden gate (T040) is open, not pass/fail — blocked on Gemini quota reset, do not report as passed or failed.
- Section 6 pending post-deploy.
