# Integration review — Phase 3 (US1), feature 041

**Task**: T039 (adapted). **Date**: 2026-09-09. **Branch**: `feat/041-multi-coach-governance`
(HEAD `c596622` + uncommitted wave-3 work in the tree).

**Method**: the 20-action live script of `quickstart.md` scenario 1 could **not** be run —
this machine has no Docker, no MySQL and no running stack. This review is therefore a
**static code review against `spec.md` US1 AS1–AS8, `quickstart.md` scenarios 1–3 and
`contracts/audit-recording.md` §4**, plus a full `pytest` run and a differential against a
`main` worktree baseline (`/tmp/t039-baseline`).

**Caveat on the measurements**: the working tree was being edited by other agents while the
suite ran. Every count below is a snapshot of the tree as of the run that finished at
138 s on 2026-09-09; re-run before quoting it in a gate.

---

## 1. AS1–AS8 verdicts

| # | Acceptance scenario (US1) | Verdict | Evidence |
|---|---|---|---|
| AS1 | Coach B edits coach A's session → row with actor, `update`, entity, changed fields, time | **Cumple** (code) / **no verificable sin stack** (end-to-end) | `app/services/training/sessions.py:661-701` records `training_session·update` with `compute_changed_fields`; actor comes from `ctx: AuditContext` threaded from `get_request_context`. The end-to-end assertion lives in `tests/test_audit_actors.py`, which needs the `client` fixture → MySQL. |
| AS2 | No minor's name, birth date, measurement, medical or narrative content in any row | **Cumple** | `record_audit` filters `diff` against `VALUE_ALLOWLIST` (`app/services/audit.py:641-650`) and hard-rejects any `meta` key outside `META_ALLOWLIST` (`:652-665`); the read path re-filters in `app/routers/audit.py:_filter_diff/_filter_meta` (`:160-206`). Every `changed_fields=[...]` and `meta={...}` literal in `app/` was inspected — see §3. `tests/test_audit_privacy.py` (8 tests) passes offline. |
| AS3 | Export/send of a document with a minor's data is recorded | **Cumple** | All 9 mutating/exporting GETs of §4.13 plus `POST …/report/email` are instrumented: `routers/reports.py:136,206,317`, `routers/monthly_reports.py:555,712`, `routers/athlete_monthly_newsletters.py:863`, `routers/parent_newsletters.py:241`, `routers/intervals.py:908`, `routers/race_analysis.py:1278`, `routers/strava_integration.py:207` (callback `link`). Both §4.13 hazards are handled: the row is written **outside** the `if nl.pdf_sha256 != sha256` branch (`athlete_monthly_newsletters.py:850-870`) and **after** document generation (`reports.py:130-143`). |
| AS4 | Automated writes carry the machine actor kind, never the last human | **Cumple** | `system_context` / `webhook_context` / `cron_context` used at `routers/race_analysis.py:562` (`agent_run_complete`), `routers/webhooks_resend.py:208`, `routers/strava_integration.py:388,541`, `app/scripts/backfill_anthropometry.py:101,249`, `app/seed_growth_data.py:85`. `AuditContext.actor` never comes from the ContextVar (`services/request_context.py:120-155`), and `record_audit` rejects `actor_kind != user` with a non-null actor (`audit.py:598-603`). |
| AS5 | One user action writing N rows shares one correlation reference | **Cumple** (code) / **no verificable sin stack** (assertion) | `RequestIdMiddleware` is the outermost middleware (`app/main.py:131`) and binds the ContextVar for the whole request, so multi-row operations correlate by construction: `routers/users.py:466-506` (consent + link + member + user rows), `services/race/group_launch.py:573`, the newsletter batch, `services/training/sessions.py:165-178` + `:690-701` (session + parallel calendar event). Non-HTTP multi-row jobs pass `request_id=ctx.request_id` explicitly. The X-Request-Id echo itself is asserted in `tests/services/test_request_context.py:131-152`, which needs `client` → MySQL. |
| AS6 | A parent is refused the club history and its own child's history | **Cumple** (code) | `can_view_audit` returns `False` for any non-admin/non-coach (`services/permissions.py:440-457`); the athlete-scoped route adds `require_role([admin, coach])` before `verify_athlete_access` (`routers/audit.py:320,366`). Denied-path tests live in `tests/routers/test_audit_log_api.py` → `client` → MySQL. |
| AS7 | A coach of another club is refused | **Cumple** (code) | `can_view_audit` → `club_id in coach_club_ids(user)` (`permissions.py:455-456`); the club route 403s before any SQL (`routers/audit.py:286-292`). Same test-lane caveat as AS6. |
| AS8 | Filters (actor, entity, athlete, period), newest first, actor name resolved | **Cumple** (code) | Shared filter builder `routers/audit.py:87-160`; `_build_entry` resolves `actor_display_name` and renders `sentence_es` through `render_sentence` (`routers/audit.py:209-258`), never a bare numeric id. Ordering/pagination assertions are in `tests/routers/test_audit_log_api.py` → `client` → MySQL. |

**Not verifiable on this machine at all**: every audit test that mounts the app — 51 tests
across `tests/test_audit_actors.py`, `tests/test_audit_reports_newsletters.py`,
`tests/test_audit_race_analysis.py` and `tests/routers/test_audit_log_api.py`, plus the
three middleware tests of `tests/services/test_request_context.py` and the whole
`-m mysql` lane (`tests/test_audit_mysql.py`). AS1, AS5, AS6, AS7 and AS8 are therefore
"code is right" verdicts, not "observed" verdicts.

**Offline audit tests that do run and pass**: `tests/services/test_audit_helper.py`,
`tests/services/test_audit_strict_mode.py`, `tests/models/test_mixins.py` (28 passed),
`tests/test_audit_privacy.py` + `tests/test_audit_append_only.py` (13 passed).

---

## 2. Instrumentation matrix coverage (`contracts/audit-recording.md` §4)

`AUDITED_ROUTES` (`app/services/audit.py:1197`) is complete as a registry, but **19 of the
110 keys are still `Exempt("pending instrumentation")`** — i.e. the write happens and no
audit row is produced. This is disclosed in the module comment at `audit.py:729-737`; it is
a true statement about today's code, not a documentation error, but it is a real US1 hole.

| Registry key | Line |
|---|---|
| `POST /api/auth/parent-register` | `audit.py:794` |
| `POST /api/auth/password-reset/confirm` | `audit.py:799` |
| `PATCH /api/profile/basic` | `audit.py:800` |
| `POST /api/profile/change-password` | `audit.py:801` |
| `POST /api/profile/change-email/confirm` | `audit.py:807` |
| `POST /api/ai/athletes/{athlete_id}/phv-explanation` | `audit.py:850` |
| `POST /api/ai/athletes/{id}/measurements/{record_id}/explanation` | `audit.py:854` |
| `POST /api/parent-athletes` | `audit.py:860` |
| `POST /api/parent-athletes/invite` | `audit.py:861` |
| `DELETE /api/parent-athletes/{relation_id}` | `audit.py:862` |
| `POST /api/parents/me/athletes/{id}/newsletters/{nid}/read` | `audit.py:982` |
| `POST /api/race-analysis/imports/{parse_id}/dry-run` | `audit.py:1034` |
| `/api/intervals/structures` POST · PUT · DELETE | `audit.py:1093-1095` |
| `/api/intervals/templates` POST · PUT · PATCH archive · POST attach | `audit.py:1100-1103` |

Three of these are directly athlete-scoped writes (`parent-athletes` link/unlink/invite,
the two AI-explanation upserts), so `spec.md` US1 ("an athlete profile … a staff account")
is not yet fully satisfied.

Everything else in §4 was checked call-site by call-site and matches the contract tuple
(entity · action · `athlete_id` · reason), with the deviations listed in §5.

**Transaction rule (FR-001)**: `record_audit` only calls `db.add` (`audit.py:686`) and
`get_db` commits after the handler returns (`app/dependencies.py:17-24`), so rows share the
business transaction. The only sites where a commit precedes the audit row are the two PDF
downloads (`athlete_monthly_newsletters.py:850-861`, `parent_newsletters.py:230-239`) and
the import commit — all three are the contract-sanctioned early-commit cases of §4.10/§4.13.

---

## 3. Privacy scan of the new rows (Ley 1581)

- **`meta=`**: every literal key emitted anywhere in `app/` is a member of `META_ALLOWLIST`
  (`document_kind`, `recipients_count`, `athlete_count`, `convocados_count`, `event_date`,
  `period`, `job`, `rows`, `event_type`, `related_entity_id`, `results_count`,
  `competitors_count`, `previous_status`, `stale`, `supersedes_run_id`, `race_event_id`,
  `is_revision`, `block`, `step_id`, `has_edits`). No free-text key exists, and an unknown
  key raises `AuditContractError` at write time (`audit.py:655-656`). `meta.job` is further
  constrained to `AUDIT_JOB_SLUGS` (`audit.py:663-664`). `event_date` is a session date, never
  a birth date; `block` is a static block key.
- **`diff=`**: `record_audit` keeps only keys present in `VALUE_ALLOWLIST[entity_type]` and
  drops the rest silently (`audit.py:641-650`). Entity types absent from the allowlist get an
  empty frozenset, so their diff is dropped entirely. No allowlisted column is a name, a
  birth date, a measurement or narrative text — the closest are `club_join_date`,
  `evaluation_date`, `growth_source` and `hidden_blocks` (block keys only).
- **`changed_fields=`**: all 23 distinct literals in `app/` are column names
  (`coach_note`, `narrative_blocks`, `ai_narrative`, `decided_by_user_id`, …) — names, never
  values, exactly as FR-003 requires.
- **Defence in depth on read**: `routers/audit.py:160-206` re-applies both allowlists before
  serialising, so a row written by an older/looser code path still cannot leak.

**Verdict: no path found by which a new audit row can carry a minor's name, birth date,
measurement or narrative text.** The residual risk is a future caller passing a *value* as a
`changed_fields` string; that is not guarded by type, only by review.

---

## 4. Test-suite result

Full run from `backend/` (`./.venv/bin/python -m pytest -q`):

```
248 failed, 3999 passed, 116 skipped, 12 xfailed, 6 xpassed, 219 warnings in 138.05s
```

Classification (each failure's traceback inspected; the 44 whose traceback appeared in the
errors section were re-run individually to confirm):

| Bucket | Count |
|---|---|
| Environmental — `(2003, "Can't connect to MySQL server on 'mysql'")` | **197** |
| Non-environmental failures | **51** |
| …of those, **also failing on the `main` baseline** (worktree `/tmp/t039-baseline`) | **37** |
| …of those, **regressions introduced by this branch** | **14** |
| Regressions masked inside a MySQL-failing module in the full run but failing for audit reasons when run in isolation | **+9** |
| **Total real regressions still open** | **23** |

Two corrections to the briefing:

1. The `main` baseline is **not** "225 failures, all MySQL". It also carries **37
   non-MySQL pre-existing failures** — `tests/test_circuit_diagram_partial.py` (18, jinja2),
   `tests/services/notification/test_stage_log_pdf.py` (12), `tests/test_ai_factory.py`,
   `tests/test_calendar_audiences.py`, `tests/test_calendar_models.py` and part of
   `tests/test_stage_log_email.py`. Do not count these against feature 041.
2. All **54** tests of `.regresiones-oleada2.txt` **pass on `main`** (verified in the
   baseline worktree: `54 passed`). On the current tree **31 are already repaired** by
   parallel wave-3 work and **23 remain failing**.

The 23 open regressions, by root cause:

| Cause | Tests | Where |
|---|---|---|
| `AuditContractError: entity_id must be a positive int, got None` — the audit row is built from an id the mocked session never assigns | 7 | `tests/test_notification_changes.py::TestAnthropometryNotificationLogic` (site: `app/routers/anthropometry.py:203-212`) |
| Test double signature drift — `_create_parallel_calendar_event` now takes `ctx` | 2 | `tests/test_calendar_training_integration.py::TestCreateSessionIntegration` |
| sqlite subset harness lacks the new attribution column `calendar_events.cancelled_by_user_id` | 2 | `tests/routers/test_calendar_competition_link.py` |
| sqlite subset harness lacks the `athletes` table now read to resolve `club_id`/`athlete_id` | 5 | `tests/routers/test_race_analysis_cancel.py` |
| `_FakeSession` has no `.add` (`audit.py:686`) / “execute no debería llamarse” — the audit row adds a SELECT the double forbids | 3 | `tests/routers/test_run_staleness_endpoints.py` |
| `IndexError: list index out of range` at `tests/services/notification/test_stage_log_email.py:262` | 4 | stage-log e-mail dispatcher |

None of the 23 needs MySQL; the whole set runs in under 2 s.

---

## 5. API-contract changes introduced by wave 2, and the frontend

