# Multi-coach governance — Design

Source: `specs/041-multi-coach-governance/` (`spec.md`, `plan.md`, `data-model.md`, nine
contracts under `contracts/`). This document summarizes the decisions actually reflected in
the branch `feat/041-multi-coach-governance` as of 2026-09-10; it does not restate the
contracts in full — each section links to the contract that owns the detail.

## Context

Club Deportivo Trocha y Ruta is onboarding a second coach who manages the club the same way
the first coach does. Before this feature, the platform had no concept of "who did this":

- No `last edited by` attribution existed anywhere, and some records lacked even a `last
  edited at` timestamp.
- Removing an athlete or a parent was a destructive cascade, including the parental-consent
  evidence Ley 1581 requires the club to keep.
- Family emails attributed every session change to the session's creator, never to the coach
  who actually performed the action.
- Regenerating a monthly report overwrote its approval evidence.
- The newsletter studio had no concurrency control — the second coach's save silently
  discarded the first coach's edits.
- There was no staff-management screen; a coach created by hand against the API without a
  club ended up signed in and staring at an empty app.
- AI runs and race-import parses were locked to their creator, while their listings were not
  filtered — a run awaiting a human decision could get stuck forever if its author was away.
- The AI spend budget was club-wide and silent about which coach was consuming it.
- No listing or report could be filtered by coach, and one surface printed a raw numeric
  user id as "created by".

Owner decisions closing the design space (2026-09-08, restated in `spec.md` Assumptions —
not reopened here):

1. Both coaches see and edit everything in the club — attribution only, no per-coach
   portfolios or owner-only editing.
2. The change log records writes plus exports/sends of documents containing a minor's data.
   **Never reads.**
3. A training session can have two or more coaches.
4. A minimal `/admin/usuarios` screen; no coach self-registration or invitation-by-token flow.
5. 24-month retention, manual purge with a preview, readable only by an administrator or a
   coach of the club.
6. The newsletter coach's note author is visible to coaches only; the family-facing voice
   stays institutional.

## Scope

**In scope**: an append-only, privacy-minimised club-wide audit trail; attribution columns
on the records that lacked them; soft-delete/restore of athletes; a bridge table for
co-coached sessions with truthful family notifications; optimistic concurrency on the
newsletter studio and approval evidence that survives regeneration; one club-scoped access
rule for AI runs and race-import parses, with spend shown per coach; read surfaces (club
history, per-athlete history, per-coach activity, staff admin); a 24-month retention purge
CLI, schedulable outside the app.

**Out of scope** (per `spec.md` Assumptions, not reopened here): per-coach athlete
portfolios, owner-only editing, recording reads, coach self-registration/invitation, any
change to how families see coach names in the newsletter, permanent purge of archived
athletes' data, partitioning the AI budget per coach, and releasing the privacy-policy
wording change on its own (FR-033 — see `policy-v1.3-draft.md`).

## Architecture

### 1. The audit trail — `record_audit` and `audit_log`

**Owning contract**: `contracts/audit-recording.md`. **Code**: `backend/app/services/audit.py`,
`backend/app/models/audit_log.py`, `backend/app/services/request_context.py`.

One new table, `audit_log`, append-only, written through a single service function,
`record_audit(db, *, action, entity_type, entity_id, actor, actor_kind, club_id, athlete_id,
changed_fields, diff, reason_code, meta, request_id)`. It only calls `db.add()` — it never
opens a session, flushes or commits — so the row shares the fate of the business write it
documents inside the caller's own transaction (56 explicit `db.commit()` sites outside
`app/dependencies.py` were audited individually to place the call above the right commit,
`contracts/audit-recording.md` §1.3).

