# Implementation Plan: Multi-coach governance — change log, attribution and per-coach reports

**Branch**: `feat/041-multi-coach-governance` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/041-multi-coach-governance/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

A second coach joins the club with the same club-wide access as the first. The feature adds (1) an append-only, privacy-minimised `audit_log` written in the same transaction as every write and every document export/send through one helper (`app/services/audit.py::record_audit`), with a route-registry coverage test so no write path can ship unaudited; (2) attribution columns (`updated_by`, `deleted_by/deleted_at`, `approved_by/approved_at`, `recorded_by`, coach-note author, `edit_version`) on the tables that lack them, via one `ActorTimestampMixin` and one Alembic revision; (3) soft-delete of athletes that preserves parental-consent evidence and is restorable by admins; (4) a `training_session_coaches` bridge for co-coached sessions plus the acting user threaded into session/attendance/calendar services so family emails name the coach who acted; (5) optimistic concurrency on the newsletter studio (`edit_version` + `If-Match` → 409) and approval evidence that survives regeneration; (6) one club-scoped rule for AI runs and import parses (owner-only guards removed) with AI spend shown per coach; (7) read surfaces — club history, per-athlete history, per-coach activity view, staff admin screen, author names instead of raw ids; (8) a 24-month retention purge as a Typer CLI (dry-run by default, `--apply` opts in), schedulable from GitHub Actions. No new runtime dependency, no background worker.

## Technical Context

**Language/Version**: Python 3.14 (backend venv; `>=3.13` in CI), TypeScript ~6.0 (frontend)

**Primary Dependencies**: FastAPI ≥0.115, SQLAlchemy 2 async over aiomysql, Alembic ≥1.17, Pydantic v2, Typer ≥0.13, Jinja2 (email templates), WeasyPrint/docxtpl (exports, unchanged); React 19.2, react-router-dom 7.14, TanStack Query 5.101, Zustand 5, React Hook Form 7.72 + Zod 4.3, shadcn/ui + Tailwind v4

**Storage**: MySQL 8.4 (Hostinger) in production; aiosqlite in-memory in the default test lane; `mysql` lane for the migration and backfill tests. New table `audit_log`, new bridge `training_session_coaches`, additive nullable columns on 14 existing tables (see `data-model.md` §4)

**Testing**: pytest + httpx.AsyncClient (default offline lane; `-m mysql` for migration/backfill); vitest + Testing Library + MSW + jest-axe; Playwright e2e on the isolated stack introduced by feature 040 (extended with a second-coach factory)

**Target Platform**: Render free tier (single web process, ~50 s cold start, ephemeral disk) + Cloudflare Pages; coach on tablet, admin on desktop, parents on Android

**Project Type**: Web application (FastAPI modular monolith + React SPA)

**Performance Goals**: writes stay within the constitution's p95 ≤ 1500 ms (audit adds one INSERT per write in the same transaction); history and activity reads p95 ≤ 500 ms on indexed single queries with server-side pagination (page ≤ 50 rows); new lazy routes ≤ 150 KB gzip each

**Constraints**: no workers/queues/cron inside the app (retention runs from GitHub Actions); audit rows hold identifiers, column names and catalogue codes only — never a minor's name, birth date, measurements, medical, feedback, note or narrative content (Ley 1581); parents never read the history; append-only enforced in code and by test; every write path must be registered as audited or exempt-with-reason