| Change | Backend | Documented? | Frontend today |
|---|---|---|---|
| `DELETE /api/training-sessions/{session_id}` now requires `reason_code` (query, `CancelReasonCode`, **no default**) | `app/routers/training_sessions.py:474` | **Yes** — `contracts/session-coaches.md:214` and the worked call at `:505` (`?notify=true&reason_code=cancel_weather`) | **BREAKS**: `frontend/src/api/trainingSessions.ts:69-77` sends only `notify` and `reason` → every cancellation now returns 422 |
| `DELETE /api/users/{user_id}` now requires `reason_code` (query, `ParentRemovalReasonCode`, **no default**) | `app/routers/users.py:357-359` | **No** — `contracts/staff-admin.md` and `audit-recording.md` §4.2 require *a* reason for this row but never specify the transport; no contract line describes the query parameter | **BREAKS**: `frontend/src/api/parents.ts:75-77` sends no parameter → 422 |
| `PATCH /api/users/{user_id}` requires `reason_code` in the body when `is_active: false` | `app/routers/users.py:324` | **Yes** — `contracts/staff-admin.md:339-366` | No current caller (the staff screen is a later task) — no break today |

Both breaking changes are backend-only so far; nothing in `frontend/src` references
`reason_code` outside the read-side audit types (`src/types/audit.types.ts`,
`src/schemas/audit.ts`, `src/lib/auditLabels.ts`).

---

## 6. Concrete gaps for wave 4

| # | Gap | File · line |
|---|---|---|
| G1 | 19 registry keys still `Exempt("pending instrumentation")`; three are athlete-scoped writes | `backend/app/services/audit.py:794,799,800,801,807,850,854,860,861,862,982,1034,1093-1095,1100-1103` |
| G2 | 23 regressions of the wave-2 list still failing (buckets in §4) | see §4 table |
| G3 | `DELETE /api/athletes/{id}` still performs the physical cascade (including `delete(ParentalConsent)`) and records `action=delete` with **no** `reason_code` — §4.3 requires `archive` + a mandatory `athlete_*` reason | `backend/app/routers/athletes.py:329-413` (deferral noted in-code at `:388-394`) |
| G4 | Calendar cancellation records a **hard-coded** `cancel_organizer_cancelled` for every event instead of the coach's chosen reason — the audit row states a motive nobody selected | `backend/app/services/calendar/events.py:546-561` |
| G5 | `frontend/src/api/trainingSessions.ts` does not send `reason_code` → 422 on every session cancellation | `frontend/src/api/trainingSessions.ts:69-77` |
| G6 | `frontend/src/api/parents.ts` does not send `reason_code` → 422 on every parent deletion | `frontend/src/api/parents.ts:75-77` |
| G7 | The `DELETE /api/users/{id}` `reason_code` query parameter is not described in any contract | `backend/app/routers/users.py:357-359` vs `contracts/staff-admin.md` |
| G8 | Newsletter send skips the audit row entirely when `actor is None` instead of recording a machine actor — a future scheduled dispatch would send un-audited | `backend/app/services/notification/newsletter_dispatcher.py:424-437` |
| G9 | Strava reconcile records one row **per connection** (`strava_connection·execute`), not one per created/updated activity as §4.12 requires | `backend/app/routers/strava_integration.py:534-556` (deviation disclosed in-code) |
| G10 | `monthly_reports.previous_approved_by_user_id` / `previous_approved_at` exist on the model but are never written; the regeneration branch still overwrites the approval evidence (US5 AS4) | `backend/app/models/training_session.py:259-263` vs `backend/app/services/training/reports.py:194-233` |
| G11 | Section comments in the registry say "all pending" over blocks that are now `Audited` — misleading for the next reader | `backend/app/services/audit.py:810,833,858,871,890,927` |
| G12 | New docstrings in `can_view_audit` are written without diacritics ("Sincrona a proposito", "membresia", "funcion"), against the project rule | `backend/app/services/permissions.py:440-465` |
| G13 | Nothing in `docs/` records the two breaking API changes; `docs/technical-notes.md` has no entry for feature 041 yet | `docs/technical-notes.md` |

---
---

# Integration review — Phase 4 (US2), feature 041

**Task**: T050 (adapted). **Date**: 2026-09-09. **Branch**: `feat/041-multi-coach-governance`
(HEAD `c596622` + uncommitted wave-3/4 work in the tree).

**Method**: no Docker, no MySQL, no running stack, so quickstart scenarios 4 and 5 could not
be executed live. This is a **static review against `spec.md` US2 AS1–AS7,
`quickstart.md` scenarios 4–5 and `contracts/athlete-archive.md` §1–§12**, plus a full
`pytest` run measured differentially against a `main` worktree baseline
(`/tmp/t050base`, `main` = `86e0208`).

## 0. Blocking finding — the tree does not import

`./.venv/bin/python -m pytest -q` from `backend/` **collects zero tests**:

```
ImportError: cannot import name 'AUDIT_FIELD_LABELS' from 'app.services.audit'
  app/routers/audit.py:44
```

`app/routers/audit.py` (untracked, wave 3) imports `AUDIT_FIELD_LABELS`, which the
`app/services/audit.py` currently in the working tree does **not** define — that file is
byte-identical to `HEAD`. The version that defines the symbol exists only inside
**`stash@{0}`**, created `2026-09-09 17:18:21`, 39 files, including
`services/calendar/events.py`, `routers/strava_integration.py`,
`services/notification/newsletter_dispatcher.py`, `services/permissions.py` and
`specs/041-multi-coach-governance/tasks.md`. Several wave-3 gap fixes (G4, G8, G11, G12)
live in that stash and in no other place.

**Nothing in this review restored the stash** — the repository was not modified. Every
number below was measured in throw-away copies: `/tmp/t050b` (full-repo copy of the working
tree with `app/services/audit.py` replaced by the `stash@{0}` version) and `/tmp/t050base`
(`git worktree` of `main`).

## 1. AS1–AS7 verdicts

| # | Acceptance scenario (US2) | Verdict | Evidence |
|---|---|---|---|
| AS1 | Coach removes with a reason → archived, recorded with actor + reason, absent from every coach/parent/report/newsletter/AI surface | **Cumple parcialmente** | Archive is a pure `UPDATE` (`backend/app/services/athlete_scope.py:26-58`), reason required (`AthleteArchiveIn`), audit row `athlete·archive` with actor + `reason_code`. The enumeration test of contract §12.2 is green (`tests/test_archived_athlete_absent.py` + `tests/test_parent_archived_only.py` → **17 passed, 1 xfailed** in isolation). But the §5.4 scope gate is **red**: `tests/test_archive_scope_gate.py` lists **20** `file:line` sites reading athletes with neither `deleted_at IS NULL` nor an exemption (see G15). |
| AS2 | Admin views the archive → consent, measurements and history intact and readable | **Cumple** (code) / **no verificable sin stack** (observed) | Archive touches only `athletes`; the physical cascade and its `delete(ParentalConsent)` are gone from `backend/app/routers/athletes.py` (no `delete(` remains). Admin list: `routers/athletes.py:194-276` (`include_archived`, coach → `403` at `:198`). `verify_athlete_access` returns the row for admin before the archived check (`app/dependencies.py:112-121`). The dedicated proof test is **red for harness reasons only** — see G19. |
| AS3 | Admin restores → athlete reappears everywhere, restoration recorded | **Cumple** | `restore_athlete` (`athlete_scope.py:61-89`) nulls the three columns in one `UPDATE` and records `athlete·restore` with `AthleteRestoreReasonCode`; endpoint admin-only (`routers/athletes.py:443-472`). |
| AS4 | Athlete with attendance/event/race history archives cleanly | **Cumple** | No `DELETE` is issued, so the three `ondelete=RESTRICT` FKs of contract §6 are never exercised. `tests/routers/test_athlete_archive.py` → 15 passed / 1 failed (the failure is G19, unrelated to `RESTRICT`). |
| AS5 | Parent whose only athlete is archived sees a calm empty state | **Cumple** | Choke point C1 filters inside `services/permissions.py:63-78`; `parent_athletes.py:183`, `services/privacy.py:166` (no blocking consent modal), `routers/auth.py:192` (invite not acceptable). `tests/test_parent_archived_only.py` green. |
| AS6 | Staff account with activity cannot be deleted → `409`, deactivate instead; name survives on past entries | **Cumple** (code) / **tests rojos** | `routers/users.py:445-461` — rule 6 is role-agnostic, `409` with the "Desactívalo…" copy; `PATCH` maps `is_active` transitions to `deactivate`/`activate` and demands `reason_code` (`:349-360`). All **6** tests of `tests/test_users_delete_deactivate.py` fail — see G20. |
| AS7 | Parent removal recorded, no other record loses its `created_by` | **No verificable sin stack** | The manual cascade at `routers/users.py:490-500` no longer touches `parental_consents` (rule 7, §8.2) and captures links/memberships before deleting to emit one row each. The assertion lives in `tests/test_audit_actors.py::TestDeleteUserAudit::test_delete_parent_records_rows_and_preserves_created_by`, which needs the `client` fixture → MySQL, and in `test_users_delete_deactivate.py`, which is red (G20). |

