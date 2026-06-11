# Plan 004: Pin down season-standings math with service-level tests and enable mutation testing on standings.py

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9871c99..HEAD -- backend/app/services/race/standings.py backend/tests/routers/test_race_standings_read.py backend/pyproject.toml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (002 touches different files; order irrelevant)
- **Category**: tests
- **Planned at**: commit `9871c99`, 2026-06-11

## Why this matters

`get_event_standings` computes the season ranking parents see for their kids:
SQL aggregation (SUM points, COUNT races, podium CASE, MIN position) plus a
Python tie-break (`total_points DESC → podiums DESC → best_position ASC`).
Today the only coverage is 6 router tests (happy path, 404s, query count) —
no test exercises a points tie, a NULL `best_position`, NULL points, podium
counting, or the parent/club filters' interaction with ranking. The module is
also excluded from mutation testing by the blanket `app/services/race/*`
exclusion, so a sign flip in the sort key would survive every gate. This plan
writes service-level characterization tests against a real (SQLite) engine and
narrows the mutation exclusion so `standings.py` is mutated.

## Current state

- `backend/app/services/race/standings.py` (260 lines) — single public
  function `get_event_standings(db, race_event_id, *, category_id, club_only,
  allowed_athlete_ids)`. Key logic to characterize:

  ```python
  # standings.py:137-142 — podium aggregation (CAST bool→Integer, then SUM)
  podium_case = func.sum(
      func.cast(
          and_(RaceResult.position.is_not(None), RaceResult.position <= 3),
          Integer,
      )
  ).label("podiums")
  ```

  ```python
  # standings.py:184-185 — parent scoping
  if allowed_athlete_ids is not None:
      stmt = stmt.where(RaceResult.athlete_id.in_(allowed_athlete_ids))
  ```

  ```python
  # standings.py:212-216 — tie-break sort key (THE critical logic)
  def _sort_key(r):
      bp = r["best_position"] if r["best_position"] is not None else 9999
      return (-(r["total_points"] or 0), -(r["podiums"] or 0), bp)

  raw_sorted = sorted(raw, key=_sort_key)
  ```

  Other behaviors stated in the module docstring (lines 9–28) and code:
  aggregates across ALL events of the event's series (subquery at line 135);
  excludes soft-deleted results (`deleted_at IS NULL`, line 164); empty
  `allowed_athlete_ids` set → early-return with `categories=[]` (lines
  110–120); returns `None` when the event doesn't exist (line 95–96);
  `is_our_club = athlete_id is not None` (line 227); ranks assigned 1..N by
  enumerate after sort (line 219).

- `backend/tests/routers/test_race_standings_read.py` — the structural
  pattern: builds `create_async_engine("sqlite+aiosqlite:///:memory:", ...,
  poolclass=StaticPool)`, creates `Base.metadata` tables, seeds
  `RaceSeries → RaceEvent → RaceCategory → RaceCompetitor → RaceResult` model
  instances, and overrides FastAPI deps. For THIS plan, skip the HTTP layer:
  call `get_event_standings(session, ...)` directly with a session from the
  same engine fixture style.

- `backend/pyproject.toml` mutation config as written today:

  ```toml
  [tool.mutmut]
  source_paths = ["app/services"]
  do_not_mutate = [
      "app/services/ai/*",
      "app/services/notification/*",
      "app/services/race/*",
      "app/services/calendar/*",
      "app/services/training/*",
  ]
  ```

- Contents of `backend/app/services/race/` (so the narrowed exclusion can be
  written exactly): subpackages `agents/`, `ai/`, `eval/`, `prompts/`, `rag/`;
  modules `analytics.py`, `analytics_charts.py`, `calendar_sync.py`,
  `club_insights.py`, `competitor_linking.py`, `csv_parser.py`,
  `group_launch.py`, `ingestor.py`, `insights_history.py`, `matcher.py`,
  `normalizer.py`, `pdf_parser.py`, `queries.py`, `results_read.py`,
  `revision.py`, `revision_diff_view.py`, `roster.py`, `run_staleness.py`,
  `schemas.py`, `season_panorama.py`, `standings.py`, `__init__.py`.