**Scale/Scope**: 1 club, ~20 athletes, 2 coaches + 1 admin, ~40 parents; 99 write endpoints plus the 9 mutating/exporting GETs — 108 registered routes in the instrumentation matrix (`contracts/audit-recording.md` §4, §4.14) — and 56 explicit commit sites outside `dependencies.py` (`contracts/audit-recording.md` §1.3) to instrument; expected audit volume low thousands of rows per year; 3 new backend read endpoints, 1 CLI, 1 migration, 3 new lazy frontend routes, ~12 modified services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | One recording helper (`record_audit`), one mixin (`ActorTimestampMixin`), one closed registry of entity types/actions/reason codes, one coverage test; existing domain trails (`race_result_revisions`, `race_competitor_link_audit`, `agent_run_events`) are kept and indexed by the new log rather than duplicated (rule of three respected: the fourth trail becomes the generic one); docstrings on `services/audit.py`, `services/retention.py`; `ruff` + `tsc --noEmit` gates. | PASS |
| II. Testing (NON-NEGOTIABLE) | Every contract ends with its required tests: happy + denied paths (parent 403, cross-club coach 403, coach on staff actions 403, inactive login), privacy invariants (allow-list test on `diff_json`, no PII in audit rows or logs, coach-note author absent from parent schema and family PDF), regression tests that fail on unfixed code for the misattributed cancellation email, the lost newsletter edit, the approval evidence lost on regenerate and the `created_by` nulling on parent delete; route-registry coverage test (FR-009); append-only test; two-coaches-same-club fixture as a shared module under `backend/tests/fixtures/`, registered as a pytest plugin (`research.md` R-32, `quickstart.md` §1.5C); jest-axe on the three new pages and the archive/conflict dialogs; migration + backfill tests in the `mysql` lane. | PASS |
| III. UX Consistency | Only shared components (shadcn `Table`, `Select`/`Combobox`, `Sheet`/`Dialog`, `Alert`, `Badge`, `EmptyState`, `ErrorState`); status tokens respected (inactive = neutral gray, archived = amber, conflict = red); 48 px targets; loading/empty/error/retry designed per surface in the UI contracts; all new copy in español neutro with diacritics (history sentences, staff screen, archive reasons, conflict message); no coach name shown to families. | PASS |
| IV. Performance | Audit is one extra INSERT inside the existing transaction; history/activity endpoints are single indexed queries over the five indexes of `data-model.md` §1.1 (`ix_audit_club_time`, `ix_audit_actor_time`, `ix_audit_entity_time`, `ix_audit_athlete_time`, `ix_audit_request_id` for the FR-002/AS5 `request_id` filter of `contracts/audit-log-api.md` §2.1) with server-side pagination and one JOIN for actor names (no N+1; query-count test); listings gain a `coach_user_id` filter on indexed columns; new routes are lazy chunks with no charts. Pre-existing violation: the entry chunk is 336 kB gzip (> 250 kB) — not introduced here, tracked in Complexity Tracking. | PASS (pre-existing debt noted) |
| V. Youth Psych. Safeguards | Not a psychological instrument. Adjacent safeguards honoured: no free text or narrative in audit rows; anxiety-assessment tables (if present) are audited by identifier only, and their read paths are not logged (FR-005 excludes reads). | N/A / respected |
| Quality gate — Privacy | `data-privacy-guard` audit is a mandatory task; allow-list per entity is code + test; actor names resolved by JOIN at read time (never denormalised); parents excluded from every history/activity endpoint; document exports logged by type and athlete id only; policy v1.3 wording drafted but bundled with the next policy release (FR-033). | PASS |
| Quality gate — Stack discipline | No new runtime dependency: Typer is already in `requirements.txt`; `@tanstack/react-table` is NOT added (plain shadcn `Table` with server-side filters suffices for ≤50-row pages); request-id middleware is pure ASGI (Starlette), no `asgi-correlation-id` package. | PASS |
| Quality gate — Observability | Pure-ASGI request-id middleware + `dictConfig` for `app.*` loggers with a `request_id` filter (fixes business logs being dropped under uvicorn); audit rows carry the same `request_id`; no request/response bodies in logs. | PASS |
| Workflow — Branching | Work on `feat/041-multi-coach-governance` (Spec Kit hook, project naming convention). | PASS |

**Post-design re-check (after Phase 1)**: unchanged. The contracts introduce no new dependency, no PII-bearing field, no colour-only status; the only budget item is the pre-existing entry-chunk size. The test-only strict flush detector (Complexity Tracking) adds no production behaviour. One spec-level deviation surfaced in design and is tracked in Complexity Tracking: FR-010's "who last edited it" is discharged by `audit_log` alone — not by a column — on `training_sessions` and the four race/interval tables.

