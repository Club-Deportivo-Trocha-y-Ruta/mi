# Multi-coach governance — QA plan

Feature `specs/041-multi-coach-governance`. See [`design.md`](design.md) for what was
built and [`runbook.md`](runbook.md) for operating it. This document says how it was
tested, what could not be run in this environment, and — for the FR-009 coverage gate
specifically — the honest limits of what a "green" result actually proves.

## 1. Test lanes

| Lane | Command | Status in this feature |
|---|---|---|
| Default (offline, aiosqlite in-memory) | `pytest` | Primary lane. Every unit/service/router test for this feature runs here. Two-coaches-same-club fixture (`backend/tests/fixtures/two_coaches.py`, registered as a pytest plugin) backs every story's tests. |
| `mysql` (real MySQL, `-m mysql`) | `pytest -m mysql` | **Written, never executed in this environment.** See §2. |
| `golden` | `pytest -m golden` | Not touched by this feature — no change to the race-analyst prompt/pipeline itself. |
| Frontend unit | `npm test` (vitest) | Green as of the last recorded run in the integration review — 344 files / 4093+ tests, see `checklists/integration-review.md`. |
| Frontend typecheck | `npm run typecheck` | Green. |
| Playwright e2e | `npm run test:e2e:isolated` | **Not executed.** See §4. |

### Why the offline lane is trustworthy here despite no MySQL

The offline lane exercises the full service and router layer against aiosqlite, including
the append-only invariants, the coverage registry, the RBAC matrix, the privacy allow-list
scan, and the two-coaches fixture's denied-path tests (parent, other-club coach, coach on
staff actions). What it structurally **cannot** exercise is anything that depends on a
real MySQL dialect — row locking under real concurrency, `fsp=6` timestamp precision, and
the actual `alembic upgrade`/`downgrade` chain. Those are exactly what the `mysql` lane
owns, and exactly what §2 lists as unverified.

## 2. What the `mysql` lane owns, and why it did not run

No Docker and no reachable MySQL instance were available in any of the three unattended
night runs that built this feature (2026-09-09/10 — confirmed in
`checklists/integration-review.md`'s own method notes for every one of its report
sections). Every `mysql`-marked test below was **written and is believed correct by
review**, but its actual, live-database result is unknown:

- `backend/tests/test_audit_mysql.py` — `occurred_at` really carries `fsp=6` and shows as
  `DATETIME(6)` in `SHOW CREATE TABLE`; the session-coach backfill (B1) gives every
  pre-existing session exactly its creator as coach; the approval backfill (B2) leaves
  `approved_by_user_id` `NULL` (never invented); re-running the backfills is a no-op;
  `alembic heads` returns exactly one head.
- `backend/tests/test_retention.py`'s `mysql`-marked cases — the microsecond boundary
  test (T20, a row exactly at the cutoff kept vs. one microsecond older removed — this is
  the one that would catch an `fsp=0` truncation regression, meaningless on SQLite) and
  the `EXPLAIN DELETE` acceptance check (T21, documenting the accepted full scan rather
  than asserting an index that deliberately does not exist).
- `backend/tests/routers/test_newsletter_concurrency.py::test_two_sessions_only_one_
  update_takes_effect` — real row-locking under two concurrent MySQL sessions. SQLite does
  not reproduce InnoDB's row lock, so the optimistic-concurrency guarantee of §4 in
  `design.md` is proven by contract and by the offline single-session test, not by a real
  concurrent-write race. Flagged as open debt B4 in the integration review.
- `alembic upgrade head` / `downgrade -1` / `upgrade head` against an empty `_test`
  database for `45cd705c6b54_multi_coach_governance.py`, and the three pre-existing
  migrations whose import-safety fix (§3 of `technical-notes.md`, 2026-09-10) this feature
  depends on to boot a fresh database at all.

**Before this lane can run**, a `TEST_DATABASE_URL` (a `mysql+aiomysql://…` URL whose
database name ends in `_test`, per `backend/tests/conftest.py:44-53`) needs to point at a
reachable MySQL 8.4 instance. Running it is the single highest-value next QA step for this
feature — everything it would catch is exactly the class of bug this environment is
structurally unable to surface (dialect-specific truncation, real locking, migration
chain integrity).

## 3. FR-009 — the audit-coverage gate, in full honesty

`backend/tests/test_audit_coverage.py` + `backend/tests/helpers/audit_reachability.py`.
This is the gate that is supposed to make "a write path shipped unaudited" impossible.
It went through two rounds of a genuine, documented failure mode worth knowing about
before trusting a green run of it: **a test can look like a coverage gate and cover
nothing.**

### 3.1 What actually happened (both bugs, fixed)