- Mutation docs/pattern: `docs/qa/mutation-testing-2026-06.md` and
  `backend/tests/test_mutation_kills.py` (tests written specifically to kill
  mutants — model the naming/docstring style if you add kill-tests).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Setup venv + deps | `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -e ".[dev]" aiosqlite mutmut` | exit 0 |
| New tests | `cd backend && .venv/bin/python -m pytest tests/services/race/test_standings_service.py -q` | all pass |
| Full backend suite | `cd backend && .venv/bin/python -m pytest -q` | all pass |
| Mutation run (scoped) | `cd backend && .venv/bin/python -m mutmut run` | runs; see Step 4 for interpreting results |

(Check `backend/scripts/` first — if a `run_mutation_test.py` or similar
wrapper exists, prefer it and document the exact invocation you used.)

## Scope

**In scope** (the only files you should modify/create):
- `backend/tests/services/race/test_standings_service.py` (create)
- `backend/pyproject.toml` (ONLY the `[tool.mutmut].do_not_mutate` list)
- `plans/README.md` (status row)

**Out of scope** (do NOT touch, even though they look related):
- `backend/app/services/race/standings.py` — this plan CHARACTERIZES current
  behavior; if a test reveals a genuine bug, that's a STOP condition, not a
  license to fix.
- `backend/tests/routers/test_race_standings_read.py` — keep as-is.
- Mutation config for any module other than `standings.py`.

## Git workflow

- Branch: follow operator instructions; if none, `advisor/004-standings-service-tests`.
- Conventional commit, e.g. `test(race): characterization de standings (desempates) + mutación habilitada en standings.py`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Build the test file with a real-engine fixture

Create `backend/tests/services/race/test_standings_service.py`. Copy the
engine/session fixture approach from
`backend/tests/routers/test_race_standings_read.py` (async engine on
`sqlite+aiosqlite:///:memory:` with `StaticPool`, `Base.metadata.create_all`).
Seed helper: one `RaceSeries` (season 2026), two `RaceEvent`s in the series
(to prove cross-event aggregation), one `RaceCategory`, and a
`mk_result(event, competitor, points, position, athlete_id=None, deleted_at=None)`
helper. Beware: `backend/tests/services/race/conftest.py` defines PDF fixtures
and a `FakeAsyncSession` for ingestor tests — do NOT use the fake here; this
plan exists precisely to test against a real engine.

**Verify**: `cd backend && .venv/bin/python -m pytest tests/services/race/test_standings_service.py -q` → collected ≥1, passing (start with a trivial happy-path test).

### Step 2: Characterization tests for ranking and aggregation

Add these cases (one test each, named as listed):

1. `test_points_tie_broken_by_podiums` — A and B tie on total points; A has
   2 podiums, B has 1 → A ranked 1.
2. `test_points_and_podiums_tie_broken_by_best_position` — tie on both; A's
   best position 2, B's 4 → A ranked 1.
3. `test_null_best_position_ranks_last_on_full_tie` — competitor whose
   positions are all NULL (e.g. DNF rows) ties on points/podiums with one who
   has a position → NULL sorts last (the 9999 sentinel).
4. `test_null_points_counted_as_zero` — results with `points_awarded=None`
   rank below any positive total and `total_points == 0` in the output row.
5. `test_aggregates_across_series_events` — same competitor scores in both
   events → `total_points` is the sum, `races_run == 2`.
6. `test_podium_counts_positions_1_to_3_only` — positions 1, 3, 4, NULL →
   `podiums == 2`.
7. `test_soft_deleted_results_excluded` — a `deleted_at`-stamped result does
   not contribute to totals.
8. `test_parent_scope_filters_and_empty_set_short_circuits` —
   `allowed_athlete_ids={x}` returns only x's rows; `set()` returns the
   event header with `categories == []`.
9. `test_club_only_filters_unlinked_competitors` — `club_only=True` drops
   rows with `athlete_id IS NULL` and `is_our_club` is True on the rest.