## Project Structure

### Documentation (this feature)

```text
specs/041-multi-coach-governance/
├── plan.md              # This file
├── spec.md              # Feature specification (8 user stories, FR-001..FR-034, SC-001..SC-010)
├── research.md          # Phase 0 — decisions R-01..R-NN with sources (web, Context7, code)
├── data-model.md        # Phase 1 — audit_log, bridge table, attribution columns, migration, state transitions
├── quickstart.md        # Phase 1 — end-to-end validation scenarios per user story
├── contracts/
│   ├── audit-log-api.md             # GET club / athlete history, sentence templates (es), RBAC, GET /api/audit/reason-codes
│   ├── audit-recording.md           # record_audit helper, request context, instrumentation matrix, coverage test
│   ├── athlete-archive.md           # soft-delete/restore, exhaustive filter sites, user delete → 409
│   ├── staff-admin.md               # users/members validation, /admin/usuarios UI
│   ├── session-coaches.md           # bridge table API, wizard, acting-coach emails, attendance attribution, calendar cancel/delete (FR-017)
│   ├── concurrency-and-approvals.md # edit_version + If-Match → 409, coach-note author, approval evidence
│   ├── scope-ai-imports.md          # club-scoped runs/imports, spend per coach, budget message
│   ├── coach-activity-report.md     # per-coach activity endpoint + UI, author chips, history pages
│   └── retention-purge.md           # Typer CLI, GitHub Actions monthly, append-only invariant
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── <rev>_multi_coach_governance.py        # audit_log, training_session_coaches, attribution columns, backfills
├── app/
│   ├── main.py                                # request-id ASGI middleware, dictConfig for app.* loggers
│   ├── models/
│   │   ├── mixins.py                          # ActorTimestampMixin (new)
│   │   ├── audit_log.py                       # AuditLog, AuditAction, AuditActorKind, AuditEntityType, AuditReasonCode + its 5 sub-enums, AuditReasonGroup (new)
│   │   ├── training_session.py                # TrainingSessionCoach (new), SessionAttendance attribution
│   │   ├── athlete.py, user.py, calendar_event.py, athlete_newsletter.py, athlete_ai_insight.py,
│   │   ├── session_media.py, anthropometry.py, race_import.py, race_series.py, club_project_profile.py,
│   │   └── club.py, agent_run.py              # additive attribution columns
│   ├── schemas/
│   │   ├── audit.py                           # AuditEntryOut, AuditListOut, AuditReasonCodeListOut, CoachActivityOut (new)
│   │   ├── user.py, club.py                   # club_id required for staff roles, membership role coherence
│   │   ├── training_session.py, calendar.py, athlete_newsletter.py, athlete.py  # coaches[], attribution, edit_version, archive reason
│   ├── services/
│   │   ├── audit.py                           # record_audit, compute_changed_fields, ALLOW_LIST, AUDITED/EXEMPT registry (new)
│   │   ├── request_context.py                 # request_id ContextVar + dependency (new)
│   │   ├── retention.py                       # purge preview/apply (new)
│   │   ├── coach_activity.py                  # per-coach aggregation (new)
│   │   ├── permissions.py                     # can_view_audit, club-scoped run/parse checks
│   │   ├── training/{sessions,attendance,reports}.py, calendar/events.py, race/ai/budget_guard.py,
│   │   └── notification/*                     # acting-coach templates, export/send audit hooks
│   ├── routers/
│   │   ├── audit.py                           # /clubs/{id}/audit-log, /athletes/{id}/audit-log, /clubs/{id}/coach-activity, /audit/reason-codes (new)
│   │   ├── athletes.py, users.py, clubs.py, training_sessions.py, calendar.py,
│   │   ├── athlete_monthly_newsletters.py, monthly_reports.py, race_analysis.py, race_imports.py, ai.py
│   │   └── (instrumented per contracts/audit-recording.md)
│   └── templates/email/training_session_{invite,updated,cancelled}.html   # coaches list + acting coach
├── scripts/retention_audit_log.py             # Typer CLI (new)
└── tests/
    ├── fixtures/                              # shared two-coaches-same-club fixture module (research.md R-32)
    ├── conftest.py                            # registers it in `pytest_plugins`, next to `tests.fixtures.race_groups`
    ├── test_audit_*.py, test_retention.py, test_coach_activity.py, test_staff_admin.py (new)
    └── (existing router/service tests updated per contracts)

frontend/src/
├── api/{users,audit,coachActivity}.ts         # new API modules
├── hooks/governance/{useAuditLog,useCoachActivity}.ts, hooks/admin/{useStaff,useArchivedAthletes}.ts   # per-domain hook folders (repo convention)
├── routes/admin/{StaffPage,ArchivedAthletesPage}.tsx        # lazy, admin-only (/admin/usuarios, /admin/atletas-archivados)
├── routes/admin/ClubHistoryPage.tsx                        # lazy, coach+admin (/club/historial, nav area `gobierno`)
├── routes/training/CoachActivityPage.tsx                   # lazy
├── routes/training/AthleteNewsletterStudioPage.tsx         # expected_version + conflict Alert
├── routes/athletes/AthleteFormPage.tsx                     # "Archivar atleta" dialog with reason
├── components/athletes/AthleteHistoryPanel.tsx             # per-athlete history (coach/admin)
├── components/audit/{AuditEntryRow,ActorChip,CoachFilter}.tsx
├── components/training/SessionCoachesField.tsx             # multi-select in the wizard
├── components/competitions/tabs/InfoTab.tsx                # ActorChip replaces raw id
└── App.tsx, components/layout/*                            # routes + nav entries by role

.github/workflows/audit-retention.yml          # monthly dry-run + manual apply
docs/19-multi-coach-governance/{design,runbook,qa}.md, docs/technical-notes.md, docs/implementation-status.md
```