1. **The gate walked zero routes for a while.** `requirements.txt` pins `fastapi>=0.115`
   with no ceiling; a fresh install picked up FastAPI 0.141.1, where `include_router` no
   longer flattens routes into `app.routes` eagerly — routes resolve lazily per request
   instead. Every test that walked `app.routes` directly saw 6 routes instead of 139, so
   the completeness test passed *vacuously* (the required set was empty) while a sibling
   test that actually needed the real route list failed. Fixed with
   `backend/tests/helpers/app_routes.py`, tolerant of both FastAPI generations — **any new
   test that walks `app.routes` must use that helper**, or this exact failure mode
   recurs silently the next time the dependency is reinstalled (including in Render's own
   unpinned deploy).
2. **The dynamic half was an unconditional skip wearing a coverage gate's clothes.**
   `test_audited_route_writes_at_least_one_audit_log_row` used to `pytest.skip()`
   unconditionally for all 81 `Audited` routes — every one showed as "skipped", which
   reads as "covered, nothing to report" in a CI summary rather than as "not tested at
   all." Its own docstring said so once corrected.

### 3.2 What the gate is today — two halves, different guarantees

- **Static reachability** (`test_audited_route_handler_reaches_record_audit`, backed by
  `audit_reachability.reaches_record_audit`): walks the call graph of each audited route
  handler **by name**, up to six hops within the `app` package, and requires that some
  reachable function calls `record_audit`. This catches the failure mode nobody else was
  watching for — a route declared `Audited` that in fact never audits, through any code
  path. **Limits, stated plainly**: it resolves by function **name**, not by type, so two
  unrelated functions with the same name are indistinguishable to it (a deliberate
  trade-off — a false negative here is preferred over a false positive that would force
  hand-written exemptions); it does not execute the route, so it says nothing about
  whether the row it would write is *correct* — only that a call exists somewhere
  reachable.
- **Dynamic smoke** (`test_audited_route_writes_at_least_one_audit_log_row`, parametrized
  over `Audited` entries that declare a `request_factory`): actually exercises the route
  and asserts a row landed. As of this doc pass, **no entry declares a `request_factory`
  yet**, so this collects zero cases — a known, named gap rather than a false green.
  Completing it needs the `client` fixture (which requires a real database connection,
  §2) and a synthesized valid request per route; it is meaningfully larger than a
  documentation task.

Read together: a route marked `Audited` is *provably reachable to* `record_audit` today,
but not yet *provably observed to write* a row. Treat "the coverage gate is green" as "no
route is silently unaudited," not as "every audited route's row is verified correct" —
the latter is what the dynamic half will eventually prove, once it has cases.

### 3.3 What is still outside both registries

20 of 111 routes in the registry remain `Exempt("pending instrumentation")` — a real gap,
not a false negative in the test. Two of them are family-link writes
(`POST /api/parent-athletes`, `POST /api/auth/parent-register`,
`DELETE /api/parent-athletes/{id}`) that FR-001 explicitly wants attributed; the rest are
mutating/exporting GETs and the interval-training module. Full list and the task tracking
it: `specs/041-multi-coach-governance/tasks.md` T030 (reopened 2026-09-10).

One additional route is exempted **by design decision, not oversight**: `POST
/api/race-analysis/imports/{parse_id}/dry-run`. The contract originally expected it to
record `race_import`·`update` with a `dry_run` status transition, but `dry_run_import`
never actually assigns that status — the ingestor runs in-memory and leaves no persistent
write. Recording an `update` here would audit a write that did not happen, and the spec's
decision 2 (§0 of `research.md`) is explicit that reads are not audited. Left as an open
decision for the owner (emit the real status transition, or formalize the exemption) —
see `technical-notes.md` (2026-09-10).

## 4. Playwright / e2e

**Not executed**, for two independent, additive reasons:

1. **No live stack in this environment.** All three night runs ran with no Docker and no
   running backend/frontend/MySQL — `npm run test:e2e:isolated` needs the isolated e2e
   compose stack (`docker-compose.e2e.yml`) up.
2. **A pre-existing migration bug**, unrelated to this feature, historically blocked any
   fresh database from booting via `alembic upgrade head` — three migrations imported
   `app.data.technique_catalog` / `app.data.strength_catalog` modules that feature 038
   deleted. This feature's own T001 wraps those three imports in `try/except ImportError`
   (committed, verified by reading the diff — see `technical-notes.md`), which should
   unblock a fresh database including the isolated e2e stack. **This fix has not been
   exercised against a real database in this environment** — it is a code-reviewed fix to
   a known problem, not a confirmed-working one. Whoever next has a live MySQL instance
   should run `alembic upgrade head` from empty as the very first check before assuming
   Playwright is unblocked.

The five specs this feature would add or extend
(`frontend/e2e/staff-admin.spec.ts`, `athlete-archive.spec.ts`, `session-coaches.spec.ts`,
`newsletter-conflict.spec.ts`, `coach-activity.spec.ts`) are tracked as T092, not started.
The `coach2` seed identity they depend on (`frontend/e2e/helpers/session.ts`,
`backend/scripts/seed.py`) is in place per the tasks list.

