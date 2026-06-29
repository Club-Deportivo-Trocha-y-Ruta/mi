# Plan 005: Add an opt-in MySQL test lane so raw-SQL paths are exercised against the production dialect

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9871c99..HEAD -- backend/tests/conftest.py backend/app/services/race/ai backend/app/services/race/agents docker-compose.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M–L
- **Risk**: MED (new test infrastructure; must not destabilize the default SQLite lane)
- **Depends on**: none (synergy with plans 002/004: their FOR UPDATE and CAST
  behaviors only fully verify on MySQL)
- **Category**: tests
- **Planned at**: commit `9871c99`, 2026-06-11

## Why this matters

Production runs MySQL 8.4; the entire test suite runs in-memory SQLite
(aiosqlite) or hand-rolled fakes. The race/AI subsystem contains ~22 raw-SQL
`text()` call sites (pseudonymization, insight memory, chat tools, analytics
charts) where SQLite quietly accepts things MySQL handles differently —
timestamp defaults/precision, implicit casts, string comparisons — and
vice versa. A query can pass every test and misbehave in production. This plan
adds an *opt-in* MySQL lane: a `mysql` pytest marker plus an engine fixture
driven by `TEST_DATABASE_URL`, applied first to the highest-risk raw-SQL
modules. Default `pytest` behavior is unchanged.

## Current state

- Raw-SQL (`text()`) call sites by module (count):
  - `backend/app/services/race/agents/analyst.py` (5)
  - `backend/app/services/race/agents/chat.py` (4)
  - `backend/app/services/race/analytics_charts.py` (3)
  - `backend/app/services/race/ai/nodes/anonymize.py` (2) — INSERTs the
    pseudonym mapping; module docstring: "SQL crudo con `text()` — patrón
    consistente con chat.py de F3."
  - `backend/app/services/race/ai/nodes/recall_memory.py` (2) — reads
    `athlete_ai_insights.summary_text`.
  - `backend/app/services/race/agents/_llm.py` (2)
  - `backend/app/services/race/ai/nodes/load_race_data.py`,
    `.../rehydrate_names.py`, `.../budget_guard.py` (under `ai/`),
    `backend/app/services/race/queries.py` (1 each)
- `backend/tests/conftest.py` (root) is minimal — only an httpx `client`
  fixture (11 lines). There is NO shared DB engine fixture; each test file
  that needs a DB builds its own `create_async_engine("sqlite+aiosqlite:///:memory:")`
  (see `backend/tests/routers/test_race_standings_read.py:66-70`) or uses the
  `FakeAsyncSession` from `backend/tests/services/race/conftest.py`.
- Existing markers in `backend/pyproject.toml` `[tool.pytest.ini_options]`:
  `integration` and `golden`, both "Excluidos por default" (the exclusion
  mechanism already exists in this repo — find how they're excluded: check
  `addopts` in pyproject or CI invocation; replicate it for `mysql`).
- Local MySQL exists: `docker-compose.yml` defines a `mysql: image: mysql:8.4`
  service (lines 47–55) with a `mysql_data` volume. Tests must NOT use the
  dev database — they must create/drop their own schema (e.g. database
  `trocha_ruta_test`).
- The async driver is `aiomysql` (already in deps); sync migrations use
  `pymysql`. Tests should use `mysql+aiomysql://...`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Setup venv + deps | `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -e ".[dev]" aiosqlite` | exit 0 |
| Start MySQL only | `docker compose up -d mysql` | container healthy |
| Default lane (unchanged) | `cd backend && .venv/bin/python -m pytest -q` | all pass, zero `mysql`-marked tests run |
| MySQL lane | `cd backend && TEST_DATABASE_URL="mysql+aiomysql://root:<root-pass-from-compose>@127.0.0.1:3306/trocha_ruta_test" .venv/bin/python -m pytest -m mysql -q` | all `mysql` tests pass |

(Read the MySQL credentials from `docker-compose.yml` / `.env` at execution
time — do not hardcode them into committed files; the URL goes in the env var
only.)

## Scope

**In scope** (the only files you should modify/create):
- `backend/pyproject.toml` (add `mysql` marker registration only)
- `backend/tests/conftest.py` (add the opt-in engine/session fixture)
- `backend/tests/services/race/test_mysql_dialect.py` (create)
- `plans/README.md` (status row)

**Out of scope** (do NOT touch, even though they look related):
- Any file under `backend/app/` — if a dialect bug is FOUND, report it
  (STOP condition); fixing is a separate plan.
- `docker-compose.yml` — the existing mysql service is sufficient.
- CI workflows (`.github/workflows/`) — the operator declined CI work in this
  cycle; note in the index when this lands that a CI job with a
  `mysql:8.4` service container is the natural follow-up.
- Existing test files — do not migrate them to the new fixture in this plan.

## Git workflow

- Branch: follow operator instructions; if none, `advisor/005-mysql-dialect-test-lane`.
- Conventional commit, e.g. `test(db): carril opt-in de tests contra MySQL 8.4 para SQL crudo del módulo race`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Register the marker and the opt-in fixture