**Structure Decision**: web application, existing monorepo layout (`backend/app/{models,schemas,services,routers}` + `frontend/src/{api,hooks,routes,components}`). New code follows the modular-monolith convention (router → service → model); the audit helper lives in `services/` and is called by services, never by routers directly, so the same rule applies to CLI and webhook callers.

## Phase 0 — Research (complete)

See [research.md](research.md). Sources: web best-practice sweep (audit-log design and data minimisation, soft-delete, optimistic concurrency RFC 9110, staff deactivation), Context7 documentation (SQLAlchemy 2 async sessions and flush events, FastAPI/Starlette ASGI middleware and dependencies, Alembic batch operations on MySQL, Python logging under uvicorn, TanStack Query v5 mutation errors, shadcn table/combobox, react-router 7 lazy routes, Zod conditional validation) and three code inventories (write paths and commit sites, domain patterns to reuse, frontend/test/e2e/CI). All Technical Context unknowns are resolved; none remain as NEEDS CLARIFICATION.

Key decisions (details and alternatives in research.md):

- **Explicit helper in the same transaction**, not an ORM flush listener (blind to ~30 Core `delete()/update()` statements incl. athlete/user deletion, and to business intent) and not DB triggers/CDC (no authenticated user, breaks the sqlite lane, stores raw values). A test-only strict flush detector guards the discipline.
- **Request context** via a pure-ASGI request-id middleware + ContextVar; actor passed explicitly from service signatures; automated callers use `actor_kind` without a user.
- **Soft-delete by columns with explicit per-site filtering**, not a global loader criterion (admins must still see archived athletes; historical counts must keep them).
- **Bridge table for co-coaches**, min-1 in the service layer, backfilled from the creator; attendance attribution independent of session coaches.
- **`edit_version` + `If-Match`** for the newsletter studio; the retired `content_version` name is not reused.
- **Club-scoped rule for AI runs and imports**; budget stays global, spend reported per coach.
- **Retention as Typer CLI + GitHub Actions**, mirroring `strava-reconcile.yml`; purge is itself audited.
- **No new dependency**: plain shadcn `Table`, no `@tanstack/react-table`; no correlation-id package.