Privacy is enforced **before the row exists**, not filtered at read time only:
`changed_fields` may list any column name, but `diff_json` keeps only the keys present in a
per-entity `VALUE_ALLOWLIST` (closed to identifiers, states, flags and dates — never a
minor's name, birth date, measurement or narrative text), and `meta_json` is rejected outright
if it carries a key outside a fixed `META_ALLOWLIST`. The read endpoints (`audit-log-api.md`)
re-apply both allow-lists as defence in depth, so a row written by an older or looser code
path still cannot leak.

A request-scoped `request_id` (pure-ASGI middleware + `ContextVar`, `RequestIdMiddleware`
in `backend/app/services/request_context.py`, mounted outermost in `app/main.py`) correlates
every row written by one HTTP request or one non-HTTP job, and is echoed back as
`X-Request-Id`. The same change fixed a pre-existing, unrelated defect: nothing under
`backend/app/` had ever called `logging.dictConfig`, uvicorn's default logging config never
touches the root logger, and the app's own `logger.info(...)` calls were silently discarded
in production. `app/main.py` now configures the `app.*` logger tree with a `request_id`
filter and `propagate=True` (chosen over the contract's original `propagate=False` so
pytest's `caplog` — used by the privacy tests that assert no minor's data appears in logs —
actually receives the records; see `backend/tests/test_logging_config.py`).

Coverage of FR-009 ("an automated check must fail when a write operation exists without a
corresponding history entry") is a closed registry, `AUDITED_ROUTES: dict[(method, path),
Audited | Exempt]` in `app/services/audit.py`, currently **99 `Audited` entries and 12
`Exempt` entries** (111 registered routes). Three complementary, individually incomplete
layers close the gap (`contracts/audit-recording.md` §7):

| Layer | Catches | Misses |
|---|---|---|
| Static registry meta-test (`test_audit_coverage.py`) | a new mutating route merged without a decision | a registry entry that lies |
| Static call-graph check (`test_audited_route_handler_reaches_record_audit`) | an `Audited` route whose handler never reaches `record_audit` on any path | whether the row is actually written at runtime |
| `AUDIT_STRICT=true` flush detector (test lane only) | a service that mutates a *second* table without recording it | anything outside a test run; ~20 raw Core `delete()`/`update()`/`text()` statements it is structurally blind to |

The dynamic smoke test the contract also asks for (§9 T4.4 — actually exercise every
`Audited` route and assert a row appears) is written as a real parametrised test but
**collects zero cases today**: `Audited` has no `request_factory` field yet, so nothing
populates the parametrisation. This is disclosed truthfully in the test's own docstring
(it used to be an unconditional `pytest.skip()` over all 81 routes, which looked like a
passing gate; that was corrected in the run of 2026-09-10 — see `technical-notes.md`).
Finishing it needs a real database (the `client` fixture requires MySQL) and a valid-request
synthesiser per route — real remaining work, not done here.

**One route stays deliberately `Exempt("pending instrumentation")`**:
`POST /api/race-analysis/imports/{parse_id}/dry-run`. The contract describes it as a
`race_import`·`update` row with `status → dry_run`, but that status transition never
actually happens in `dry_run_import` — the enum member exists but no code path emits it
(`app/models/race_import.py`'s own docstring says so). Recording an `update` here would
audit a write that never occurred, which contradicts decision 2 (never record reads/no-ops).
The two honest fixes — making the status transition real, or reclassifying the route as a
genuine `§4.14` exemption — change either the contract or the import wizard's behaviour, so
this was left marked pending for someone with the authority to choose, rather than resolved
unilaterally. See the code comment at `app/services/audit.py:1077-1091`.

### 2. Attribution columns

**Owning contracts**: `data-model.md` §4-§5, and the per-domain contracts. One
`ActorTimestampMixin` plus per-table additive `<verb>_by_user_id` / timestamp column pairs
were added to 14 existing tables in the single migration described below, so every record
that can be edited, archived or approved keeps who and when — resolved by a join at read
time into an `ActorRef` (`{user_id, display_name}`), never a raw numeric id, and resolvable
for a deactivated account (FR-013, FR-018).

**One recorded, deliberate narrowing of FR-010**, not a constitution violation
(`plan.md` Complexity Tracking, carried forward here because it changes what a reader of
`training_sessions`, `race_events`, `race_event_roster`, `interval_structures` and
`interval_templates` can expect): none of those five tables gained an
`updated_by_user_id` column. They keep `created_by_user_id` and `updated_at`; the last
**actor** to touch them is answerable only from `audit_log` (every mutating endpoint on all
five is instrumented in the same transaction as the write), not from a column. Reversing this
is cheap DDL, but was deferred because no screen renders a "last edited by" chip for these
five tables yet, and adding an unread column risks becoming a second, driftable source of
truth for a fact the log already holds — see `plan.md` Complexity Tracking for the full
argument and the owner's reversal path.

### 3. Athlete archive (soft-delete)

**Owning contract**: `contracts/athlete-archive.md`. `DELETE /api/athletes/{id}` no longer
performs a physical cascade (the former `delete(ParentalConsent)` call is gone entirely from
`app/routers/athletes.py`); it sets `deleted_at` / `deleted_by_user_id` / `deleted_reason_code`
in one `UPDATE`, requires a reason from a closed catalogue, and is recorded as
`athlete`·`archive`. `POST /api/athletes/{id}/restore` (admin only) reverses it in one
`UPDATE` and is recorded as `athlete`·`restore`.

There is deliberately **no global loader filter** — an admin must still see archived
athletes and their full history — so every read site that must exclude an archived athlete
was enumerated and fixed individually against a dedicated coverage gate,
`tests/test_archive_scope_gate.py` (an `ARCHIVE_SCOPE_EXEMPT` allow-list, currently 10
entries, for the handful of sites that legitimately reconstruct the past — e.g. resolving
`athlete_id → club_id` for an audit row, or a Resend webhook recording delivery of an
already-sent newsletter — rather than acting on the present). As of the phase-6 review this
gate is green; it started at 20 unfiltered call sites in phase 4.

Deleting a coach or administrator account with recorded activity is refused with `409` and
a message pointing to deactivation (role-agnostic — this also protects a coach account, not
only an admin); deactivation keeps the account's name resolvable on its past entries.
Removing a parent account is recorded and no longer nulls the `created_by` attribution of the
records that account created (`app/routers/users.py`'s former
`UPDATE users SET created_by = NULL` cascade is deleted).

### 4. Staff administration

**Owning contract**: `contracts/staff-admin.md`. No new backend route — the delta is on the
existing `POST /api/users`, `PATCH /api/users/{id}`, `GET /api/users` and
`POST /api/clubs/{id}/members`. `club_id` is now unconditionally mandatory when the
**target** role is `coach` or `admin` (the readiness-audit bug was that the check only ran
`if current_user.role == UserRole.coach`, so an admin creating a coach skipped it and the
club membership block entirely, leaving a coach who signs in to an empty app). A password is
rejected outright for a staff account — the person always receives the existing
set-password email, never a credential chosen by someone else. `/admin/usuarios`
(`frontend/src/routes/admin/StaffPage.tsx`) is admin-only; the navigation entry is hidden for
a coach.

### 5. Co-coached sessions and truthful family notifications

**Owning contract**: `contracts/session-coaches.md`. A new bridge table,
`training_session_coaches`, backed by a min-1 invariant enforced in the service layer
(removing the last coach from a session is refused, `409`/`422`). The three session email
templates (`invite`, `updated`, `cancelled`) drop the single `coach_name` context key —
which the contract explicitly avoids re-purposing, having learned that lesson from the
`content_version` naming mistake elsewhere — and gain three: `acting_coach_name` (who
performed *this* change), `coach_names` (the session's coaches, for pluralisation) and
`coaches_text` (a Spanish-joined string: "Ana Coach", "Ana Coach y Bruno Coach", "Ana, Bruno
y Carla"). The body of the email names who acted; the signature names who leads — that split
is what makes "coach B cancels a session coach A planned" produce a mail that correctly names
B. The label above the coaches list switches "Entrenador a cargo" / "Entrenadores a cargo"
depending on `coach_names|length` — the plural pattern reused for the privacy-policy draft
(`policy-v1.3-draft.md`).

Attendance/rating/feedback rows gain independent `recorded_by_user_id` /
`updated_by_user_id` attribution (a session's *coaches* and a rating's *recorder* are
tracked separately — co-coaching a session does not imply co-authoring every entry in it).
Removing an athlete from a roster after ratings exist archives those entries instead of
deleting them (`archived_at`), readable by an admin; re-adding the athlete unarchives them.
Session and calendar-event cancellation both gained a mandatory `reason_code` from a closed
catalogue.

### 6. Concurrency and approval evidence

**Owning contract**: `contracts/concurrency-and-approvals.md`. The newsletter studio gained
an `edit_version INT NOT NULL DEFAULT 1` column (the retired name `content_version` was
deliberately not reused) exposed as both a body field and an `ETag` header; `PATCH` requires
`If-Match` and resolves the write as a single `UPDATE ... WHERE edit_version = :expected`
decided by `rowcount`, never a Python-side compare-then-write (a real TOCTOU risk under
concurrent MySQL sessions). Missing precondition → `428`; stale version → `409` with the
current version; sent newsletter → `409` without one. The frontend keeps the coach's
unsaved draft in state through the conflict and offers "Recargar" rather than discarding it.

The coach-note gained `coach_note_author_id` / `coach_note_updated_at`, visible in the coach
schema only — absent from the parent schema, the family PDF and the family email, verified
against the **actual rendered artifacts** (a real WeasyPrint PDF render and the real email
template), not just by reading the schema.

Monthly-report approval evidence now survives regeneration: `force_regenerate` copies
`approved_by_user_id` / `approved_at` to `previous_approved_by_user_id` /
`previous_approved_at` before clearing them and stamping the new `generated_by_user_id` — a
regression test extracted the pre-change `reports.py` and confirmed it fails there, proving
the test catches the real defect.

### 7. One club-scoped rule for AI runs and imports

**Owning contract**: `contracts/scope-ai-imports.md`. `_ensure_run_owner` (admin bypass, else
"is the caller the one who launched this run") is deleted; seven call sites in
`app/routers/race_analysis.py` move to a club-membership check (`coach_club_ids(user) ∩
run's club(s) ≠ ∅`), with a legacy fallback that keeps a club-less historical run reachable
by its original author without widening access to anyone else. The same change applies to
race-import parses. `agent_runs.decided_by_user_id` / `decided_at` are now persisted (the
deciding user used to exist only in an in-memory HITL payload and was dropped before
persistence). The AI administration page gained a per-coach trailing-30-day spend
breakdown that sums to the club total, and the budget-exhausted refusal now names the period
and states that in-flight runs finish.

### 8. Per-coach reporting and author names everywhere

**Owning contract**: `contracts/coach-activity-report.md`. A new read-only endpoint,
`GET /api/clubs/{club_id}/coach-activity`, aggregates sessions (by state, counting a
co-led session once **per coach** and once for the club total — the reconciliation rule
SC-008 depends on), attendance/feedback entries recorded, AI runs launched, race-results
operations, and documents approved/sent, over an explicit date window (both bounds
mandatory, capped at 366 days). The club-wide reports (monthly technical report, dashboard
summary, race insights, season panorama) are asserted **unchanged** in content, filters and
institutional signature by `tests/test_monthly_report_unchanged.py` (FR-031). A shared
`ActorChip` component replaces the one surviving raw-numeric-id author display
(`InfoTab.tsx`).

### 9. Retention and purge

**Owning contract**: `contracts/retention-purge.md`. See `runbook.md` §5 for the operator
procedure; the design decision is summarised here. `audit_log` is kept 24 months on
`occurred_at`. The only remover is `backend/app/services/retention.py`
(`preview_purge` / `apply_purge`), wrapped by a Typer CLI,
`backend/scripts/retention_audit_log.py`, dry-run by default (`--apply` opts in). No
in-app endpoint and no background worker exist for this — Render's free tier has neither a
scheduler nor a worker process, and an internet-reachable endpoint able to delete audit
evidence was explicitly rejected as a weaker control than "the destructive code path is not
reachable over the network at all" (`retention-purge.md` §4). The preview/confirm split is
structural: a GitHub Actions workflow runs a dry-run `preview` job on a monthly schedule and
on every manual dispatch, and a second `apply` job that can only run on manual dispatch with
`confirm=true`, gated behind the `production` GitHub Environment's required reviewers. The
cutoff is computed once by `preview` and handed to `apply` via job outputs — never
recomputed — so the two jobs are guaranteed to act on the same candidate set. The purge
itself writes one `audit_log` row per affected club (`action=purge`,
`reason_code=retention_24m`), so a purge is itself part of the history it purges from.

**FR-030's "restricted to administrators" is discharged by construction, not by an
in-process check**: there is no HTTP route to call, so the restriction lives in who has
GitHub write access (can dispatch the workflow at all) and who is a required reviewer on the
`production` environment (can let `apply` through). Both lists must be kept in sync with the
club's real administrator set — see `runbook.md` §5.5. This means the CLI performs **no
authorisation check of its own**: `--actor-kind` is a label the caller supplies, not a
verified identity, and validating it would fabricate exactly the attribution the design
elsewhere refuses to invent (see the backfill note below).

Append-only (FR-004) is enforced by three complementary checks in
`backend/tests/test_audit_append_only.py`: a static grep scan for `UPDATE`/`DELETE`
patterns against `AuditLog` outside `retention.py` (textual, so an aliased import or a fully
dynamic `sa.table("audit_log")` could slip through — a known, accepted limit); a model test
asserting the table shape makes an accidental update structurally hard (no `onupdate`, no
non-`viewonly` relationships, `RESTRICT` on the actor FK); and a behavioural test that runs
two batches of real actions plus a purge and asserts every earlier row is present, unchanged,
in every later read.

## Migration

One Alembic revision, `45cd705c6b54` (`down_revision = "2a8baa967cc6"`, the `growth_source`
migration of feature 040) — currently the single head of the chain (`alembic heads` returns
exactly one). It was deliberately **not** split into "new tables" and "attribution columns +
backfills" as two revisions, because an intermediate state would leave every existing session
with zero coaches, violating the bridge table's minimum-one invariant.

Adds: `audit_log` (five indexes: four composite plus `ix_audit_request_id`),
`training_session_coaches` (composite PK, backfilled so every existing session keeps
exactly its creator as coach), additive nullable attribution columns on the 14 tables named
above, and three read-path indexes (`ix_athletes_deleted_at`,
`ix_calendar_events_deleted_at`, `ix_session_attendance_archived_at`). `audit_log.occurred_at`
is explicitly declared `DATETIME(fsp=6)` on MySQL — a bare `sa.DateTime()` truncates to
`fsp=0` and would make two same-second actions by two coaches indistinguishable, the exact
pre-existing gap `race_result_revisions.changed_at` has and that this table must not
inherit. Backfills (B1, B2, B4–B7) are idempotent (`NOT EXISTS`/`IS NULL` guards, safe to
re-run) and are **not** restored on `downgrade()` — the schema shape is fully reversible, the
historical attribution/coach rows it wrote are not recoverable after a downgrade, stated in
the migration's own docstring with the same honesty as the precedent
(`8b5ac1f24f61`'s docstring).

**Backfill posture on approval evidence** (`monthly_reports.approved_at` backfilled from
`generated_at` for already-approved rows, `approved_by_user_id` left `NULL`): the migration
never fabricates an approver for historical data it cannot verify; the UI renders "aprobado
(sin registro de autor)" for those legacy rows rather than inventing a name. The same
discipline governs why the retention CLI's `--actor-kind` has no `user` option (§9 above) —
manufacturing an attribution nobody can verify is treated as a privacy/integrity risk in this
codebase, not a convenience.

**Not verified against a real MySQL database in this environment.** This sandbox has no
Docker and no MySQL server, so the migration's own claims — a clean `upgrade` from
`2a8baa967cc6`, the round-trip `upgrade → downgrade → upgrade`, and the FK-constraint DDL
timing on Hostinger-equivalent MySQL 8.4 — are supported by the offline SQLite lane and by
the migration author's documented review, not by an executed `pytest -m mysql` run in this
session. This is the same gap `T014`/`T027`/`T028` name for feature 040, applied here to a
new migration; see `runbook.md` §6 and `qa.md` for what is and is not covered.

## Known pre-existing issues touched or found (not introduced by this feature)

- **`backend/app/routers/race_events.py` — two coach-only endpoints inconsistent with the
  rest of the module.** `cleanup_duplicate_race_event` (`DELETE
  /api/race-analysis/race-events/{id}/cleanup`) and
  `create_calendar_event_for_race_event` (`POST
  /api/race-analysis/race-events/{id}/calendar-event`) are gated
  `require_role([UserRole.coach])`, so an **admin** gets a `403` from them — every other
  mutation in the same router (create, update, delete, calendar-link) accepts
  `[admin, coach]`. Decision-1 of this feature ("both coaches and the admin see and edit
  everything") makes this inconsistency more visible than before, but it predates the
  branch and was explicitly left as a documented follow-up rather than fixed here
  (`plan.md` "Open operational decisions"; see `technical-notes.md` for the dated entry).
- **`GET /api/clubs/{id}` and `GET /api/clubs`** expose every club member's name (staff and
  families) to *any* authenticated user, including a parent or an athlete account — confirmed
  byte-identical to `main` on the two handlers in question, so it predates this feature. Out
  of scope for this task's file permissions (`clubs.py` beyond `create`/`update`/`add-member`
  was never meant to change here); recorded in `specs/041-multi-coach-governance/checklists/
  integration-review.md` (findings F1/F2) for the next wave.
- **The historical fresh-database migration bug** (three migrations importing
  `app.data.technique_catalog` / `app.data.strength_catalog`, modules deleted by feature 038)
  was already identified and fixed by feature 040
  (`e1f2a3b4c5d6_technique_gymkhana_library.py`,
  `f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py`,
  `a7b8c9d0e1f2_strength_training_library.py`, each now guarded with
  `try/except ModuleNotFoundError`). This feature's migration sits on top of that fix and
  was not blocked by it, but the underlying reason feature 040's Playwright specs could not
  run on a from-empty database is the same reason this feature's Playwright specs (T092)
  have not been attempted in *this* sandbox: there is no Docker/MySQL here at all, which is a
  stricter constraint than the bug feature 040 fixed.
- **Frontend/DB privacy-policy version drift, pre-existing.** `frontend/src/routes/
  PrivacyPage.tsx` hardcodes `POLICY_VERSION = "1.1"` (dated 6 May 2026 in its own header
  comment) while the database's active policy is already `v1.2` (the AI-processing consent
  clause added by `a2b3c4d5e6f7_add_policy_v1_2_ai_processing.py`, 15 May 2026) — the static
  page was never updated when v1.2 shipped. See `policy-v1.3-draft.md` for the consequence
  for this feature's task (sync to the DB version) and why it is documented, not applied,
  here.