10. `test_missing_event_returns_none` — unknown `race_event_id` → `None`.

**Verify**: `cd backend && .venv/bin/python -m pytest tests/services/race/test_standings_service.py -q` → 10+ tests pass.

### Step 3: Narrow the mutation exclusion to un-exclude standings.py

mutmut's `do_not_mutate` is a list of glob patterns. Replace the single
`"app/services/race/*"` entry with explicit entries for everything in
`app/services/race/` EXCEPT `standings.py` — i.e. the five subpackage globs
(`app/services/race/agents/*`, `.../ai/*`, `.../eval/*`, `.../prompts/*`,
`.../rag/*`) plus each sibling module listed in "Current state"
(`app/services/race/analytics.py`, ..., `app/services/race/season_panorama.py`,
`app/services/race/__init__.py`) — every file except `standings.py`. Keep the
other four top-level exclusions (`ai`, `notification`, `calendar`,
`training`) untouched.

**Verify**: `cd backend && grep -c "app/services/race" pyproject.toml` → ≥20 (the enumerated list), and `grep -n "race/standings" pyproject.toml` → no matches.

### Step 4: Run mutation testing on standings.py and kill survivors

Run `cd backend && .venv/bin/python -m mutmut run` (or the repo's wrapper
script in `backend/scripts/` if present). Then `mutmut results` to list
survivors in `app/services/race/standings.py`. For each survivor that
represents real logic (sort-key signs, the 9999 sentinel, the `<= 3` podium
bound, filter conditions): add a killing test to the Step-2 file. Survivors in
logging lines (`logger.info(...)` at lines 244–249) may be left and noted.

If the mutation run is impractically slow (mutmut runs the whole suite per
mutant by default), scope it: check the repo wrapper or limit with
`mutmut run` after temporarily setting `tests_dir`/pytest args per mutmut's
docs — and record exactly what you ran in the commit message. Do not let this
step silently time out: either complete it or report it as BLOCKED with the
timing data.

**Verify**: `cd backend && .venv/bin/python -m mutmut results` → zero
surviving mutants in `standings.py` logic lines (logging-only survivors
documented in the test file's module docstring).

### Step 5: Full suite

**Verify**: `cd backend && .venv/bin/python -m pytest -q` → all pass.

## Test plan

The plan IS the test plan (Steps 2 and 4). Pattern:
`backend/tests/routers/test_race_standings_read.py` for fixtures/seeding,
`backend/tests/test_mutation_kills.py` for mutant-killing test style.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd backend && .venv/bin/python -m pytest -q` exits 0
- [ ] `tests/services/race/test_standings_service.py` exists with ≥10 tests, all passing
- [ ] `grep -n "race/standings" backend/pyproject.toml` → no matches (standings is mutable)
- [ ] `grep -n "app/services/race/agents" backend/pyproject.toml` → ≥1 match (subpackages still excluded)
- [ ] Mutation run executed; survivors in standings.py logic = 0 (or BLOCKED row with timing data)
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any characterization test FAILS against current code — that is a real bug
  in parent-visible rankings. Report the failing case with the seeded data and
  observed vs expected order; do NOT change `standings.py`.
- `func.cast(and_(...), Integer)` errors on aiosqlite (dialect issue) — the
  podium aggregation would then be MySQL-only behavior; report (feeds plan 005).
- mutmut cannot run with this repo's layout after one honest attempt (e.g.
  src-layout issues); report the exact error instead of restructuring config.

## Maintenance notes

- These are characterization tests: if ranking rules ever change deliberately
  (e.g. FCC changes tie-break rules), update tests together with the rule and
  say so in the commit.
- Reviewer focus: seeded fixtures must use NULLs (positions, points,
  athlete_id) the way real ingested DNF/DNS rows do — see
  `backend/app/services/race/ingestor.py:354-401` for how those rows are born.
- Follow-up deferred: enabling mutation on `competitor_linking.py` and
  `ingestor.py` (bigger lift; FakeAsyncSession-based tests may not kill
  DB-level mutants).