## Phase 1 — Design (complete)

- [data-model.md](data-model.md): `audit_log` (columns, five indexes — four composite plus the single-column `ix_audit_request_id` — append-only invariants, allow-list), catalogues (`AuditAction`, `AuditActorKind`, `AuditEntityType`, `AuditReasonCode`), `training_session_coaches`, attribution columns per table with what already exists, `ActorTimestampMixin`, the single Alembic revision (down_revision `2a8baa967cc6`) with idempotent backfills, state transitions (athlete active → archived → restored; newsletter draft/approved/sent with `edit_version`; monthly report approval evidence on regenerate), key queries and the no-double-count rule.
- [contracts/](contracts/): nine contracts listed above; each fixes request/response schemas, RBAC, exact code sites (`path:line`), Spanish copy, and the required tests.
- [quickstart.md](quickstart.md): prerequisites (two coaches in one club), commands, and one validation scenario per user story mapped to SC-001..SC-010, including the dry-run purge, the 409 conflict, the acting-coach email in MailHog, the archived athlete invisible to the parent, and the audit privacy scan.
- Agent context: the managed block in `CLAUDE.md` is refreshed to point at this plan.

## Phase 2 — Task generation (next: `/speckit-tasks`)

Ordering to encode in `tasks.md`:

0. **Unblock (pre-existing bugs, S)**: make the three migrations that import deleted modules boot on a fresh database (`e1f2a3b4c5d6_technique_gymkhana_library.py:276`, `f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py:60`, `a7b8c9d0e1f2_strength_training_library.py:284` → `app.data.technique_catalog` / `app.data.strength_catalog` no longer exist; research.md R-34) — this is the "pre-existing migration bug" that blocked feature 040's Playwright specs; add an interim admin-only guard on `DELETE /api/athletes/{id}` until US2 lands.
1. **Setup**: `ActorTimestampMixin`, request-id middleware + `dictConfig`, `audit_log` model + `record_audit` + registries + coverage test skeleton, Alembic revision with backfills (mysql-lane test), two-coaches fixture (shared module under `backend/tests/fixtures/`, registered in `pytest_plugins`), second-coach e2e factory.
2. **US1 history**: instrument the five governance actions first (athlete archive, parent delete, calendar permanent delete/cancel, account state/role), then the remaining domains per the instrumentation matrix, then export/send hooks, then the read endpoints, then `ClubHistoryPage` + `AthleteHistoryPanel`.
3. **US2 archive**: soft-delete columns, exhaustive filter sites + the "archived athlete is invisible everywhere" test, restore, attendance archiving, user delete → 409, archive dialog.
4. **US3 staff**: `club_id` required, membership coherence, list/deactivate, `StaffPage`, nav guard.
5. **US4 sessions**: bridge table API, wizard field, acting user in services, email templates, attendance attribution, coach filters, inactive-only-coach flag.
6. **US5 concurrency/approvals**: `edit_version` + 409, coach-note author (coach schema only), monthly report approval evidence, studio conflict UX.
7. **US6 scope/spend**: replace owner guards with club checks (update tests), `decided_by`, spend per coach on the AI page, budget message.
8. **US7 reporting**: `coach_activity` service + endpoint, `CoachActivityPage`, `users.ts`, `ActorChip` replacing raw ids, reconciliation test (SC-008), club-wide report snapshot test (SC-009).
9. **US8 retention**: CLI, GitHub Actions workflow, append-only tests.
10. **Polish**: `data-privacy-guard` audit, docs (`docs/19-multi-coach-governance/`, technical-notes, implementation-status), policy v1.3 wording draft, quickstart walkthrough, post-deploy smoke.

## Open operational decisions (owner)