## Pending / not verified in this pass

Carried over from `specs/041-multi-coach-governance/tasks.md` (T091–T098), unchecked as of
this writing:

- **T091 — mandatory `data-privacy-guard` audit.** Not run as a dedicated pass in this
  session. What this document *can* attest, from reading the code directly: the allow-lists
  in `app/services/audit.py` are code-enforced (not merely documented), the coach-note author
  matrix was verified against a real rendered PDF and email (not just the schema), and
  `test_audit_privacy.py` / `test_newsletter_coach_note_author.py` exist and encode these
  invariants. A dedicated `data-privacy-guard` pass is still the constitution's mandatory
  gate and has not been recorded.
- **T092 — Playwright specs** (`staff-admin`, `athlete-archive`, `session-coaches`,
  `newsletter-conflict`, `coach-activity`) do not exist in the working tree yet. This
  environment has no Docker and no MySQL, so even the isolated e2e stack feature 040 built
  cannot be booted here.
- **T078 — backend club-scope regression tests** (`test_race_imports_club_scope.py`,
  `test_spend_by_user.py`) do not exist yet; `test_race_analysis_club_scope.py` does (17
  cases). See `qa.md`.
- **T080 — security review of the scope change** (US6) has not been recorded.
- **T086 — integration review of phases 5–9 on a live dev stack** (bundle sizes, nav areas
  per role) has not been recorded; no dev stack is reachable from this sandbox.
