---

description: "Task list for feature 041 — multi-coach governance: change log, attribution and per-coach reports"
---

# Tasks: Multi-coach governance — change log, attribution and per-coach reports

**Input**: Design documents from `/specs/041-multi-coach-governance/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md; contracts in `contracts/audit-recording.md`, `contracts/audit-log-api.md`, `contracts/athlete-archive.md`, `contracts/staff-admin.md`, `contracts/session-coaches.md`, `contracts/concurrency-and-approvals.md`, `contracts/scope-ai-imports.md`, `contracts/coach-activity-report.md`, `contracts/retention-purge.md`

**Tests**: Included — the constitution (Principle II) makes tests part of the deliverable, every router change needs a denied-path test, every bug fix needs a regression test that fails first, and code touching minors' data needs explicit privacy invariants. Each contract's "Required tests" section is the source; test tasks precede or accompany the implementation task they guard.

**Organization**: Phase 1 unblocks the stack and adds the two-coach fixtures; Phase 2 is the blocking foundation (audit model, helper, registries, migration, request context); then one phase per user story in spec priority order (US1 history, US2 archive, US3 staff, US4 sessions, US5 concurrency, US6 scope, US7 reporting, US8 retention); then close-out.

## Format: `[ID] [P?] [Story] Description → agent · model`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1..US8 from spec.md
- **→ agent · model**: subagent from `.claude/agents/` and the model tier to launch it with. Assignment rule (owner, 2026-09-09): **sonnet** for mechanical, fully specified work (schemas, components, templates, docs, tests with a written matrix); **opus** for the migration, the audit helper and registries, permissions/RBAC changes, optimistic concurrency, privacy-sensitive filtering, and every review/verification task. **Effort**: automatic — do not pass a reasoning-effort override.

## Path Conventions

Web app: `backend/app/…`, `backend/tests/…`, `backend/scripts/…`, `backend/alembic/versions/…`, `backend/templates/…`, `frontend/src/…`, `frontend/e2e/…`, `.github/workflows/…`, `docs/…`.

## Agent roster for this feature

| Agent | Model | Used for |
|---|---|---|
| `engineering-lead` | opus | Wave coordination, integration review after each phase, PR description |
| `database-architect` | opus | Alembic revision with backfills, `-m mysql` verification, index review |
| `fastapi-architect` | opus | Audit helper/registries, request context, permissions, concurrency, archive filters, retention service |
| `fastapi-architect` | sonnet | Schemas, straightforward endpoints, email templates, budget message, service parameter threading |
| `react-ui-engineer` | sonnet (×2 in parallel in Phases 3, 5, 9) | Components, hooks, pages, MSW handlers |
| `qa-engineer` | sonnet | pytest / vitest / jest-axe / MSW / Playwright per contract matrices |
| `qa-engineer` | opus | Coverage test (FR-009), archived-athlete enumeration test, append-only proof, privacy tests |
| `data-privacy-guard` | opus | Mandatory privacy audit (audit rows, parent schemas, logs, PDFs) |
| `security-engineer` | opus | RBAC review of the new read endpoints and the scope change on AI runs/imports |
| `devops-engineer` | sonnet | GitHub Actions workflow, `dictConfig` logging, CORS `expose_headers`, entrypoint |
| `parent-communicator` | sonnet | Family e-mail copy review (acting coach, session coaches list) |
| `technical-writer` | sonnet | `docs/19-multi-coach-governance/*`, technical-notes, implementation-status, policy v1.3 wording draft |
| `release-manager` | sonnet | Post-deploy smoke, runbook execution of the first dry-run purge |

---

## Phase 1: Setup (unblock the stack, shared fixtures)

**Purpose**: Make a fresh database bootable, put an interim guard on the destructive athlete delete, and create the two-coaches fixtures every story's independent test relies on.

- [X] T001 Make the three migrations that import deleted modules import-safe (`try/except ImportError` around `app.data.technique_catalog` in `backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py:276` and `backend/alembic/versions/f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py:60`, and `app.data.strength_catalog` in `backend/alembic/versions/a7b8c9d0e1f2_strength_training_library.py:284`; skip the seed step when the module is absent) so `alembic upgrade head` succeeds on an empty `_test` database — verify with `pytest -m mysql` (research.md R-34) → database-architect · opus
- [X] T002 [P] Add an interim admin-only guard on `DELETE /api/athletes/{athlete_id}` in `backend/app/routers/athletes.py:329` (coach → 403 with copy "Solo un administrador puede eliminar un atleta por ahora.") plus a regression test in `backend/tests/routers/test_athlete_delete_guard.py`; removed again by T060 → fastapi-architect · sonnet
- [X] T003 [P] Create the shared two-coaches-same-club fixture module `backend/tests/fixtures/two_coaches.py` (`club`, `admin_user`, `coach_a`, `coach_b`, `other_club_coach`, `parent_user`, athlete stubs with synthetic data only, token helpers) and register it in `pytest_plugins` in `backend/tests/conftest.py` next to `tests.fixtures.race_groups` (research.md R-32, quickstart.md §1.5C) → qa-engineer · sonnet
- [X] T004 [P] Add the `coach2` seed identity (synthetic name/e-mail) to `backend/scripts/seed.py` and to `frontend/e2e/helpers/session.ts` (`SeedRole` gains `'coach2'`) and `frontend/e2e/helpers/demo-athlete.ts` (parametrised coach e-mail) so e2e specs can sign in as either coach (research.md R-34) → qa-engineer · sonnet
- [X] T005 [P] Add `expose_headers=["X-Request-Id", "ETag"]` and `"If-Match"` to `allow_headers` on `CORSMiddleware` in `backend/app/main.py:59-64`, with the CORS test `backend/tests/test_cors_etag.py` (contracts/concurrency-and-approvals.md §1.3, contracts/audit-log-api.md §9) → devops-engineer · sonnet
- [X] T006 [P] Add `dictConfig` for `app.*` loggers with a `request_id` filter and `disable_existing_loggers: False` at the top of `backend/app/main.py` so business logs reach uvicorn's handlers in production (contracts/audit-recording.md §6, research.md section H); test in `backend/tests/test_logging_config.py` that a record from `app.services.audit` reaches the root handler with `request_id` → devops-engineer · sonnet

**Checkpoint**: a fresh `_test` database migrates; `pytest` has `coach_a`/`coach_b` in one club; e2e can sign in as two coaches.

---

## Phase 2: Foundational (audit model, helper, registries, migration, request context)

**Purpose**: Everything every user story writes through. No story work starts before this phase is green.

**⚠️ CRITICAL**: T007–T020 block all user stories.

- [X] T007 Create `backend/app/models/mixins.py` with `ActorTimestampMixin` (`updated_by_user_id` FK users RESTRICT nullable + `declared_attr` relationship) and `UpdatedByMixin` per data-model.md §5; unit test in `backend/tests/models/test_mixins.py` → fastapi-architect · opus
- [X] T008 Create `backend/app/models/audit_log.py` with `AuditLog`, `AuditAction`, `AuditActorKind` (DB enums with `values_callable`), the five composite indexes and the `occurred_at` `mysql.DATETIME(fsp=6)` variant exactly as data-model.md §1–§1.1; register in `backend/app/models/__init__.py` → fastapi-architect · opus
- [X] T009 Create the closed catalogues in `backend/app/services/audit.py`: `AuditEntityType` (one per auditable table, data-model.md §2.3, table `athlete_ai_explanations` spelled correctly), `AuditReasonCode` with the five sub-enums, `AuditReasonGroup` and Spanish labels (§2.4, contracts/athlete-archive.md §3.1), `VALUE_ALLOWLIST` per entity (§2.5), `CLUB_OPTIONAL` and `META_ALLOWLIST` (contracts/audit-recording.md §1.7) → fastapi-architect · opus
- [X] T010 Implement `record_audit(...)` in `backend/app/services/audit.py` per contracts/audit-recording.md §1 (signature §1.1, ordered behaviour §1.2, transaction rule §1.3, rules §1.4, errors `AuditContractError`/`AuditReasonRequired` §1.5, `club_id`/`athlete_id` resolution §1.6) and `compute_changed_fields(before, after, allow_list)` per §2; tests `backend/tests/services/test_audit_helper.py` and `backend/tests/services/test_compute_changed_fields.py` → fastapi-architect · opus
- [X] T011 [P] Create `backend/app/services/request_context.py` (ContextVar `request_id`, `AuditContext`, `get_request_context` dependency, non-HTTP `system_context(job=…)`/`webhook_context`/`cron_context` helpers) and the pure-ASGI `RequestIdMiddleware` registered as the outermost middleware in `backend/app/main.py` (contracts/audit-recording.md §3.1–§3.3, §10 point 2 on ordering); test `backend/tests/services/test_request_context.py` (isolation across concurrent requests, header echo) → fastapi-architect · opus
- [X] T012 [P] Create the append-only proof: static grep test over `backend/app/` that no module except `app/services/retention.py` issues `update(AuditLog)`/`delete(AuditLog)`/`.delete()` on an `AuditLog` instance, plus the model-level test that `AuditLog` has no `updated_at`/`onupdate` and rejects attribute mutation after flush, in `backend/tests/test_audit_append_only.py` (contracts/retention-purge.md §5, contracts/audit-recording.md §5) → qa-engineer · opus
- [X] T013 Write the single Alembic revision `backend/alembic/versions/<rev>_multi_coach_governance.py` (`down_revision = "2a8baa967cc6"`): `audit_log` + indexes, `training_session_coaches` (composite PK, `ix_tsc_coach_user_id`), the additive columns on the 14 tables of data-model.md §4, backfills B1–B7 (session coaches = creator; `monthly_reports.approved_at` = `generated_at` for approved rows with `approved_by_user_id` left NULL; `agent_runs.athlete_id` from `input_json`; all idempotent and dialect-aware), MySQL 8.4 notes §6.4 (`batch_alter_table`, `fsp=6`, no JSON index), full `downgrade()`; run `alembic upgrade head` + `downgrade -1` + `upgrade head` against a `_test` MySQL → database-architect · opus
- [X] T014 [P] Write the migration tests required by data-model.md §6.5 in `backend/tests/test_audit_mysql.py` (`-m mysql`: `fsp=6` on `occurred_at` and `DATETIME(6)` in `SHOW CREATE TABLE`, backfill B1 gives every existing session exactly its creator as coach, B2 leaves `approved_by_user_id` NULL, re-running the backfills is a no-op, `alembic heads` returns one head) → database-architect · opus
- [X] T015 [P] Add the SQLAlchemy model changes for every attribution column of data-model.md §4 (users §4.1, athletes §4.2, session_attendance §4.3, calendar_events §4.4, monthly_reports §4.5, athlete_monthly_newsletters §4.6 with `edit_version`, athlete_ai_insights §4.7, and the §4.8 tables: session_media, anthropometric_records, race_imports, race_series, club_project_profiles, club_members, agent_runs) using the mixins from T007; `TrainingSessionCoach` model in `backend/app/models/training_session.py` per data-model.md §3 → fastapi-architect · sonnet
- [X] T016 Make the test lane build `audit_log` and `training_session_coaches` in every subset harness: add the shared table list helper in `backend/tests/conftest.py` and update the `Base.metadata.create_all(..., tables=[…])` call sites listed by contracts/audit-recording.md §8 (run `pytest` and fix every `no such table: audit_log`) → qa-engineer · sonnet
- [X] T017 [P] Add the test-only strict flush detector (`AUDIT_STRICT=true` in the test lane): an `after_flush` listener in `backend/app/services/audit.py` that raises when an auditable table was mutated in a flush whose unit of work queued no `AuditLog` row with the current `request_id` (plan.md Complexity Tracking); enabled only under `APP_ENV=test`; test in `backend/tests/services/test_audit_strict_mode.py` → fastapi-architect · opus
- [X] T018 [P] Create the coverage registry and test (FR-009): `AUDITED_ROUTES` / `EXEMPT_ROUTES` (with reason strings) in `backend/app/services/audit.py` per contracts/audit-recording.md §4.14 and §7, and `backend/tests/test_audit_coverage.py` that walks `app.routes` for every POST/PUT/PATCH/DELETE plus the mutating/exporting GETs of §4.13, fails on any route in neither registry, and — for every audited route exercised by the suite — asserts at least one `audit_log` row was written (contracts/audit-recording.md §9) → qa-engineer · opus
- [X] T019 [P] Create the privacy test `backend/tests/test_audit_privacy.py`: for every fixture-driven write in the suite, no `audit_log` row contains a fixture athlete's first/last name, birth date, any anthropometric value, feedback/note/narrative text, or a `diff_json` key outside `VALUE_ALLOWLIST[entity_type]`; every audited entity type yields a non-null `club_id` unless in `CLUB_OPTIONAL` (data-model.md §2.5, §8.4) → qa-engineer · opus
- [X] T020 Add `can_view_audit(db, user, club_id)` and `can_view_athlete_audit(db, user, athlete_id)` to `backend/app/services/permissions.py` (admin; coach of the club; parent and other-club coach refused) per contracts/audit-log-api.md §4.2, with denied-path tests in `backend/tests/test_permissions_audit.py` → fastapi-architect · opus

**Checkpoint**: `pytest` green with `audit_log` present everywhere; `record_audit` usable; migration applied on a `_test` MySQL; coverage test lists every write route (all still exempt-with-reason "pending instrumentation" until Phase 3 removes them one by one).

---

## Phase 3: User Story 1 — Every change has a name on it (Priority: P1) 🎯 MVP

**Goal**: Every write and every document export/send produces an `audit_log` row in the same transaction; coaches/admins read the club history and the per-athlete history in Spanish; parents are refused.

**Independent Test**: quickstart.md scenario 1 — two coaches and one admin perform 20 scripted actions; the club history shows every one with the correct actor and record; filtering by coach B shows only B's; a parent gets 403; the privacy scan finds no PII (SC-001).

### Instrumentation — governance actions first (contracts/audit-recording.md §4)

- [X] T021 [US1] Instrument staff and club routes (`backend/app/routers/users.py` create/patch/delete, `backend/app/routers/clubs.py` create/patch/add-member) per §4.2: actions `create`/`update`/`deactivate`/`activate`/`hard_delete`, `changed_fields` via `compute_changed_fields`; remove the `UPDATE users SET created_by = NULL` at `users.py:343-345` in the same change (pre-existing defect, §10); tests in `backend/tests/test_audit_actors.py` → fastapi-architect · opus
- [X] T022 [P] [US1] Instrument athlete routes (`backend/app/routers/athletes.py` create/update/delete, anthropometry create/update, consent) per §4.3–§4.4 with `athlete_id` set on every row; tests extend `backend/tests/test_audit_actors.py` → fastapi-architect · sonnet
- [X] T023 [P] [US1] Instrument calendar routes (`backend/app/routers/calendar.py`, `backend/app/services/calendar/events.py` create/update/cancel/permanent-delete/RSVP with parent actor) per §4.5; tests in `backend/tests/test_calendar_router.py` (extended) → fastapi-architect · sonnet
- [X] T024 [P] [US1] Instrument training-session routes (`backend/app/routers/training_sessions.py`, `backend/app/services/training/sessions.py`, `attendance.py`: create with `meta.convocados_count`, update, execute, cancel, roster update, attendance/rubric/feedback, media upload/delete) per §4.6; tests in `backend/tests/test_training_session_router.py` (extended) → fastapi-architect · sonnet
- [X] T025 [P] [US1] Instrument monthly reports and club project profile (`backend/app/routers/monthly_reports.py`, `backend/app/services/training/reports.py`: generate=`create`, regenerate=`execute`, block update, approve/unapprove, project profile put/patch) per §4.7 → fastapi-architect · sonnet
- [X] T026 [P] [US1] Instrument family newsletters (`backend/app/routers/athlete_monthly_newsletters.py`: generate, patch, attach-insights, approve/unapprove, send=`send` with `meta.recipients_count`) per §4.8 → fastapi-architect · sonnet
- [X] T027 [P] [US1] Instrument AI runs and insights (`backend/app/routers/race_analysis.py` launch=`create`, HITL accept/edit=`approve`, reject=`unapprove`, cancel, re-execute, invalidate=`update`; `backend/app/routers/athletes.py` insights approve/archive/answer) per §4.9 → fastapi-architect · sonnet
- [X] T028 [P] [US1] Instrument the race-results domain (`backend/app/routers/race_imports.py` parse=`create`, commit=`execute` with `meta.race_event_id`/`is_revision`; `race_events.py`, `race_series.py`, `race_competitors.py` link/unlink, revisions) per §4.10, writing the summary row that points at `race_result_revisions` / `race_competitor_link_audit` → fastapi-architect · sonnet
- [X] T029 [P] [US1] Instrument interval training and Strava/activities/webhooks (`backend/app/routers/intervals.py`, `activities.py`, `strava_integration.py` incl. the mutating GET callback at `:201-313`, `webhooks_resend.py` with `webhook_context`) per §4.11–§4.12; Strava reconcile and start-up backfills (`backend/app/scripts/backfill_anthropometry.py`, `backend/app/seed_growth_data.py`, `backend/entrypoint.sh` order) with `system_context(job=…)` per §3.3 → fastapi-architect · sonnet
- [ ] T030 [US1] Instrument the exporting GETs (`export` rows for anthropometry/growth PDF, medical-authorisation DOCX, newsletter PDF, monthly report DOCX/PDF, race-analysis PDF; `send` for notification e-mails) per §4.13, then empty the "pending instrumentation" exemptions so `backend/tests/test_audit_coverage.py` (T018) passes with only the §4.14 exemptions left → fastapi-architect · opus

### Read API (contracts/audit-log-api.md)

- [X] T031 [P] [US1] Create `backend/app/schemas/audit.py` (`AuditEntryOut`, `AuditListOut`, `ActorRef`, `ReasonCodeOut`, `ReasonCodesOut`) per §5 and §14.3 → fastapi-architect · sonnet
- [X] T032 [US1] Implement `SENTENCE_TEMPLATES`, `AUDIT_DOCUMENT_LABELS`, `format_count_es` and `render_sentence(entry)` in `backend/app/services/audit.py` per §7 (placeholders §7.2, algorithm §7.4, catalogue §7.5 including the singular/plural purge form, automated-actor labels §6.2); unit tests in `backend/tests/services/test_audit_sentences.py` covering every template → fastapi-architect · sonnet
- [ ] T033 [US1] Implement `backend/app/routers/audit.py`: `GET /api/clubs/{club_id}/audit-log` (§2: filters, page/limit, ordering, actor `LEFT JOIN` §6.1, read-time re-filter of `diff`/`meta` §8), `GET /api/athletes/{athlete_id}/audit-log` (§3, ordering trap §4.3), `GET /api/audit/reason-codes?group=` (§14), `X-Request-Id` echo (§9); mount in `backend/app/main.py` → fastapi-architect · opus
- [ ] T034 [US1] Tests `backend/tests/routers/test_audit_log_api.py` per §13 (happy path with resolved names, every filter, pagination, parent 403, other-club coach 403, archived athlete still returned to coach/admin, no PII in response, query-count ≤ 2 via `backend/tests/helpers/query_counting.py`) → qa-engineer · opus

### Frontend (contracts/audit-log-api.md §12, contracts/coach-activity-report.md §8)

- [X] T035 [P] [US1] Create `frontend/src/types/audit.types.ts`, `frontend/src/schemas/audit.ts` (Zod mirror), `frontend/src/api/audit.ts` (club/athlete history, reason codes) and hooks `frontend/src/hooks/governance/useAuditLog.ts`, `frontend/src/hooks/useAuditReasonCodes.ts` with query keys carrying the filters; MSW handlers `frontend/src/test/msw/auditHandlers.ts`; add keys to `frontend/src/lib/persistAllowList.ts`; hook test `frontend/src/hooks/__tests__/useAuditLog.test.ts` → react-ui-engineer · sonnet
- [X] T036 [P] [US1] Create `frontend/src/components/audit/AuditEntryRow.tsx` (sentence, relative time via `frontend/src/lib/datetime.ts`, "Ver detalle" `Collapsible` with changed fields and allow-listed diff), `frontend/src/components/audit/CoachFilter.tsx` (Select of club staff, "Todos los entrenadores", "Limpiar filtros" — clone of the `ActivityReviewPage` filter bar) with tests `frontend/src/components/audit/__tests__/AuditEntryRow.test.tsx`, `CoachFilter.test.tsx` → react-ui-engineer · sonnet
- [ ] T037 [US1] Create `frontend/src/routes/admin/ClubHistoryPage.tsx` (lazy route `/club/historial`, coach+admin; filters actor/period/record type/athlete/action; server-side pagination on shadcn `Table`; loading/empty/error/retry states; 48 px targets) and register the `gobierno` nav area in `frontend/src/lib/navigation.ts` per contracts/coach-activity-report.md §8.2 and contracts/staff-admin.md §6; update `frontend/src/lib/__tests__/navigation.test.ts`; tests `frontend/src/routes/admin/ClubHistoryPage.test.tsx` + jest-axe → react-ui-engineer · sonnet
- [ ] T038 [US1] Create `frontend/src/components/athletes/AthleteHistoryPanel.tsx` ("Historial" section on `frontend/src/routes/athletes/AthleteDetailPage.tsx`, coach/admin only, 15 rows + "Ver más") per contracts/coach-activity-report.md §8.1 with `frontend/src/components/athletes/__tests__/AthleteHistoryPanel.test.tsx` (parent variant renders nothing) → react-ui-engineer · sonnet
- [ ] T039 [US1] Integration review of Phase 3 against spec US1 AS1–AS8 and quickstart scenario 1: run the 20-action script on the dev stack, confirm counts, confirm `X-Request-Id` groups multi-row operations, confirm parent/other-club 403s, run `backend/tests/test_audit_privacy.py`; record deltas in `specs/041-multi-coach-governance/checklists/integration-review.md` → engineering-lead · opus

**Checkpoint**: US1 independently demoable — history readable, every write route audited, privacy scan clean.

---

## Phase 4: User Story 2 — Deleting an athlete keeps the evidence (Priority: P1)

**Goal**: Athlete removal becomes an archive with a reason; every active surface hides archived athletes; admins can restore; user accounts with activity cannot be deleted.

**Independent Test**: quickstart.md scenarios 2–3 — archive an athlete as coach A, verify absence from every surface and the parent's calm empty state, verify consent/measurements intact for admin, restore, verify return; user delete refused with 409 (SC-003).

- [ ] T040 [US2] Replace the cascade in `DELETE /api/athletes/{athlete_id}` (`backend/app/routers/athletes.py:329-368`) with the archive per contracts/athlete-archive.md §1 (body `AthleteArchiveIn.reason_code` from the `athlete` group, `deleted_at`/`deleted_by_user_id`/`deleted_reason_code`, 204, 409 if already archived, audit `soft_delete`); remove the T002 interim guard; preserve everything in §6 → fastapi-architect · opus
- [ ] T041 [P] [US2] Add `POST /api/athletes/{athlete_id}/restore` (admin only, `AthleteRestoreIn`, audit `restore`) and `GET /api/athletes?include_archived=true` (admin only) per §2 and §4 → fastapi-architect · sonnet
- [ ] T042 [US2] Apply `deleted_at IS NULL` at the three choke points of §5.1 (`verify_athlete_access` with the admin-sees-archived / coach-and-parent-get-404 branch, the athlete list query, `parent_athlete_ids`) → fastapi-architect · opus
- [ ] T043 [US2] Apply the filter at every remaining site of §5.2 (dashboard summary, monthly report metrics, newsletter list/generation, AI athlete picker and insights, calendar audiences incl. birthdays, race roster add, competitor candidates, import matching, growth, badges, Strava listings) and confirm the §5.3 "must NOT filter" sites keep archived athletes → fastapi-architect · opus
- [ ] T044 [P] [US2] Write the enumeration test `backend/tests/test_archived_athlete_absent.py` (§12.2): seed one archived athlete and assert every coach and parent list/aggregate endpoint of the app excludes them, and every §5.3 site still includes them; plus the scope gate `backend/tests/test_archive_scope_gate.py` (§12.5) that fails when a new athlete-listing query lacks the filter → qa-engineer · opus
- [ ] T045 [P] [US2] Tests `backend/tests/routers/test_athlete_archive.py` (§12.1: archive/restore happy paths, reason required 422, coach cannot restore 403, parent 403, consent + measurements + attendance + results preserved, audit rows) and `backend/tests/test_parent_archived_only.py` (§12.3, §7: parent with only an archived athlete gets an empty list, no 500) → qa-engineer · sonnet
- [ ] T046 [US2] Implement `DELETE /api/users/{user_id}` refusal when the account has recorded activity (§8: activity probes §8.1, 409 body §8.3, rule 7 no longer nulls `created_by` §8.2, audit `hard_delete`) and `PATCH /api/users/{user_id}` `is_active` audit mapping (§9); keep the unconditional 403 for admin/coach targets (contracts/staff-admin.md §5) → fastapi-architect · opus
- [ ] T047 [P] [US2] Tests `backend/tests/test_users_delete_deactivate.py` (§12.4: 409 with activity, parent without activity deleted and audited, `created_by` of created users untouched — regression test that fails on old code, deactivate/activate audited) → qa-engineer · sonnet
- [ ] T048 [P] [US2] Frontend archive dialog: "Archivar atleta" trigger and reason dialog on `frontend/src/routes/athletes/AthleteFormPage.tsx:132-144` using `frontend/src/components/shared/ConfirmDialog.tsx` and `useAuditReasonCodes('athlete')`, copy of §10, `apiClient.delete(url, { data })`; test `frontend/src/routes/athletes/__tests__/AthleteFormPage.archive.test.tsx` + jest-axe → react-ui-engineer · sonnet
- [ ] T049 [P] [US2] Frontend admin "Atletas archivados" view `frontend/src/routes/admin/ArchivedAthletesPage.tsx` (lazy `/admin/atletas-archivados`, admin-only nav item, restore action with confirmation, states of §11) with `frontend/src/hooks/admin/useArchivedAthletes.ts`, test `frontend/src/routes/admin/__tests__/ArchivedAthletesPage.test.tsx` + jest-axe; parent empty state assertion in `frontend/src/routes/parents/ParentDashboardPage.test.tsx` → react-ui-engineer · sonnet
- [ ] T050 [US2] Integration review of Phase 4 against US2 AS1–AS7 and quickstart scenarios 2–3 on the dev stack (archive with two years of synthetic history, parent view, restore) → engineering-lead · opus

---

## Phase 5: User Story 3 — The second coach is onboarded from the app (Priority: P1)

**Goal**: Admin creates coaches with a mandatory club from a "Personal del club" screen, lists and deactivates staff; coaches cannot reach it.

**Independent Test**: quickstart.md scenario 4 — create a coach without club (refused), with club (created, e-mail sent), sign in as the new coach and compare counts with coach A, deactivate, verify sign-in refused, verify coach cannot open the screen (SC-004).

- [ ] T051 [US3] Backend staff creation per contracts/staff-admin.md §1: `club_id` required when `role ∈ {coach, admin}` (422 copy §1.2), account + membership in one unit of work with `role_in_club = role` and `club_members.added_by_user_id` (§1.3), set-password e-mail via the existing `password_reset` flow (§1.4), audit rows (§1.5), response (§1.6) in `backend/app/routers/users.py` and `backend/app/schemas/user.py` → fastapi-architect · opus
- [ ] T052 [P] [US3] `POST /api/clubs/{club_id}/members` role-coherence validation (422) per §2 in `backend/app/routers/clubs.py` and `backend/app/schemas/club.py` → fastapi-architect · sonnet
- [ ] T053 [P] [US3] `GET /api/users` staff list per §3 (repeatable `role` param, `is_active`, `club_id`, `created_by_display_name`, `created_at`) and `PATCH /api/users/{user_id}` deactivate/reactivate rules §4.2 (incl. the self-deactivation guard moved outside the coach branch) with audit mapping §4.3 → fastapi-architect · sonnet
- [ ] T054 [US3] Tests `backend/tests/test_staff_admin.py` per §14.1 (club required 422, membership coherence 422, coach creating coach 403, list filters, deactivate → login refused with existing message, audit rows, no password in any response or log) and update `backend/tests/test_users.py::test_admin_creates_coach` to send `club_id` → qa-engineer · sonnet
- [ ] T055 [P] [US3] Frontend data layer per §7: `frontend/src/api/users.ts` (staff list, create, set-active), `frontend/src/api/clubs.ts` (if missing), `frontend/src/types/user.types.ts`, hooks `frontend/src/hooks/admin/{useStaff,useCreateStaff,useSetStaffActive,useClubs}.ts`, MSW `frontend/src/test/msw/staffHandlers.ts`, `persistAllowList` keys → react-ui-engineer · sonnet
- [ ] T056 [P] [US3] Zod schema `frontend/src/schemas/staff.schema.ts` (club required when role is coach/admin, e-mail validation, localized messages) with `frontend/src/schemas/staff.schema.test.ts` per §9 → react-ui-engineer · sonnet
- [ ] T057 [US3] Page `frontend/src/routes/admin/StaffPage.tsx` (lazy `/admin/usuarios`, admin-only guard in `frontend/src/App.tsx`, nav item hidden for coach in `frontend/src/lib/navigation.ts` §6, shadcn `Table` with name/role/state/created-at/created-by, active filter, states §8), `frontend/src/components/admin/StaffCreateSheet.tsx` (§9), deactivate/reactivate `ConfirmDialog` (§10), copy §11, 48 px targets; tests `frontend/src/routes/admin/__tests__/StaffPage.test.tsx`, `StaffPage.a11y.test.tsx`, `frontend/src/components/admin/__tests__/{StaffCreateSheet,StaffStateDialog}.test.tsx`, nav tests `frontend/src/components/layout/__tests__/{SidebarNav,BottomNav}.test.tsx` → react-ui-engineer · sonnet
- [ ] T058 [US3] RBAC review of T051–T053 and T057 (coach cannot create/patch/list staff, admin cannot self-deactivate, parent 403 everywhere, no privilege escalation through `role`/`club_id`) → security-engineer · opus

---

## Phase 6: User Story 4 — Sessions can be co-coached, families hear the right name (Priority: P2)

**Goal**: Sessions carry one or more coaches; the acting coach is named in family e-mails; attendance/rubric/feedback record who entered them; roster removals archive instead of delete; listings filter by coach.

**Independent Test**: quickstart.md scenarios 5–7 — coach A creates a co-coached session, coach B cancels it, MailHog shows "El entrenador B ha cancelado" with both coaches listed; attendance shows "registrado por A, última edición por B"; removing the athlete from the roster keeps the entry readable by admin (SC-005).

- [ ] T059 [US4] Session coaches API per contracts/session-coaches.md §3: `TrainingSessionRead.coaches[]`, `coach_user_ids` on create/update (default `[creator]`, validation matrix §3.3 incl. min-1 and active-coach-of-club checks with `SELECT … FOR UPDATE` on removal), service functions in `backend/app/services/training/sessions.py` → fastapi-architect · opus
- [ ] T060 [US4] Thread the acting user through `update_session`, `cancel_session`, `execute_session`, `update_convocatoria`, `update_attendance` (§4) — never re-derive from `created_by_user_id`; `cancel` takes `reason_code` from the `session_cancel` group (§7.1, flat 422 `{"detail": "Selecciona un motivo de cancelación."}`) → fastapi-architect · opus
- [ ] T061 [P] [US4] Family e-mail templates `backend/templates/email/training_session_{invite,updated,cancelled}.html` (+ `.txt` twins) with the session-coaches list and the acting coach per §5 (exact copy §5.2); context keys in `backend/app/services/notification/*` (§5.1) → fastapi-architect · sonnet
- [ ] T062 [P] [US4] Attendance attribution per §6: `recorded_by_user_id`/`updated_by_user_id` on write (§6.2), `AttendanceOut.recorded_by`/`last_edited_by` `ActorRef`s (§6.1), roster shrink sets `archived_at` instead of deleting (§6.3), `archived_at IS NULL` on every read of `session_attendance` (§6.4 site list) → fastapi-architect · opus
- [ ] T063 [P] [US4] Calendar cancellation and permanent deletion per §7.2–§7.3 (FR-017): `EventCancelIn.reason_code` from the `event_cancel` group, `cancelled_by_user_id`/`cancelled_at`/`cancellation_reason_code`, permanent delete becomes soft (`deleted_at`/`deleted_by_user_id`) with the three read-path filters of §7.3, audit rows §9 → fastapi-architect · sonnet
- [ ] T064 [P] [US4] Coach filter `coach_user_id` on `GET /api/training-sessions` and `GET /api/calendar/events` per §8 (creator for events; virtual birthdays excluded when the filter is set) → fastapi-architect · sonnet
- [ ] T065 [US4] Backend tests per §12: `backend/tests/test_session_coaches.py` (new: min-1, inactive coach 422, other-club coach 422, backfill default), extend `backend/tests/test_training_session_notifications.py` (regression: coach B cancels A's session → e-mail names B; fails on old code), `test_training_session_service.py`, `test_training_session_router.py` (filter), `test_attendance_validation.py` (recorded_by, archive instead of delete), `test_calendar_router.py`/`test_calendar_events_service.py`/`test_calendar_notifications.py` (reason code, cancelled_by, soft permanent delete), `test_training_session_privacy.py` (parent schema has no attribution fields) → qa-engineer · sonnet
- [ ] T066 [P] [US4] Frontend `frontend/src/components/training/SessionCoachesField.tsx` (multi-select with chips, prefilled with the current coach, min-1) wired into `frontend/src/components/training/session-wizard/StepGeneral.tsx` and the session Zod schema per §10.1–§10.2; tests `SessionCoachesField.test.tsx` + wizard test update → react-ui-engineer · sonnet
- [ ] T067 [P] [US4] Frontend listings and signals per §10.3–§10.4: coach filter on the sessions list and calendar (reuse `CoachFilter` from T036), cancel dialog with reason `Select` (sessions and events, `CancelEventDialog.test.tsx`, `EventDrawer.test.tsx`), "único entrenador inactivo" badge on `SessionsTable` (`SessionsTable.test.tsx`), attendance rows show recorder/last editor (`AttendanceTable.test.tsx`); parent surfaces `ParentSessionCard.tsx` / `ParentSessionDetailPage.tsx` list the coaches by name only → react-ui-engineer · sonnet
- [ ] T068 [US4] Family copy review of the three e-mails and the parent session surfaces (español neutro, diacritics, no clinical language, plural coaches read naturally) → parent-communicator · sonnet

---

## Phase 7: User Story 5 — Two coaches never silently overwrite each other (Priority: P2)

**Goal**: Newsletter saves carry `edit_version`; a stale save gets 409 and a reload action; the coach-note author is visible to coaches only; monthly-report approval evidence survives regeneration.

**Independent Test**: quickstart.md scenarios 8–9 — two browsers on one newsletter: second save gets the conflict dialog and loses nothing; family view shows no coach name; approve a report as A, regenerate as B, both facts visible and audited (SC-006).

- [ ] T069 [US5] `PATCH /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}` per contracts/concurrency-and-approvals.md §2: `If-Match` header or `expected_version` (exactly one), precondition resolution §2.2 (409 stale with `current_version`, 428 missing), version bump and `last_edited_by_user_id` §2.3, `ETag` on reads §1.2, which writes move the version §2.6 (incl. `attach-insights` create path) in `backend/app/routers/athlete_monthly_newsletters.py` → fastapi-architect · opus
- [ ] T070 [P] [US5] Coach-note authorship per §3 (`coach_note_author_id`/`coach_note_updated_at` written on PATCH; exposure matrix §3.2: coach schema only, absent from parent schema, family PDF `backend/templates/documents/pdf/athlete_stage_log.html` and family e-mail `backend/templates/email/athlete_stage_log.html`) and approve/unapprove actor per §4 → fastapi-architect · sonnet
- [ ] T071 [P] [US5] Monthly report approval evidence per §5: `approve` writes `approved_by_user_id`/`approved_at`; `force_regenerate` copies them to `previous_approved_*` before clearing, sets the new `generated_by_user_id`, audits `execute` + `unapprove`; response §5.5 with `ActorRef`s in `backend/app/services/training/reports.py` and `backend/app/routers/monthly_reports.py` → fastapi-architect · sonnet
- [ ] T072 [US5] Backend tests per §9: `backend/tests/routers/test_newsletter_concurrency.py` (409 race, 428 missing, ETag round-trip, version increments, sent newsletter immutable 409), `backend/tests/routers/test_newsletter_coach_note_author.py` (author in coach schema, absent from parent schema/PDF/e-mail), `backend/tests/test_monthly_report_approval_evidence.py` (regression: regenerate after approve keeps `previous_approved_*`; fails on old code), extend `backend/tests/test_newsletter_privacy.py` → qa-engineer · opus
- [ ] T073 [US5] Frontend `frontend/src/routes/training/AthleteNewsletterStudioPage.tsx` per §6: send `If-Match` with the loaded `edit_version`, on 409 open the blocking `AlertDialog` with "Recargar" while keeping the local draft in state until reload, retry guard in the mutation options, coach-note author line (§6.4), copy/a11y/test ids §6.5; tests `frontend/src/routes/training/AthleteNewsletterStudioPage.test.tsx` (extended) → react-ui-engineer · sonnet
- [ ] T074 [P] [US5] Frontend report approval evidence per §7 ("Aprobado por X el D" / "Aprobado previamente por X el D" / legacy "aprobado (sin registro de autor)") in the report detail page; test `frontend/src/routes/training/ReportDetailPage.test.tsx` (extended) → react-ui-engineer · sonnet

---

## Phase 8: User Story 6 — Either coach can act on the club's AI runs and imports (Priority: P2)

**Goal**: One club-scoped rule replaces owner-only guards on runs and import parses; runs show who launched and who decided; spend is visible per coach; budget refusal names the period.

**Independent Test**: quickstart.md scenarios 10–11 — coach A's run awaiting a decision is decided by coach B; coach B commits A's import; other-club coach gets 403; per-coach spend sums to the total (SC-007).

- [ ] T075 [US6] Add the club-resolution helper pair (`run_club_ids`, `import_club_ids`, decision matrix §1.4, fallback for unresolvable club) to `backend/app/services/permissions.py` per contracts/scope-ai-imports.md §1; delete `_ensure_run_owner` and move the seven call sites in `backend/app/routers/race_analysis.py` to the club check (§2); replace the ownership check in `backend/app/routers/race_imports.py:712-721` (§6.1) → fastapi-architect · opus
- [ ] T076 [P] [US6] Persist `agent_runs.decided_by_user_id`/`decided_at` on HITL decisions and expose `requested_by`/`decided_by` `ActorRef`s in `RunStatusResponse`/`HITLDecisionResponse` (§3–§4, additive); fix the two `agent_runs.athlete_id` insert sites (§1.3); `race_imports.committed_by_user_id`/`committed_at` on commit (§6.2) → fastapi-architect · sonnet
- [ ] T077 [P] [US6] `spend_by_user_last_30d` in `backend/app/services/race/ai/budget_guard.py` (§7.1, `COALESCE(requested_by_user_id, generated_by_user_id)`, "Sin atribuir" bucket), additive `by_coach` on `GET /api/race-analysis/admin/ai-usage` widened to coach+admin (§7.2), single budget-refusal formatter used by the four call sites with period and "los análisis en curso terminan" (§8) → fastapi-architect · sonnet
- [ ] T078 [US6] Backend tests per §11: new `backend/tests/test_race_analysis_club_scope.py` (coach B decides A's run 200, cancel/re-execute/PDF by B, other-club 403, unresolvable-club fallback), `backend/tests/test_race_imports_club_scope.py` (B commits A's parse; other-club 403), `backend/tests/test_spend_by_user.py` (per-coach sums equal total, unattributed bucket); update the existing intra-club 403 assertions in `backend/tests/routers/test_race_imports.py:691,714`, `test_race_analysis.py`, `test_race_analysis_cancel.py`, `test_run_staleness_endpoints.py` (§11.2) → qa-engineer · sonnet
- [ ] T079 [P] [US6] Frontend per §4.4 and §7.3: launched-by / decided-by chips on the run views, per-coach spend `Table` section on `frontend/src/routes/admin/AIHealthPage.tsx` with loading/empty/error states and 48 px rows, `/admin/ai` guard widened to coach+admin in `frontend/src/App.tsx:430`; tests extended + jest-axe → react-ui-engineer · sonnet
- [ ] T080 [US6] Security review of the scope change (no cross-club leak through run/parse ids, admin bypass paths, listing vs detail consistency, spend endpoint exposes only amounts and staff names) → security-engineer · opus

---

## Phase 9: User Story 7 — Club-wide and per-coach reports (Priority: P3)

**Goal**: Per-coach activity view for a period; club-wide reports unchanged; author names replace raw ids everywhere.

**Independent Test**: quickstart.md scenario 12 — seeded month reconciles exactly (A: 4 sessions, 2 runs; B: 3 sessions, 1 approval); club-wide monthly report identical to before; every "created by" shows a name (SC-008, SC-009).

- [ ] T081 [US7] Service `backend/app/services/coach_activity.py` and `GET /api/clubs/{club_id}/coach-activity` in `backend/app/routers/audit.py` per contracts/coach-activity-report.md §1–§4 (counting rule §2: a co-coached session counts for each coach, club total counts once; sources §3; RBAC §4; `coach_user_id` optional filter) → fastapi-architect · opus
- [ ] T082 [P] [US7] Tests `backend/tests/test_coach_activity.py` per §9.1 (reconciliation SC-008, period anchoring, parent 403, other-club 403, empty period) and the FR-031 guard `backend/tests/test_monthly_report_unchanged.py` (§9.2: metrics snapshot and section headings for a fixed synthetic month identical before/after) → qa-engineer · opus
- [ ] T083 [P] [US7] Frontend types/schema/api/hooks per §6: `frontend/src/types/coachActivity.types.ts`, `frontend/src/schemas/coachActivity.schema.ts`, `frontend/src/api/coachActivity.ts`, `frontend/src/hooks/governance/{useCoachActivity,useClubStaff}.ts`, MSW `frontend/src/test/msw/coachActivityHandlers.ts` → react-ui-engineer · sonnet
- [ ] T084 [US7] Page `frontend/src/routes/training/CoachActivityPage.tsx` (lazy `/training/reports/actividad-entrenadores`, coach+admin, period + coach selectors cloned from `frontend/src/hooks/activities/useActivityReview.ts` pattern, `StatCard` tiles per coach, link to the filtered club history, states §6.3, copy §6.4, a11y §6.5); tests `CoachActivityPage.test.tsx`, `CoachActivityPage.a11y.test.tsx`; `ReportsListPage` untouched except the link (`ReportsListPage.test.tsx`) → react-ui-engineer · sonnet
- [ ] T085 [P] [US7] `frontend/src/components/audit/ActorChip.tsx` per §7.2 (name, role badge, inactive state, "Sin atribuir") with `__tests__/ActorChip.test.tsx`; replace the raw "Creado por usuario ID" in `frontend/src/components/competitions/tabs/InfoTab.tsx:150-156` (§7.3) and use the chip for evaluated-by / generated-by / approved-by / imported-by surfaces; `InfoTab.test.tsx` updated → react-ui-engineer · sonnet
- [ ] T086 [US7] Integration review of Phases 5–9 on the dev stack: quickstart scenarios 4–12, nav areas per role, bundle sizes of the three new lazy routes ≤ 150 KB gzip, entry chunk not regressed; record in `checklists/integration-review.md` → engineering-lead · opus

---

## Phase 10: User Story 8 — The history is kept for two seasons and purged deliberately (Priority: P3)

**Goal**: 24-month retention with a previewed, confirmed, audited purge; no automatic removal inside the app.

**Independent Test**: quickstart.md scenario 14 — seed entries at 25 and 23 months; dry-run reports 1 and removes nothing; apply removes the 25-month entry only and writes the purge row (SC-010).

- [ ] T087 [US8] Service `backend/app/services/retention.py` per contracts/retention-purge.md §1 (`preview_purge(cutoff)`, `apply_purge(cutoff)` statement order §1.3 in one transaction, purge audit row per distinct `club_id` §1.4 with `meta {"job": "audit_retention", "removed_count", "cutoff"}`, idempotent zero case §1.5) → fastapi-architect · opus
- [ ] T088 [P] [US8] CLI `backend/scripts/retention_audit_log.py` (Typer; dry-run default, `--apply`, `--months 24`, `--cutoff` handover, `--actor-kind`, engine from env by name, stdout JSON contract §2.3, stderr operator log §2.4, exit codes §2.5, refusals §2.6) → fastapi-architect · sonnet
- [ ] T089 [P] [US8] `.github/workflows/audit-retention.yml` per §3 (monthly `schedule` dry-run job always; `apply` job only on `workflow_dispatch` with `confirm=true`, `environment: production` required reviewers, cutoff handover §3.3, secrets by name §3.4 — `AUDIT_RETENTION_DATABASE_URL`); document the Hostinger reachability precondition (§3.5) and leave the schedule dry-run-only until confirmed (plan.md open decisions) → devops-engineer · sonnet
- [ ] T090 [US8] Tests `backend/tests/test_retention.py` per §8.1 (preview removes nothing, apply removes only `< cutoff`, purge row written with count, `cutoff` reuse between steps, zero case, CLI exit codes via `CliRunner`) and confirm `backend/tests/test_audit_append_only.py` (T012) treats `app/services/retention.py` as the single exemption → qa-engineer · sonnet

---

## Phase 11: Polish & cross-cutting concerns

- [ ] T091 Mandatory privacy audit of the whole feature: `audit_log` rows and `diff_json`/`meta_json` allow-lists, parent schemas (newsletter, sessions, calendar) carry no attribution fields, family PDF/e-mail show no coach name, logs carry `request_id` and no bodies, exports audited by type + athlete id only, fixtures synthetic; checklist in `specs/041-multi-coach-governance/checklists/privacy-audit.md` → data-privacy-guard · opus
- [ ] T092 [P] Playwright specs on the isolated e2e stack (now bootable after T001): `frontend/e2e/staff-admin.spec.ts`, `athlete-archive.spec.ts`, `session-coaches.spec.ts` (two browsers, MailHog assertion), `newsletter-conflict.spec.ts`, `coach-activity.spec.ts` per the e2e sections of the contracts → qa-engineer · sonnet
- [ ] T093 [P] Docs: create `docs/19-multi-coach-governance/{design.md,runbook.md,qa.md}` (runbook §5 = purge procedure from contracts/retention-purge.md §6 incl. the "run from the owner's machine" path), append dated entries to `docs/technical-notes.md` (migration, request-id/logging change, scope change on runs/imports, the identified pre-existing migration bug, the `race_events.py` coach-only follow-up) and update `docs/implementation-status.md` → technical-writer · sonnet
- [ ] T094 [P] Draft the privacy-policy v1.3 wording (plural coaches, habeas-data channel in plural, sync `frontend/src/routes/PrivacyPage.tsx` version with the DB) as `docs/19-multi-coach-governance/policy-v1.3-draft.md` — NOT released in this feature (FR-033, spec assumption on consent renewal) → technical-writer · sonnet
- [ ] T095 Run the full gates: `ruff check`, `pytest`, `pytest -m mysql` on a `_test` database, `npm run build`, `npm test`, `npm run test:e2e`; fix regressions; confirm `backend/tests/test_audit_coverage.py` has zero "pending" exemptions → engineering-lead · opus
- [ ] T096 Quickstart walkthrough: execute every scenario of `quickstart.md` on the dev stack with two coaches, record results per SC-001..SC-010 in `checklists/integration-review.md`; SC-002 is the moderated test with the club's coach (manual) → engineering-lead · opus
- [ ] T097 Post-deploy: smoke `/health`, one authenticated endpoint, `GET /api/clubs/{id}/audit-log` as coach, first production `retention_audit_log.py` dry-run from the owner's machine (expected: 0 candidates), confirm `X-Request-Id` in Render logs → release-manager · sonnet
- [ ] T098 PR description with the constitution compliance statement, the FR-010 narrowing and the open operational decisions from `plan.md`, written to `specs/041-multi-coach-governance/pr-description.md` → engineering-lead · opus

---

## Dependencies & execution order

- **Phase 1 → Phase 2 → stories**: T001 unblocks fresh databases (needed by T013/T014 and every e2e); T003/T004 fixtures are used by every story's tests; T005/T006 are needed by T011 and T069.
- **Phase 2 is blocking**: T007 → T015; T008/T009 → T010 → T017/T018/T019; T013 → T014, T016; T020 → T033.
- **US1 (Phase 3)** depends only on Phase 2. T021–T029 can run in parallel; T030 last (closes the coverage exemptions). T031/T032 → T033 → T034; T035/T036 → T037/T038.
- **US2 (Phase 4)** depends on Phase 2 and on T022 (athlete instrumentation). T040 → T042 → T043 → T044; T046 → T047; T048/T049 need T035 (reason codes hook).
- **US3 (Phase 5)** depends on Phase 2 and T021. T051 → T054; T055/T056 → T057 → T058.
- **US4 (Phase 6)** depends on Phase 2 and T024. T059 → T060 → T061/T062/T063/T064 → T065; T066/T067 need T036 (`CoachFilter`) and T055 (`users.ts`).
- **US5 (Phase 7)** depends on Phase 2, T005 (CORS) and T026. T069 → T072/T073; T070/T071 → T072/T074.
- **US6 (Phase 8)** depends on Phase 2 and T027/T028. T075 → T076/T077 → T078 → T080.
- **US7 (Phase 9)** depends on US4 (session coaches), US6 (`committed_by`, `decided_by`) and US1 (history read API). T081 → T082; T083 → T084; T085 needs T055.
- **US8 (Phase 10)** depends on Phase 2 only. T087 → T088/T090; T089 parallel.
- **Polish** after all stories; T091 and T095 gate the PR.

## Parallel execution examples

- **Phase 2**: T011, T012, T014, T015, T017, T018, T019 in parallel once T007–T010 and T013 are in.
- **Phase 3**: two `fastapi-architect · sonnet` workers split T022–T029 by domain while `fastapi-architect · opus` does T021; `react-ui-engineer · sonnet` ×2 do T035/T036 then T037/T038.
- **Phases 4–5** can run concurrently (different routers and pages) after Phase 3's T022 and T021 respectively.
- **Phases 6–8** can run concurrently after their instrumentation tasks; keep one worker per router file to avoid conflicts in `race_analysis.py` and `training_sessions.py`.
- **Phase 9** waits for Phases 6 and 8; Phase 10 can start right after Phase 2.

## Implementation strategy

- **MVP = Phase 1 + Phase 2 + US1**: the second coach can start working with every action attributed and readable. Ship behind no flag — the history endpoints are additive and the instrumentation is invisible to families.
- **Second increment = US2 + US3**: safe removal and self-service onboarding; T002's interim guard buys time until US2 lands.
- **Third increment = US4 + US5 + US6**: truthful family e-mails, no lost edits, one scope rule.
- **Fourth increment = US7 + US8 + Polish**: reporting, retention, docs, PR.
- Commit per phase on `feat/041-multi-coach-governance` (Conventional Commits, Spanish descriptions, no AI mention).

## Model assignment summary

| Model | Tasks |
|---|---|
| opus | T001, T007–T014, T017–T021, T030, T033, T034, T039, T040, T042–T044, T046, T050, T051, T058, T059, T060, T062, T069, T072, T075, T080, T081, T082, T086, T087, T091, T095, T096, T098 |
| sonnet | T002–T006, T015, T016, T022–T029, T031, T032, T035–T038, T041, T045, T047–T049, T052–T057, T061, T063–T068, T070, T071, T073, T074, T076–T079, T083–T085, T088–T090, T092–T094, T097 |
