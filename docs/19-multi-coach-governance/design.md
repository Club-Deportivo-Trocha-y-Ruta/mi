# Multi-coach governance — Design

Feature `specs/041-multi-coach-governance`. Branch `feat/041-multi-coach-governance`.
Second coach onboarding for Club Deportivo Trocha y Ruta: every write gets an actor and a
timestamp, an athlete removal archives instead of destroying, a session can be led by more
than one coach, and history retains 24 months before an explicit, previewed purge.

This document records what the code does, with `path:line` evidence where verified. Full
requirements: `specs/041-multi-coach-governance/spec.md` (FR-001..FR-034). Full schema
detail: `specs/041-multi-coach-governance/data-model.md`. Contracts for each surface live
in `specs/041-multi-coach-governance/contracts/`.

> **Verification note**: no Docker and no live MySQL were available in any of the three
> unattended night runs that built this feature (2026-09-09/10). Everything below marked
> "verified" was checked by reading the committed code or by running the offline `pytest`
> lane (aiosqlite in-memory). Everything that needs the `mysql` lane, a live stack, or
> production is marked accordingly — see `qa.md` for the full list.

## 1. The audit-log foundation

### 1.1 `audit_log` — the club-wide index

One new table, `backend/app/models/audit_log.py`, appended to in the same transaction as
every recorded write (FR-001) and never updated or deleted by the application (FR-004).
Three existing domain trails — `race_result_revisions`, `race_competitor_link_audit`,
`agent_run_events` — are **kept** as detail and are not duplicated; `audit_log` is the
one place a coach or admin can search across every domain.

| Column | Purpose |
|---|---|
| `id` | `BigInteger` PK, SQLite-variant-aware (see below). |
| `occurred_at` | `DATETIME(fsp=6)` on MySQL — sub-second precision, required because two coaches can act inside the same second (US5). MySQL 8.4 defaults `DATETIME` to `fsp=0` and silently truncates; this is the one column in the feature that must not inherit that gap. |
| `actor_user_id` | FK `users.id`, `ondelete=RESTRICT`. `NULL` only when `actor_kind != user`. Never denormalised — the name is always resolved by a `LEFT JOIN` at read time, which is what lets a deactivated coach's name stay readable forever (FR-013, FR-018). |
| `actor_kind` | `user` \| `system` \| `webhook` \| `cron`. Never defaults to `user` — an automated write must say so explicitly. |
| `actor_role` | Snapshot of the actor's role at write time, not re-derived later. |
| `club_id` | FK `clubs.id`, `ondelete=SET NULL`. Keyword-required (no default) on `record_audit` so a club-less row can never happen by omission. |
| `athlete_id` | FK `athletes.id`, `ondelete=SET NULL`, set only when the action concerns one athlete. Survives archiving — an archived athlete's history stays readable. |
| `entity_type` / `entity_id` | Polymorphic discriminator + id. `entity_type` is a **closed Python catalogue** (`AuditEntityType`), not a DB enum — adding an auditable table should not need an `ALTER TABLE`. `entity_id` carries no FK (accepted risk, `data-model.md` §8.4). |
| `action` | Closed `AuditAction` DB enum matching FR-001's verb list (`create`, `update`, `archive`, `delete`, `restore`, `approve`, `unapprove`, `send`, `export`, `cancel`, `execute`, `link`, `unlink`, …). |
| `changed_fields` | JSON array of **column names only**, never values. |
| `diff_json` | `{"<field>": {"before": …, "after": …}}`, restricted to `VALUE_ALLOWLIST[entity_type]` — the only fields whose *values* may ever reach the table (states, flags, dates, identifiers). Anything not allow-listed is dropped before the row is built. |
| `reason_code` | Closed `AuditReasonCode` Python catalogue, mandatory for the `(entity_type, action)` pairs in `REASON_REQUIRED`. |
| `request_id` | `uuid4().hex`, one per logical operation — the correlation reference that groups a bulk save into one operation (FR-002 / AS5). |
| `meta_json` | Small non-PII rendering context, validated against `META_ALLOWLIST` — e.g. `{"document_kind": "growth_pdf"}`, `{"removed_count": 143}`. |