| Decision | Recommendation | Why it matters |
|---|---|---|
| Scheduled purge reachability: GitHub-hosted runners have rotating IPs and Hostinger MySQL is IP-allowlisted (`docs/10-race-results/runbook-ops.md`), so the monthly Actions job may not reach the database. | Ship the CLI and runbook; run the monthly purge from the owner's machine (which already reaches prod for the newsletter PDF skill); keep `audit-retention.yml` as `workflow_dispatch` dry-run-only until reachability is confirmed. | FR-030 is satisfied by the CLI + documented procedure; the schedule is a convenience, not a requirement. |
| Family e-mail wording "El entrenador {nombre}" is gendered (spec FR-025 states it that way). | Keep as specified for this feature; revisit copy when the second coach's profile is known. | Changing product copy is a separate, cheap task; not blocking. |
| `backend/app/routers/race_events.py:606-609,700-703` are coach-only and 403 an admin, unlike every other mutation there. | Out of scope; log as follow-up in `docs/technical-notes.md`. | Pre-existing inconsistency, unrelated to attribution. |
| Approval backfill: `monthly_reports.approved_at` is backfilled from `generated_at` for approved rows, `approved_by_user_id` left NULL (data-model.md §6.3 B2). | Accept: never fabricate an approver; UI shows "aprobado (sin registro de autor)" for legacy rows. | Ley 1581 responsibility demonstrated with true data only. |

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

The third row is not a constitution violation: it is a deliberate narrowing of a spec
requirement (FR-010), recorded here so it is visible at plan and PR review time instead of
living as an open point inside one contract.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Entry chunk 336 kB gzip > 250 kB budget (pre-existing, not introduced by this feature) | Carried from earlier features; this feature adds only lazy routes and must not regress it (bundle check in the build gate). | Reducing the entry chunk is a separate refactor (already noted in feature 040); bundling it here would widen scope. |
| Test-only strict flush detector (`AUDIT_STRICT=true` in the test lane) alongside the explicit helper | The explicit helper is discipline-based; the detector makes a forgotten `record_audit` call fail fast in tests, complementing the route-registry coverage test. | A pure ORM listener as the *recording* mechanism was rejected (blind to Core statements and business intent); a registry test alone cannot catch a service that mutates a second table without recording it. |
| **FR-010 narrowed** (spec requirement, not a constitution principle): no `updated_by_user_id` column on `training_sessions` (`backend/app/models/training_session.py:63`), `race_events` (`race_event.py:79`), `race_event_roster` (`race_event_roster.py:61`), `interval_structures` and `interval_templates` (`interval_structure.py:107`, `:248`). All five keep `created_by_user_id` and `updated_at`; only the last-editor **actor** is absent, and is answerable from `audit_log` alone. | These five are coach-internal planning records with no author surface: FR-013's "shows the person's name" list is created / evaluated / generated / approved / imported by, never "last edited by", and no screen in `contracts/session-coaches.md` or `contracts/coach-activity-report.md` renders a last-editor chip for them. Every mutating endpoint on all five is instrumented in the same transaction as the write (`contracts/audit-recording.md` §4.5 for the session deleted with its calendar event, §4.6, §4.10, §4.11), so "who last edited this?" is one indexed `audit_log` query (`ix_audit_entity_time`, `data-model.md` §1.1) on the per-club and per-athlete history this feature already ships. Accepted cost, stated so the owner can reverse it: the actor takes a history lookup instead of a column read, and it is gone once the 24-month purge (FR-030) removes the entry. | Adding the five nullable FKs is cheap DDL (`UpdatedByMixin` already exists, `data-model.md` §5) but not free: each one must then be *set on every write path*, and a path that forgets it yields a column that silently disagrees with the log — a second source of truth for a fact the log already holds, which is the redundant copy `data-model.md` §4.3 rejects for `archived_by_user_id` on the same grounds. Rejected while no reader exists; revisit with the first "última edición por" surface designed for a session, a race event or an interval structure. |