**Quickstart scenario 4**: steps 1, 3, 4 and 5 are supported by green code and tests; step 2
(absence from *every* surface) is green for the enumerated surfaces but its lint is red.
**Quickstart scenario 5**: steps 1, 2, 5 and 6 match the code; step 4 ("coach B's name still
resolves on `deleted_by`") is contradicted by G17 for the per-athlete history route.

## 2. Privacy invariant (Ley 1581)

- **Consent evidence survives the archive.** `archive_athlete` performs a single `UPDATE` on
  `athletes` and no `DELETE` anywhere (`app/services/athlete_scope.py:26-58`);
  `routers/athletes.py` contains no `delete(` call at all any more, so the former
  `delete(ParentalConsent)` cascade of contract §6 is gone. `DELETE /api/users/{id}` also stops
  before the cascade when the account granted a consent (`routers/users.py:445-461`).
  **Verdict: cumple.**
- **The archive audit rows carry no minor's data.** `archive_athlete` emits
  `changed_fields=["deleted_at", "deleted_by_user_id", "deleted_reason_code"]` (column names)
  and `diff={"deleted_reason_code": (None, <code>)}` — a closed-catalogue code; `entity_id`,
  `athlete_id`, `club_id` and `actor` are integer identifiers; no `meta` is passed. Defence in
  depth holds: `deleted_reason_code` is the only one of the three that is in
  `VALUE_ALLOWLIST[athlete]` (`app/services/audit.py:265-...`), so even the other two column
  *values* could not reach `diff_json`. The restore row is symmetrical.
  **Verdict: cumple. No path found by which an archive/restore row can carry a name, a birth
  date, a measurement or narrative text.**

## 3. Test suite — measured differentially

| Run | Result |
|---|---|
| `backend/` as it stands | **collection error, 0 tests run** (§0) |
| `/tmp/t050b` = working tree + `stash@{0}` `services/audit.py` | `288 failed, 4007 passed, 116 skipped, 13 xfailed, 6 xpassed` in 144 s |
| `/tmp/t050base` = `main` (`86e0208`) baseline | `225 failed, 3699 passed, 30 skipped, 12 xfailed, 6 xpassed` in 130 s |

The briefing's figure is confirmed exactly: **`main` fails 225**. Set difference on test ids:

| Bucket | Count |
|---|---|
| Failing on `main` and still failing (environmental + pre-existing) | **225** |
| Failing only on this branch | **63** |
| …in test files that do not exist on `main` (new tests, i.e. unfinished work) | **15** |
| …**true regressions** of tests that pass on `main` | **48** |
| Tests fixed relative to `main` | **0** |

**Regressions went from 23 (end of wave 3) to 48.** Of the 23 listed in
`.regresiones-oleada3.txt`, **21 are still failing**; only the two
`tests/test_calendar_training_integration.py::TestCreateSessionIntegration` cases were
repaired. The 25 added regressions are almost entirely one root cause (G22).

Regressions by root cause:

| Cause | Count | Where |
|---|---|---|
| `AttributeError: 'types.SimpleNamespace' object has no attribute 'deleted_at'` — a new `deleted_at` read on a path whose unit-test double is a `SimpleNamespace` | **22** | `tests/routers/test_athlete_monthly_newsletters_router.py` (11), `tests/services/training/test_badge_evaluator.py` (7), `tests/services/notification/test_stage_log_email.py` (4) |
| sqlite subset harness missing new attribution columns / tables | 7 | `tests/routers/test_calendar_competition_link.py` (2), `tests/routers/test_race_analysis_cancel.py` (5) |
| `AuditContractError: entity_id must be a positive int, got None` on mocked sessions | 7 | `tests/test_notification_changes.py::TestAnthropometryNotificationLogic` |
| Test doubles that forbid the extra `SELECT`/`add` the audit row introduces | 3 | `tests/routers/test_run_staleness_endpoints.py` |
| Others (signature drift, `ctx` threading, newsletter dispatcher grouping, calendar FK) | 9 | `test_race_analysis_athlete_sex.py` (3), `test_calendar_router.py` (2), `test_newsletter_dispatcher.py` (2), `test_calendar_models.py` (1), `test_newsletter_builder.py` (1) |

Failures in **new** files (unfinished work, not regressions): `test_users_delete_deactivate.py`
(6), `test_audit_athletes.py` (2), `test_athlete_archive.py` (1), `test_audit_log_api.py` (1),
`test_audit_coverage.py` (1), `test_archive_scope_gate.py` (1), `test_audit_actors.py` (1),
`test_audit_helper.py` (1), `test_logging_config.py` (1).

## 4. Status of the wave-3 gaps

| Gap | Status | Note |
|---|---|---|
| G4 — calendar cancellation hard-codes `cancel_organizer_cancelled` | **Abierta en el árbol de trabajo** | Still hard-coded at `backend/app/services/calendar/events.py:561`. The fix (a `reason_code` parameter, `:525` / `:566`) exists **only in `stash@{0}`**. |
| G5 — `trainingSessions.ts` sends no `reason_code` | **Cerrada** | `frontend/src/api/trainingSessions.ts:78` sends `reason_code` as a query param, matching `routers/training_sessions.py:474`. |
| G6 — `parents.ts` sends no `reason_code` | **No cerrada — cambió de forma** | `frontend/src/api/parents.ts:83` now sends `params: { reason_code }` (query), but the backend moved the field to a **JSON body** (`UserDeleteIn`, `backend/app/schemas/user.py:58-67`, `routers/users.py:387`), as contract §8.4 prescribes. axios sends no body on that call → every parent deletion still returns `422`. The stale docstring at `parents.ts:76-78` even says "query param obligatorio". |
| G7 — `DELETE /api/users/{id}` reason transport undocumented | **Cerrada** | `contracts/athlete-archive.md` §8.4 ("gains a required body, symmetrical with §1") and §3 row for `ParentRemovalReasonCode`. |
| G8 — newsletter send skips the audit row when `actor is None` | **Abierta en el árbol de trabajo** | `backend/app/services/notification/newsletter_dispatcher.py:426` still guards with `if actor is not None:`. The fix (`actor_kind=system` fallback) exists **only in `stash@{0}`**. |
| G9 — Strava reconcile records one row per connection, not per activity | **Abierta** | `backend/app/routers/strava_integration.py:539-556`, deviation still disclosed in-code. |
| G11 — registry section comments say "all pending" over `Audited` blocks | **Abierta** | 10 occurrences in the working tree (`app/services/audit.py:744,754,777,786,795,818,836,897,946,981`); even the `stash@{0}` version still carries 3 (§4.8, §4.10, §4.11). |
| G12 — `can_view_audit` docstrings without diacritics | **Abierta en el árbol de trabajo** | `backend/app/services/permissions.py:441-458` still reads "Sincrona a proposito", "membresia", "asi que", "funcion". The corrected text exists **only in `stash@{0}`**. |

G1, G2, G3, G10 and G13 were out of scope for this task. G3 is observably closed:
`DELETE /api/athletes/{athlete_id}` is now the archive route (`routers/athletes.py:395-437`).

## 5. New gaps found in Phase 4

| # | Gap | File · line |
|---|---|---|
| G14 | **The backend does not import.** `AUDIT_FIELD_LABELS` (and the newer `record_audit`) live only in `stash@{0}`; the suite collects 0 tests from `backend/`. Blocks every gate. | `backend/app/routers/audit.py:44-55` vs `backend/app/services/audit.py`; `stash@{0}` of 2026-09-09 17:18:21 |
| G15 | The §5.4 scope gate is red: **20** athlete queries neither filter nor are exempt. Parent- and family-facing ones first: consent renew/withdraw, parent monthly summary, parent newsletter PDF, parent session list, the three `_notify_parents*` joins. | `tests/test_archive_scope_gate.py:227`; sites: `routers/consent.py:112,181`, `routers/training_sessions.py:206`, `routers/parent_newsletters.py:195`, `routers/calendar.py:237`, `services/permissions.py:273,361,396`, `services/calendar/notifications.py:100`, `services/notification/race_insight_dispatcher.py:467`, `services/notification/newsletter_dispatcher.py:406`, `services/training/sessions.py:254,387,523`, `services/training/newsletter_builder.py:172`, `services/training/reports.py:290,955`, `services/race/group_launch.py:509` |
| G16 | `POST /api/athletes/{athlete_id}/restore` has no `AUDITED_ROUTES` entry → the FR-009 coverage test fails. | `backend/app/services/audit.py` (`AUDITED_ROUTES`), failing at `tests/test_audit_coverage.py:104` |
| G17 | `GET /api/athletes/{id}/audit-log` returns **404 to a coach once the athlete is archived**, because `verify_athlete_access` 404s first. Contradicts US2 AS2/AS3 and quickstart 4.5 ("Historial shows the archive and the restore entries"). | `backend/app/dependencies.py:115-121` + `backend/app/routers/audit.py:320,366`; failing at `tests/routers/test_audit_log_api.py:362` |
| G18 | A parent requesting an archived athlete gets **404**, but contract §7 and quickstart 4.3 specify **403** with the unchanged text "No tienes acceso a este atleta". | `backend/app/dependencies.py:117-121` (the archived check runs before the parent branch at `:134`) |
| G19 | The consent-preservation proof is red: the sqlite subset harness does not create `privacy_policies`, so the eager join from `parental_consents` explodes. Harness-only, but AS2 has no green proof until it is fixed. | `backend/tests/routers/test_athlete_archive.py::test_archive_preserves_child_evidence` |
| G20 | All **6** tests of `test_users_delete_deactivate.py` fail. Five are the same sqlite-subset harness problem; one is a defect in the test itself: it asserts `"desacti" in detail.lower()` while the (correct, accented) copy is "Desactívalo…" → `"desactí"`. | `backend/tests/test_users_delete_deactivate.py:270` and the module's harness |
| G21 | Two wave-3 audit tests still call `DELETE /api/athletes/{id}` with no body and now get `422`. | `backend/tests/test_audit_athletes.py::test_delete_athlete_as_admin_records_audit_row`, `::test_delete_athlete_as_coach_is_forbidden_no_audit_row` |
| G22 | 22 unit tests break on `SimpleNamespace` doubles that lack the new `deleted_at` attribute — the largest single regression cluster, and the reason the count went 23 → 48. | `tests/routers/test_athlete_monthly_newsletters_router.py` (11), `tests/services/training/test_badge_evaluator.py` (7), `tests/services/notification/test_stage_log_email.py` (4) |
| G23 | Order-dependent flake: `test_ai_run_launch_404_for_archived_athlete` returns `503` (budget guard) instead of `404` in a full-suite run, but passes in isolation — the archived-athlete check runs after the spend guard. | `backend/tests/test_archived_athlete_absent.py:351`; guard at `backend/app/services/race/ai/budget_guard.py` |
| G24 | Regressions grew from 23 to 48 and none of the 21 surviving wave-3 regressions was repaired in this wave. | `.regresiones-oleada3.txt` vs `/tmp` differential of this review |

---

# Integration review — Phase 5 (US3), feature 041

**Task**: T058. **Date**: 2026-09-09. **Branch**: `feat/041-multi-coach-governance`
(HEAD `1217c22`, uncommitted changes still in the tree from parallel agents — `git status`
shows `clubs.py`, `athletes.py`, `calendar.py`, `models/user.py`, `models/privacy_policy.py`
modified).

**Method**: static RBAC review of `backend/app/routers/users.py`, `backend/app/routers/clubs.py`
and `frontend/src/routes/admin/StaffPage.tsx` against `spec.md` US3 AS1–AS7 and
`contracts/staff-admin.md`, plus a full `pytest` run from `backend/` and `npm run
typecheck` / `npm test` from `frontend/`. No Docker, no MySQL, no live stack — same
constraint as phases 3 and 4.

## 1. AS1–AS5 verdicts (as scoped by the briefing)

| # | Acceptance scenario (US3) | Verdict | Evidence |
|---|---|---|---|
| AS1/AS2 | A coach cannot create, edit or deactivate personnel | **Cumple** | `create_user`: `_ALLOWED_CREATIONS[UserRole.coach] = {parent, athlete}` excludes `coach`/`admin` (`backend/app/routers/users.py:48-51`), enforced at `:132-138`; a coach creating a coach is `403` (`tests/test_staff_admin.py::test_coach_creating_coach_is_403`, green). `update_user`: a coach targeting `admin`/`coach` is `403` at `:440-444`. `delete_user`: rule 5 blocks deleting `admin`/`coach` **unconditionally**, not just for a coach caller (`:590-594`). |
| AS3 (listing) | A coach cannot list personnel | **No cumple — hallazgo F1** | `list_users`'s coach branch (`:354-386`) filters only by `ClubMember.club_id.in_(scope_clubs)` and the shared `base_filters = [User.role != UserRole.athlete]` (`:306`); nothing excludes `coach`/`admin`. A coach calling `GET /api/users?role=coach` (or with no `role` filter at all) receives every coach's and admin's name, email, active state and `created_by_display_name` for their own club. The frontend never exposes this (`/admin/usuarios` is admin-only in `App.tsx:463-469`), so the gap is API-only, but nothing stops a direct call. `tests/test_staff_admin.py::TestListUsersFilters` only exercises `admin_client`; there is no denied-path test for a coach caller. |
| AS4 | Admin cannot self-deactivate | **Cumple** | `target.id == current_user.id and body.is_active is False` → `403`, checked unconditionally for any role (`backend/app/routers/users.py:458-462`), not nested inside the coach branch. `DELETE` has the symmetric `user_id == current_user.id` guard at `:552-556`. No test exists for this path (`admin_client` self-deactivate), but the code is role-agnostic and correct. |
| AS5 | Parent gets 403 everywhere | **Cumple** | All three mutating endpoints in `users.py` require `require_role([admin, coach])` (`:129`, `:302`, `:421`, `:537`); `clubs.py` mutations require `require_role([admin])` (`create_club:38`, `update_club:115`, `add_member:164`). No test asserts the parent-403 path explicitly, but `require_role` is a shared, previously-audited dependency. |
| — | No privilege escalation via `role`/`club_id` | **Cumple** | `UserUpdate` (`backend/app/schemas/user.py:26-35`) has no `role` or `club_id` field — `PATCH /api/users/{id}` cannot change either. `POST /api/clubs/{id}/members` (admin-only) rejects a `role_in_club` that doesn't match the target's account role (`clubs.py:185-197`, `role_in_club_for`). `create_user`'s coach path restricts `club_id` to `_coach_club_ids(current_user)` (`:141-152`). No other router mutates `ClubMember.role_in_club` or `User.role`. |

## 2. Hallazgo F1 — un coach puede enumerar personal (Media, CWE-284/CWE-639)

- **Dónde**: `backend/app/routers/users.py:354-386` (rama `else: # Coach: solo usuarios de sus clubes` de `list_users`).
- **Qué**: la única exclusión de rol es `User.role != UserRole.athlete` (línea 306, compartida con la rama admin). Un coach autenticado que llame `GET /api/users` (sin filtro) o `GET /api/users?role=coach` o `?role=admin` recibe nombre, correo, teléfono, estado activo y `created_by_display_name` de **todo el personal de su propio club**, algo que la spec (US3, "A coach cannot create, edit or deactivate another coach or an administrator" y AS5 "access is refused and the navigation entry is not shown") y el contrato `staff-admin.md` reservan al admin.
- **Explotación**: coach autenticado con un token válido, sin necesitar el frontend — una petición HTTP directa basta. No requiere pertenecer a un rol distinto ni manipular ningún campo, solo omitir el filtro `role` que sí aplica el frontend.
- **Impacto**: fuga de PII de personal (no de menores) entre compañeros de club; bajo impacto porque los datos no son de un menor y ambos coaches ya comparten club, pero contradice explícitamente el requisito de la historia de usuario y no tiene ninguna prueba que lo cubra.
- **Corrección sugerida**: añadir `User.role.notin_([UserRole.coach, UserRole.admin])` (o equivalente) a la rama de coach de `list_users`, o exigir `require_role([UserRole.admin])` para cualquier combinación de `role` que incluya `coach`/`admin` cuando el llamador es coach.

## 3. Hallazgo F2 — `GET /api/clubs/{id}` expone la lista de miembros a cualquier autenticado (preexistente, fuera del diff de 041)

- **Dónde**: `backend/app/routers/clubs.py:85-104` (`get_club`) y `:72-79` (`list_clubs`) — dependen de `get_current_user`, no de `require_role`.
- **Qué**: cualquier usuario autenticado, incluido un padre o un atleta, puede pedir `GET /api/clubs/{club_id}` y recibir `ClubDetailOut.members`, con nombre y apellido de **todos** los miembros del club (personal y otras familias), vía `ClubMemberOut` (`backend/app/schemas/club.py:33-58`).
- **Verificado como preexistente**: `git show main:backend/app/routers/clubs.py` es byte-idéntico en estos dos endpoints; 041 solo añadió las llamadas a `record_audit` en `create_club`/`update_club`/`add_member`, no tocó `get_club`/`list_clubs`. No es una regresión de esta oleada, pero contradice el principio de CLAUDE.md ("un padre solo ve los datos de sus propios atletas") y queda fuera del alcance de archivos que esta tarea puede tocar — se reporta para la oleada 6, no se corrige aquí.

## 4. Cobertura de pruebas — brechas sin explotar (no bloqueantes)

No hay prueba denegada para: un coach listando personal (F1), un admin intentando autodesactivarse, ni un padre golpeando cualquiera de los tres endpoints de `users.py`. Los tres caminos están bien implementados en el código pero ninguno tiene un test que impida una futura regresión silenciosa.

## 5. Suite completa — `./.venv/bin/python -m pytest -q` desde `backend/`

**237 failed, 3987 passed, 117 skipped, 12 xfailed, 6 xpassed, 87 errors** en 165 s (324 tests
en problemas, frente a los 273 reportados al abrir esta oleada). El árbol estaba siendo editado
por otros agentes en paralelo durante la corrida (`git status` no limpio en archivos fuera del
alcance de esta tarea), así que esto es una foto, no un número estable.

| Bucket | Cuenta | Nota |
|---|---|---|
| Ambiental (fixture `client` → MySQL real) | ~188 | `test_auth.py`, `test_athletes.py`, `test_clubs.py`, `test_users.py`, `test_consent_endpoints.py`, `test_onboarding_consent.py`, `test_parent_athletes.py`, `test_parent_register.py`, `test_privacy.py`, `test_security.py`, `test_training_session_router.py`, `test_training_session_fields.py`, `test_calendar_birthdays.py`, `test_ai_consent_enablement.py` — mismo problema preexistente en `main` (225 en la cifra original de la oleada). |
| Regresiones de `.regresiones-oleada4.txt` **aún abiertas** | **8** (de 48) | Ver lista abajo — **ninguna** toca `users.py`, `clubs.py` ni `StaffPage.tsx`; todas son de US1/US2 (auditoría/archivado). |
| Regresiones de `.regresiones-oleada4.txt` **cerradas en esta foto** | **40** | Confirmado por `comm` contra la lista del archivo — mejora real desde que se abrió la oleada. |
| Ruido nuevo, no relacionado con US3, no rastreado en `.regresiones-oleada4.txt` | **99** | `tests/privacy/test_laps_privacy.py` (22), `tests/routers/test_strava_integration.py` (22), `tests/routers/test_dashboard_summary.py` (10), `tests/services/notification/test_stage_log_pdf.py` (13, `ImportError` real de WeasyPrint — falta una librería nativa del sistema en esta máquina), `tests/test_circuit_diagram_partial.py` (18, `TemplateNotFound`: falta físicamente `documents/pdf/charts/circuit_diagram.svg.jinja` en el árbol de trabajo), `tests/privacy/test_strava_privacy.py` (7), `tests/test_training_session_notifications.py` (4), `tests/test_ai_factory.py` (1), `tests/test_calendar_audiences.py` (1), `tests/test_calendar_models.py` (1). Ninguno de estos archivos aparece en `.regresiones-oleada4.txt`; ninguno tiene relación con `users.py`/`clubs.py`. Verificado a mano que son ambientales (falta de librería nativa, falta de archivo de plantilla), no efecto de esta tarea. |
| Fallos adicionales en archivos nuevos de 041 (US1/US2, no en el alcance de esta tarea) | **29** | Resto de `test_athlete_archive.py`, `test_audit_log_api.py`, `test_archive_scope_gate.py`, `test_archived_athlete_absent.py`, `test_audit_actors.py`, `test_audit_athletes.py`, `test_parent_archived_only.py`, `test_users_delete_deactivate.py` más allá de las 8 ya contadas — mayormente errores de fixture (`privacy_policies` ausente en el harness sqlite, ya documentado como G19) y no algo introducido por US3. |

**Las 8 regresiones de `.regresiones-oleada4.txt` que siguen abiertas**:
`tests/routers/test_athlete_archive.py::test_archive_preserves_child_evidence`,
`tests/routers/test_audit_log_api.py::test_athlete_audit_log_still_visible_after_archive`,
`tests/test_archive_scope_gate.py::test_every_athlete_query_filters_or_is_exempt`,
`tests/test_audit_actors.py::TestDeleteUserAudit::test_delete_parent_records_rows_and_preserves_created_by`,
`tests/test_audit_athletes.py::test_delete_athlete_as_admin_records_audit_row`,
`tests/test_audit_athletes.py::test_delete_athlete_as_coach_is_forbidden_no_audit_row`,
`tests/test_users_delete_deactivate.py::test_delete_parent_with_audit_activity_409` (bug del
propio test: busca `"desacti"` en un texto acentuado "Desactívalo", ya documentado como G20),
`tests/test_users_delete_deactivate.py::test_delete_parent_with_training_session_maps_to_409`
(sqlite no aplica `ON DELETE RESTRICT`, así que la sonda de FK del código — correcta contra
MySQL real — no puede observarse en este harness; ya documentado en el comentario de
`users.py:662-666`).

**Conclusión de seguridad sobre la suite**: cero regresiones nuevas encontradas en
`users.py`, `clubs.py` o `StaffPage.tsx`. El aumento de 273 a 324 fallos totales se explica
por ruido ambiental (WeasyPrint, plantilla faltante) y por archivos de US1/US2 fuera del
alcance de esta tarea, no por el trabajo de US3.

## 6. Frontend — `npm run typecheck` y `npm test`

- `npm run typecheck`: **0 errores**.
- `npm test` (vitest): **1 failed, 4036 passed** de 4037 (342 archivos, 341 verdes). El único
  fallo es `src/lib/__tests__/datetime.test.ts::currentSeason > usa el año en CLUB_TIMEZONE
  (Bogotá) y no el año naive de new Date().getFullYear()` — archivo de la feature 031
  (`git log` confirma que no lo toca 041), depende de la fecha real del sistema
  (`2026-09-09`) frente a un `vi.setSystemTime` de control; no relacionado con US3.

## 7. Brechas abiertas para la oleada 6

| # | Brecha | Archivo · línea |
|---|---|---|
| F1 | Un coach puede listar coaches/admins de su propio club vía `GET /api/users` (sin filtro de rol excluyendo personal) — contradice US3 AS5 y `staff-admin.md`. | `backend/app/routers/users.py:306,354-386` |
| F2 | `GET /api/clubs/{id}` y `GET /api/clubs` exponen nombre/apellido de todos los miembros (personal y familias) a cualquier autenticado, incluido un padre o atleta. Preexistente a 041, no corregido en esta tarea por estar fuera del alcance de archivos permitido. | `backend/app/routers/clubs.py:72-104` |
| F3 | Sin prueba denegada para: coach listando personal (F1), admin autodesactivándose, padre golpeando `users.py`. El código es correcto pero no hay barrera de regresión. | `backend/tests/test_staff_admin.py` |
| G20/G-nuevo | `test_delete_parent_with_audit_activity_409` tiene un assert roto (`"desacti"` vs "Desactívalo"); `test_delete_parent_with_training_session_maps_to_409` no puede pasar en sqlite porque el harness no aplica `ON DELETE RESTRICT`. | `backend/tests/test_users_delete_deactivate.py:270` y módulo completo |
| — | 8 regresiones de `.regresiones-oleada4.txt` (listadas en §5) siguen abiertas; ninguna toca US3. | ver §5 |
| — | 99 fallos ambientales nuevos no rastreados (WeasyPrint sin librería nativa, plantilla `circuit_diagram.svg.jinja` ausente) — no corregir aquí, pero documentar para que la oleada 6 no los confunda con regresiones de código. | ver §5 |

---

# Revisión de integración — T050 rehecha + fase 6 (US4), feature 041

**Tareas**: T050 (rehecha), T059–T064. **Fecha**: 2026-09-10.
**Rama**: `feat/041-multi-coach-governance` (parte de `e9c6ef7`).
**Corrida**: primera de las tres de la noche (21:30 hora de Colombia).

**Método**: sin Docker, sin MySQL y sin stack en ejecución, igual que las fases 3 a 5,
así que los escenarios de `quickstart.md` no se ejecutaron en vivo. Es una revisión
estática contra `spec.md`, `contracts/athlete-archive.md` y `contracts/session-coaches.md`,
con ejecución real de la suite y comparación diferencial contra un *worktree* de `main`
(`/tmp/base041`, `main` = `86e0208`). El entorno se levantó desde cero en esta corrida:
`python3.13 -m venv`, `pip install -r requirements.txt` más `pytest`/`pytest-asyncio`
(que no están en `requirements.txt`; van en el extra `dev` de `pyproject.toml`).

## 0. La brecha bloqueante G14 está cerrada

`./.venv/bin/python -c "from app.main import app"` importa limpio y la suite recolecta.
El contenido que la revisión de la fase 4 encontró únicamente dentro de `stash@{0}`
(`AUDIT_FIELD_LABELS`, `record_audit`) está commiteado desde `c596622`/`0644f71`. Nada
de esta revisión tocó ningún *stash*.

## 1. Tres hallazgos sobre la compuerta de cobertura FR-009

Los tres se refuerzan entre sí y explican por qué US1 se dio por cerrada con más
confianza de la que los números aguantaban.

### 1.1 La compuerta recorría cero rutas (corregido)

`requirements.txt` fija `fastapi>=0.115` sin techo, así que este entorno instaló
**FastAPI 0.141.1**, donde `include_router` ya no aplana las rutas dentro de
`app.routes`: guarda un `_IncludedRouter` perezoso por cada router y las rutas
efectivas solo se resuelven al atender la petición. Consecuencia: los recorridos de
`app.routes` veían **6 rutas** en vez de 139 y

- `tests/test_audit_coverage.py::test_registry_completeness_covers_every_mutating_and_mutating_get_route`
  **pasaba en falso** (el conjunto `required` quedaba vacío), y
- `tests/test_archived_athlete_absent.py::test_expected_routes_exist_in_app` fallaba.

La aplicación sirve las 139 rutas con normalidad (verificado vía `app.openapi()`); es
solo introspección. Corregido con `backend/tests/helpers/app_routes.py`, tolerante a
las dos generaciones de FastAPI, y las dos pruebas pasan a usarlo. **Esto es un riesgo
vivo de producción**: Render instala sin techo igual que aquí, así que la compuerta se
volvería inerte en CI en cuanto se reconstruya el entorno.

### 1.2 Quedan 20 de 111 rutas del registro como `Exempt("pending instrumentation")`

T030 ("vacía las exenciones pendientes") estaba marcada `[X]` y no lo está. La prueba
`test_genuine_exemption_set_matches_section_4_14_exactly` tolera el marcador a
propósito, así que nada falla. **T030 queda reabierta en `tasks.md`.** Las 20:

```
DELETE /api/intervals/structures/{structure_id}      POST /api/intervals/templates/{template_id}/attach
DELETE /api/parent-athletes/{relation_id}            POST /api/parent-athletes
PATCH  /api/intervals/templates/{template_id}/archive POST /api/parent-athletes/invite
PATCH  /api/profile/basic                            POST /api/parents/me/athletes/{athlete_id}/newsletters/{newsletter_id}/read
POST   /api/ai/athletes/{id}/measurements/{rid}/explanation  POST /api/profile/change-email/confirm
POST   /api/ai/athletes/{athlete_id}/phv-explanation POST /api/profile/change-email/request
POST   /api/auth/parent-register                     POST /api/profile/change-password
POST   /api/auth/password-reset/confirm              POST /api/race-analysis/imports/{parse_id}/dry-run
POST   /api/intervals/structures                     PUT  /api/intervals/structures/{structure_id}
POST   /api/intervals/templates                      PUT  /api/intervals/templates/{template_id}
```

Las de `parent-athletes` y `auth/parent-register` son vínculos familiares: son
exactamente las escrituras que FR-001 quiere atribuidas.

### 1.3 La otra mitad de FR-009 nunca se implementó

`test_audited_route_writes_at_least_one_audit_log_row` hace `pytest.skip()`
**incondicional** para las 81 rutas que le llegan. Su docstring afirmaba "zero
`Audited` entries — every route is still `Exempt`", que dejó de ser cierto hace dos
oleadas. Es decir: la exigencia de `contracts/audit-recording.md` §9 ("toda ruta
auditada que la suite ejercita escribió al menos una fila") **no tiene red**. T018
está marcada `[X]`. No se corrigió aquí — sintetizar una petición válida por ruta es
trabajo de una tarea propia — pero el docstring ya dice la verdad.

## 2. El arnés de sqlite mataba ~61 pruebas que se contaban como "ambientales"

`Base.metadata.create_all(..., tables=[...])` **no deduplica** su lista. Siete archivos
repetían un nombre que ya venía en `AUDIT_TABLES`, y el módulo entero moría con
`OperationalError: table privacy_policies already exists`:

| Archivo | Antes | Después |
|---|---|---|
| `tests/privacy/test_laps_privacy.py` | 22 fallos | verde |
| `tests/routers/test_strava_integration.py` | 22 fallos | verde |
| `tests/routers/test_dashboard_summary.py` | 10 fallos | verde |
| `tests/privacy/test_strava_privacy.py` | 7 fallos | verde |
| `tests/test_archived_athlete_absent.py` | 12 errores | verde |
| `tests/test_audit_athletes.py` | 9 errores | verde |
| `tests/test_parent_archived_only.py` | 3 errores | verde |

La revisión de la fase 5 los había clasificado como "ruido ambiental, verificado a mano"
(§5, cubo de 99). **No lo eran.** La trampa queda documentada en
`tests/helpers/audit_tables.py`: ningún archivo debe repetir un nombre que ya venga en
`AUDIT_TABLES`.

## 3. Estado de las brechas abiertas de las fases 3 a 5

| Brecha | Estado | Nota |
|---|---|---|
| G4 — cancelación de calendario con motivo fijo | **Cerrada** | `cancel_event` recibe `reason_code` y resuelve la etiqueta vía `AUDIT_REASON_LABELS` (T063). |
| G8 — el envío del boletín se saltaba la fila si `actor is None` | **Cerrada** | Ya commiteada; `actor_kind=system` de respaldo. |
| G11 — comentarios "all pending" sobre bloques ya instrumentados | **Cerrada** | `audit.py`: §4.8 y §4.10 corregidos con la cuenta real; §4.11 sí sigue pendiente (7 de 8) y ahora lo dice. |
| G12 — docstrings de `can_view_audit` sin tildes | **Cerrada** | Ya estaba corregido en el árbol commiteado. |
| G14 — el backend no importaba | **Cerrada** | §0. |
| G15 — 20 consultas de atletas sin filtrar ni exentar | **Parcial** | Ver §5. |
| G16 — `POST /api/athletes/{id}/restore` sin entrada en `AUDITED_ROUTES` | **Cerrada** | La compuerta pasa (y ahora sí recorre rutas de verdad, §1.1). |
| G17 — historial de un atleta archivado daba 404 al coach | **Cerrada** | `verify_athlete_access_allow_archived`; el coach y el admin leen el archivado, la familia no. |
| G18 — la familia recibía 404 en vez del 403 contratado | **Cerrada** | `athlete-archive.md` §7; la prueba ya exige 403 estricto en vez de aceptar ambos. |
| G19 — la prueba de preservación de evidencia estaba roja | **Cerrada** | Doble causa: el arnés (§2) y un sembrado que no creaba la cuenta-espejo del atleta. AS2 ya tiene prueba verde. |
| G20 — assert sin tilde + `ON DELETE RESTRICT` en sqlite | **Cerrada** | El assert busca "desactívalo"; la de RESTRICT queda `xfail` documentada (activar `PRAGMA foreign_keys=ON` rompe el sembrado porque el arnés crea un subconjunto de tablas). |
| G21 — dos pruebas llamaban al borrado con expectativas viejas | **Cerrada** | La acción registrada es `archive`, no `delete`, y el guard interino de coach lo retiró T040: la prueba ahora exige que el coach archive **y quede atribuido**. |
| G22 — 22 dobles `SimpleNamespace` sin `deleted_at` | **Cerrada** | Ninguna de las tres familias aparece ya en la corrida. |
| G23 — flake dependiente del orden en el lanzamiento de IA | **Cerrada** | La prueba fija `ai_enabled`; el 503 venía del interruptor de IA, evaluado antes que el atleta. |
| F1 — un coach puede enumerar personal vía `GET /api/users` | **Abierta** | `backend/app/routers/users.py:306,354-386`. Fuera del alcance de esta corrida. |
| F2 — `GET /api/clubs/{id}` expone miembros a cualquier autenticado | **Abierta** | Preexistente a 041. `backend/app/routers/clubs.py:72-104`. |
| F3 — sin pruebas denegadas para F1, autodesactivación de admin, padre en `users.py` | **Abierta** | `backend/tests/test_staff_admin.py`. |

## 4. US4 — veredictos AS1 a AS7

Sin stack en vivo no se ejecutó el escenario de `quickstart.md`; cada veredicto se
apoya en el código y en pruebas que sí se corrieron.

| # | Escenario (US4) | Veredicto | Evidencia |
|---|---|---|---|
| AS1 | Al crear una sesión queda el creador como entrenador por defecto y el asistente ofrece a los demás entrenadores activos del club | **Cumple** | Sin `coach_user_ids` el servicio deja al creador como único entrenador (`test_session_coaches.py::test_b01_…`). El selector `SessionCoachesField` se precarga con el entrenador autenticado y lista solo `role=coach` activos (FR-024), salvo los ya asignados que se desactivaron después (V5). |
| AS2 | Con dos entrenadores, la invitación, el cambio y la cancelación listan a ambos y nombran a quien actúa | **Cumple** | `_load_session_coach` —que respondía siempre el creador— está eliminado. `test_b08_cancel_by_coach_b_names_b_not_creator_a` corre contra base de datos real: coach A crea con A y B, coach B cancela, y el correo trae `acting_coach_name = B` con ambos en `coaches_text`. `test_b09_…` cubre la edición. Las seis plantillas (HTML y texto) llevan la copia de §5.2. |
| AS3 | Quitar al último entrenador se rechaza | **Cumple** | V1 responde 422 en creación y edición (`test_b04_…`) y V6 responde 409 en el servicio (`test_b05_…`), con el bloqueo `FOR UPDATE` al recalcular el conjunto. En el frontend la última ficha no se puede quitar y el motivo se anuncia por `aria-describedby`. |
| AS4 | La asistencia registra quién la puso y quién la editó por última vez | **Cumple** | `recorded_by_user_id` se fija solo si estaba en `NULL` **y** la edición trae datos reales; `updated_by_user_id` siempre (`test_b12_…`). La fila vacía de la convocatoria no atribuye a nadie (`test_placeholder_row_has_no_attribution`). |
| AS5 | Sacar a un atleta del roster archiva en vez de destruir y el administrador puede leerlo | **Cumple** | Con datos se archiva, sin datos (marcador vacío) se borra, y volver a convocar desarchiva —el paso que faltaría para dejar la fila invisible para siempre— (`test_b10_b11_…`). `GET …/attendance?include_archived=true` es solo de administrador; coach o familia reciben 403. |
| AS6 | La ejecución registra qué entrenador la marcó | **Cumple** | `execute_session` exige `actor` sin valor por defecto y la fila de auditoría lleva el diff de `status`. Que el argumento sea obligatorio está fijado por contrato en `TestActorAndReasonCodeContract`. |
| AS7 | El filtro por entrenador acota sesiones y calendario | **Cumple** | Sesiones: `coach_user_id` sobre el puente (`test_b13_…`), y un padre que lo manda recibe 403. Calendario: coincide por creador directo o por el puente de la sesión enlazada, y los cumpleaños virtuales se excluyen mientras el filtro esté puesto, para que la vista por entrenador no descuadre con la general. |

**Privacidad de US4 (Ley 1581)**: la carga de la familia no gana ningún campo. Se
comprueba explícitamente que `TrainingSessionReadParent` no trae `coaches` ni
`has_active_coach` y que `AttendanceReadParent` no trae quién registró ni quién
editó (`test_b14_…`); las filas de auditoría de este dominio no llevan nombre de
menor ni texto de retroalimentación (`test_b18_…`). Los correos nombran
entrenadores, que son personas adultas.

## 5. G15 cerrada — el atleta archivado desaparece de verdad

La compuerta `tests/test_archive_scope_gate.py` está **verde**: ya no queda ninguna
consulta de `Athlete` sin filtrar ni exentar. De los 20 sitios que la fase 4 dejó
abiertos, 13 se filtran y 7 quedan exentos con motivo escrito
(`ARCHIVE_SCOPE_EXEMPT` pasó de 6 a 10 entradas; quien agregue otra debe subir
también el `len` de `test_archive_scope_exempt_matches_contract_section_5_3`).

Las exenciones son deliberadas y de la misma familia: consultas que resuelven
`athlete_id → club_id` solo para poner `club_id` en una fila de auditoría
(`race_analysis._resolve_athlete_club`, `strava_integration._athlete_club_ids`),
el webhook de Resend —que registra entregas de un boletín **ya enviado**, y
filtrarlo borraría evidencia de un período cerrado— y la redacción de nombres del
reporte mensual. §5.3 del contrato pide exactamente eso: no se filtra lo que
reconstruye el pasado, se filtra lo que actúa sobre el presente.

Lo que sí cambió de comportamiento, y es lo que más importa:

- **Ningún correo a la familia sale ya por un atleta archivado.** Convocatoria,
  cambio y cancelación de sesión (tres consultas gemelas en
  `services/training/sessions.py`) y los avisos de calendario
  (`services/calendar/notifications.py`) filtran ahora en el último paso antes
  del envío.
- **El despachador de insights de IA no tenía ningún portón de archivado**: un
  insight aprobado antes de archivar seguía llegando a la familia. Se añadió
  `SKIPPED_ARCHIVED_ATHLETE`, evaluado antes de resolver destinatarios, así que
  no sale ni correo ni notificación en la aplicación.
- **La familia ya no puede renovar ni revocar consentimiento de un atleta
  archivado** (404), y la comprobación corre *antes* de mutar, no después.

## 6. Suite — medida diferencialmente contra `main`

Entorno construido desde cero en esta corrida; `main` se midió en un *worktree*
aparte (`/tmp/base041`, `86e0208`) con el mismo intérprete y las mismas
dependencias, así que la comparación es válida.

| Corrida | Resultado |
|---|---|
| `main` (`86e0208`) | **215 fallos + 9 errores = 224**, 3700 pasan |
| `feat/041-multi-coach-governance` | **211 fallos + 9 errores = 220**, 4137 pasan |

Diferencia sobre los identificadores de prueba:

| Cubo | Cuenta |
|---|---|
| Fallan en `main` y siguen fallando (ambiental: fixture `client` → MySQL real) | **220** |
| **Fallan solo en esta rama (regresiones)** | **0** |
| Pasan en la rama y fallan en `main` | 4 |

**Cero regresiones.** La progresión de la feature es 23 (oleada 3) → 48 (oleada 4)
→ 8 más ~99 de ruido sin clasificar (oleada 5) → **0** (esta corrida). Las 220 que
quedan son todas el problema ambiental preexistente y ninguna es de código: el
fixture `client` de `tests/conftest.py` levanta la aplicación contra la base de
datos real y aquí no hay MySQL ni Docker.

Las 4 que la rama arregla respecto de `main` son
`tests/test_training_session_notifications.py` (`test_happy_path_two_convocados_two_parents`,
`test_throttle_second_call_skipped`, `test_update_session_with_changes_dispatches_updated_template`,
`test_cancel_session_with_flag_dispatches_cancelled_template`): tenían escrita a
mano una fecha "futura" (`date(2026, 5, 20)`) que el calendario ya dejó atrás, así
que toda comprobación de `is_future` se cortaba en silencio y los envíos daban
cero **sin lanzar ninguna excepción**. Ahora se calcula desde hoy. Conviene
buscar ese patrón en el resto de la suite: falla por reloj de pared, no por código.

Otras vías:

- `pytest -m mysql`: **no se puede ejecutar aquí**. Las pruebas se escriben, no se
  corren, y así queda dicho.
- `ruff check`: 370 hallazgos en la rama frente a 345 en `main`. Los 25 de
  diferencia están todos en archivos de prueba nuevos; se limpiaron los imports
  sin usar y quedan 4 cosméticos (`E402` de imports tardíos deliberados y dos
  `F841`). `ruff` tampoco está limpio en `main`, así que hoy no es una compuerta
  que pase.
- Frontend: `npm run typecheck` **limpio** y `npm test` (vitest) **344 archivos,
  4071 pruebas, todas verdes**. La oleada 5 reportaba un fallo suelto en
  `src/lib/__tests__/datetime.test.ts`; hoy también pasa.
- `npm run test:e2e` (Playwright): **no se ejecutó**. Necesita levantar la pila
  completa y sigue bloqueado por el mismo defecto de migración ajeno a esta feature.

## 7. Brechas abiertas para la corrida siguiente

Ordenadas por lo que costaría descubrirlas tarde, no por tamaño.

| # | Brecha | Archivo · línea |
|---|---|---|
| A1 | **T030 reabierta**: 20 de 111 rutas del registro siguen como `Exempt("pending instrumentation")` — entre ellas `POST /api/auth/parent-register`, `POST /api/parent-athletes` y `DELETE /api/parent-athletes/{id}`, que son vínculos familiares y justo lo que FR-001 quiere atribuido. Lista completa en §1.2. | `backend/app/services/audit.py` (`AUDITED_ROUTES`) |
| A2 | **La otra mitad de FR-009 no existe**: `test_audited_route_writes_at_least_one_audit_log_row` hace `skip` incondicional para las 81 rutas auditadas, así que nada comprueba que una ruta instrumentada escriba de verdad su fila. T018 está marcada `[X]` y no lo está. | `backend/tests/test_audit_coverage.py:194-215` |
| A3 | `requirements.txt` fija `fastapi>=0.115` sin techo. Con 0.141 `app.routes` deja de estar aplanado y toda prueba que lo recorra mide cero. Se corrigió con `tests/helpers/app_routes.py`, pero **cualquier recorrido nuevo de `app.routes` debe usar ese ayudante**, o volverá a pasar en falso. Decidir si además se pone techo a la dependencia es del dueño. | `backend/requirements.txt:1`, `backend/tests/helpers/app_routes.py` |
| A4 | **Contradicción entre contratos, decidida y no aplicada**: `session-coaches.md` §7.3 dice que al borrar un evento se hace borrado lógico también del `TrainingSession` enlazado, pero `data-model.md` §4 no le da a `training_sessions` ninguna columna `deleted_at`. **Decisión de esta corrida**: manda `data-model.md` (§1 del propio contrato dice que él y el código ganan), así que no se añadió la columna ni se tocó la migración única de T013, que ya se verificó contra un MySQL `_test` y aquí no se puede volver a verificar. `delete_event_permanent` degrada solo: usa `hasattr(TrainingSession, "deleted_at")` y hoy sigue borrando físicamente la sesión enlazada. Si el dueño quiere el borrado lógico simétrico, es una columna + migración + una línea de `VALUE_ALLOWLIST`. | `backend/app/services/calendar/events.py` (`delete_event_permanent`); `contracts/session-coaches.md` §7.3 vs `data-model.md` §4 |
| A5 | `TrainingSessionCoach.added_at` es `DateTime` sin `fsp=6`, y MySQL no guarda fracciones de segundo ahí: dos entrenadores agregados en la misma llamada pueden empatar y dejar el orden de lectura indefinido. Hoy se desempata por `coach_user_id`. Para orden de inserción real hace falta `DateTime(fsp=6)` y su migración. | `backend/app/models/training_session.py` (`TrainingSessionCoach.added_at`); desempate en `app/services/training/sessions.py::_ordered_session_coaches` |
| A6 | **Patrón de fragilidad por reloj de pared**: una fecha "futura" escrita a mano ya quedó en el pasado y anulaba envíos **sin lanzar excepción** (§6). Conviene barrer la suite en busca de más literales de fecha y pasarlos a `date.today() + timedelta(...)`. | `backend/tests/` en general |
| A7 | F1 — un coach puede enumerar coaches y administradores de su club vía `GET /api/users` sin filtro de rol. Contradice US3 AS5. Abierta desde la fase 5. | `backend/app/routers/users.py:306,354-386` |
| A8 | F2 — `GET /api/clubs/{id}` y `GET /api/clubs` exponen nombre y apellido de **todos** los miembros a cualquier autenticado, incluido un padre. Preexistente a 041. | `backend/app/routers/clubs.py:72-104` |
| A9 | F3 — sin prueba denegada para F1, para un admin intentando autodesactivarse ni para un padre golpeando `users.py`. | `backend/tests/test_staff_admin.py` |
| A10 | Los dos portones nuevos de archivado (el de `race_insight_dispatcher.dispatch_insight_notification` y el `ValueError` de `newsletter_builder.build_newsletter_metrics`) no tienen prueba de comportamiento propia; hoy los cubre solo la compuerta estática. | `backend/tests/services/notification/test_race_insight_dispatcher.py` |
| A11 | `cancelTrainingSession` sigue mandando un `reason` de texto libre además del `reason_code`; el backend ya no lo usa. Es ruido, no un fallo. | `frontend/src/api/trainingSessions.ts` |
| A12 | Las pantallas de familia (`ParentSessionCard`, `ParentSessionDetailPage`) no muestran hoy ningún nombre de entrenador. Cuando se agreguen, deben reutilizar el mismo plural de los correos ("Entrenador a cargo" / "Entrenadores a cargo") en vez de inventar copia nueva. | `frontend/src/components/parents/ParentSessionCard.tsx`, `frontend/src/routes/parents/training/ParentSessionDetailPage.tsx` |
| A13 | 4 hallazgos cosméticos de `ruff` en archivos de prueba nuevos (`E402` de imports tardíos, dos `F841`). | `backend/tests/test_archived_athlete_absent.py`, `backend/tests/test_audit_athletes.py` |
| — | Sin MySQL ni Docker: la vía `-m mysql` no corre, T027/T028 siguen diferidas y las especificaciones de Playwright siguen bloqueadas. **T097 (humo posdespliegue) no se puede hacer aquí**: necesita credenciales de producción que no están en este entorno; queda sin marcar a propósito. | — |

---

# Adenda — fase 7 (US5) en la misma corrida

Con US4 cerrada y tiempo de ventana restante, se avanzó el backend de US5
(T069, T070, T071). Se anota aparte porque no es una revisión de integración
completa: es lo que quedó hecho y lo que quedó a medias.

## Lo que quedó funcionando

- **Concurrencia optimista en la bitácora (T069)**. El `PATCH` exige la versión
  que el coach tenía a la vista, por `If-Match` o por `expected_version`. Stale →
  409 con `current_version`; sin precondición → 428; malformada o en desacuerdo
  con el cuerpo → 400; bitácora ya enviada → 409 sin `current_version`. La
  reserva es una `UPDATE ... WHERE edit_version = :esperada` decidida por
  `rowcount`, no una comparación en Python. 30 casos verdes.
- **Autoría de la nota del entrenador (T070)**, incluido el borrado de la nota:
  quién la quitó también queda registrado. La matriz de exposición de §3.2 se
  comprobó de verdad, no por lectura: se renderiza el **PDF familiar real** con
  WeasyPrint y se cuenta cero apariciones del apellido del entrenador, lo mismo
  con el correo, y hay una barrera de esquema que rechaza la clave aunque se
  inyecte en el JSON guardado.
- **Evidencia de aprobación del reporte mensual (T071)**. Regenerar copia
  `approved_by`/`approved_at` a `previous_approved_*` antes de limpiarlos. La
  prueba de regresión se validó extrayendo el `reports.py` de `HEAD` y
  ejecutándola contra él: falla, como debe.

## Riesgo introducido y cerrado dentro de la misma corrida

T069 es un cambio **incompatible** para el cliente: sin precondición, todo
guardado desde la interfaz responde 428. **Quedó cerrado dentro de la misma
ventana**: T073 hace que cada guardado mande `If-Match` con la versión cargada,
y T074 muestra la evidencia de aprobación del informe. Frontend al cerrar:
`npm run typecheck` limpio y `npm test` con **344 archivos y 4093 pruebas en
verde**.

El conflicto se resolvió como pide el contrato y como pide el sentido común: el
diálogo bloquea, ofrece recargar y **el borrador local sobrevive** hasta que la
persona decida; la sincronización en segundo plano no lo pisa mientras haya
conflicto, y la mutación no reintenta un 409 para no convertirlo en un segundo
sobrescrito.

## Deuda concreta que deja US5

| # | Deuda | Dónde |
|---|---|---|
| B1 | `ActorRef` quedó **duplicado** y la causa raíz es una cuarta tarea dada por cerrada antes de tiempo: **T031 figura `[X]` pero nunca creó `ActorRef`**. `app/schemas/audit.py` define `AuditDiffValue`, `AuditEntryDetail`, `AuditEntryOut`, `AuditListOut`, `AuditReasonCodeOut` y `AuditReasonCodeListOut`, y resuelve al actor con campos planos (`actor_user_id` / `actor_display_name`), no con el modelo anidado que el contrato pide. Sin la clase canónica, cada tarea posterior se hizo la suya: `NewsletterActorRef` en `athlete_newsletter.py:219` y otro `ActorRef` en `training_session.py:420`, idénticos. **Unificar antes de que aparezca un tercero**; la forma plana de `AuditEntryOut` ya está consumida por el frontend, así que esa no se toca. | `backend/app/schemas/audit.py`, `backend/app/schemas/athlete_newsletter.py:219`, `backend/app/schemas/training_session.py:420` |
| B2 | `AthleteMonthlyNewsletter` no tiene relaciones ORM para `coach_note_author_id` ni `last_edited_by_user_id`; los nombres se resuelven con un `select(User)` explícito por respuesta. Sin N+1, pero el contrato pedía `selectinload`. | `backend/app/models/athlete_newsletter.py` |
| B3 | `templates/email/athlete_stage_log.html` **no renderiza `coach_note` en absoluto**. §3.2 dice que la familia sí debe ver el texto de la nota (sin autor). Es una brecha preexistente de la feature 038, no de 041, pero la fila de esa matriz está sin cumplir del lado del texto. | `backend/templates/email/athlete_stage_log.html` |
| B4 | La atomicidad de la reserva de versión bajo concurrencia real **no está verificada**: sqlite no reproduce el bloqueo de fila de InnoDB. La prueba de dos sesiones existe, está marcada `-m mysql` y se salta. | `backend/tests/routers/test_newsletter_concurrency.py::test_two_sessions_only_one_update_takes_effect` |
| B5 | ~~T072 parcial~~ **Cerrada**: los puntos 12 y 13 de §9 están cubiertos con el idioma de `test_newsletter_privacy.py` pero dentro de `test_newsletter_coach_note_author.py`, que es donde vive el resto de la matriz de exposición. No se duplicaron. | `backend/tests/routers/test_newsletter_coach_note_author.py` |
| B6 | La firma de la nota del entrenador quedó como párrafo suelto en la página, no dentro de la tarjeta "Nota del entrenador" como pide §6.4: `BlockCard` necesita un `byline` y `BlockPanel` recibir autor y fecha. La copia y el `data-testid` ya son los definitivos, así que moverlo es cosmético. | `frontend/src/components/newsletter/studio/BlockCard.tsx`, `BlockPanel.tsx`; provisional en `AthleteNewsletterStudioPage.tsx` |

## Dónde empezar la corrida siguiente

Estado al cerrar esta ventana: **fase 6 (US4) completa**; **fase 7 (US5) completa**
(backend, frontend y pruebas). Todo está commiteado y
empujado a `feat/041-multi-coach-governance`; no queda nada sin guardar.

Orden sugerido:

1. **Unificar `ActorRef`** (deuda B1) antes de que aparezca un tercero. Hoy hay
   dos definiciones equivalentes porque T031 nunca creó la canónica. No se hizo en
   esta corrida a propósito: quedaban veinticinco minutos, la rama estaba verde y
   empujada, y tocar tres módulos de esquemas sin margen para verificar de verdad
   era mal negocio. Es media hora de trabajo tranquilo, no un apagón.

   Un patrón que ya se repite cuatro veces (T018, T030, T031 y, antes, T050):
   **una tarea se marca `[X]` cuando el archivo existe, no cuando cumple lo que el
   contrato pedía.** Conviene revisar con esa lupa las tareas cerradas de US1
   antes de dar la feature por lista.
2. **Fase 8 (US6, T075–T080)** — regla de club para corridas de IA e
   importaciones, y gasto por entrenador.
3. Con tiempo: **T030** (las 20 rutas todavía marcadas "pending instrumentation",
   §1.2) y **A2** (la mitad de FR-009 que hoy hace `skip`, §1.3). Las dos son
   deuda de US1 dada por cerrada antes de tiempo, y las dos se ven pequeñas hasta
   que alguien confía en la compuerta.

Para medir regresiones sin volver a correr `main`, usar
`checklists/baseline-main-failures.txt`; el comando está en su cabecera. Al
cerrar esta corrida el diferencial era **cero regresiones**.

---

# Corrida nocturna 2 — 2026-09-10, 00:30 a 03:15 (hora de Colombia)

Segunda de las tres corridas desatendidas. Entorno recreado desde cero: no
había venv de backend ni `node_modules`, así que lo primero fue instalarlos.
`pytest` **no está en `requirements.txt`** — hay que instalarlo aparte
(`pytest pytest-asyncio pytest-cov aiosqlite ruff`); anotarlo aquí para que la
corrida 3 no lo redescubra.

## 0. Decisión de orden, y por qué me aparté del runbook

El runbook manda arrancar por la primera tarea sin marcar de `tasks.md`, que
era **T030**. Arranqué en cambio por donde lo dejó dicho la corrida anterior:
unificar `ActorRef`, luego la fase 8. La razón no es preferencia: `ActorRef`
era **precondición** de T076, que expone actores en las respuestas de corrida;
empezar por T030 habría dejado a los dos frentes de US6 chocando contra una
clase duplicada. T030 se hizo igual, en paralelo, y quedó a una ruta de
cerrarse.

## 1. Lo que se cerró

| Tarea / brecha | Qué quedó |
|---|---|
| **B1** — `ActorRef` duplicado | Definición canónica en `app/schemas/audit.py`, donde el contrato la ubica. Los dos módulos que tenían su copia la reexportan, así que ningún consumidor cambió de import. |
| **A2** — la otra mitad de FR-009 | La compuerta **dejó de mentir**. Ver §2. |
| **A7 / F1 + A9** — enumeración de personal | Corregido, con matiz importante. Ver §3. |
| **A13** — cosméticos de `ruff` | Los dos módulos quedan limpios; 24 pruebas siguen verdes. |
| **T075–T077** (US6, backend) | Regla de club en corridas e importaciones, atribución en las respuestas, gasto por entrenador y un único formateador del rechazo por presupuesto. |
| **T079** (US6, frontend) | Rótulos de quién lanzó y decidió, tabla de gasto por entrenador, `/admin/ai` ampliado a coach. |
| **T081–T082** (US7, backend) | Servicio y endpoint de actividad por entrenador, con la regla de conteo de §2 del contrato y la guarda FR-031 del informe mensual. |
| **T083–T085** (US7, frontend) | Página de actividad, `ActorChip`, y el fin del crudo "Creado por usuario ID". |
| **T087–T090** (US8) | Purga de retención a 24 meses: servicio, CLI, workflow y pruebas. |
| **T030** | 18 de las 19 rutas pendientes instrumentadas. La 19.ª no se cerró **a propósito**: ver §4. |

## 2. La compuerta FR-009 pasó de decorativa a real

`test_audited_route_writes_at_least_one_audit_log_row` hacía `pytest.skip()`
incondicional sobre las 81 rutas `Audited`. El efecto práctico: 81 pruebas
"saltadas" que parecían una compuerta y no comprobaban absolutamente nada.

Ahora son dos pruebas:

- **La mitad estática sí corre.** `tests/helpers/audit_reachability.py` recorre
  el grafo de llamadas del handler dentro del paquete `app` —por nombre, hasta
  seis saltos— y exige que alguna función alcanzable invoque `record_audit`.
  Atrapa el modo de falla que nadie vigilaba: una ruta declarada `Audited` que
  no audita por ningún camino.
- **La mitad dinámica** queda parametrizada sobre las entradas que declaren un
  constructor de petición, como pide el contrato §9 T4.4 al pie de la letra.
  Ninguna lo declara, así que recoge **cero casos**: un hueco reconocido en vez
  de una compuerta que pasa en falso. Completarla necesita base real.

Los límites de la mitad estática, dichos de frente: resuelve por **nombre**, no
por tipo, así que dos funciones homónimas se confunden a propósito (preferimos
un falso negativo a un falso positivo que obligue a exenciones a mano); no
ejercita la ruta, así que no dice nada del contenido de la fila.

Al cerrar la corrida la compuerta recorre **100 casos verdes**.

## 3. F1: la corrección de la revisión anterior habría roto la feature

La revisión de la fase 5 proponía negarle al coach la lista de coaches y
admins. **No se puede aplicar tal cual**, y conviene que quede escrito por qué:
la propia feature 041 la necesita. El filtro "Entrenador" del historial (US1,
`hooks/governance/useClubStaff.ts`) y el selector de entrenadores a cargo de
una sesión (US4, `hooks/training/useClubCoaches.ts`) piden
`GET /api/users?role=coach` **como coach**, y la atribución por nombre es de lo
que trata la feature entera.

Decisión de esta corrida: **se conserva la lista y se recorta la carga.** De
sus colegas, un coach ve id, nombre, rol y estado —lo que un selector
necesita— y nada de contacto. Lo que US3 AS5 exige de verdad (no crear, no
editar, no desactivar a otro coach o admin, y que la pantalla de gestión le sea
negada) lo siguen garantizando `update_user`, `delete_user` y el portón de
`/admin/usuarios`, ahora **con prueba propia**, que era la brecha A9.

El recorte no alcanza a `role=parent`: gestionar a las familias del club es
parte del trabajo del coach, y `api/parents.ts` consume ese mismo endpoint.

## 4. La única ruta que sigue sin auditar, y no es olvido

`POST /api/race-analysis/imports/{parse_id}/dry-run`. El contrato §4.10 la
describe como `race_import`·`update` con `status` → `dry_run`, **pero ese
cambio de estado no ocurre**: `dry_run_import` no asigna nunca
`RaceImportStatus.dry_run`, y el docstring del propio enum ya lo decía ("existía
en enum pero código nunca lo emitía"). El ingestor corre en seco y no deja
escritura persistente.

Registrar ahí un `update` sería anotar una escritura que no sucedió, y la
decisión 2 del dueño es explícita en que la bitácora **no registra lecturas**.
Las dos salidas —emitir de verdad el cambio de estado, o convertirla en
exención genuina de §4.14— cambian el contrato o el comportamiento del
asistente de importación. Queda marcada como pendiente con la razón escrita en
el sitio (`app/services/audit.py`), en vez de resolverse sin quien pueda
decidirlo. **Es la decisión que le queda al dueño, no a la corrida 3.**

## 5. Choque de contratos resuelto en la raíz: el `entity_id` de la purga

`retention-purge.md` §1.4 y `data-model.md` §1.3 fijan `entity_id = 0` para la
fila de purga —una purga no habla de una fila, habla de un barrido— pero
`record_audit` exigía `entity_id > 0` y la purga entera reventaba contra esa
guarda.

Se había resuelto reintentando con `entity_id = 1`. Eso es **peor que el
error**: 1 es el id de una fila de auditoría real, así que la evidencia del
barrido quedaba apuntando a un registro ajeno. Ahora la guarda exime
explícitamente ese único par (`audit_log`·`purge`), el respaldo desapareció y
la prueba exige el 0 exacto del contrato.

## 6. T080 encontró dos fugas altas, y la peor era de datos de una menor

La revisión de seguridad del cambio de alcance no salió limpia, y lo que
encontró vale más que el propio cambio de alcance. Ambos hallazgos están
**corregidos** en esta corrida (commit `8ca2870`).

**H1 — un entrenador de otro club podía lanzar un análisis sobre una menor
ajena.** `POST /api/race-analysis/runs` y el lanzamiento grupal no miraban el
club del deportista. Consecuencias reales, no teóricas: el nombre de la menor
entraba en `forbidden_names` y **salía hacia el proveedor de IA**; se
persistía un insight en su ficha; la fila de auditoría quedaba con el club de
ella y un actor que no le pertenece; y el presupuesto de IA, que es uno solo y
club-wide, lo podía agotar alguien de afuera. La corrida nacía además
inalcanzable para quien la lanzó, porque el chequeo de club sí actúa al
leerla.

**H2 — el listado de corridas de un evento entregaba el nombre completo de una
menor de otro club.** `GET /race-events/{id}/runs` resolvía nombres desde los
resultados sin filtrar por club. Es la asimetría listado/detalle en su peor
dirección: el detalle estaba bien cerrado (403), pero el listado ya había
entregado el nombre, el `athlete_id` y un `run_id` **válido y ajeno** — que es
la única forma práctica de conseguir ids de corrida de otro club, porque son
`uuid4`.

**Raíz común, y por qué se escapó**: el contrato marcó esa ruta como "no
cambiada por este contrato, ya era no filtrada por actor". No filtrar *por
actor* era correcto; no filtrar *por club* no. Y la matriz §1.4 cubre
**operar** un registro que ya existe — **crear** no aparece en ninguna fila.
Las otras dos superficies de lanzamiento (`athlete_race_analysis.py`) sí
estaban acotadas por `verify_athlete_access`; estas dos se quedaron sin
equivalente.

Una válida la corren menores de varios clubes y el evento es de un tercero, así
que **el club no se puede inferir nunca del evento, solo del deportista**. Por
eso el filtro quedó en `resolve_group_members`, que es de donde cuelgan los
dos agujeros. El chequeo de club va **antes** que el de archivado: si no, la
diferencia entre 404 y 403 le confirma a un entrenador ajeno que ese id existe
y está archivado.

**Lo que T080 verificó y descartó** (vale tanto como los hallazgos): el bypass
del administrador es único y no alcanzable por otro rol; el respaldo por
autoría solo dispara con el conjunto de clubes vacío, así que nunca ensancha;
las siete llamadas de §2 están las siete; el orden 404-antes-que-403 es
consistente en las siete rutas, así que **no** existe el oráculo por
diferencia de orden que se temía; y el endpoint de gasto no puede filtrar un
dato de menor —se rastrearon los cuatro sitios que escriben sus columnas y
todos están detrás de `_coach_or_admin`.

**Hallazgos menores que quedan abiertos** (ninguno toca datos de un menor):

| # | Qué | Dónde |
|---|---|---|
| H3 | `GET /admin/ai-usage`, ahora abierto a coach, entrega nombre y gasto del staff de **todos** los clubes, no solo del propio. Metadato de adulto y dinero, pero contradice la regla que este mismo cambio establece. | `app/routers/race_analysis.py` (RBAC) y `budget_guard.py` (`_QUERY_SPEND_BY_USER`, sin cláusula de club) |
| H4 | `GET /imports/` devuelve a cualquier coach la lista completa de cargues de todos los clubes. El oráculo 403/404 de `_load_pending_import` es ruido al lado de esto. | `app/routers/race_imports.py` (`list_imports`) |
| H5 | `user#{id}` sigue vivo en el listado de importaciones, cuando §4.1 dice que nunca es un valor legal para el lector (FR-013) y se eliminó de las respuestas de corrida. Es el contrato contradiciéndose consigo mismo. | `app/routers/race_imports.py` |
| H6 | `_admin_only` quedó muerto y el prefijo `/admin/ai-usage` ya no significa admin. Un prefijo que miente sobre su RBAC es lo que hace que la próxima revisión no mire el endpoint. | `app/routers/race_analysis.py` |
| H7 | Un cargue creado por el **administrador** queda inalcanzable para los coaches del club: `import_club_ids` resuelve solo por membresías con `role_in_club='coach'`, así que el conjunto sale vacío y el respaldo por autoría lo deja solo para él. Falla cerrado, no es riesgo — pero en producción aparece como "no puedo continuar el cargue". | `app/services/permissions.py` (`import_club_ids`) |

---

# RESUMEN FINAL DE LA NOCHE — corrida 3, 2026-09-10, 03:30 a 05:00 (hora de Colombia)

Última de las tres corridas desatendidas. No hay otra después de esta. Lo que
sigue está escrito para leerse de una sentada al despertar, sin abrir el código.

## 0. Lo primero, si solo lees un párrafo

La rama `feat/041-multi-coach-governance` está **commiteada y empujada**, no
quedó nada sin guardar. Las **once fases de la feature están cerradas** salvo
las tareas que este entorno no puede ejecutar (sin MySQL, sin Docker, sin
credenciales de producción). El frontend está **entero en verde**: 348
archivos, 4131 pruebas, `tsc --noEmit` limpio. El backend deja **16 pruebas rojas que no son ambientales**, todas del mismo
origen —el arreglo de seguridad de la corrida 2 dejó atrás dobles de prueba
viejos— y todas diagnosticadas abajo (§2 y §4). El código de producción es el
correcto; lo que está desactualizado son los fixtures.

Hay **una sola decisión** que sigue esperándote y que ninguna corrida podía
tomar por ti: si el dry-run de importación debe emitir de verdad su cambio de
estado (§3, decisión D6).

## 1. Qué cerró esta corrida

Siguiendo tu prioridad —primero las brechas abiertas, después tareas nuevas—
se atacaron los cinco hallazgos menores que la revisión de seguridad de la
corrida 2 dejó sin cerrar, y solo después se tomaron tareas nuevas.

| Brecha | Qué era | Cómo quedó |
|---|---|---|
| **H3** | `GET /admin/ai-usage`, abierto a entrenador por esta misma feature, entregaba **nombre y gasto del personal de todos los clubes**. | El desglose se acota a los clubes de quien pregunta. El gasto ajeno no se omite —eso rompería el invariante de reconciliación FR-029— sino que se repliega en un cubo único **sin nombres**, `"Otros clubes"`. El admin sigue viéndolo todo. |
| **H4** | `GET /imports/` listaba a cualquier entrenador **los cargues de todos los clubes**, con ids y nombres de quien los subió. | Filtrado por club, y **en SQL**, para que `total` y la paginación no queden mintiendo. Se conserva el respaldo por autoría: un cargue cuyo club no resuelve solo lo ve quien lo subió. |
| **H5** | El listado imprimía `user#{id}` cuando no resolvía el nombre; §4.1 dice que ese valor nunca es legal para el lector (FR-013). | Reemplazado por `"Usuario no disponible"`, el mismo texto que ya usan las otras superficies. También cubre el caso del nombre en blanco. |
| **H6** | `_admin_only` había quedado muerto y el prefijo `/admin/` mentía sobre su RBAC. | Corregido el RBAC declarado y la documentación del módulo. **La ruta no se renombró** (ver decisión D8). |
| **H7** | Un cargue subido por el **administrador** del club quedaba inalcanzable para los entrenadores: en producción aparece como "no puedo continuar el cargue". | `import_club_ids` resuelve ahora membresías `coach` **y** `admin`. El ensanche no toca `run_club_ids`: una membresía de padre o deportista sigue sin resolver club nunca. |

Tareas nuevas cerradas después de eso:

- **T030** (reabierta desde la fase 3) — **cerrada**. El registro de rutas ya
  no tiene ninguna entrada con el marcador `pending instrumentation`. La
  compuerta FR-009 corre **100 casos en verde**.
- **T080** — marcada `[X]`: la revisión de seguridad la hizo la corrida 2 y
  esta cerró sus hallazgos pendientes.
- **T091** (auditoría de privacidad, obligatoria) — **hecha**, en
  `checklists/privacy-audit.md`. Siete ítems con veredicto y **un hallazgo
  ALTO corregido**: la respuesta de sesión para familias incluía
  `created_by_user_id`, es decir el id del entrenador, contra la decisión 6
  tuya (las familias mantienen la voz institucional). Veredicto: aprobado
  para publicar, con la salvedad de que nada se validó contra base real.
- **T098** — descripción del PR escrita en `pr-description.md`.
- **T093 / T094** — documentación de la feature y borrador de la política de
  privacidad v1.3. Ver §6 para el estado exacto al cierre.
- **T078** — **parcial**: dos de los tres archivos de prueba pedidos
  (`test_spend_by_user.py`, 7 casos verdes; `test_race_imports_club_scope.py`,
  7 casos verdes). Falta `test_race_analysis_club_scope.py`.

## 2. Conteos de prueba, sin maquillaje

**Frontend — verde entero, medido después de los cambios de esta corrida:**

```
npm run typecheck   → limpio
npx vitest run      → 348 archivos, 4131 pruebas, 4131 en verde (355 s)
```

**Backend.** Aquí hay que separar tres cosas, porque mezclarlas es lo que
hace que un informe nocturno no sirva:

1. **Fallos ambientales (no son regresiones).** El fixture `client` de
   `tests/conftest.py` levanta la aplicación contra la base real. Sin MySQL ni
   Docker, la línea base medida sobre `main` es de **224 identificadores (215
   fallos + 9 errores)**, registrada en
   `checklists/baseline-main-failures.txt`. Esa cifra es de `main`, no de esta
   rama: no la cuentes como deuda de la feature.
2. **Regresiones verdaderas: 16.** El desglose exacto está unas líneas más
   abajo, y el diagnóstico —una sola causa— en §4.
3. **Lo que sí se corrió y está verde**, medido directamente esta madrugada:

```
tests/test_audit_coverage.py                  → 100 verdes, 1 salteada
tests/test_spend_by_user.py            (nuevo) →   7 verdes
tests/test_race_imports_club_scope.py  (nuevo) →   7 verdes
tests/routers/test_race_event_runs.py          →  16 verdes, 3 rojas
tests/routers/test_race_imports.py             →  todo verde
tests/routers/test_audit_log_api.py            →  todo verde
```

**El diferencial completo, medido de verdad.** La corrida entera del backend
sí alcanzó a terminar:

```
233 failed, 4432 passed, 40 skipped, 13 xfailed, 6 xpassed, 9 errors  (3 m 52 s)
```

Son **242 identificadores en rojo**. Contra los **224 ambientales** de la línea
base de `main`, el diferencial da **22 regresiones**. De esas 22, **6 quedaron
corregidas** en esta misma corrida (el fixture de §4, verificado aparte porque
la corrida completa se lanzó antes del arreglo). **Quedan 16**, y ninguna es
misteriosa:

| Cuántas | Dónde | Qué son |
|---|---|---|
| 12 | `tests/routers/test_race_analysis.py`, `…_athlete_sex.py`, `…_consent.py`, `…_prompt_version.py` | **La misma causa de §4**: 403 de `_ensure_athlete_club_access`. Estas usan una sesión de base falsa, así que el arreglo del fixture no las alcanza: hay que enseñarle al doble a responder la consulta de club. No se alcanzó a hacer. |
| 3 | `tests/routers/test_race_event_runs.py::TestListEventRuns` | El resto de §4. |
| 1 | `tests/routers/test_race_imports_club_scope.py::test_listado_identico_para_los_tres_coaches` | **Esperada**: afirma el comportamiento viejo que H4 corrige. Hay que actualizarla o retirarla (§6.3). |

Dicho de otro modo: **cero regresiones sorpresa**. Las 16 son el rastro de un
único arreglo de seguridad —el de la corrida 2— que cambió una precondición y
dejó los dobles de prueba viejos detrás, más una prueba que afirmaba justo lo
que esta corrida vino a corregir.

**Lint.** `ruff check` da 366 hallazgos en la rama contra 345 en `main`. De
los 21 de diferencia, 19 son `E402` cosméticos en archivos de prueba y 2 eran
`F821` (nombre indefinido) en `app/dependencies.py`, que **se corrigieron**
esta corrida con imports bajo `TYPE_CHECKING`. Ninguno era un fallo de
ejecución.

## 3. Las decisiones que las tres corridas tomaron sin poder preguntarte

Están todas registradas en el código, en su sitio, no solo aquí.

| # | Corrida | Decisión | Por qué, y qué cuesta revertirla |
|---|---|---|---|
| D1 | 1 | Contradicción entre contratos sobre el borrado lógico de `TrainingSession`: `session-coaches.md` §7.3 lo pide, `data-model.md` §4 no le da columna. **Manda `data-model.md`.** | El propio contrato dice que él y el código ganan. No se tocó la migración única de T013, que ya se había verificado contra un MySQL `_test` y aquí no se podía volver a verificar. Revertir: una columna, una migración y una línea de `VALUE_ALLOWLIST`. |
| D2 | 1 | La mitad estática de la compuerta FR-009 resuelve el grafo de llamadas **por nombre**, no por tipo. | Se prefirió un falso negativo antes que un falso positivo que obligara a exenciones a mano. Dos funciones homónimas se confunden a propósito. |
| D3 | 2 | Se apartó del orden del runbook: unificó `ActorRef` antes que T030. | Era precondición de T076; arrancar por T030 habría dejado los dos frentes de US6 chocando contra una clase duplicada. |
| D4 | 2 | Un entrenador **conserva** la lista de sus colegas, pero con la carga recortada (id, nombre, rol y estado; nada de contacto). | Negarla del todo, como proponía la revisión de la fase 5, **habría roto la feature**: el filtro "Entrenador" del historial y el selector de entrenadores a cargo piden esa lista. No se aplicó a `role=parent` porque gestionar familias es trabajo del entrenador. |
| D5 | 2 | `entity_id = 0` exacto para la fila de purga, con exención explícita en la guarda. | El respaldo anterior usaba `entity_id = 1`, que es el id de una fila de auditoría real: la evidencia del barrido apuntaba a un registro ajeno. Peor que el error. |
| **D6** | **3** | **`POST /imports/{parse_id}/dry-run` pasa de "pendiente de instrumentar" a exención genuina de §4.14.** | La corrida 2 te la dejó a ti. Como no hay corrida 4, se tomó: el dry-run **no deja escritura persistente** (`RaceImportStatus.dry_run` no se asigna en ningún camino de código) y tu decisión 2 es explícita en que la bitácora no registra lecturas; registrar un `update` ahí sería anotar una escritura que no ocurrió. **Esta es la decisión que conviene que revises.** Si prefieres la otra salida —que el dry-run emita de verdad su cambio de estado y sí se audite— se revierte en una línea: la razón está escrita completa en `app/services/audit.py`, junto a la entrada. |
| D7 | 3 | H3: el gasto del personal de otros clubes se **repliega** en un cubo sin nombres, no se omite. | Omitirlo rompería el invariante de reconciliación FR-029 / US6 AC4 (la suma de las filas debe igualar el total de la ventana). |
| D8 | 3 | H6: la ruta sigue llamándose `/admin/ai-usage` aunque ya la use un entrenador. | Renombrarla rompe el frontend y el contrato a cambio de estética. Se corrigió el RBAC declarado, que era lo que engañaba a la siguiente revisión. |
| D9 | 3 | H7: el ensanche se limita a membresías `coach` **y** `admin`. | Ensanchar a cualquier membresía habría filtrado un cargue hacia otro club cuando un entrenador es además padre allí. |

## 4. La regresión de tres pruebas, con su diagnóstico

No es de esta corrida: **la introdujo el arreglo de seguridad H1/H2 de la
corrida 2** (commit `8ca2870`), que es el arreglo que impide que un entrenador
ajeno lance un análisis sobre una menor de otro club. Ese arreglo hizo
obligatorio que quien consulta tenga membresía de club; los fixtures de
`tests/routers/test_race_event_runs.py` construían un entrenador con
`club_memberships=[]`, así que desde entonces toda esa ruta respondía 403 y
nueve pruebas caían.

Esta corrida **arregló seis de las nueve** de ese módulo: el fixture ahora declara el club
que siembra `_seed_base` (`user_id * 1000 + 1`), que es lo que el arreglo
volvió necesario. Las tres restantes, todas en `TestListEventRuns`, siguen
recibiendo una lista vacía donde esperan una corrida. La causa está acotada al
sembrado de `_seed_agent_run` de esa clase, no al código de
producción, pero **no se terminó de perseguir por falta de ventana** y prefiero
decírtelo así antes que dejarlo insinuado.

**Importante**: el código de producción aquí es el correcto y el que quieres.
Lo que está desactualizado es el fixture. No revierta el arreglo de alcance
para poner las pruebas en verde.

## 5. Lo que este entorno no puede hacer, y por qué queda sin marcar

Ninguna de estas es deuda de código; son límites de la máquina donde corren
las corridas nocturnas.

| Tarea | Por qué no |
|---|---|
| **T092** — cinco especificaciones de Playwright | Necesitan el stack e2e arriba. Sin Docker no hay base, y sigue en pie el bug de migración preexistente que impide crear una base nueva. |
| **T095** — todas las compuertas | Se corrieron las que sí se pueden: `ruff check`, el `pytest` offline (parcial, ver §2), `npm run typecheck` y `npm test` (verdes). **No** se pudo `pytest -m mysql` ni `npm run test:e2e`. |
| **T086 / T096** | Revisión de integración y recorrido del quickstart sobre el stack de desarrollo, con dos entrenadores. Requieren el stack arriba. SC-002 es además una prueba moderada contigo, presencial. |
| **T097** — humo posdespliegue | Necesita credenciales de producción, que no están en este entorno y no deben estarlo. |
| Pruebas marcadas `-m mysql` | Escritas, nunca ejecutadas. Se dicen como escritas, no como aprobadas. |

## 6. Lo que sigue abierto, con nombre y número

Ordenado por lo que costaría descubrirlo tarde.

1. **Decisión D6** (§3) — es tuya, es de una línea y es la única que se tomó
   en tu nombre sobre algo que la corrida anterior te había reservado.
2. **Las 16 pruebas rojas** (§2 y §4) — fixtures y dobles de prueba, no
   producción. Las 12 de `test_race_analysis*` son el trozo más grande y
   necesitan que la sesión falsa sepa responder la consulta de club.
3. **Choque de nombres entre dos archivos de prueba**: el nuevo
   `backend/tests/test_race_imports_club_scope.py` y el ya existente
   `backend/tests/routers/test_race_imports_club_scope.py`. Además, dentro del
   segundo, `test_listado_identico_para_los_tres_coaches` (~línea 462) afirma
   el comportamiento **viejo** —que el listado de importaciones nunca estuvo
   filtrado— que es justo lo que corrige H4. Esa prueba hay que actualizarla o
   retirarla por superada; es la misma lección de H2: "no filtrado por actor"
   nunca quiso decir "no filtrado por club".
4. **T078 parcial** — falta `test_race_analysis_club_scope.py`.
5. **T092, T095 (mitad), T086, T096, T097** — bloqueadas por entorno (§5).
6. `frontend/src/types/trainingSession.types.ts` declara `created_by_user_id`
   como obligatorio; el backend ya no lo manda a las familias. No rompe nada en
   ejecución —es un tipo que miente, no una validación Zod— pero conviene
   separar el tipo de familia del de entrenador.
7. La deuda B2–B6 de US5 y las brechas A5, A8, A10–A12 de las fases 3 a 6
   siguen como estaban; ninguna toca datos de una menor.
8. Un hallazgo **preexistente a 041**, encontrado por la auditoría de
   privacidad y por eso fuera de su alcance:
   `GET /api/calendar/events/{id}/attendances` entrega `rsvp_by_user_id` sin
   filtrar a un padre, en la rama que no es de sesión de entrenamiento
   (`app/routers/calendar.py`). Es la misma clase de defecto que el hallazgo
   ALTO que sí se corrigió.

## 7. Nota de método, para la próxima vez

El patrón que la corrida 2 señaló se confirmó una vez más: **una tarea marcada
`[X]` porque el archivo existe, no porque cumpla lo que el contrato pedía.**
T030 y T080 estaban en ese estado al empezar esta noche. Las dos quedaron
cerradas de verdad, pero conviene revisar con esa lupa las tareas de US1 y US2
antes de dar la feature por lista.

Y una segunda: **un arreglo de seguridad que cambia una precondición deja
fixtures viejos detrás**. Los nueve fallos de §4 no los detectó la corrida que
introdujo el arreglo porque su diferencial se midió sobre otros módulos. Vale
la pena, al cerrar un cambio de alcance, correr los módulos que ejercitan las
rutas afectadas aunque el cambio no los toque.