Five composite indexes serve the read side without a JOIN fan-out: `ix_audit_club_time`,
`ix_audit_actor_time`, `ix_audit_entity_time`, `ix_audit_athlete_time`,
`ix_audit_request_id`. `occurred_at` alone is **deliberately not indexed** — the only
query that scans it without a club filter is the monthly retention purge, and a sixth
index on a write-hot table is not worth it below roughly 1M rows (`data-model.md` §9).

`id` uses `BigInteger().with_variant(SQLITE_INTEGER(), "sqlite")` — without the SQLite
variant the offline test lane fails with `NOT NULL constraint failed`, because a plain
`BIGINT` primary key is not a ROWID alias in SQLite. Same idiom already used by
`race_competitor_link_audit`.

### 1.2 `record_audit` — the single write entry point

`backend/app/services/audit.py::record_audit(db, *, action, entity_type, entity_id,
actor, actor_kind=user, club_id, athlete_id=None, changed_fields=None, diff=None,
reason_code=None, meta=None, request_id=None) -> AuditLog | None`.

Behaviour, in order: validate the enums and `entity_id > 0`; check actor/`actor_kind`
coherence (a `user` action needs an `actor`, anything else must not have one); resolve
`request_id` from the current request context if not passed explicitly; require a
`reason_code` for the `(entity_type, action)` pairs that need one (else
`AuditReasonRequired`, mapped to `422` at the router); on a no-op `update` (no
`changed_fields` and no `diff`) return `None` without writing a row; minimise —
`changed_fields` is the sorted union of names, `diff_json` keeps only allow-listed keys,
`meta_json` is validated; `db.add()` the row and return it.

