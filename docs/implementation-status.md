# Implementation Status — Full History

> Detailed per-module implementation history for the Club Trocha y Ruta backend/frontend.
> Moved out of `CLAUDE.md` (2026-06-09) to keep the always-loaded project memory lean.
> `CLAUDE.md` keeps only a short pointer + active-work summary; the full step tables live here.

## Implementation status (Phase 1)

| Step | Description | Status |
|---|---|---|
| 1 | FastAPI monolith scaffolding | ✅ Complete |
| 2 | SQLAlchemy models + Alembic migration + seed | ✅ Complete |
| 3 | JWT authentication | ✅ Complete |
| 4 | CRUD clubs and users | ✅ Complete |
| 5 | CRUD athletes + PHV Mirwald | ✅ Complete |
| 6-8 | React frontend | ⏳ Pending |
| 9 | Docker Compose | ✅ Complete (together with Step 2) |
| 10 | Tests | ⏳ Pending |

## Implementation status — Training Sessions Module (Phase 1.5)

> Backend + Frontend + Tests + AI: complete. Deployment pending user approval.

| Step | Description | Status |
|---|---|---|
| 1 | SQLAlchemy models: TrainingSession, SessionAttendance, MonthlyReport + 3 enums | ✅ Complete 2026-05-06 |
| 2 | Pydantic schemas + RBAC permissions (`can_view_session`, `can_edit_session`, etc.) | ✅ Complete 2026-05-06 |
| 3 | Service layer: sessions, attendance, metrics, reports, route_files | ✅ Complete 2026-05-06 |
| 4 | Session CRUD routers (7 endpoints /training-sessions/*) | ✅ Complete 2026-05-06 |
| 5 | Attendance endpoints + .gpx upload (gpxpy + defusedxml anti-XXE) | ✅ Complete 2026-05-06 |
| 6 | Backend tests: models, service, router, privacy, notifications (669 collected) | ✅ Complete 2026-05-06 |
| 7 | Parent notification when planning a session (template training_session_invite) | ✅ Complete 2026-05-06 |
| 8 | AI monthly report use case (guardrails: no names, max 500 words, no individual judgment) | ✅ Complete 2026-05-06 |
| 9 | Monthly report endpoint + email to club (4 endpoints /clubs/{id}/monthly-reports) | ✅ Complete 2026-05-06 |
| 10 | Coach frontend: session list + form (SessionsListPage, SessionFormPage) | ✅ Complete 2026-05-06 |
| 11 | Coach frontend: detail + attendance + rubric (AttendanceTable, RubricSliders, RouteViewer) | ✅ Complete 2026-05-06 |
| 12 | Coach frontend: monthly report UI (ReportsListPage, ReportDetailPage, AI banner) | ✅ Complete 2026-05-06 |
| 13 | Parent frontend: filtered session read + own monthly summary (no other athletes' data) | ✅ Complete 2026-05-06 |
| 14 | Frontend tests: 717 vitest tests (58 files, 0 a11y violations) | ✅ Complete 2026-05-06 |
| 15 | E2E checklist + deploy artifacts + docs + Alembic fork fix | ✅ Complete 2026-05-06 |

## Implementation status — Session Media Module (Phase 1.6)

> Photo and video upload to sessions. Storage on Hostinger SFTP (local fallback in dev). Privacy filtering for parents by intersection with tagged athletes.

| Step | Description | Status |
|---|---|---|
| 1 | `SessionMedia` model + M:N `session_media_athlete` + `MediaType` enum | ✅ Complete 2026-05-16 |
| 2 | Pydantic schemas with mandatory `consent_ack` + restricted parent view | ✅ Complete 2026-05-16 |
| 3 | `media_files.py` service: magic bytes, strip EXIF (Pillow), thumbnails; `storage_sftp.py` Paramiko wrapper + local fallback | ✅ Complete 2026-05-16 |
| 4 | 4 CRUD media endpoints with RBAC + called-up athlete validation | ✅ Complete 2026-05-16 |
| 5 | Permissions: `can_view_session_media` + `filter_media_for_parent` | ✅ Complete 2026-05-16 |
| 6 | Alembic migration `d7f1a2b3c4e5` (2 tables + enum + indexes) | ✅ Complete 2026-05-16 |
| 7 | Frontend: `MediaGallery` + `MediaUploadZone` with Ley 1581 banner + integration in coach/parent detail pages | ✅ Complete 2026-05-16 |
| 8 | Tests: 21 backend (magic bytes, EXIF strip, schemas, filtering) + 10 frontend (API + UploadZone) | ✅ Complete 2026-05-16 |
| 9 | Deploy: configure `HOSTINGER_SFTP_*` and `HOSTINGER_PUBLIC_BASE_URL` in Render | ⏳ Pending |

## Implementation status — Copa Valle Results Module (Phase 1.7)

> Ingestion and analysis pipeline for official Copa Valle XCO PDFs (RESULTADOS + GENERAL). Fuzzy normalization of names/clubs, transactional persistence in MySQL, longitudinal analytics (progression, podium gap, club ranking, projection). Ingestion is operated through the web Import Wizard (Competitions module, `/api/race-analysis/imports/*`).

| Step | Description | Status |
|---|---|---|
| 0 | Bootstrap: `data-analyst` agent, `services/race/` and `docs/10-race-results/snapshots/` folders, deps (`pdfplumber`, `rapidfuzz`, `pandas`, `Unidecode`, `typer`) | ✅ Complete 2026-05-19 |
| 1 | Closed technical design: 26 categories mapped, edge cases documented, TyR Válida IV oracle | ✅ Complete 2026-05-19 |
| 2 | SQLAlchemy models: `race_event` (+weather), `race_category`, `rider`, `race_result`, `race_series`, `race_points_scheme`, `race_import`, `race_result_revision` + 8 enums + delta migration `64c263edd07f` + `season_standings` view + 26-category seed | ✅ Complete 2026-05-19 |
| 3 | `pdf_parser.py` + `normalizer.py` (`is_trocha_y_ruta` with length guard for `partial_ratio`, `parse_time` returns ms, not seconds) | ✅ Complete 2026-05-19 |
| 4 | `matcher.py` (rapidfuzz top-3 with category boost) + `ingestor.py` (transactional, idempotent via SHA256 in `RaceImport`) + `FakeAsyncSession` for tests | ✅ Complete 2026-05-19 |
| 5 | `analytics.py`: 4 functions (`athlete_progression`, `podium_gap`, `club_ranking`, `projection`) — flat queries + pandas, confidence:low if n<5 | ✅ Complete 2026-05-19 |
| 6 | ~~Typer CLI `scripts/ingest_race.py`~~ — **removed**; ingestion runs through the web Import Wizard (`routers/race_imports.py`: `parse → dry-run → commit`) over the same `services/race/` layer | ✅ Superseded 2026-06-09 |
| 7 | Test plan + Válida IV PDF fixtures: 305 green tests in 25.25s, 98% coverage in `services/race/` | ✅ Complete 2026-05-19 |
| 8 | Minors privacy audit: 0 critical/high findings, fixture policy documented, conservative privacy default | ✅ Complete 2026-05-19 |
| 9 | Válida IV dry-run backfill (V-I/II/III pending coach PDFs) | ✅ Complete 2026-05-19 |
| 10 | Docs + completion report + CLAUDE.md/README docs update | ✅ Complete 2026-05-19 |

> V-I/II/III backfill pending official PDFs; real ingest against MySQL Hostinger pending coach approval.

### UI Extension — Race conditions (2026-05-26)

> Optional environmental capture (weather, temperature, surface, altitude, notes) in the UI. No Alembic migration: columns already exist in `race_events` since Step 2 (`64c263edd07f`). Technical detail in `docs/10-race-results/upload-design.md` §14.

| Step | Description | Status |
|---|---|---|
| E1 | Schemas: `RaceEventConditionsUpdate`, `RaceEventConditionsRead`, `ImportParseRequestFields` (5 optional fields) in `app/schemas/race_imports.py` | ✅ Complete 2026-05-26 |
| E2 | `POST /api/race-analysis/imports/parse` extended with 5 optional form fields; Decimal bug in `ValidationError.errors()` fixed (HTTP 500 → 422) via `jsonable_encoder` | ✅ Complete 2026-05-26 |
| E3 | New endpoint `PATCH /api/race-analysis/race-events/{race_event_id}/conditions` (RBAC coach+admin, partial update with `exclude_unset=True`, log keys only) | ✅ Complete 2026-05-26 |
| E4 | Frontend wizard Step 1: "Race conditions (Optional)" section with ToggleGroup chips (≥48px), auto-altitude from `VENUE_ALTITUDES` (7 Copa Valle venues), neutral toast if proceeding empty, `noValidate` on form (fix HTML5 vs Zod) | ✅ Complete 2026-05-26 |
| E5 | `RaceConditionsCard` (tri-state: Complete ≥4 / Partial 1-3 / Empty 0, no warning language) + `EditConditionsDialog` (lazy lateral Sheet, RHF+Zod, PATCH on save) | ✅ Complete 2026-05-26 |
| E6 | TS types + API client + hook: `raceEvents.types.ts`, `api/raceEvents.ts::updateRaceEventConditions`, `hooks/race/useRaceEventConditions.ts::useUpdateRaceEventConditions` (mutation with invalidation) | ✅ Complete 2026-05-26 |
| E7 | Tests: 27 backend (16 PATCH + 11 extended parse) + 55 frontend (vitest + 5 a11y axe) | ✅ Complete 2026-05-26 |
| E8 | Privacy audit X1 — APPROVED WITH CONDITIONS: 3 placeholders corrected (1 HIGH real name `revision_reason` pre-existing + 2 MEDIUM `weather_notes` placeholders without privacy guidance) | ✅ Complete 2026-05-26 |
| E9 | Commit + deploy Render | ⏳ Pending |

### Competitions Module (Phase 1.7+/1.8) (2026-05-27)

> CRUD for `race_events` to manage the Copa Valle rounds lifecycle: plan before the PDF, edit metadata, associate with calendar, launch import wizard, and cancel. No Alembic migration (`RaceEventStatus.CANCELLED` and all columns already existed). Technical detail in `docs/10-race-results/competitions-module.md`.

| Step | Description | Status |
|---|---|---|
| CB1 | Backend: 5 endpoints in `app/routers/race_events.py` (GET list with filters + derived flags, GET detail with `has_calendar_event`, POST create empty, PATCH metadata, DELETE admin-only with dependency guards). Endpoint `PATCH /{id}/conditions` already existed (Phase 1.7+). | ✅ Complete 2026-05-27 |
| CB2 | Pydantic v2 schemas in `app/schemas/race_event.py` (Create/Update/Read/ListItem/ListResponse + `ConditionsCompleteness` Literal) + `app/services/race_events.py` service with 422/409 guards + 32 tests in `tests/routers/test_race_events_crud.py` (0 regressions, 834 total green race tests) | ✅ Complete 2026-05-27 |
| CF1 | Codemod: `components/ai/ImportWizard.tsx` → `components/competitions/import/ImportWizard.tsx` (+ `RaceUploadZone`, `DiffTable`, tests). 4 imports updated | ✅ Complete 2026-05-27 |
| CF2 | `api/raceEvents.ts` extended (get/create/update/delete/list) + `hooks/race/useRaceEvents.ts` with query keys + cross-invalidations raceEvents↔calendar + `test/msw/raceEventsHandlers.ts` | ✅ Complete 2026-05-27 |
| CF3 | "Competitions" sidebar between Newsletters and AI Analysis. 6 routes in `App.tsx` (`/competitions`, `/new`, `/import`, `/:id`, `/:id/edit`, `/:id/import`) with `ProtectedRoute allowedRoles=[coach, admin]` (parent → 403) | ✅ Complete 2026-05-27 |
| CF4 | `CompetitionsListPage` (desktop table + mobile cards, filters, tri-state badges, kebab actions, DELETE admin-only) + `CompetitionFormPage` (RHF+Zod, create/edit, auto-altitude `VENUE_ALTITUDES`, 409 inline, `?returnTo`) + `CompetitionFiltersBar` + `CompetitionStatusBadges` | ✅ Complete 2026-05-27 |
| CF5 | `CompetitionDetailPage` with header + 5 URL-driven tabs (`?tab=info|results|conditions|athletes|insights`) in `components/competitions/tabs/`. Lazy `AthletesTab` and `InsightsTab`. Mechanical refactor without touching `RaceAnalysisPage` or `ClubInsightsByRacePage` | ✅ Complete 2026-05-27 |
| CF6 | `CompetitionImportPage` with mounted wizard (with/without `:id`) + `EventForm` with `prefillRaceEventId` + inline "Create new round" link + `EventFormPage` reads `?race_event_id` + "Associate to calendar" button in detail when `has_calendar_event=false` | ✅ Complete 2026-05-27 |
| CF7 | Frontend tests: 69 new vitest (1682 total) + 4 a11y axe (0 violations). 2 post-CF7 fixes: URL `/calendar/new` → `/calendar/events/new`, `navigate` in `useEffect` (avoids setState during React 19 render) | ✅ Complete 2026-05-27 |
| CX1 | Competitions module privacy audit | ✅ APPROVED with 1 correction (open-redirect `?returnTo`) 2026-05-27 |
| CX2 | Docs (`competitions-module.md` + CLAUDE.md + README) | ✅ Complete 2026-05-27 |
| CX3 | Commit + deploy Render | ⏳ Pending |

## Implementation status — Individual Monthly Newsletter Module (Phase 1.8)

> Monthly delivery to parents (HTML email + PDF attachment) with longitudinal metrics, AI coach narrative, and anthropometry. Multi-child: groups newsletters for multiple children in a single email with N PDFs. Full anthropometry ONLY in the PDF (never in the email body).

| Step | Description | Status |
|---|---|---|
| 1 | SQLAlchemy models: `AthleteMonthlyNewsletter`, `AthleteBadge`, M:N `parent_athlete_newsletter` + 3 enums (`NewsletterStatus`, `BadgeType`, `BadgeSource`) + migration `a1b2c3d4e5f7` | ✅ Complete 2026-05-24 |
| 2 | Pydantic schemas with strict privacy contract: `sent_to`/`pdf_only_blocks`/`pdf_storage_url` NEVER in response; replaced by `has_pdf: bool` | ✅ Complete 2026-05-24 |
| 3 | `badge_evaluator`: attendance thresholds (100/≥90/≥75) + competitive badges (first podium, MTP, Top 10), idempotent by period | ✅ Complete 2026-05-24 |
| 4 | `newsletter_builder`: orchestrates 10 data blocks, strictly separates `email_blocks` (no anthropometry) vs `pdf_only_blocks` (with anthropometry) | ✅ Complete 2026-05-24 |
| 5 | AI use case `athlete_monthly_newsletter_v1` with guardrails (dynamic forbidden_names from DB, MAX_WORDS per block, medical term wording). Property tests verify real name never appears in output | ✅ Complete 2026-05-24 |
| 6 | `assert_ai_consent_for_newsletter` (Ley 1581 Art. 9): blocks generation with HTTP 409 if consent is missing | ✅ Complete 2026-05-24 |
| 7 | 4 Jinja SVG macros for longitudinal charts (positions, gap%, cumulative points, projection with confidence band) + A4 PDF template with header, anthropometry, charts, and Ley 1581 footer | ✅ Complete 2026-05-24 |
| 8 | `newsletter_dispatcher`: groups by parent, attaches N PDFs, idempotent, blocks send if sibling is still draft (escape `force_individual`) | ✅ Complete 2026-05-24 |
| 9 | Router with 8 endpoints + batch creation (`/api/athletes/{id}/monthly-newsletters/*` and `/api/clubs/{id}/monthly-newsletters/batch`), RBAC coach/admin, controlled state transitions | ✅ Complete 2026-05-24 |
| 10 | Privacy audit: 3 HIGH findings resolved (`error_message` closed catalog, `pdf_storage_url` removed from schema, email subject without minor's name) + 2 MEDIUM (email regex in dispatcher, anthropometry defense) | ✅ Complete 2026-05-24 |
| 11 | Backend tests: 137 green (123 functional + 14 privacy invariants consolidated in `test_newsletter_privacy.py`) | ✅ Complete 2026-05-24 |
| 12 | TS types + API client + 8 TanStack Query hooks with `userId` in query keys (Privacy R2) + MSW handlers and fixtures | ✅ Complete 2026-05-24 |
| 13 | Frontend dashboard `/training/athlete-newsletters`: month/year selector, badge × status grid, filters, batch generate modal with created/skipped/failed summary | ✅ Complete 2026-05-24 |
| 14 | Frontend detail `/training/athlete-newsletters/:athleteId/:newsletterId`: 2-column layout, `NewsletterPreviewBlocks`, `NewsletterNarrativeEditor` (RHF+Zod, 500 chars, confidence tooltip), approve/send/download PDF buttons, sibling-blocking dialog with `force_individual` | ✅ Complete 2026-05-24 |
| 15 | Frontend tests: 1295 green tests (81 new from module + 6 a11y with jest-axe, 0 violations). `BadgesBlockView` hides the block when there are no badges (do not reinforce negative comparisons in minors) | ✅ Complete 2026-05-24 |
| 16 | Deploy to Render | ⏳ Pending |

> Deployment pending coach approval and merge to `main`. Alembic migration verified in SQLite via tests (chained to `f9a0b1c2d3e4`).

## Implementation status — Monthly Technical Report Module (Phase 1.9)

> Refactor of the "Club Monthly Report" (Phase 1.5) into a **Monthly Technical Report** styled as a funder report. Structured document by chapters with club project profile (1:1), AI pre-drafted narrative by blocks that the coach edits and approves, month's podiums (Copa Valle), and restricted-distribution PDF (coach/admin). High-Performance Group only; "Population Served" section OMITTED; no program segmentation. Technical detail in `docs/11-informe-tecnico-mensual/`. Migration chained to head `c6d7e8f9a0b1` → `d4e5f6a7b8c9`.

| Step | Description | Status |
|---|---|---|
| 1 | `ClubProjectProfile` model (1:1 club) + `monthly_reports` columns (`narrative_blocks` JSON, `competition_results` JSON, `status` draft/approved) + `training_sessions` (`session_kind` enum, `objectives`) + `SessionKind`/`MonthlyReportStatus` enums + migration `d4e5f6a7b8c9` | ✅ Complete 2026-06-03 |
| 2 | Pydantic schemas (`ClubProjectProfile*`, `NarrativeBlock`, `CompetitionResultItem`, `MonthlyReportBlocksUpdate`, `ALLOWED_BLOCK_KEYS`) + `reports.py` services (update/regenerate blocks) + `competition_results.py` helper (club's month podiums, degrades to `[]`) | ✅ Complete 2026-06-03 |
| 3 | AI per block: `MonthlyReportBlocksUseCase` + `monthly_report_blocks.j2` prompt (6 narrative blocks, word limits per block, independent fallback per block). Reuses `MonthlyReportGuardrails` (no real names, no medical terms); AI never receives names or `competition_results` | ✅ Complete 2026-06-03 |
| 4 | Router: `project-profile` CRUD (GET/PUT/PATCH), `PATCH .../monthly-reports/{year}/{month}/blocks`, `POST .../blocks/{block_key}/regenerate`, `GET .../pdf` with technical template. RBAC coach/admin; parent view without blocks/competition | ✅ Complete 2026-06-03 |
| 5 | PDF: `training_monthly_technical_report.html` template (institutional cover page, context, territory, group activities, competition+podiums, joint activities, material support, group analysis, conclusions, photographic record) + `TRAINING_MONTHLY_TECHNICAL_REPORT` registration. DRAFT banner if `draft` + Ley 1581 restricted distribution notice | ✅ Complete 2026-06-03 |
| 6 | Frontend: `ReportDetailPage` block editor (generate/regenerate AI, edit, approve, download PDF) + `ProjectProfilePage` + status badges + `session_kind`/`objectives` fields in session form + types/API/hooks (`useProjectProfile`, `useUpsertProjectProfile`, `useUpdateReportBlocks`, `useRegenerateBlock`) | ✅ Complete 2026-06-03 |
| 7 | Privacy: AI never emits names; parents do not receive `narrative_blocks`/`competition_results`; minors' names in PDF (podiums/attendance) as deliberate exception for controlled external document, gated by RBAC + approval + notice | ✅ Complete 2026-06-03 |
| 8 | Tests: 52 targeted green backend + 1742 green frontend vitest + clean `tsc` | ✅ Complete 2026-06-03 |
| 9 | Docs: `docs/11-informe-tecnico-mensual/` (`workflow.md`, `design.md`, `runbook.md`) + CLAUDE.md + README docs | ✅ Complete 2026-06-03 |
| 10 | Deploy to Render | ⏳ Pending |

> Deployment pending user approval. Migration verified in SQLite via tests.

## Implementation status — Password Reset Module (specs/003-password-reset-login)

> Self-service password recovery from the login page. URL token by email, stored
> SHA-256-hashed, single-use, 1h expiry. Enumeration-safe (identical neutral message +
> async email for constant timing), per-email rate limit (no Redis), no auto-login,
> confirmation email. OWASP Forgot Password Cheat Sheet alignment. No new dependencies.
> Spec/plan/research/tasks under `specs/003-password-reset-login/`.

| Step | Description | Status |
|---|---|---|
| 1 | `PasswordResetToken` model (`token_hash` unique, `used_at`, `expires_at`) + migration `a1b2c3d4e5f8` (head `d4e5f6a7b8c9`) + 3 settings | ✅ Complete 2026-06-07 |
| 2 | `services/password_reset.py` (request/validate/consume, hashed tokens, rate-limit, sibling invalidation, logs ids-only) | ✅ Complete 2026-06-07 |
| 3 | 3 endpoints in `routers/auth.py` (`/password-reset/request|validate|confirm`), neutral responses, async email dispatch, no JWT on confirm | ✅ Complete 2026-06-07 |
| 4 | Email templates `password_reset.html` + `password_changed.html` (español, no names) + `NotificationTemplate` enum + registry specs | ✅ Complete 2026-06-07 |
| 5 | Frontend: `ForgotPasswordPage`, `ResetPasswordPage`, login link, 2 public routes, api client + types (RHF+Zod, `noValidate`, full state set) | ✅ Complete 2026-06-07 |
| 6 | Tests: 18 backend (service + router + privacy invariants) + 10 frontend vitest (5 a11y axe, 0 violations); clean `tsc` + `ruff` | ✅ Complete 2026-06-07 |
| 7 | Deploy to Render | ⏳ Pending |

> Deployment pending user approval. Backend MySQL-dependent tests not run here (no DB in
> container); password-reset suite verified on SQLite. Migration verified single-head.

## Implementation status — User Profile & Account Settings Module (specs/004-user-profile)

> Self-service "Mi perfil / Ajustes de cuenta" for every login-capable user (admin,
> coach, parent): edit basic info, change password in-session (current-password re-auth +
> confirmation email), and change email via verify-new-email-before-apply (single-use
> hashed token to the new address, alert to the old address). OWASP-aligned (reuses the
> password-reset token pattern). No new dependency. Spec/plan/research/data-model/
> contracts/tasks under `specs/004-user-profile/`.

| Step | Description | Status |
|---|---|---|
| 1 | `EmailChangeRequest` model (`token_hash` unique, `new_email`, `used_at`, `expires_at`) + 3 settings (`email_change_*`) | ✅ Complete 2026-06-07 |
| 2 | `services/profile.py` (basic info; change_password w/ re-auth; request/confirm email change — hashed tokens, rate-limit, sibling invalidation, anti-enumeration, ids-only logs) | ✅ Complete 2026-06-07 |
| 3 | `routers/profile.py` 5 endpoints (`/api/profile/me`, `/basic`, `/change-password`, `/change-email/request`, `/change-email/confirm` public), self-only RBAC via `get_current_user` | ✅ Complete 2026-06-07 |
| 4 | Email templates `email_change_verify.html` (to new addr) + `email_changed_notice.html` (to old addr) + `NotificationTemplate` enum + registry specs | ✅ Complete 2026-06-07 |
| 5 | Frontend: `ProfilePage` (3 RHF+Zod sections) + public `ConfirmEmailChangePage`, `/perfil` + `/confirmar-correo` routes, "Mi perfil" menu link, api/types/hooks | ✅ Complete 2026-06-07 |
| 6 | Migration `b4c5d6e7f8a9` — creates `email_change_requests` AND merges the 3 prior Alembic heads into one (`8c1d2e3f4a5b`, `a1b2c3d4e5f7`, `a1b2c3d4e5f8`) | ✅ Complete 2026-06-07 |
| 7 | Tests: 37 backend (service + router + privacy invariants, SQLite) + 25 frontend vitest (a11y axe, 0 violations); clean `tsc` + `ruff` | ✅ Complete 2026-06-07 |
| 8 | Deploy to Render | ⏳ Pending |

> Deployment pending user approval. Known gap (documented in plan Complexity Tracking):
> no session/refresh-token revocation after credential change (stateless JWT). Backend
> MySQL-dependent tests not run here; profile suite verified on SQLite. Migration verified
> single-head (3-way merge).

## Implementation status — AI Session Clarify & Draft (specs/006-ai-session-clarify-draft)

> Pre-wizard "Asistente IA": single-round clarifying questions (single/multi-select +
> free-text "Otro") then an editable draft that prefills the session wizard. Stateless,
> no DB changes. AI receives aggregate-only context (age-mix counts + Copa Valle race
> proximity); athlete call-up is a criterion resolved client-side — no minor PII to the
> model. Docs: `docs/09-training-planning/session-ai-assistant.md`.

| Step | Description | Status |
|---|---|---|
| 1 | Schemas `session_assistant.py` (Clarify/Draft req/resp + `AthleteCallUpCriterion`, count/length validators) | ✅ Complete 2026-06-08 |
| 2 | Prompts `session_clarify.j2` + `session_draft.j2` (JSON-only, español, non-negotiables) + registry specs | ✅ Complete 2026-06-08 |
| 3 | `services/training/session_assistant_context.py` — aggregate-only context + `COPA_VALLE_2026` race proximity (no ids/names) | ✅ Complete 2026-06-08 |
| 4 | `SessionClarifyUseCase` + `SessionDraftUseCase` (BaseUseCase + safe JSON parse + guardrail scrub + Pydantic) | ✅ Complete 2026-06-08 |
| 5 | Router `/api/clubs/{id}/session-assistant/{clarify,draft}` — coach/admin RBAC, 503/422 mapping + DI providers | ✅ Complete 2026-06-08 |
| 6 | Frontend: `SessionAssistantPanel`, `ClarifyQuestionCard` (ToggleGroup single/multiple + "Otro"), pre-wizard route, `reset(keepDirtyValues)` prefill, per-field "IA" markers | ✅ Complete 2026-06-08 |
| 7 | Tests: 64 backend (use case + router + context + privacy invariants) + 31 frontend vitest (a11y axe 0); full FE suite 1817 green; `tsc` clean, `ruff` clean on new files | ✅ Complete 2026-06-08 |
| 8 | Privacy audit (data-privacy-guard): 0 critical, 1 HIGH + 2 MEDIUM remediated — schema-error logs now `exc_type` only (no raw LLM output), and coach free-text (`intent_text`/`other_text`) is redacted against club athlete names before reaching the LLM (+6 privacy tests) | ✅ Complete 2026-06-08 |
| 9 | Deploy to Render | ⏳ Pending |

> Deployment pending user approval. Backend session-assistant suite verified on SQLite
> (no DB-dependent paths). Provider-native structured output and multi-round clarification
> deliberately out of scope (fast-follows).

## Implementation status — Unified Competitions Module (specs/007-competitions-consolidation)

> Consolidates `/competitions` CRUD and `/coach/race-analysis` AI module into one `/competitions` area. Adds read endpoints for per-event results and season standings, call-up roster (`race_event_roster`), stale-analysis marking on re-ingest, bidirectional 1:1 calendar sync, and AI insights relocation. Delivered in 6 independently shippable waves. Technical detail in `docs/12-competitions-unification/` and `specs/007-competitions-consolidation/`.

| Step | Description | Status |
|---|---|---|
| Wave A | `GET /api/race-events/{id}/results` + `/standings` (per-event finishing table + season standings from `season_standings` view; `is_our_club` highlight; parent row-scoping); `ResultsTab` + `StandingsTab` with shadcn Table primitive, category filter, "solo mi club" toggle | ✅ Complete 2026-06-08 |
| Wave B | Single "Competencias" sidebar; AI analysis reachable only inside `/competitions/*`; `<Navigate>` redirects for `/coach/race-analysis` → `/competitions/insights` and `/training/races/:id/club-insights` → `/competitions/:id?tab=insights` (410 flip deferred post-deploy) | ✅ Complete 2026-06-08 |
| Wave C | `race_event_roster` table + migration `e5f6a7b8c9d0` (status enum `called_up\|confirmed\|withdrawn`, UNIQUE per event+athlete); 4 roster endpoints on `race_events` router; `RosterPanel` with reconciliation (called-up-no-result / result-not-called-up) | ✅ Complete 2026-06-08 |
| Wave D | On changed-PDF re-ingest: sets `agent_runs.stale_since`; marks `AthleteMonthlyNewsletter` outdated; no auto re-run/resend; `StaleAnalysisBadge` surfaced in frontend | ✅ Complete 2026-06-08 |
| Wave E | `calendar_sync` service (`create_linked` / `propagate` / `link_existing`); `create_calendar_event` checkbox on create (default on); PATCH propagation (date/name/location/cancellation); `POST /{id}/calendar-link`; BigInteger.with_variant SQLite fix for calendar PK | ✅ Complete 2026-06-08 |
| Wave F | AI privacy invariant tests; confirmed no duplicate insights pages; insights placement finalized inside `/competitions/*` | ✅ Complete 2026-06-08 |
| Deploy | Deploy to Render + 410 flip for legacy redirects | ⏳ Pending |

> Deployment pending coach approval. 410 flip for legacy redirects is a post-deploy follow-up (one release cycle, per D7).

## Implementation status — One-click Associate Competition to Calendar (specs/008-associate-competition-calendar)

> Single-action button that creates an all-day calendar event and links it to an existing `race_event` (1:1, idempotent — 409 if already linked). Coach-only. No new model; reuses `calendar_sync` service from Wave E of specs/007. Technical detail in `specs/008-associate-competition-calendar/`.

| Step | Description | Status |
|---|---|---|
| T001 | Backend: `POST /api/race-events/{id}/associate-calendar` endpoint (coach-only RBAC, 409 on duplicate, 422 if event not found) | ✅ Complete 2026-06-09 |
| T002 | Service: `calendar_sync.create_linked` called from new endpoint; idempotency guard in service layer | ✅ Complete 2026-06-09 |
| T003 | Schemas: `AssociateCalendarResponse` (calendar event id + `race_event_id`) | ✅ Complete 2026-06-09 |
| T004 | Frontend: "Asociar al calendario" button in `CompetitionDetailPage` header (visible only when `has_calendar_event=false`, coach/admin only) | ✅ Complete 2026-06-09 |
| T005 | API client + TanStack Query mutation `useAssociateCalendar` with `raceEvents` + `calendar` key invalidation | ✅ Complete 2026-06-09 |
| T006 | Backend tests: 409 duplicate guard, 422 not-found, success path, RBAC (parent blocked) | ✅ Complete 2026-06-09 |
| T007 | Frontend tests: vitest + Testing Library (button hidden when linked, success toast, error state, a11y axe) | ✅ Complete 2026-06-09 |
| T017 | Docs: `docs/implementation-status.md` + `CLAUDE.md` status table updated | ✅ Complete 2026-06-09 |
| Deploy | Deploy to Render | ⏳ Pending |

> Deployment pending user approval. All tests green on SQLite. No Alembic migration (reuses existing `calendar_events` + `race_events` tables and the `calendar_sync` service).

## Implementation status — Cleanup Duplicate Competition (specs/009-cleanup-duplicate-competition)

> Coach removes a **no-results** duplicate competition together with its linked calendar event in one confirmed action. The calendar event is **deleted, not unlinked** (CHECK `ck_calendar_competition_race_event` + FK `RESTRICT` forbid a NULL `race_event_id` on competition events). Existing admin-only `DELETE /{id}` is untouched (FR-010); competitions with results stay protected (409). No new model, no migration. Technical detail in `specs/009-cleanup-duplicate-competition/`.

| Step | Description | Status |
|---|---|---|
| T002–T003 | Service `cleanup_duplicate_race_event` (null race-side FK → delete CalendarEvent w/ cascade audiences+attendances → delete RaceEvent, one transaction; 404/409 guards) | ✅ Complete 2026-06-09 |
| T004 | Endpoint `DELETE /api/race-analysis/race-events/{id}/cleanup` (coach-only RBAC, 204/403/404/409) | ✅ Complete 2026-06-09 |
| T005–T007 | Backend tests: happy path with/without calendar event, cascade of audiences, privacy (IDs-only logs) | ✅ Complete 2026-06-09 |
| T008–T009 | Frontend: `cleanupDuplicateRaceEvent` API client + `useCleanupDuplicateRaceEvent` mutation (invalidates lists + calendar tree) | ✅ Complete 2026-06-09 |
| T010 | Frontend: "Eliminar duplicado" kebab action (coach + `!has_results`) reusing `ConfirmDeleteDialog` | ✅ Complete 2026-06-09 |
| T013–T015 | Tests: results-protected 409, RBAC (parent/admin 403), 404, UI gating (coach/parent), a11y axe on dialog | ✅ Complete 2026-06-09 |
| T016–T017 | Docs: router + API client inventory comments; `docs/implementation-status.md` + `CLAUDE.md` updated | ✅ Complete 2026-06-09 |
| Deploy | Deploy to Render | ⏳ Pending |

> All tests green: backend 707 passed (ruff clean); frontend 114 passed in competitions + race hooks suites, `tsc --noEmit` clean. No Alembic migration.

## Implementation status — Competitions AI Insights (specs/010-competitions-ai-insights)

| Step | Scope | Status |
|---|---|---|
| T001–T004 | Harness check; `GroupRun*`/`RaceEventRuns*` schemas + `ChatRequest.race_event_id` + `ProgressionAssessment`; `services/race/group_launch.py`; TS type mirrors | ✅ Complete 2026-06-09 |
| T005–T012 (US1) | `POST/GET /api/race-analysis/race-events/{id}/runs` (group fan-out via `submit_run`, typed per-athlete outcomes, refresh recovery); `useGroupAnalysis` hook; `GroupAnalysisPanel`/`GroupRunRow` in InsightsTab with HITL reuse; 19 backend + 12 frontend tests | ✅ Complete 2026-06-09 |
| T013–T018 (US2) | `season_comparative` + `progression_assessment` computed in `compute_metrics` (Python, not LLM); `race_analyst_v2.md` "Contexto de temporada" + no-fabrication rule; persisted in `metrics_snapshot_json` (additive); season section + progression badge in InsightsTimeline; 21 unit tests | ✅ Complete 2026-06-09 |
| T019–T020 (US3) | "Analizar con IA ahora" in ImportWizard post-commit panel (route-level RBAC); 7 tests | ✅ Complete 2026-06-09 |
| T021–T022 (US4) | Per-athlete launch action in ResultsTable (freshness check → ConfirmModal; season/valida from cached `useRaceEvent`); 14 tests | ✅ Complete 2026-06-09 |
| T023–T026 (US5) | `ChatRequest.race_event_id` scoping (insights + results tools constrained to the válida, event label seeded); `CompetitionChatPanel` (per-competition session, collapsible, 503-aware); 5 backend + 12 frontend tests | ✅ Complete 2026-06-09 |
| T027 | Privacy audit (data-privacy-guard): APPROVED — 1 HIGH log finding fixed (`athlete_id` → `run_id` in exception log) | ✅ Complete 2026-06-09 |
| T028 | Quality gates: ruff clean on feature files; backend race suites 87 passed; `tsc --noEmit` clean; full-suite failures verified pre-existing on `main` (see specs/010-…/notes.md) | ✅ Complete 2026-06-09 |
| Deploy | Deploy to Render | ⏳ Pending |

> No Alembic migration. AI provider/model unchanged (Gemini); Claude Fable 5 support deferred to a future spec at the coach's request.

## Implementation status — Perceived Performance Cache (specs/012-perceived-performance-cache)

> Frontend-only. Persists an **audited allow-list** of non-sensitive TanStack Query data to `localStorage` (`tyr:rq-cache:v1`) so return visits render instantly while Render Free wakes (~50 s); honest cold-start banner + `/health` warm-up; navigation polish. **No backend change, no migration.**

| Step | Scope | Status |
|---|---|---|
| T001–T003 | Deps (`@tanstack/react-query-persist-client` + `query-async-storage-persister` 5.101.0; Stryker dev-only); `__APP_VERSION__` via Vite define; scoped `stryker.config.json` | ✅ Complete 2026-06-10 |
| T004–T013 (US1) | `persistAllowList` (default-deny) + `queryPersister` (buster `{ver}:{userId}`, 24 h maxAge, logout wipe, graceful degradation) + `PersistQueryClientProvider` in App. **Privacy audit BLOCK → fixed**: excluded standings/results/competitors (minor names), calendar-event detail (birthday name), session lists (`media[].athlete_ids` + `coach_notes`). Mutation gate 72.64 % (allow-list 96.15 %) | ✅ Complete 2026-06-10 |
| T014–T024 (US2) | `serverWaking.store` (3 s threshold, interceptor-fed) + `ServerWakingBanner` (amber, role=status; copy "La aplicación está iniciando…" per ux-researcher) + deduped `warmUp()` ping on login/shell mount. UX review APPROVED-WITH-RECOMMENDATIONS (top 3 applied) | ✅ Complete 2026-06-10 |
| T025–T036 (US3) | `keepPreviousData` on standings/results/competitions/sessions/unlinked lists; `usePrefetchOnIntent` wired on competitions + sessions rows; post-login landing prefetch; optimistic roster update w/ rollback (attendance was already optimistic) | ✅ Complete 2026-06-10 |
| T022 | Playwright e2e `e2e/cold-start.spec.ts` (warm-up, ≥3 s banner, offline-reload restore) — **written + type-checked; unverified in sandbox (no chromium; download blocked)**. Run with `npm run test:e2e` locally | ⚠️ Written, pending local run |
| Quality gates | Full suite **199 files / 2138 tests green**; `tsc --noEmit` clean; Stryker ≥ 70 % | ✅ Complete 2026-06-10 |
| Deploy | Cloudflare Pages / production build | ⏳ Pending |

> **Privacy note (authoritative)**: the persistence allow-list is `lib/persistAllowList.ts` — additions require a `data-privacy-guard` review. Session lists / calendar-event detail may only be re-allowed after a backend summary schema strips athlete fields.

## Implementation status — Coach Per-Athlete Race Notes (specs/013-race-result-athlete-notes)

> Coach/admin can attach a short free-text qualitative note per club rider per válida from the Competition results view; the note is fed (after the same real-name scrub + pseudonymization as `weather_notes`) to BOTH the automatic per-athlete AI insight AND the coach-only competition chat. Parents/athletes never see it.

| Step | Scope | Status |
|---|---|---|
| Foundational (T002–T004) | `coach_note` (String 500) + `coach_note_author_id` (FK users, SET NULL) + `coach_note_updated_at` on `race_results`; migration `a3b4c5d6e7f8` (revises `f9a0b1c2d3e4`); legacy importer `notes` column untouched | ✅ Complete 2026-06-14 |
| US1 backend (T005–T008) | `ResultRow` exposes `result_id`/`coach_note`/`coach_note_updated_at`; `CoachNoteUpdate` (strip + 1..500); `PUT`/`DELETE /api/race-analysis/race-events/race-results/{id}/coach-note` (coach/admin RBAC, 404/409/422); results read round-trips fields | ✅ Complete 2026-06-14 |
| US1/US2 frontend (T009–T013, T016) | `RaceResultRow` types; `setResultCoachNote`/`clearResultCoachNote` API; optimistic `useSetResultCoachNote`/`useClearResultCoachNote`; `EditResultNoteDialog` (RHF+Zod, español, a11y); `ResultsTable` note preview + add/edit affordance (coach/admin, club rows only) | ✅ Complete 2026-06-14 |
| US3 AI (T019–T022) | `_serialize_result` carries `coach_note`; `anonymize` scrubs per-row + `coach_notes_by_valida`; `analyst_agent` injects scrubbed note into `race_meta`; chat `fetch_results` tool returns scrubbed `nota_entrenador`; null note → unchanged behaviour (FR-009) | ✅ Complete 2026-06-14 |
| Privacy (T024) | **CRITICAL fixed**: `results_read.py` now suppresses `coach_note`/`coach_note_updated_at` for parent-scoped reads (parents must not see the coach's private note about their child). 13 privacy-invariant tests lock real-name scrub + parent suppression + no-note-logging | ✅ Complete 2026-06-14 |
| Quality gates | Feature tests: backend 57 (router 25 + AI 14 + privacy 18); broader race suites 65; frontend vitest 132; `tsc --noEmit` clean; ruff clean on changed files. Full backend suite failures verified environmental (no MySQL on :3306 / missing PDF+email libs), not regressions | ✅ Complete 2026-06-14 |
| Deploy | Deploy to Render (migration runs via `entrypoint.sh`) | ⏳ Pending |

> Frontend integration fix during gates: coach-note client path corrected to `/api/race-analysis/race-events/race-results/{id}/coach-note` (router mounted under `/race-events`). Pre-existing second Alembic head `e5f6a7b8c9d0` (feature 007) is unrelated and would need a separate merge migration.

## Implementation status — Cup vs Championship Series (specs/014-cup-vs-championship-series)

> Adds a `kind` discriminator (`cup` | `championship`) to `race_series` so that single annual championships (e.g., Campeonato Departamental) are modeled as their own series without round numbers or cumulative-points contribution, while existing Copa Valle cup rounds remain unchanged. Reclassifies the existing Departmental Championship 2026 event via an idempotent data migration. No change to `race_events`, `race_results`, or any other table. Technical detail in `specs/014-cup-vs-championship-series/`.

| Step | Scope | Status |
|---|---|---|
| T001 | Verify single Alembic head `a3b4c5d6e7f8`; proceed on `main` | ✅ Complete 2026-06-15 |
| T002 | `RaceSeriesKind(str, enum.Enum)` (`cup`, `championship`) + `kind` mapped column on `race_series` | ✅ Complete 2026-06-15 |
| T003 | Alembic revision `b1c2d3e4f5a6` (`down_revision=a3b4c5d6e7f8`): `ADD COLUMN kind ENUM`; idempotent data step creates championship series + repoints Departmental event; downgrade restores Copa Valle seq 99 | ✅ Complete 2026-06-15 |
| T004 | `backend/app/schemas/race_series.py`: `RaceSeriesCreate`, `RaceSeriesRead`, `RaceSeriesListResponse` (with `event_count`, `extra="forbid"`) | ✅ Complete 2026-06-15 |
| T005 | `backend/app/routers/race_series.py`: `GET /api/race-analysis/race-series?season=&kind=` + `POST` (409 on duplicate `(name, season_year)`); registered in `main.py` | ✅ Complete 2026-06-15 |
| T006 | `backend/app/services/race/series_rules.py`: `derive_event_fields_for_series` (forces `sequence_number=1`, `is_championship=True` for championships); `assert_championship_single_event` (raises 409 if series already has an event) | ✅ Complete 2026-06-15 |
| T008 | `sequence_number` optional in `RaceEventCreate`; `create_race_event` applies guards and derives fields from series kind; removes `sequence_number=99` convention | ✅ Complete 2026-06-15 |
| T009 | `ingestor.py`: honors series kind on event creation (championship → seq 1 / `is_championship=True`) via shared helper | ✅ Complete 2026-06-15 |
| T017 | `race_imports.py`: `_get_or_create_series` resolves by `(series_name, season, kind)`; removes hardcoded `_SERIES_NAME`; `series_kind` Form field (default `cup`); championship single-event guard on commit | ✅ Complete 2026-06-15 |
| T023 | `season_panorama.py`: adds `AND rs.kind = 'cup'` to aggregate query (championships excluded from cumulative points/podiums/wins) | ✅ Complete 2026-06-15 |
| T024 | `standings.py`: guard returns `None` / empty payload when series is not `kind=cup`; standings router updated | ✅ Complete 2026-06-15 |
| T026 | Migration data step (in T003 file): idempotent upsert of `Campeonato Departamental 2026` series (`Liga Vallecaucana de Ciclismo`, `championship`); guarded `UPDATE` repoints legacy Departmental event (seq 99 / `is_championship=1`) to new series with `sequence_number=1` | ✅ Complete 2026-06-15 |
| T007, T010, T018, T025, T027 | Backend pytest: foundation, US1 championship single-event guard, US3 import, US5 ranking exclusion, US6 migration idempotency | ⏳ Pending |
| T011–T016, T019–T022 | Frontend: `CompetitionFormPage` type selector, `ImportWizard` type-aware flow, `CompetitionDetailPage` standings tab guard, series API client + Zod schema, vitest + jest-axe | ⏳ Pending |
| T028–T031 | Polish gates (`ruff`, `mypy`, `eslint`, `tsc`), privacy audit, docs, quickstart end-to-end | ⏳ Pending |
| Deploy | Deploy to Render (migration `b1c2d3e4f5a6` runs via `entrypoint.sh`) | ⏳ Pending |

> Ola A (backend skeleton) complete. Frontend series-type-aware flows (US1–US4) and all pytest suites are the next increment. Migration is idempotent and prod-safe; re-runs and championship-free environments succeed without error.

## Implementation status — Prefill Import from Competition (specs/015-prefill-import-from-competition)

> Frontend-only. Launching the results import **from a competition** (`/competitions/{id}/import`) now opens the wizard prefilled and locked with everything the system knows about that competition (name, date, city, series, type, round). Type and series are derived (no in-flow control); `válida #` is hidden for championships; an "Editar metadata" escape hatch handles genuine corrections; if the series/type can't be determined the import is blocked (FR-009). The standalone `/competitions/import` path is unchanged. No backend change, no migration — the existing `/parse`→`/dry-run`→`/commit` pipeline links to the exact competition because the prefilled values equal the stored `(series_id, sequence_number)`.

| Task | Scope | Status |
|---|---|---|
| T001–T002 | Mutation tooling: extended `stryker.config.json` `mutate` + `vitest.stryker.config.ts` include to cover `useImportPrefill.ts`; `test:mutation` script in `package.json` | ✅ Complete 2026-06-16 |
| T003 | `ImportPrefill` / `ImportPrefillValues` / `ImportPrefillStatus` view-model types in `src/types/raceImports.types.ts` | ✅ Complete 2026-06-16 |
| T004 | `useImportPrefill(raceEventId)` hook — composes `useRaceEvent` + `useRaceSeriesList`, resolves series by `series_id`, returns `loading\|ready\|blocked\|error`, derives `series_kind`/`valida_num` (null for championship), builds `editMetadataHref` | ✅ Complete 2026-06-16 |
| T005 | MSW prefill fixtures: `makeChampionshipRaceEventRead` + `prefillCupEventHandler` / `prefillChampionshipEventHandler` / `prefillUnresolvableSeriesEventHandler` (competition metadata only, zero PII) | ✅ Complete 2026-06-16 |
| T009–T011 (US1) | `raceEventId?` prop on `ImportWizard`; consumes `useImportPrefill`; `reset()` RHF on `ready`; cold-start-aware `PrefillLoadingState`; `CompetitionImportPage` passes `raceEventId` | ✅ Complete 2026-06-16 |
| T015–T017 (US2) | `PrefillLockedSummary` read-only block (static text + `aria`, not `disabled`); removes in-flow type/series controls when prefilled; "Editar metadata" escape hatch; `PrefillBlockedState` (FR-009) | ✅ Complete 2026-06-16 |
| T019 (US3) | All prefill/lock logic guarded behind `raceEventId != null`; `useRaceSeriesList({ enabled })` so standalone fires zero new requests; standalone regression test green | ✅ Complete 2026-06-16 |
| T021 (US4) | `válida #` hidden in the locked summary when `series_kind=championship` (driven by derived value) | ✅ Complete 2026-06-16 |
| T006–T008, T012–T014, T018, T020 | Vitest + RTL + MSW + jest-axe: hook ready/blocked/error/standalone mapping, locked/derived/escape-hatch/blocked render, championship-hides-válida, standalone regression, a11y zero violations | ✅ Complete 2026-06-16 |
| T022 | Playwright e2e `e2e/prefill-import-from-competition.spec.ts` (cup prefilled+locked, championship hides válida, standalone unchanged, privacy no-name-before-dry-run; ids discovered from backend) | ✅ Written — pending local run vs live stack |
| T023 | Privacy audit: prefill payloads/fixtures/logs carry only competition metadata — no minor name/DOB/medical (FR-013) | ✅ Complete 2026-06-16 |
| T025 | Bundle/perf: `ImportWizard` stays a lazy chunk (10.99 kB gz ≪ 150 KB budget); 2 cached GETs, no N+1; cold-start state surfaced | ✅ Complete 2026-06-16 |
| Quality gates | `tsc --noEmit` clean; full frontend vitest **2217 passed / 209 files**; `vite build` green | ✅ Complete 2026-06-16 |
| T024 | Mutation run (`npm run test:mutation`, scoped to `useImportPrefill.ts`) | ⏳ On-demand (per repo convention — not in CI) |
| T026 | `quickstart.md` manual end-to-end (coach login, cup/championship/standalone/block) | ⏳ Pending live stack |
| Deploy | Frontend deploy (Cloudflare Pages — pending); no backend/migration | ⏳ Pending |

> Notable decisions: (1) mutation scope limited to `useImportPrefill.ts` rather than the 1600-line `ImportWizard.tsx` — mutating the whole component with only prefill tests would surface false-positive survivors from unrelated steps and tank the shared `break:70` gate. (2) `useRaceSeriesList` gained an optional `{ enabled }` so the standalone wizard makes zero extra requests, honoring FR-007 strictly.

## Implementation status — Race-Analysis Championship Charts Fix (specs/016-race-analysis-championship-charts-fix)

> Fixes the athlete AI-analysis Distribution & Evolution charts so they handle the Departmental Championship correctly after feature 014 retired the `valida_num=99` convention. Root cause: both charts identified races by `valida_num`; feature 014 replaced that with `race_series.kind` + dedicated series, so the championship appeared as `sequence_number=1` — colliding with Copa Valle Válida I on the Evolution axis, and producing an HTTP 500 on Distribution (invalid empty `DistributionResponse(category_id=0, category_code="")`). Fix: race identity moved to stable `event_id` throughout. No database migration (reuses feature-014 columns). Out of scope and untouched: AI insight text/chat, results ingestion, ranking, ComparatorPanel, the agentic `valida_num` contract.

**Root causes fixed:**

1. **Distribution HTTP 500 for championship / no-data races** — empty fallback built a schema-violating `DistributionResponse`; replaced by `AthleteDidNotParticipate` → HTTP 404 for a non-participated event, schema-valid no-data 200 for DNF/small-field.
2. **Evolution championship point merged with Válida I** — `romanForValida(1)="I"` labeled the championship identically to cup round 1; corrected by `event_id`-keyed points with `series_kind`+`label` from the backend, and `ORDER BY event_date ASC` (was `valida_num, event_date`).

**Files introduced / modified:**

| Layer | File | Change |
|---|---|---|
| Backend | `backend/app/services/race/race_labels.py` | NEW — pure helper `build_race_label(series_kind, sequence_number, event_date)` |
| Backend | `backend/app/routers/race_analysis.py` | NEW `GET /api/athletes/{id}/race-analysis/races?season=` endpoint |
| Backend | `backend/app/services/race/distribution.py` | `valida_num` → `event_id`; deleted invalid empty fallback; raises `AthleteDidNotParticipate` |
| Backend | `backend/app/schemas/race_analysis.py` | `DistributionResponse.valida_num` → `event_id`; `EvolutionPoint` gains `series_kind`+`label` |
| Backend | `backend/app/services/race/evolution.py` | `ORDER BY event_date ASC`; propagates `series_kind`+`label` |
| Frontend | `src/hooks/race/useAthleteRaces.ts` | NEW hook — feeds the distribution picker from `/races` endpoint |
| Frontend | `src/lib/raceOptionLabel.ts` | NEW helpers — builds "Temporada (todas)" informational entry and per-race labels |
| Frontend | `src/components/ai/DistributionChart.tsx` | Picker uses `event_id`; labels from new endpoint |
| Frontend | `src/components/ai/EvolutionChart.tsx` | Points keyed by `event_id`; championship labeled distinctly |

**Tests added:** regression pytest (championship distribution 200, no-data 200, non-participated 404, `/races` list/RBAC/privacy, evolution `series_kind`+`label`+date-order); vitest + jest-axe on both charts and the picker (zero a11y violations); mutation gate extended to `useAthleteRaces.ts` and `raceOptionLabel.ts`; Playwright e2e.

| Step | Scope | Status |
|---|---|---|
| B1 | `race_labels.py` pure helper + `GET /races` endpoint (RBAC coach/admin/parent-scoped, privacy: pseudonyms only) | ✅ Complete 2026-06-16 |
| B2 | `distribution.py`: `valida_num`→`event_id`, invalid empty fallback deleted, `AthleteDidNotParticipate` raised for HTTP 404 | ✅ Complete 2026-06-16 |
| B3 | `evolution.py`: `ORDER BY event_date ASC`, `series_kind`+`label` propagated per point | ✅ Complete 2026-06-16 |
| B4 | Schemas updated (`DistributionResponse`, `EvolutionPoint`) | ✅ Complete 2026-06-16 |
| F1 | `useAthleteRaces` hook + `raceOptionLabel.ts` helpers + "Temporada (todas)" informational entry | ✅ Complete 2026-06-16 |
| F2 | `DistributionChart` picker uses `event_id` + real labels from new endpoint | ✅ Complete 2026-06-16 |
| F3 | `EvolutionChart` points keyed by `event_id`; championship labeled distinctly | ✅ Complete 2026-06-16 |
| QA | Pytest regression suite + vitest + jest-axe + Playwright e2e; mutation gate extended | ✅ Complete 2026-06-16 |
| Deploy | Frontend + backend read endpoints deploy to Render/Cloudflare Pages | ⏳ Pending |

> No Alembic migration. Reuses `race_series.kind`, `event_id`, `event_date` columns introduced by feature 014. The agentic `valida_num` contract in AI insight/chat is untouched.

---

## Competitive Anxiety Assessment — specs/017-competitive-anxiety-assessment (Phase 2 mental performance)

Coach-facing module to administer/score/interpret state competitive-anxiety
questionnaires (CSAI-2R default 13–15, SAS-2 10–12, CSAI-2 import-only) for youth
XCO athletes, anchored to each athlete's own baseline, mastery-climate framed,
wellbeing-not-diagnosis (Constitution Principle V). See
[`docs/13-competitive-anxiety/workflow.md`](13-competitive-anxiety/workflow.md).

**Backend — ✅ Complete (migration `c2d3e4f5a6b7`), deploy pending:**

| Layer | File | Change |
|---|---|---|
| Migration | `alembic/versions/c2d3e4f5a6b7_anxiety_assessment_module.py` | NEW — 4 `anxiety_*` tables + `parental_consents.psychological_assessment` |
| Models | `app/models/anxiety_{instrument,assessment,response_token,baseline}.py` | NEW — enums via `values_callable` |
| Schemas | `app/schemas/anxiety.py` | NEW — create/batch/answer/read/interpret/dashboard/import |
| Services | `app/services/anxiety/{tokens,consent_gate,baseline,analysis,assessments,submit,interpretation,importer}.py` | NEW (alongside existing `scoring`/`selection`/`instrument_keys`/`rule_interpreter`) |
| AI | `app/services/ai/use_cases/anxiety_interpretation.py` + `prompts/anxiety_interpretation_v1.j2` | NEW — LLM interpretation, JSON schema, guardrail scrub; rule fallback |
| Router | `app/routers/anxiety.py` (+ `main.py`, `dependencies.py`, `prompts/registry.py`) | NEW — 11 endpoints under `/api/anxiety` |

**Tests:** `backend/tests/anxiety/` — 51 pass (in-memory SQLite + httpx). Covers
auth/consent/override (409/422/403), token single-use (410) + partial scoring,
recompute determinism, interpretation LLM path + invalid-JSON→rule fallback
parity + alert flag, privacy (real name never in provider payload), dashboards
(series + group buckets), import (incl. CSAI-2 27-item) + export round-trip,
baseline seed-once + deltas. No regressions in the existing suite.

**Frontend — ✅ Complete, deploy pending:** `src/api/anxiety.ts` + Zod schemas
(`schemas/anxiety.schemas.ts`) + types; TanStack Query hooks (`hooks/anxiety/*`);
components (`Questionnaire`, `AssessmentWizard`, `AnalyzeButton`,
`InterpretationPanel`, `IndividualPanel` w/ lazy `BaselineChart`, `GroupPanel`,
`ImportDialog`); public token `AnswerPage` (`/anxiety/responder/:token`) + coach
`AnxietyDashboardPage` (`/anxiety`); route wiring in `App.tsx` + AppShell nav.
**8 vitest + jest-axe tests pass** (`vitest run src/components/anxiety`); anxiety
sources typecheck clean.

**Remaining (ops/review):** UX field review, mobile/3G WCAG pass, privacy audit,
perf budgets, Render deploy of migration `c2d3e4f5a6b7`, quickstart e2e — all
pending the running stack / reviewer.

---

## Implementation status — Technique & Gymkhana Library (specs/018-technique-gymkhana-library)

Coach/admin-facing module: searchable catalog of ~24 pre-seeded technique drills and gymkhana exercises (filterable by skill A–H, age band 7–9/10–12/13–15, difficulty, and available materials), each with a runnable detail card and an illustrative ASCII circuit layout; session assembly through the existing Training Sessions module (no parallel store); per-athlete skill progress tracking (introducido / en_progreso / dominado) as individual growth anchored to biological age — no comparison surface. Seeded from `docs/14-tecnica-gymkana-7-15/research.md`. No AI/LLM. Module design: `docs/15-tecnica-gymkana-modulo/design.md`.

**Privacy fixes applied during audit (2026-06-25):** `_require_athlete_club_scope()` helper added to progress endpoints (cross-club 403); 4 seed-content corrections (mastery-climate label, vosotros→ustedes ×3); Exercise 15 difficulty downgraded `avanzada→media`; PHV-awareness notes added to Exercises 15/16/17; age-band mapping comment expanded with prerequisite-gate guidance.

| Step | Scope | Status |
|---|---|---|
| M001 | Alembic migration `e1f2a3b4c5d6`: `technique_skills`, `technique_materials`, `technique_exercises` + 3 join tables (`_age_bands`, `_skills`, `_materials`), `technique_session_exercises`, `athlete_skill_progress`; 4 enums (`AgeBand`, `ExerciseDifficulty`, `SessionSegment`, `SkillProgressStatus`); idempotent seed (A–H skills, 9 materials, ~24 exercises with `how_to` + `layout_ascii` + `layout_alt` in español neutro) | ✅ Complete 2026-06-25 |
| M002 | SQLAlchemy 2 async models: `TechniqueSkill`, `TechniqueMaterial`, `TechniqueExercise` (+ association tables), `TechniqueSessionExercise`, `AthleteSkillProgress`; `selectinload` on all M2M relationships | ✅ Complete 2026-06-25 |
| M003 | Pydantic v2 schemas: `ExerciseListItem`, `ExerciseDetail`, `TechniqueSessionCreate`, `TechniqueSessionItem`, `SkillProgressEvent`, `AthleteProgressRead`, `ExerciseCreate/Update`, `VisibilityUpdate` | ✅ Complete 2026-06-25 |
| M004 | Services: `catalog.py` (filter query with NOT-EXISTS material-subset filter + `sin_material` always-match); `assembler.py` (wraps `training_svc.create_session`, writes session + link rows in one transaction, computes `mixes_age_bands`); `progress.py` (append event, current-per-skill, season history) | ✅ Complete 2026-06-25 |
| M005 | Router `app/routers/technique.py`: 11 endpoints under `/api/technique` — `GET /exercises`, `GET /skills`, `GET /materials`, `GET /exercises/{id}`, `POST /sessions`, `GET /sessions/{id}/exercises`, `GET /athletes/{id}/progress`, `POST /athletes/{id}/progress`, `POST /exercises`, `PUT /exercises/{id}`, `PATCH /exercises/{id}/visibility`; RBAC coach/admin on all; `_require_athlete_club_scope()` on progress endpoints | ✅ Complete 2026-06-25 |
| M006 | Seed data module `backend/app/data/technique_catalog.py`: A–H skill taxonomy, 9 materials, 24 exercises with full `how_to` (NICA Dilo→Muéstralo→Háganlo→Revísenlo + mastery-climate paragraph), `layout_ascii` croquis + `layout_alt` screen-reader alternative; confidence tags from research report | ✅ Complete 2026-06-25 |
| F001 | API client `frontend/src/api/technique.ts` + Zod schemas + TypeScript types | ✅ Complete 2026-06-25 |
| F002 | TanStack Query hooks: `useTechniqueCatalog`, `useTechniqueExercise`, `useAssembleTechniqueSession`, `useAthleteSkillProgress` (with `useSetSkillProgress` mutation) | ✅ Complete 2026-06-25 |
| F003 | `CatalogPage`: `FilterBar` (skill/age-band/difficulty/materials chips, 48 px touch targets), `CatalogGrid` (exercise cards), clear empty state (FR-004), cold-start-aware loading state | ✅ Complete 2026-06-25 |
| F004 | `ExerciseDetailPage`: full detail card + `CircuitLayout` component (`<pre>` monospace + `layout_alt` visually-hidden for screen readers, WCAG 2.1 AA); mastery-climate `how_to` display | ✅ Complete 2026-06-25 |
| F005 | `SessionBuilderPage`: `SessionAssembler` (warm-up / main / cool-down segments, position ordering); `MixedAgeNotice` banner (FR-014); saves through `POST /api/technique/sessions` → `TrainingSession` appears in existing calendar and session list | ✅ Complete 2026-06-25 |
| F006 | `AthleteProgressPage` + `SkillProgressBoard`: per-athlete A–H skill grid, current status badges, season event history; no ranking, no comparison, no cross-athlete view (FR-017, SC-005) | ✅ Complete 2026-06-25 |
| F007 | `CatalogAdminPage` + `ExerciseForm`: create/edit (gymkhana layout required validation), hide/unhide, `include_hidden` view for curators | ✅ Complete 2026-06-25 |
| QA001 | Backend tests `backend/tests/technique/` — 178 pass: catalog filter (skill/age/difficulty/material subset + sin_material), RBAC (parent 403, cross-club coach 403 on progress), assemble creates real `TrainingSession` in existing module, session exercises survive hide/edit, progress append/current/history, no-comparison invariant, privacy (no PII in response/log), migration idempotency | ✅ Complete 2026-06-25 |
| QA002 | Performance query tests `test_perf_queries.py`: `list_exercises` emits exactly 4 SELECT statements for 12 exercises (O(1) = main table + 3 selectinloads); `MAX_SELECTS=10` ceiling verified | ✅ Complete 2026-06-25 |
| QA003 | Frontend vitest + jest-axe — 230 pass: catalog/detail/assembler/progress/curation; `SkillProgressBoard` explicitly asserts absence of ranking/leaderboard/comparison elements; 0 a11y violations | ✅ Complete 2026-06-25 |
| AUD001 | Privacy audit (data-privacy-guard): PASS_WITH_FIXES — 1 HIGH cross-club progress exposure fixed (`_require_athlete_club_scope()`); 2 new cross-club 403 tests; no PII in responses/logs/schemas confirmed | ✅ Complete 2026-06-25 |
| AUD002 | Content/language audit (technique-coach + sports-science-advisor): PASS_WITH_FIXES — 4 seed-copy corrections (mastery-climate label in Ex 7; vosotros→ustedes in Ex 8/14/24); no non-negotiable violations found | ✅ Complete 2026-06-25 |
| AUD003 | Sports-science audit: PASS_WITH_FIXES — Exercise 15 difficulty `avanzada→media`; PHV-awareness notes added to Ex 15/16/17; age-band mapping comment with prerequisite-gate guidance | ✅ Complete 2026-06-25 |
| AUD004 | Performance audit: PASS — selectinload O(1) query count confirmed by instrumented tests; no N+1 detected | ✅ Complete 2026-06-25 |
| Deploy | Run migration `e1f2a3b4c5d6` on Render (`alembic upgrade head` via `entrypoint.sh`); deploy backend + frontend | ⏳ Pending |

> Module design and data model in `docs/15-tecnica-gymkana-modulo/design.md`. All 180 technique tests pass (178 backend + 2 performance tests). No new runtime dependency.