1. In `backend/pyproject.toml` `[tool.pytest.ini_options].markers`, add:
   `"mysql: tests contra MySQL real (TEST_DATABASE_URL). Excluidos por default; correr con -m mysql."`
   Use the same exclusion mechanism the `integration`/`golden` markers use
   (locate it first — likely `addopts = "-m 'not integration and not golden'"`
   in pyproject or the CI command; extend it consistently so `mysql` is also
   excluded by default).
2. In `backend/tests/conftest.py`, add a session-scoped fixture
   `mysql_engine` that:
   - reads `TEST_DATABASE_URL` from the environment; if unset or not
     `mysql+aiomysql://`, `pytest.skip("TEST_DATABASE_URL (mysql) no configurada")`;
   - asserts the database name ends with `_test` (refuse to run against
     `trocha_ruta` dev/prod data — hard `pytest.fail` otherwise);
   - creates the engine, runs `Base.metadata.create_all`, yields, then
     `drop_all` and dispose.
   Also add a function-scoped `mysql_session` that yields an `AsyncSession`
   and rolls back/truncates between tests (model the session handling on
   `tests/routers/test_race_standings_read.py`).

**Verify**: `cd backend && .venv/bin/python -m pytest -q` → suite unchanged, no new failures, no mysql tests collected/run.

### Step 2: First wave of dialect tests — pseudonym mapping and insight memory

Create `backend/tests/services/race/test_mysql_dialect.py`, all tests marked
`@pytest.mark.mysql`, exercising the real functions (not copies of their SQL)
against `mysql_session`:

1. Anonymize node round-trip: invoke the function in
   `backend/app/services/race/ai/nodes/anonymize.py` that INSERTs the
   pseudonym mapping (read the module first; call its public entrypoint with
   seeded athlete/competitor rows), then the reverse lookup in
   `rehydrate_names.py` — assert pseudonym→athlete_id survives the MySQL
   round-trip including timestamp columns.
2. `recall_memory.py`: seed 2 rows in `athlete_ai_insights` with
   `summary_text` > 500 chars and assert the returned list is truncated to
   500 chars each, ordering consistent with the SQL's ORDER BY on MySQL.
3. `queries.py` (1 site) and one representative query from
   `analytics_charts.py`: seed minimal rows, assert non-empty, correctly-typed
   results (ints are ints, not Decimal surprises — MySQL SUM returns Decimal;
   if the code assumes int, that IS the kind of divergence this lane exists to
   catch; report per STOP conditions if found).
4. Cross-check with plan 002/004 behaviors: one test that
   `select(...).with_for_update()` executes without error on MySQL, and one
   that the standings `func.cast(and_(...), Integer)` aggregation returns the
   same podium counts as the SQLite lane for identical seed data.

Read each target module fully before writing its test; the entrypoint
signatures were not inlined here on purpose (they're agentic-node functions
with state dicts — copy real call patterns from their existing SQLite/fake
tests under `backend/tests/services/race/`).

**Verify**: `docker compose up -d mysql`, then the MySQL-lane command from
"Commands you will need" → all new tests pass.

### Step 3: Confirm the default lane is untouched

**Verify**: `cd backend && .venv/bin/python -m pytest -q` → same pass count as
before this plan (mysql tests skipped/deselected), exit 0.

### Step 4: Document the lane

Add a short section to `backend/tests/services/race/test_mysql_dialect.py`'s
module docstring: how to start MySQL, the env var shape, the `_test` database
safety rule, and the list of raw-SQL modules still uncovered (from "Current
state") so future waves know where to extend.

**Verify**: `grep -n "TEST_DATABASE_URL" backend/tests/services/race/test_mysql_dialect.py` → ≥1 match in docstring.

## Test plan

Steps 1–2 are the test plan. Structural patterns:
`tests/routers/test_race_standings_read.py` (engine/session),
`tests/services/race/` existing node tests (call signatures for the AI nodes).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] Default `pytest -q` exit 0 with zero mysql-marked tests executed
- [ ] `pytest -m mysql -q` with `TEST_DATABASE_URL` set → ≥6 tests, all pass
- [ ] Fixture refuses non-`_test` database names (covered by a unit test or demonstrated and noted)
- [ ] No files under `backend/app/` modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any dialect test reveals an actual behavioral divergence (wrong truncation,
  Decimal-vs-int type break, ordering difference, failed CAST). That is the
  whole point of the lane — report the module, the seeded data, and both
  lanes' outputs; do NOT patch app code.
- `Base.metadata.create_all` fails on MySQL 8.4 (e.g. enum `values_callable`
  or JSON column issues) — report; schema-creation strategy may need Alembic
  instead, which is an advisor decision.
- Docker/MySQL is unavailable in the execution environment — mark the plan
  BLOCKED with environment details; do not fake the lane with SQLite.

## Maintenance notes

- Natural follow-up (deliberately out of scope): a CI job with a `mysql:8.4`
  service container running `pytest -m mysql`; and migrating waves 2+ (chat.py,
  analyst.py, `_llm.py`, season_panorama.py, group_launch.py) onto the lane.
- Reviewer focus: the `_test`-suffix safety check, and that no credentials
  land in committed files.
- If plan 002 landed, its FOR UPDATE test here is the only place real lock
  semantics are exercised — keep it when refactoring.
