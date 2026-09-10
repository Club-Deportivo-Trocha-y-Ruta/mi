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

### 3.3 What is still outside both registries — now closed

Earlier in the same night run, 20 of 111 routes sat as `Exempt("pending instrumentation")`
— a real gap, not a false negative in the test (reopened as T030 after the corrida-2
review). As of the closing pass (corrida 3, 2026-09-10, commit `a943642`), **all 20 are
instrumented**; `test_audit_coverage.py` passes with 0 pending exemptions. The two
family-link writes FR-001 explicitly wants attributed
(`POST /api/parent-athletes`, `POST /api/auth/parent-register`,
`DELETE /api/parent-athletes/{id}`) are audited like every other write.

One route was resolved as a **genuine exemption, not an instrumentation gap**: `POST
/api/race-analysis/imports/{parse_id}/dry-run`. The contract originally expected it to
record `race_import`·`update` with a `dry_run` status transition, but `dry_run_import`
never actually assigns that status — the ingestor runs in-memory and leaves no persistent
write, so recording an `update` would audit a write that did not happen, and the spec's
decision 2 is explicit that reads are not audited. The owner could not be reached
overnight, so the decision taken (documented in `app/services/audit.py` itself, next to
the exemption) is to formalize it as a §4.14 exemption rather than change
`dry_run_import`'s behaviour — reversible in one line if the owner prefers the other
resolution (make the status transition real). See `technical-notes.md` (2026-09-10).

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

## 5. Privacy — the mandatory audit (T091) and the corrida-2/3 security findings

### 5.1 Mandatory privacy audit (T091) — done, APROBADO with caveats

`data-privacy-guard` ran the full mandatory audit against the feature's diff, recorded in
`specs/041-multi-coach-governance/checklists/privacy-audit.md`. All 7 checklist points
verdict **Cumple**:

| # | Point | Verdict |
|---|---|---|
| 1 | `audit_log.diff_json`/`meta_json` respect `VALUE_ALLOWLIST`/`META_ALLOWLIST` | Cumple |
| 2 | Family-facing schemas (newsletter, sessions, calendar) carry no attribution fields | Cumple, **1 fix applied in the same pass** |
| 3 | Family PDF/email carry no coach name where the contract forbids it | Cumple |
| 4 | Logs carry `request_id`, never the request body | Cumple |
| 5 | Exports audited by document type + `athlete_id` only | Cumple |
| 6 | Versioned fixtures/seeds are synthetic | Cumple |
| 7 | Per-coach activity report and per-coach AI spend expose adult staff only | Cumple |

**Fix applied during the audit** ("hallazgo A", committed in `a943642` together with H3–H7
below): `TrainingSessionReadParent` was returning `created_by_user_id` — a raw, unresolved
staff id — to the family. The contract's rule ("no coach identity of any kind reaches a
parent, not even an unresolved id") already excluded `coaches`/`has_active_coach` from that
schema but had missed this field; both the Pydantic schema and the response-model exclusion
in `training_sessions.py` now drop it.

**Closing verdict**: *"APROBADO para publicación desde el punto de vista de privacidad"*,
with one explicit caveat carried forward from every other section of this document —
**nothing in this audit ran against a real database or a live app**; it is 100% code
reading plus one offline unit test for the fix itself. Before a production release,
someone with `TEST_DATABASE_URL` or the Docker stack should run
`pytest tests/test_audit_privacy.py tests/test_coach_activity.py tests/test_session_coaches.py
backend/tests/test_training_session_router.py -m mysql` and confirm the privacy-named tests
in those files are still green with the fix applied — verbatim what the audit itself asks
for, restated here so it is not lost.

**One pre-existing finding noted but explicitly not fixed** (outside this feature's diff,
so outside the audit's stated scope): `rsvp_by_user_id` in `app/routers/calendar.py` has
an incidental issue the audit flagged but did not correct, being pre-existing in `main`.
Worth a look the next time `calendar.py` is touched.

### 5.2 Security review of the club-scope change (T080) — both minor-data findings fixed

A **security review of the club-scope change itself** ran on 2026-09-10 and found two
findings that reached a minor's data — **both fixed and committed** (`8ca2870`, see
`design.md` §2.1 and `technical-notes.md` for the full account):