`record_audit` **never flushes, never commits, and never opens its own session** — it
queues the row so it shares fate (commit or rollback) with the business write it
accompanies. This mirrors an existing project convention (the same rule
`compute_changed_fields`'s sibling helpers already followed) and is what makes an audit
row disappear correctly if the write it describes is rolled back.

`club_id` is **keyword-required with no default** specifically so that forgetting it is a
`TypeError` at call time, not a silently club-less row that never shows up in a club's
history.

**Where it is called from**: the service layer only, never a router body directly — so
the CLI, the two webhooks, and the LangGraph completion callbacks that run after the HTTP
response all obey the same rule. Of the 56 explicit `await db.commit()` sites outside
`app/dependencies.py` (measured 2026-09-09), each was individually checked so that
`record_audit` runs **before** the commit it needs to share, not after an early one (race
imports especially — the ingest commits its own transaction, separate from the router's).

### 1.3 Request context

`backend/app/services/request_context.py` (new): a `ContextVar[str]` holding the current
`request_id`, an `AuditContext` dataclass, a `get_request_context` FastAPI dependency, and
non-HTTP helpers (`system_context(job=…)`, `webhook_context`, `cron_context`) for callers
that run outside a request — the retention CLI, webhook handlers, cron-style scripts.

`RequestIdMiddleware` is pure-ASGI (Starlette, no new dependency) and registered as the
**outermost** middleware in `backend/app/main.py` — verified at `app.add_middleware
(RequestIdMiddleware)`, the last `add_middleware` call, which is how it ends up outermost
under Starlette's LIFO wrapping. It stamps `X-Request-Id` on the response and feeds the
same value into `record_audit` calls for that request, which is how one HTTP call that
changes several rows (e.g. saving a session roster) shares one correlation reference
across all of them.

### 1.4 Structured logging with `request_id`

`backend/app/main.py` also carries a `logging.config.dictConfig` block
(`disable_existing_loggers: False`) for the `app.*` logger namespace, with a
`RequestIdLogFilter` that reads the current `request_id` from the context var (falling
back to `"-"` outside a request) and injects it into every `app.*` log record. Before this
change, business logs from `app.services.*` were not reliably reaching uvicorn's own
handlers in production — see `technical-notes.md` (2026-09-10) for the mechanism.

### 1.5 Coverage registry (FR-009)

`backend/app/services/audit.py` carries two closed registries: `AUDITED_ROUTES` (route →
`Audited(entity_type, action, …)` policy) and `EXEMPT_ROUTES` (route → a written reason,
at least 20 characters). `backend/tests/test_audit_coverage.py` walks every
POST/PUT/PATCH/DELETE plus the mutating/exporting GETs of the instrumentation matrix and
fails if a route is in neither registry, or in both.

The static half (reachability) is real and, as of the closing pass (corrida 3,
2026-09-10, commit `a943642`), the pending-instrumentation gap is closed: the 20 routes
that used to sit as `Exempt("pending instrumentation")` are now all instrumented, and one
(`POST /api/race-analysis/imports/{parse_id}/dry-run`) resolved to a genuine, documented
exemption instead. The gate now runs with 0 pending exemptions. The **dynamic half**
(actually executing a route and asserting a row landed) still collects zero cases — no
`Audited` entry declares a `request_factory` yet, which needs the `client` fixture (a real
database connection) to complete. See `qa.md` §3 for the full, honest account, including
why two earlier "closed" markings on this exact gate (T018, T030) turned out to be
premature before this pass — caught only by the corrida-2 integration review
(`specs/041-multi-coach-governance/checklists/integration-review.md` — search "compuerta
FR-009").

## 2. Club scope replaces the creator-lock on AI runs and race imports

Before this feature, a race-analysis run or an import parse could only be acted on by the
coach who launched it (`_ensure_run_owner`). With two coaches sharing a club, that lock
made a run started by coach A on a day off unreachable by coach B — exactly the scenario
FR-028 forbids.

**New rule** (`backend/app/services/permissions.py`): *anything belonging to the club can
be acted on by any coach of the club; an administrator always can; a coach of another club
never can.* `_ensure_run_owner` is deleted; its seven call sites move to
`ensure_run_club_access` / `ensure_import_club_access`.

- **Run → club**: `agent_runs.athlete_id` first, then `input_json["athlete_id"]` as a
  fallback (two of the four insert sites leave the column `NULL` — a gotcha the contract
  calls out explicitly), then the athlete's `club_id`. `deleted_at` is **not** filtered
  here — a run about an archived athlete stays openable.
- **Import → club**: race imports, series and events carry no `club_id` of their own
  (races are third-party competitions, not club-owned rows), so the only truthful link is
  the importer's `club_members` row with `role_in_club='coach'`.

**Response contract**: `agent_runs` gained `decided_by_user_id` / `decided_at`;
`race_imports` gained `committed_by_user_id` / `committed_at`. The run and import read
schemas now surface who launched and who decided, so the UI can show "Iniciado por Ana,
decidido por Bruno" instead of one implicit name.

**Spend per coach**: `budget_guard.py::spend_by_user_last_30d` groups the trailing-30-day
AI cost by `generated_by_user_id`, with an "Sin atribuir" bucket for rows that predate
attribution, reconciling exactly against the existing club-wide total (FR-029 AC4). The
budget itself stays **one club-wide limit** — this only makes the spend visible per coach,
it does not partition it.

### 2.1 A security review found two real cross-club leaks, both fixed

The club-scope change itself was reviewed for the same class of bug it was fixing, and the
review (T080, corrida 2, 2026-09-10) found two findings that were **not** about the new
code path but about launch/list surfaces the contract had marked "unchanged" on the
(correct, but incomplete) grounds that they were "already unfiltered by actor":

- **H1** — `POST /api/race-analysis/runs` and its group-launch sibling did not check the
  target athlete's club at all. A coach of another club could launch an analysis on a
  minor who was not theirs: her name reached `forbidden_names` and the AI provider, an
  insight was persisted to her file, and the audit row carried her club with an actor who
  does not belong to it. Fixed by adding the club check to `resolve_group_members` (the
  one place both launch surfaces funnel through), **before** the archived-athlete check —
  ordering matters, because 404-before-403 would let an outside coach distinguish
  "doesn't exist" from "exists and is archived" for an athlete that is not theirs.
- **H2** — `GET /race-events/{id}/runs` resolved athlete names from results without a club
  filter: the list endpoint handed out a minor's full name, athlete id, and a **valid
  `run_id` belonging to another club** — the only practical way to obtain another club's
  run id, since they are `uuid4`. The paired detail endpoint was already correctly closed
  (403), so this was a listing/detail asymmetry in the worst direction.

Both are fixed and committed (`8ca2870`). See `technical-notes.md` (2026-09-10) for the
full root-cause note and what the review verified and ruled out. Six smaller findings from
the same review (H3–H7 — an AI-spend endpoint not club-scoped for coaches, an unfiltered
imports listing, a stale `user#{id}` fallback, a dead RBAC guard, and an admin-authored
import unreachable by any coach) carried **no minor's data** and were closed in the same
night run's final pass (`a943642`): AI spend for a coach now folds every other club's
staff into one unnamed "Otros clubes" bucket instead of naming them; the imports list is
now filtered in SQL to the requester's own club(s), with an authorship fallback; the
`user#{id}` fallback is gone; the RBAC docstring on `/admin/ai-usage` states its real,
coach+admin scope; and `import_club_ids` now resolves through `(coach, admin)`
memberships so an admin-uploaded import is reachable by the club's coaches. Full
before/after detail: `qa.md` §5.2.

## 3. Co-coached sessions

### 3.1 `training_session_coaches` — the bridge table

New composite-PK table, `backend/app/models/training_session.py::TrainingSessionCoach`:
`(session_id, coach_user_id)` primary key, `added_by_user_id` (nullable — `NULL` on the
migration backfill), `added_at`. A secondary index on `coach_user_id`
(`ix_tsc_coach_user_id`) makes "sessions where X is a coach" cheap in both directions
(FR-026 filter, FR-032 activity report).

Chosen over a JSON `coach_ids` column because every other N:M relation in this schema is
already a junction table, a JSON array cannot be indexed for the coach filter without a
generated column, and there would be nowhere to put `added_by_user_id` / `added_at`.
`training_sessions.created_by_user_id` is **kept** and keeps its original meaning ("who
planned it") — the bridge answers a different question ("who leads it now").

**Minimum-one invariant** (FR-024): enforced in the service layer inside the removal's own
transaction — `SELECT COUNT(*) ... FOR UPDATE` on the session's coach rows before a
removal; if the count would drop to zero, `409`. The row lock is what closes the race
where two coaches each try to remove "the other" at the same instant. Not a DB `CHECK`
(MySQL 8.4 cannot reference sibling rows in one) and not a trigger (this codebase has
zero triggers; the constitution's stack-discipline gate treats introducing the first one
as a written-justification event).

**Backfill**: one row per existing session, `coach_user_id = created_by_user_id`,
`added_by_user_id = NULL`, `added_at = training_sessions.created_at`.

### 3.2 Truthful family notifications

Before this feature, `_load_session_coach` always resolved the session's **creator**,
regardless of who actually cancelled or edited it — coach B cancelling a session coach A
planned produced an email that named A. That function is deleted; every session/calendar
email template now receives the **acting** coach plus the full `coaches[]` list, and a
verified test (`test_b08_cancel_by_coach_b_names_b_not_creator_a`) exercises this against a
real database: A creates with A+B, B cancels, and the dispatched email's
`acting_coach_name` is B.

The family-facing schema (`TrainingSessionReadParent`) never carries `coaches` or
`has_active_coach` (verified by test) and, since a fix applied during the mandatory T091
privacy audit, no longer carries `created_by_user_id` either — the same "no coach identity
of any kind, not even an unresolved id" rule the contract states for the named fields also
holds for the raw id, and the schema and the response-model exclusion in
`training_sessions.py` now both enforce it.

### 3.3 Attendance and feedback attribution

`session_attendance` gained `recorded_by_user_id` (set once, on first non-empty entry —
never overwritten) and `updated_by_user_id` (always current). A placeholder row created by
the roster (nobody has entered anything yet) attributes to no one. Removing an athlete
from a roster **after** ratings/feedback exist archives those rows instead of deleting
them (FR-016); removing one with no data yet still deletes it; re-adding the athlete
un-archives the row rather than creating a duplicate.

## 4. Newsletter optimistic concurrency

`athlete_monthly_newsletters` gained `edit_version` (integer, starts at 1). Saving a draft
requires the version the coach last saw, via `If-Match` or `expected_version` in the body:

| Condition | Response |
|---|---|
| Version matches | Saved; `edit_version` incremented by a single `UPDATE ... WHERE edit_version = :expected` decided by `rowcount` — never a compare-then-write in Python, which would race under concurrent MySQL sessions. |
| Version is stale | `409`, body carries `current_version` so the client can offer "reload and see what changed". |
| No precondition sent at all | `428` (Precondition Required) — a deliberate, incompatible break for any caller that used to save blind. |
| Malformed precondition, or precondition disagrees with the body's own version | `400`. |
| Newsletter already sent | `409`, without `current_version` (nothing to reload into). |

`CORSMiddleware` gained `If-Match` in `allow_headers` and `ETag` in `expose_headers` — a
concurrency contract that ships without these is invisible to a browser client no matter
how correct the backend is.

The frontend studio was updated in the same window to always send `If-Match` with the
version it loaded (closing the 428-everywhere break before it shipped), and the conflict
dialog blocks with a reload action while **preserving the coach's local draft** until they
decide — the background sync does not silently overwrite a pending conflict, and a `409`
is never retried automatically (retrying it would turn one conflict into a second
overwrite).

**Coach-note authorship** (FR-012): the newsletter's coach note stores who wrote it and
when, shown to coaches/administrators only. The family-facing PDF and email were verified
by actually rendering them (WeasyPrint) and counting occurrences of the author's surname —
zero, in both channels — plus a schema-level barrier that rejects the author key even if
injected into the stored JSON.

**Approval evidence survives regeneration** (FR-010, US5 AS4): the monthly report's
`approved_by_user_id` / `approved_at` are copied to `previous_approved_by_user_id` /
`previous_approved_at` before being cleared on regeneration or edit, and the UI renders
"previously approved by" from the copy. A regression test extracted the pre-fix
`reports.py` from `HEAD` and confirmed it fails against the old behaviour, then passes
against the new one.

## 5. Per-coach activity report

`GET /api/clubs/{club_id}/coach-activity?from=&to=&coach_user_id=`
(`backend/app/routers/audit.py`, service `backend/app/services/coach_activity.py`).
Mandatory `from`/`to` (max 366-day window) — an implicit "current month" default would
make the reconciliation guarantee (SC-008) depend on the clock.

Returns `club_totals` plus one row per **active** club coach, plus any coach who is now
inactive but has a non-zero counter in the window (so a deactivated coach's contribution
during the period they worked is not silently dropped). Per coach: sessions
planned/executed/cancelled/co-led, attendance/feedback entries recorded, AI runs launched,
results operations (imports, revisions, competitor links), documents approved or sent, and
a link into that coach's own history entries.

**Counting rule**: a co-led session counts once for *each* of its coaches (so `co_led` is
visible per coach) while the club total counts the session once — this is exactly what
makes the reconciliation invariant of SC-008 true: summing each coach's sessions counted
once per session equals the club total.

A window that includes sessions or documents belonging to an **archived** athlete still
counts them — a report reconstructing a past period must not filter `athletes.deleted_at`,
the same "reconstructs the past vs. acts on the present" distinction the archive-scope
gate (`G15`, see `qa.md` §5) draws for every other read path.

Club-wide reports (monthly technical report, dashboard summary, race insights, season
panorama) are explicitly **unchanged** by this feature (FR-031) — the per-coach view is
additive, not a replacement.

## 6. Archiving instead of destroying

Removing an athlete no longer cascades a physical delete. `DELETE
/api/athletes/{athlete_id}` now sets `deleted_at` / `deleted_by_user_id` /
`deleted_reason_code` (reason from a fixed catalogue) and returns `204`; a second call
returns `409`. The athlete disappears from every active coach/parent/report/newsletter/
AI/dashboard surface while parental-consent evidence, measurements, attendance and history
remain intact for an administrator, who can restore the athlete in one action.

`contracts/athlete-archive.md` §5.3 names 20 read sites; 13 now filter `deleted_at IS
NULL`, and 7 are exempt with a written reason — all of them queries that resolve
`athlete_id → club_id` purely to stamp an audit row, or reconstruct a closed period (a
past newsletter's delivery webhook, the monthly report's name redaction) rather than act
on the present. This is tracked by its own gate,
`backend/tests/test_archive_scope_gate.py`, so a new unfiltered query cannot ship silently.

Deleting a staff account with recorded activity is refused (`409`, guidance to
deactivate) — FR-018. Deactivating one keeps the name resolvable on every past entry.
Deleting a parent account is still allowed, is recorded, and — a pre-existing defect fixed
in the same pass — no longer nulls the `created_by` attribution of records that account
created (`backend/app/routers/users.py`, see `technical-notes.md`).

## 7. Staff administration

A minimal `/admin/usuarios` screen lets an administrator create a coach (name, email, club
— club is mandatory and the form refuses without one), list staff with active state,
creation date and creator, filter by active state, and deactivate/reactivate. A coach
cannot reach the screen or its underlying actions. Club memberships are validated
consistent with the account role — a mismatched combination is refused at save time.

`GET /api/users?role=coach` stays reachable **by a coach** — it is a precondition of this
feature's own history filter and the co-coach selector, not an oversight — but the payload
a coach receives from it is trimmed to id/name/role/active-state, with no contact
information; the actions that matter (create/edit/deactivate another coach or admin, reach
the admin screen) stay administrator-only and now carry their own denied-path tests. See
`qa.md` §5 (F1) for the finding this decision closes.

## 8. Retention purge — 24 months

Full detail (this is the core operational surface) lives in `runbook.md` §5, sourced
verbatim from `specs/041-multi-coach-governance/contracts/retention-purge.md` §6. Summary:

- `backend/app/services/retention.py` owns the **only** `DELETE` against `audit_log` in
  the application — `preview_purge` (count only) and `apply_purge` (count + delete + one
  purge row per affected club, all in the caller's transaction).
- `backend/scripts/retention_audit_log.py` is a Typer CLI, dry-run by default
  (`--apply` opts in), printing one JSON line to stdout (`candidates`, `deleted`,
  `cutoff`) and a readable operator log to stderr, never the database URL.
- `.github/workflows/audit-retention.yml` runs a `preview` job monthly and on every manual
  dispatch (always safe, never touches data) and an `apply` job that only runs on manual
  dispatch with `confirm=true`, reusing the exact cutoff the preview published.
- The purge row itself is additive (one `INSERT`), so it does not violate the append-only
  rule, which forbids `UPDATE`/`DELETE` of *existing* rows.
- Append-only is proven three ways: a static grep test that no module outside
  `app/services/retention.py` issues `update(AuditLog)`/`delete(AuditLog)`, a model-level
  test that the ORM class carries no `updated_at`/`onupdate` and rejects post-flush
  mutation, and a behavioural test that a realistic multi-action scenario leaves every
  existing row's `id`/`occurred_at`/`diff_json` unchanged.

## 9. What is deliberately out of scope

- **DB-level hardening** of `audit_log` (a `BEFORE UPDATE`/`BEFORE DELETE` trigger, or a
  grant without `UPDATE`/`DELETE`) — this codebase has zero triggers and Hostinger gives
  the app a single DB user; documented as a runbook follow-up, not built.
- **The AI-spend-overrun email** — still the pre-existing documented `TODO` in
  `budget_guard.py`, unrelated to this feature.
- **Permanent purge of archived athletes** — this feature only purges `audit_log` rows;
  an archived athlete's own retention/purge is out of scope for the whole feature
  (spec.md, Assumptions).
- **The `race_events.py` coach-only inconsistency** — two endpoints
  (`backend/app/routers/race_events.py:606-609,700-703`) require the `coach` role and
  403 an administrator, unlike every other mutation in that module. Pre-existing,
  unrelated to attribution, logged as a follow-up rather than fixed silently — see
  `technical-notes.md` (2026-09-10).