**SC-002** ("a coach can answer *who changed this athlete's record, and when?* from the
athlete page in under 30 seconds, 5/5 in a moderated test") is a moderated usability
criterion, not an automated assertion. It has not been run — it needs a live UI and an
actual coach, neither of which this environment has. Record the result here as a dated
addendum when it is run.

## 5. Privacy and the open findings from the corrida-2 security review

The mandatory `data-privacy-guard` audit for the whole feature (task T091) has **not**
run yet — it is a separate, explicit task, not implied by the offline test suite passing.
`backend/tests/test_audit_privacy.py` continuously scans every produced `audit_log` row
against `VALUE_ALLOWLIST`/`META_ALLOWLIST` for every fixture-driven write in the suite,
which is necessary but not sufficient for the full audit T091 asks for.

A **security review of the club-scope change itself** (T080) did run, on 2026-09-10, and
found two findings that reached a minor's data — **both fixed and committed** (`8ca2870`,
see `design.md` §2.1 and `technical-notes.md` for the full account):

- **H1** — a coach of another club could launch an AI analysis on an athlete who was not
  theirs, via `POST /api/race-analysis/runs` / the group launch, because neither checked
  the target athlete's club.
- **H2** — `GET /race-events/{id}/runs` returned another club's minor's name, athlete id,
  and a valid run id to any authenticated coach.

Six smaller findings from the same review carry **no minor's data** (adult staff names
and spend figures, or endpoint-shape inconsistencies) and were open as of the last
recorded state (2026-09-10, corrida 2's closing addendum):

| # | Finding | Where | Status as of this doc pass |
|---|---|---|---|
| H3 | `GET /admin/ai-usage`, now reachable by coaches, returns spend and names for **every** club's staff, not just the caller's own | `app/routers/race_analysis.py` (RBAC), `budget_guard.py` (`_QUERY_SPEND_BY_USER`) | A club-scoping fix (`visible_user_ids` on `spend_by_user_last_30d`, folding out-of-club spend into one unnamed "Otros clubes" bucket) was **present but uncommitted** in the working tree at the time this document was written — its final, committed state is unverified here. Check `git log -- backend/app/services/race/ai/budget_guard.py` for the current state before relying on this row. |
| H4 | `GET /imports/` returns the full cross-club import list to any coach | `app/routers/race_imports.py::list_imports` | Open, unverified as fixed. |
| H5 | `user#{id}` fallback still appears in the imports listing, contradicting FR-013 and the contract's own §4.1 | `app/routers/race_imports.py` | Open. |
| H6 | `_admin_only` is dead code; the `/admin/ai-usage` prefix no longer means admin-only | `app/routers/race_analysis.py` | Open — a documentation/naming hazard for the next reviewer, not a data leak by itself. |
| H7 | An import created by the **administrator** is unreachable by any coach — `import_club_ids` resolves only through `role_in_club='coach'` memberships, so the admin-authored-import set is empty and the authorship fallback leaves only the admin able to continue it | `app/services/permissions.py::import_club_ids` | Open. Fails closed (an inconvenience, not a leak) but will surface in production as "no puedo continuar el cargue" for a coach trying to finish an admin-started import. |

**Do not treat H3's row above as "fixed"** without re-checking the committed state — it
was mid-edit, by a different agent, at doc-writing time; documenting it as closed here
would be a false all-clear the next reader could not catch.

## 6. Fixtures and privacy invariants in tests

- `backend/tests/fixtures/two_coaches.py` — club, admin, coach A, coach B, an other-club
  coach, a parent, and athlete stubs, all synthetic. Used by every story's tests, and
  registered once in `pytest_plugins` rather than redefined per file.
- Every audited write exercised by the test suite is scanned by
  `backend/tests/test_audit_privacy.py` for a fixture athlete's name, birth date, any
  anthropometric value, or feedback/note/narrative text in `diff_json` / `meta_json` — 0
  occurrences is the bar, checked automatically rather than by manual review.
- No real athlete data appears anywhere in this feature's tests, fixtures, or the docs
  referenced above — every example in `design.md` and `runbook.md` uses synthetic
  "Ana Coach" / "Bruno Coach" names or numeric illustrative figures.

## 7. Summary — what to do before calling this feature verified

In priority order, based on what each step would actually catch:

1. Point `TEST_DATABASE_URL` at a real MySQL 8.4 `_test` database and run `pytest -m
   mysql` — closes §2 entirely, including confirming `alembic upgrade head` actually
   works from empty.
2. Bring up the isolated e2e stack and run `npm run test:e2e:isolated` — closes §4,
   confirms the migration-bug fix works live, not just by code review.
3. Re-check the committed state of H3–H7 (§5) and the 20 pending-instrumentation routes
   (§3.3) against `git log`/`tasks.md`, since both were mid-flight at the time of this
   documentation pass.
4. Run the mandatory `data-privacy-guard` audit (T091) — the automated privacy scan in
   §6 is necessary but was explicitly scoped as not sufficient by the feature's own plan.
5. Run the moderated SC-002 usability check with the club's actual coach.