- **H1** — a coach of another club could launch an AI analysis on an athlete who was not
  theirs, via `POST /api/race-analysis/runs` / the group launch, because neither checked
  the target athlete's club.
- **H2** — `GET /race-events/{id}/runs` returned another club's minor's name, athlete id,
  and a valid run id to any authenticated coach.

Six smaller findings from the same review touched only adult staff data (names, spend
figures) or endpoint-shape inconsistencies, never a minor's data. **All six are now fixed
and committed** (`a943642`, corrida 3, same night run):

| # | Finding | Where | Fix |
|---|---|---|---|
| H3 | `GET /admin/ai-usage`, reachable by coaches, returned spend and names for **every** club's staff | `race_analysis.py` (new `_coach_visible_staff_ids`), `budget_guard.py::spend_by_user_last_30d` | A coach now sees identity + individual spend only for staff of their own club(s); everyone else's spend is folded into one unnamed "Otros clubes" bucket. The reconciliation invariant (sum of returned rows equals the club-wide total) is preserved — the fold sums cost, never drops it. Admin behaviour (`visible_user_ids=None`) is unchanged. |
| H4 | `GET /imports/` returned the full cross-club import list to any coach | `race_imports.py::list_imports` | Filtered in SQL (not in Python, so `total`/pagination stay correct) to imports uploaded by a coach-or-admin member of the requester's own club(s), with an authorship fallback (a coach always sees their own uploads even if club resolution fails) that never widens access. |
| H5 | `user#{id}` fallback appeared in the imports listing, contradicting FR-013 | `race_imports.py` | Replaced with the same human fallback text used elsewhere in the feature ("Usuario no disponible") when the uploader can't be resolved. |
| H6 | `_admin_only` was dead code; the `/admin/ai-usage` prefix no longer meant admin-only | `race_analysis.py` | Docstring and RBAC comment corrected to state the route is coach+admin with a club-scoped breakdown; the route path itself is unchanged (kept for frontend contract stability). `_admin_only` is still imported by test files outside this feature's scope and was left in place rather than deleted. |
| H7 | An import created by the **administrator** was unreachable by any coach | `permissions.py::import_club_ids` | Widened to resolve through `(coach, admin)` memberships instead of `coach` only — an admin-uploaded import now resolves to the club's coaches too. `run_club_ids` (a sibling helper) deliberately keeps the narrower `coach`-only behaviour; the two were never meant to share it (a parent who is also a coach elsewhere must never leak a club through that path). |

Test coverage added alongside: `backend/tests/test_race_imports_club_scope.py`,
`backend/tests/test_spend_by_user.py`, plus fixture updates in
`backend/tests/routers/test_race_event_runs.py` (declaring the requesting coach's club,
made mandatory by the corrida-2 scope fix). All in the offline lane — not yet run against
MySQL, same caveat as everywhere else in this document.

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
   works from empty. This is the single highest-value remaining step: T091's own verdict,
   the migration fix, H3–H7's new tests, and the concurrency guarantee are all
   code-reviewed and offline-tested, not live-verified, for exactly this reason.
2. Bring up the isolated e2e stack and run `npm run test:e2e:isolated` (T092, not
   started) — closes §4, confirms the migration-bug fix works live, not just by code
   review, and finally exercises the five specs this feature adds.
3. Run T095's full gate list (`ruff check`, `pytest`, `pytest -m mysql`, `npm run build`,
   `npm test`, `npm run test:e2e`) and T096's quickstart walkthrough with two real coaches
   — neither has run in this environment; SC-002 (§4) is T096's moderated leg.
4. T093/T094 (this documentation) and T091 (privacy audit, §5.1, APROBADO) are done. T080
   (security review, §5.2) and T030 (coverage gate closure, §3.3) are done and committed.
   What remains before the feature can be called verified is entirely the live-stack work
   in steps 1–3 above, plus T097's post-deploy smoke once merged and deployed.
