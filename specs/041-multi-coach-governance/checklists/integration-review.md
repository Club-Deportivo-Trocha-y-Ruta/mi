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