- **`pytest -m mysql`, the migration's MySQL round-trip, and post-deploy smoke (T097)** all
  need a real MySQL/production endpoint this sandbox does not have. Written and reasoned
  about, not executed.
- **Full-suite regression status**: the most recent recorded full run
  (`checklists/integration-review.md`, US4/US5 close-out, 2026-09-10) measured **zero
  regressions** against a `main` worktree baseline. Several other agents were editing
  `backend/` while this document was written; a fresh full run attempted during this session
  did not finish within a usable window because it was contending for CPU with those
  parallel edits (see `qa.md` for what was actually re-verified in this pass: file existence,
  registry counts, and targeted reads of the code, not a fresh `pytest -q` number).

## References

- `specs/041-multi-coach-governance/spec.md`, `plan.md`, `data-model.md`
- `specs/041-multi-coach-governance/contracts/*.md` (nine contracts, cited by name above)
- `specs/041-multi-coach-governance/checklists/integration-review.md` — full review history
  across phases 3–7 (US1–US5), with every gap found and its resolution status
- `docs/19-multi-coach-governance/runbook.md` — retention/purge operator procedure
- `docs/19-multi-coach-governance/qa.md` — test plan and coverage as actually found
- `docs/19-multi-coach-governance/policy-v1.3-draft.md` — draft privacy-policy wording (not
  released in this feature)
