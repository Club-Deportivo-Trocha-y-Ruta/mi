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

---

## Implementation status — Strength Training Exercise Library (specs/021-strength-training-library)

Coach/admin-facing module: illustrated catalog of strength-training exercises (own artwork/ASCII diagrams — never licensed third-party photos), filterable by equipment (bodyweight/no-equipment vs. gym-equipment) and age band (10-12 / 13-15), each with execution steps and common-errors guidance; time-boxed strength-block assembly (≤30 min target, running-total within/at/over indicator) attached to existing Training Sessions module (Phase 1.5, no parallel store); age-band safety guardrails encoding club dosing differentiation (10-12 bodyweight-only, 13-15 progressive equipment) with block-then-override-with-recording behavior; per-athlete strength progress notes, coach-only, no cross-athlete comparison. Mirrors specs/018-technique-gymkhana-library conventions.

**Status:** ✅ Complete — deploy pending (migration `a7b8c9d0e1f2`).

## Implementation status — Newsletter Audit Fixes (specs/024-newsletter-audit-fixes)

Parent-facing individual monthly newsletter (PDF + email) correctness + polish sweep from an audit of the June 2026 boletín. Five confirmed bugs (Section A) and nine presentation improvements (Section B).

Section A: (A1) championship KPI shows its own short label `CD`/`CN` instead of colliding `V1` (spec-014 `sequence_number=1`), via new `short_label` from `_race_short_label`; (A2) AI coach narrative uses correct grammatical gender through a pre-derived `athlete_reference` ("su hijo"/"su hija"/"su hijo/a") injected into the prompt context — no name/PII added; (A3) gallery images embedded as base64 data URIs at PDF render time (WeasyPrint can't fetch Hostinger SFTP URLs), reusing the spec-022 `build_report_photo_evidence` pattern (2 MB budget, graceful skip), with a three-state section gate (omit / placeholder-with-count / images); data URIs are render-time only, never persisted or emailed; (A4) OMNI RPE reference corrected to `0-10 (base: 3-5 · alta intensidad: 6-8)`; (A5) weekly-hours LTAD compliance (`weekly_hours_avg = total/(days_in_month/7)` vs age-decimal limit) with ✓/⚠ status.

Section B: (B6) `focus_groups` via new pure `focus_grouping.py` mapping free-text `technical_focus` to the A–H skill taxonomy + `resistencia_acondicionamiento` + `otros`; (B7) `category_label` from `race_categories.label`; (B8) shared `format_date_es` / `date_es` Jinja filter (no babel); (B9) page-1 reflow (per-subsection `break-inside`, not atomic card); (B10) SVG label clamp (`pad_top` 16 + `y` clamp); (B11) anthro table headers; (B12) `streak_days`→`streak_sessions` (single render site; fixes a latent frontend/backend key mismatch); (B13) championship no-points chart footnote (mirrors spec-022); (B14) age-banded, month-rotated (deterministic) support-at-home tips preserving zero-supplements/no-calorie-counting.

New files: `app/services/training/focus_grouping.py`, `app/services/notification/media_embedding.py`, `app/services/utils/dates_es.py`. Implemented via a 5-wave multi-agent workflow scoped by file ownership (sonnet agents). Additive `metrics_snapshot`/`ai_narrative` fields with template fallbacks for pre-024 snapshots.

**Status:** ✅ Complete — deploy pending (no Alembic migration; additive JSON-column changes only). Feature-scoped tests green (133 newsletter/helper tests). The one WeasyPrint PDF-layout render test is env-blocked locally (macOS lacks pango/glib `libgobject-2.0-0`); it passes in the Docker/Render image.

---

## Implementation status — Strava Activity Sync (specs/025-strava-activity-sync)

Per-athlete Strava account connection via OAuth (guardian-consent-gated), automatic activity ingestion (webhook push + daily reconcile pull), and **coach-gated manual linking** of a synced activity to a specific training session. Athletes' Garmin/Magene/iGPSport devices already sync to Strava; Strava is the single integration hub. Privacy-first (Ley 1581): GPS/lat/lng/polyline/map/description are never persisted or exposed; logs carry numeric IDs only. Coach/admin link activities; parents get read-only visibility of their own children. Technical detail in `docs/16-strava-sync/` and `specs/025-strava-activity-sync/`.

**Backend — ✅ Complete (migration `a4b5c6d7e8f9`, single head on `d3e4f5a6b7c8`), deploy pending:**

| Layer | File | Change |
|---|---|---|
| Migration | `alembic/versions/a4b5c6d7e8f9_add_strava_sync_tables.py` | NEW — `strava_connections`, `strava_activities` tables + `parental_consents.external_activity_sync` column |
| Models | `app/models/strava_connection.py`, `strava_activity.py` | NEW — `StravaConnection` (status enum, Fernet-encrypted token columns, UNIQUE athlete/strava_athlete_id), `StravaActivity` (UNIQUE `strava_activity_id`, `upstream_state`/`ingest_source` enums, composite `(training_session_id, start_date_utc)` index, **no GPS columns**) |
| Schemas | `app/schemas/strava.py` | NEW — `ConnectionStatusOut`, `AuthorizeUrlOut`, `ActivityOut` (nested `link`, no coordinate fields), `LinkUpdateIn`, `SessionSuggestionOut`, `ReconcileResultOut`, `StravaWebhookEvent` |
| Services | `app/services/strava/{token_store,oauth,client,ingest,reconcile}.py` | NEW — Fernet encrypt/decrypt; OAuth authorize URL + signed 15-min `state` + token exchange/refresh-rotation; httpx Strava client (auto-refresh, 429/rate-limit aware); idempotent GPS-stripping ingest + webhook dispatch; watermark reconcile |
| RBAC | `app/services/permissions.py` | `can_view_activity`, `can_link_activity`, `filter_activities_for_parent` |
| Routers | `app/routers/strava_integration.py`, `activities.py` (+ `main.py` flag-gated, `config.py`) | NEW — connect/status/disconnect, OAuth callback, webhook GET validation + POST (immediate 200, deferred processing), secret-gated reconcile; review list, athlete activities, session-suggestions, coach-only `PATCH .../link`, session activities |

**Tests:** 110 passed + 1 xfail (backend, aiosqlite + httpx mocks): model constraints, OAuth/callback/webhook/reconcile router paths, service token-refresh/idempotency/GPS-strip/deauth, privacy invariants (no GPS in schema/model/response, numeric-only logs), RBAC (parent 403, cross-club 422), query-count anti-N+1. Frontend 48 passed (vitest + jest-axe). `ruff` clean on new modules. No regressions.

> Privacy-suite bug caught & fixed during implementation: `upsert_activity` logged `extra={"created": ...}`, which collides with `LogRecord`'s reserved `created` field and would raise `KeyError` at INFO level in prod — renamed to `row_created` (`app/services/strava/ingest.py`).

**Frontend — ✅ Complete, deploy pending:** `api/stravaActivities.ts` + `types/strava.types.ts`; hooks `hooks/activities/*` (`useStravaConnection`, `useAthleteActivities`, `useActivityReview`, `useLinkActivity`, `useSessionActivities`); components `components/activities/*` (`ConnectionStatusBadge`, `ActivityCard`, `LinkSessionDialog`); coach review page `routes/activities/ActivityReviewPage.tsx` (lazy route `/activities`, coach/admin); connection card + activity section on athlete detail; linked-activities section on session detail; parent read-only view. All copy español neutro. `tsc --noEmit` clean.

**Audits:** security-engineer — 2 actionable findings applied (webhook `subscription_id` validation; fail-closed on empty shared secrets); data-privacy-guard — data minimization confirmed at schema/API/log layers.

**Remaining (ops/deploy):** Strava dashboard self-service athlete-cap upgrade (1 → 10) + Developer Program application for full club; set Render env vars (`STRAVA_*` incl. `STRAVA_TOKEN_ENCRYPTION_KEY`, `STRAVA_RECONCILE_TOKEN`, `STRAVA_SUBSCRIPTION_ID`); set the app's Authorization Callback Domain to the prod host; run migration `a4b5c6d7e8f9` on Render (auto via `entrypoint.sh`); create the one-time webhook subscription against the prod callback; add GitHub secret `STRAVA_RECONCILE_TOKEN` for `.github/workflows/strava-reconcile.yml`; pilot one real athlete for SC-001/SC-002 validation. See `specs/025-strava-activity-sync/deploy-checklist.md` + `docs/16-strava-sync/runbook-ops.md`.

> **Data privacy (authoritative):** `strava_activities` persists only summary fields (external id, athlete FK, connection FK, `name`, `sport_type`, start UTC/local, elapsed/moving time, distance, elevation gain, avg/max heart rate, trainer flag, upstream/link state). **No** GPS (`lat/lng/latlng`), `map.polyline`, `description`, photos, or segment data — enforced at schema, API, and log layers with a dedicated invariant test suite (`backend/tests/privacy/test_strava_privacy.py`). `strava_connections` stores `access_token`/`refresh_token` Fernet-encrypted. All reads scoped by RBAC (parent → own children read-only). See `specs/025-strava-activity-sync/data-model.md` § Privacy.

---

## Implementation status — Structured Interval Training with Strava Correlation (specs/026-structured-interval-training)

Coach-authored interval structures (warmup / repeatable work-recovery groups / cooldown, each block with duration + HR zone + cadence target) attached 1:1 to a training session — the same "attached entity" pattern as features 018/021, not a wizard step. From a structure the coach can download a brand-specific PDF instructivo (iGPSport / Magene / Garmin) and, once a Strava activity is linked to the session (existing feature-025 flow), get an **automatic plan-vs-actual comparison** computed by sequential order-based matching of the activity's newly persisted **laps** (never GPS) against the flattened planned blocks, with a manual recalculation trigger. A club-scoped, tagged template library (age band × mesocycle phase × competition proximity) provides reuse via copy-on-attach — editing or deleting a template never mutates sessions that already used it. Age gating is hybrid: hard block for Z3+ intensity on 10-12 structures (no override), confirm-and-record for Z1-Z2 10-12 structures. Everything under `/api/intervals` (structures, templates, match detail, laps, instructivo) is coach/admin-only in v1 — parents/athletes get 403. Technical detail in `specs/026-structured-interval-training/` (plan, research, data-model, contracts/api.md).

**Backend — ✅ Complete (migration `b5c6d7e8f9a0`, `down_revision=a4b5c6d7e8f9`), deploy pending:**

| Layer | File | Change |
|---|---|---|
| Migration | `alembic/versions/b5c6d7e8f9a0_interval_training.py` | NEW — `interval_structures`, `interval_structure_blocks`, `interval_templates`, `interval_template_blocks`, `strava_activity_laps`, `interval_match_results` tables + `intervalblocktype`/`hrzone`/`matchtrigger` enums; reuses the existing `ageband` enum from migration `e1f2a3b4c5d6` (does not recreate/drop it) |
| Models | `app/models/interval_structure.py`, `strava_activity_lap.py` | NEW — `IntervalStructure` (UNIQUE `training_session_id`, age-gate confirmation columns), `IntervalStructureBlock` (UNIQUE `(structure_id, position)`, nullable `repeat_group`/`repeat_count`, **no power column**), `IntervalTemplate`/`IntervalTemplateBlock` (club-scoped, soft-archive), `StravaActivityLap` (UNIQUE `(strava_activity_id, lap_index)`, **no geo/cadence/watts columns**), `IntervalMatchResult` (UNIQUE `(structure_id, strava_activity_id)`, `result_json`) |
| Schemas | `app/schemas/intervals.py` | NEW — `StructureOut`/`TemplateOut`/`BlockIn` family, match-detail response (`status: computed\|no_activity\|computing\|failed`), machine-readable 422 codes (`cadence_below_minimum`, `age_gate_z3_blocked`, `age_gate_confirmation_required`, `invalid_repeat_group`) |
| Services | `app/services/intervals/{structures,templates,matching,match_runner,instructivo_pdf}.py` | NEW — CRUD + age-gate/cadence validation (band `10-12` + any flattened block `≥Z3` → hard 422; `10-12` + all Z1-Z2 without `age_gate_confirmed` → 422); template CRUD + copy-on-attach (clone, no retained FK); pure order-based matching engine (flatten repeat groups → drop laps `<10s` → pair by position → `cumplido`/`fuera_tolerancia`/`sin_dato`/`extra` at ±30% duration tolerance); deferred fetch-laps→persist→compute runner (allow-lists exactly `lap_index`/`elapsed_time`/`moving_time`/`average_heartrate`/`average_speed`, drops everything else pre-flush); brand-specific (Garmin/Magene/iGPSport) PDF wrapper reusing `DocumentGenerator` |
| Router | `app/routers/intervals.py` (+ `main.py`) | NEW — `/api/intervals`: structure CRUD, template CRUD + filterable list + attach, match detail (`GET .../match`) + manual `POST .../recalculate`, instructivo PDF download; every route behind `require_role([admin, coach])` + club scope |
| Strava client | `app/services/strava/client.py` | EDIT — new `get_activity_laps(activity_id)` through the existing `_request()` choke point (token refresh, 429→`StravaRateLimited`) |
| Activities router | `app/routers/activities.py` | EDIT — `PATCH .../link` now dispatches a deferred match job (`TaskDispatcher`, same pattern as the webhook path) when the target session has a structure; unlink deletes the pairing's match row, leaves laps intact |
| PDF template | `templates/documents/pdf/session_instructivo.html` | NEW — extends `base/layout.html`; per-brand configuration steps + mandatory "desactivá el auto-lap" instruction for all three brands |

**Tests:** `backend/tests/intervals/` (structures, age-gate guardrail, templates, matching engine, instructivo PDF, RBAC) + `backend/tests/privacy/test_laps_privacy.py` (no-geo/no-cadence/no-watts invariants on the laps model and every match/lap-bearing response schema, mirrors `test_strava_privacy.py`).

**Frontend — ✅ Complete, deploy pending:** `api/intervals.ts` + `schemas/intervals.schema.ts` (Zod: cadence ≥60, repeat-count ≥2) + `types/intervals.types.ts`; hooks `hooks/intervals/useIntervals.ts`; components `components/intervals/{StructureEditor,AgeGateDialog,BlockRow,PlanVsActualTable,InstructivoDownloadButton,TemplatePicker}.tsx` (`AgeGateDialog` mirrors `AgeBandGuardrailDialog` from feature 021); `SessionDetailPage.tsx` gains an "Estructura de intervalos" section; new lazy coach/admin routes `routes/intervals/TemplateLibraryPage.tsx` and `routes/training/ActivityMatchPage.tsx`, both wrapped in `ProtectedRoute allowedRoles={[coach, admin]}`. Compliance badges use the canonical semantics (green=cumplido, amber=fuera de tolerancia, gray=sin dato); loading/empty/error states designed for the match view ("aún no hay actividad enlazada", "calculando comparación…").

**Status:** ✅ Complete — deploy pending. Run migration `b5c6d7e8f9a0` on Render (`alembic upgrade head` via `entrypoint.sh`).

> **Data privacy (authoritative):** `strava_activity_laps` persists only `lap_index`, `elapsed_time_s`, `moving_time_s`, `average_heartrate` (nullable), `average_speed_m_s` (nullable), `fetched_at`. **Explicitly absent**: `start_latlng`/`end_latlng`, polyline/map of any kind, lap free-text name, `average_cadence` (deferred to v2), `average_watts`. Lap data appears only inside the match-detail response — there is no standalone laps listing endpoint. `interval_structure_blocks`/`interval_template_blocks` have no power column at all (v1 targets are HR zone + cadence only, by construction, not by age-conditional gating). All `/api/intervals` routes are coach/admin-only; parents/athletes get 403 on every route, including match detail and laps. See `specs/026-structured-interval-training/data-model.md` § Access control invariants.

---

## Implementation status — Coach Home Mission Control (specs/031-coach-home-mission-control)

Rebuild of the coach's `/dashboard` landing page as a "mission control" surface: a hero strip (next session, next race with taper-window urgency tiers, weekly-load meter by age band) plus a 5-row pending inbox (results to import, activities to link, newsletters due, consents pending, insights stale), with the existing `MeasurementAlerts` row preserved byte-for-byte (FR-006). Two independently shippable increments per `plan.md`: **A** — hero tiles + inbox rows on existing/reused data, no backend change; **B** — one new endpoint `GET /api/dashboard/coach-summary` (`consents_pending`, `insights_stale`, `weekly_load`) feeding the meter and the two net-new inbox rows, each sub-aggregate independently `try/except`-isolated so a partial failure degrades that field to `null` instead of 500ing the page. No new runtime dependency (`recharts` deliberately **not** imported into this route — Constitution IV). No Alembic migration. Backend router/service/schema, frontend tiles/hooks/MSW mocks, and the `frontend/e2e/dashboard-coach.spec.ts` link-through spec are implemented in the working tree; this entry currently documents **T059 only** (the Polish-phase LCP guard note) — see `specs/031-coach-home-mission-control/tasks.md` for the remaining Polish-phase checklist (T060 manual SC sweep, T061 lint/typecheck) still to be run and recorded.

**T059 — LCP guard note (`quickstart.md` §4, Constitution IV: dashboard-route LCP ≤ 2.5 s, simulated 3G, mid-tier Android):**

- **No dedicated Lighthouse harness is checked into this repo.** The only prior LCP measurement against `/dashboard` was a one-off manual pass done for `specs/028-frontend-design-foundation` (`tasks.md` T076): `playwright-lighthouse` was installed **locally only** (never added to `frontend/package.json`) and is not present in `frontend/node_modules` today. Per this task's own constraints (no new dependency installs), that tool was not reinstalled to produce a fresh number — **flagging this gap explicitly rather than silently skipping it**, per the task instruction.
- **028's last recorded measurement is the relevant baseline, and it already failed the budget**: `/dashboard` LCP **6.6 s** vs. the ≤2.5 s target (`/athletes` passed at 1.2 s), attributed to a pre-028, still-unaddressed structural cause — a single ~610 kB gzip main bundle with no route-level code-splitting, paid in full on the first post-login page load under throttling. 028 explicitly flagged this as a legitimate out-of-scope follow-up (candidate "033 or a new perf-focused feature"), not caused by 028 itself.
- **This feature (031) makes the pre-existing gap materially more relevant, not less**: `/dashboard` now issues 6 fixed-shape fetches on landing (next-session, next-race/results-to-import share one `useRaceEventsList`, activities-unlinked, newsletters-due, alerts, plus the new `coach-summary`) versus 1-2 before (`plan.md` Performance Goals, `research.md` R2). None of the new requests are render-blocking above the fold in a way that changes the bundle-size root cause identified in 028, so the expectation is the LCP regression persists at roughly the same magnitude — but this has **not been re-measured** and is called out here as unverified rather than assumed.
- **Action needed before this feature can be marked deploy-ready on the LCP criterion**: either (a) stand up a real, checked-in Lighthouse/Playwright-perf harness (`playwright-lighthouse` added to `frontend/package.json` as a devDependency, or an equivalent CI-runnable check) and run it against a production `vite build` + `vite preview` of this route, or (b) explicitly accept the pre-existing 028 finding as the tracked baseline and open the dedicated bundle-splitting follow-up 028 already recommended. Neither has happened yet — this is the flagged gap, not a resolution.

---

## Implementation status — Session Content Unification (specs/032-session-content-unification)

Collapses three contradictory "attach training content to a session" interactions into one pattern. Before: intervals attached inline on the session (the good pattern); strength required building a block on a separate page then searching for the target session by name (no preselect); technique could only *create a brand-new duplicate session* via a parallel creation endpoint — there was no way to attach technique exercises to a session that already existed. After: all three attach from within an existing session's Plan tab through the same picker interaction, and `SessionDetailPage.tsx`'s 7 stacked blocks are reorganized into 4 named, URL-synced sections (Resumen/Asistencia/Plan/Media) on `ui/tabs.tsx`, plus a "Hoy" quick filter + non-color-alone today marker on the sessions list. Every existing age-band safety gate (`AgeBandGuardrailDialog`, `AgeGateDialog`) is reused verbatim at the same trigger points — zero new gates, zero regressions (SC-007).

**Backend — ✅ Complete, no migration (verified via autogenerate-diff-and-discard against the local dev DB — `technique_session_exercises`/`strength_session_blocks`/`interval_structures` do not appear in the generated diff):**

| Layer | File | Change |
|---|---|---|
| Schemas | `app/schemas/technique.py` | NEW — `AttachExercisesRequest` (`items: list[AssembleItem]`, min 1), `AttachExercisesResponse` (`mixes_age_bands`, `items`), reusing existing `AssembleItem`/`TechniqueSessionItem` verbatim |
| Router | `app/routers/technique.py` | NEW `POST /api/technique/sessions/{training_session_id}/exercises` — sibling of the existing `GET` at the same path, `_require_coach_or_admin` + `_coach_club_id` |
| Service | `app/services/technique/assembler.py` | NEW `attach_exercises_to_session()` — 404 on session not found/foreign-club (never 403, no existence leak); 422 via `_load_exercises_by_ids` on unknown exercise id; de-dupes on `(exercise_id, segment)` (idempotent retry — FR-009); appends at `max_position_in_segment + 1`; reuses `_compute_mixes_age_bands` |

**Tests:** `backend/tests/technique/test_technique_attach_to_session.py` (9 cases: happy path, append-onto-existing, RBAC 403, not-found 404 ×2, validation 422 ×2, idempotency-retry row-count regression, query-count no-N+1 guard). Full `tests/technique/` + `tests/strength/` regression (316 tests) green, no regressions.

**Frontend — ✅ Complete:** new `components/training/session-plan/` folder — `SessionPickerDialog.tsx` (shared "¿a qué sesión?" picker, re-sorts the API's `scheduled_date DESC` response ascending client-side per the R6/R10 ordering gotcha), `TechniqueAttachPicker.tsx` and `StrengthBlockPicker.tsx` (both modeled on `TemplatePicker.tsx`'s idle/pending/error convention; a strength `409` renders as a soft "ya está adjunto" notice, not a blocking error), `PlanSection.tsx` (hosts all three content types + the unchanged intervals block relocated verbatim + one combined `EmptyState` when all three are empty). `BlockBuilderPage.tsx` gained `?session_id=` read/lock (static-text + Lock/Pencil "locked read-only summary" convention from feature 015, not a `disabled` input) and auto-attach-then-navigate on save. `SessionDetailPage.tsx` restructured onto `ui/tabs.tsx` (`TabsTrigger` bumped `min-h-11`→`min-h-12`, the club's 48px floor) with `?section=resumen|asistencia|plan|media` URL sync — defaults to `asistencia` on the day of the session (club timezone) else `resumen`, push for explicit clicks vs. replace for the auto-default so back-navigation returns to the previous section. `frontend/src/lib/datetime.ts` gained `todayISODate()`/`isToday()`; `SessionFiltersBar.tsx` gained a "Hoy" quick filter; `SessionsTable.tsx` gained an icon+text today marker in both its mobile-card and desktop-table render branches.

**Touch-target fix applied post-implementation:** the real (non-mocked) Playwright run of the new `frontend/e2e/session-content-unification.spec.ts` caught 3 genuine Constitution III violations under the 48×48px floor — `TechniqueAttachPicker`'s selection checkbox (20×20px native `<input type=checkbox>`), `StrengthBlockPicker`'s "Adjuntar a la sesión" button (`Button size="sm"`, 36px), and `PlanSection`'s "Crear estructura" trigger (raw `<button>`, no min-height, relocated verbatim from feature 026). Fixed by resizing the checkbox to `h-12 w-12`, the strength button to `size="lg"`, and adding `min-h-12` to the intervals trigger — all three using patterns already proven compliant elsewhere in this codebase. Re-verified via the affected vitest suites (70/70 pass) and a full frontend regression run (3412/3418 — the 6 failures are pre-existing, in files this feature never touches: `datetime.test.ts`'s environment-TZ-dependent `currentSeason` assertion, feature-031's `DashboardPage.test.tsx`, and feature-016's `event_id`-contract change in `ResultsTableLaunch.test.tsx`/`InsightsTabAnalyze.test.tsx`).

**Outstanding before deploy:** T048 — the manual quickstart.md walkthrough on an actual tablet or throttled-network desktop emulation (US1 AC1–5, US2 AC1–4, US3 AC1–2, the mid-attach connection-loss edge case, both age-band gate edge cases) has **not** been performed; it requires a human coach and a physical device, consistent with this repo's "deploy pending" convention for finished-but-unvalidated features. SC-003 (attach all three content types in under 3 minutes) also has no automated timing assertion — needs sign-off as part of the same manual pass.

**Status:** ✅ Complete — deploy pending (no migration to run; T048 manual validation pending).

---

## Implementation status — Visual Coherence & Polish (specs/033-visual-coherence-polish)

Presentation-only sweep (FR-010: no schema change, no AI pipeline/prompt/scoring/budget-logic change, no generated-document change, no Principle V anxiety-module wording/logic/consent-gate change — only how existing state is rendered/styled). Five user stories: **US1** one shared `success/warning/danger/neutral` status vocabulary via `StatusBadge` everywhere (8 domains migrated), plus the A/B/C race-class ramp fixed so `"CD"` (Campeonato Departamental) reads as tier `A` instead of a spurious 4th value; **US2** honest charts — solid grids, shared color roles, an on-point championship diamond marker, capped reference labels past 8 riders, and a "Gráfica"/"Tabla" toggle on both `DistributionChart`/`EvolutionChart`; **US3** técnica/fuerza/intervalos/ansiedad modules de-slated (`slate-*` → `text-charcoal`/`text-mid-gray`/`bg-light-gray`/`border-border-gray`) to match the rest of the app, plus técnica and fuerza's near-duplicate catalog/filter/card components consolidated into shared `components/shared/{CatalogGrid,LibraryFilterBar,LibraryEntityCard}.tsx`; **US4** one AI identity everywhere — noun "Insights IA", verb "Analizar con IA", icon `Sparkles` (all `BrainCircuit`/"Lanzar" instances removed, `MessageSquare` kept only as chat's documented exception), one run-progress view at two densities (`AnalysisRunTimeline` full/`compact`), and a new proactive pre-launch AI budget/wait hint (`GET /api/ai/status`) instead of only a post-click failure; **US5** (P3, optional — shipped) a dark appearance following device/stored preference at the same contrast bars as light mode (coach surfaces only, parent portal stays light-only), plus `g`+letter/`n`/`?` keyboard shortcuts for desktop navigation with input/modal guardrails.

**Backend — ✅ Complete, no migration:** `GET /api/ai/status` (`backend/app/routers/ai.py`, `AIStatusResponse` in `app/schemas/ai.py`) — `budget_status`/`budget_remaining_pct` reusing `_sum_cost_last_30d()`/`race_ai_budget_usd_30d` (`services/race/ai/budget_guard.py`), `concurrency_available` reusing `has_capacity()` (`services/race/ai/runner.py`), `est_wait_seconds` from the same p50-latency computation `admin_ai_usage()` already performs; coach/admin-gated, no PII. **Regression fix found by its own idempotency test**: `budget_status`'s `"exhausted"` branch is anchored to the same raw comparison `check_budget()` uses (not the already-rounded `budget_remaining_pct`), so a tiny nonzero remainder can no longer round down to a false "exhausted" reading that would drift from the real 503 trigger (SC-004's load-bearing regression concern). 26 tests in `backend/tests/routers/test_ai_status.py`.

**Frontend — ✅ Complete:** 8 pure status adapters (`connectionStatus`, `resultadosStatus`/`calendarioStatus`/`condicionesStatus`, `sessionStatus`, `confidenceStatus`, `newsletterStatus`, `consentStatus`/`aiConsentStatus`, `staleAnalysisStatus`, `groupRunStatus`) each feeding the shared `<StatusBadge>`, replacing 8 hand-rolled color implementations (including deleting `GroupRunRow.tsx`'s `StateChip` and `AthleteAIAnalysisTab.tsx`'s duplicate confidence-badge logic). New `frontend/scripts/validate-palette.mjs` (self-authored equivalent of the `dataviz` skill's validator — the original source wasn't found on this machine to vendor from; calibrated against `research.md`'s published contrast/lightness numbers) backs both the chart-palette and A/B/C-ramp regression tests and the new dark-token contrast audit. New `useAIStatus()` hook + `AIBudgetHint` wired into all three AI launch entry points (`AnalyzeAthleteButton`, `GroupAnalysisPanel`, `SessionAssistantPage`). Dark mode: `data-theme` activation via a pre-hydration inline script in `index.html` (no flash-of-wrong-theme), `localStorage` key `tyr:theme-preference:v1`, Sistema/Claro/Oscuro toggle in `UserMenu.tsx`. Keyboard shortcuts: `frontend/src/hooks/layout/useKeyboardShortcuts.ts` + `KeyboardShortcutsDialog.tsx`, mounted once in `UserMenu.tsx` (rendered shell-wide via `AppShell`).

**Dark-mode bug found and fixed during this feature's own final gate:** `DistributionChart.tsx`/`EvolutionChart.tsx`'s `<CartesianGrid>` and the new `KeyboardShortcutsDialog.tsx` hardcoded light-mode-only `rgba(34,42,53,...)` literals instead of `var(--color-border-gray)`/`border-border-gray` — `contracts/chart-style.md` (written before dark mode was in scope) had told US2's implementers to keep the literal verbatim, which was correct for light-only but never got reconciled against `contracts/dark-theme-tokens.md` turning that same token dynamic. Result: grid hairlines and dialog borders would have gone near-invisible on the `#1a1a1a` dark surface. Caught by the new `darkTheme.a11y.sweep.test.tsx`'s dedicated "dark-on-dark invisible marks" check, fixed by swapping the 4 literals for the CSS variable/utility class (byte-identical in light mode).

**Two findings documented but deliberately left unfixed (outside this feature's literal task scope, FR-010 discipline):** (1) técnica's `CatalogPage.tsx`, fuerza's `CatalogPage.tsx`, and `AnxietyDashboardPage.tsx` still hand-roll their page `<h1>` instead of the shared `PageHeader` component (feature 028) every other top-level page uses — same color/size, but renders in the body typeface (Inter) instead of the display typeface (Cal Sans) every other page title uses. (2) `frontend/src/components/training/session-plan/{TechniqueAttachPicker,StrengthBlockPicker,SessionPickerDialog}.tsx` (feature 032, session-planning flow) still carry ~21 `slate-*` occurrences — they live outside the exact 8 directories this feature's slate-remediation tasks targeted, so a coach attaching técnica/fuerza content mid-session-planning still sees the old slate-gray styling.

**Status:** ✅ Complete — deploy pending. No migration. No new runtime dependency. Zero regressions in the anxiety module (Principle V, line-by-line diff-reviewed: 100% className/token-only changes across all 9 touched files) or in generated documents (no document-generation file touched by this feature's diff at all).

---

## Implementation status — Align Monthly Report to Approved Format (specs/022-align-monthly-report-format)

New `plan_entrenamiento` narrative block + auto-generated `competencia`; PDF restructured to approved institutional section order; per-session detail table + per-athlete rubric averages in `metrics_snapshot`; competition results grouped by jornada (`event_id`/`series_kind`/`awards_points`) with points/no-points note; photo register auto-grouped by section from `session_kind` + race-date heuristic; new DOCX export via docxtpl, `GET .../monthly-reports/{year}/{month}/docx`; shared `build_report_document_context` feeds both PDF and DOCX with backward-compatible "Pendiente — regenerar informe" fallback for pre-feature snapshots.

**Status:** ✅ Complete — deploy pending (no Alembic migration, additive JSON-column changes only).

---

## Implementation status — Interval Duration Usability (specs/034-interval-duration-usability)

mm:ss entry for block durations via new `MmSsInput`; `duration_type` discriminator `fixed`/`open_lap` restricted to warmup/cooldown, never inside repeat groups; open-ended "Libre — hasta botón de vuelta" blocks in editor, totals, PDF instructivo; plan-vs-actual comparison ENGINE_VERSION 1→2 with informational `libre` status, stored v1 comparisons unchanged. `duration_s` made nullable — `fixed` keeps exact-seconds behavior, `open_lap` carries no duration (enforced in editor and server-side at save time). Comparisons stored under engine v1 render verbatim, no retroactive recomputation. `MmSsInput` replaces raw-seconds entry in both the structure editor and the template library editor — storage stays integer seconds, only display/entry changes. PDF instructivo (all brands) renders open-ended blocks with zone/cadence still shown. Backward-compatible/additive — pre-existing rows and drafts without an explicit duration type default to `fixed`.

**Status:** ✅ Complete — deploy pending (migration `c7d8e9f0a1b2`).

---

## Implementation status — Nav & Coach Dashboard Redesign (specs/035-nav-dashboard-redesign)

Frontend-only visual/IA redesign of the lateral navigation (coach/admin + parent portal) and the coach home, implemented from the design canvas mockups in `specs/035-nav-dashboard-redesign/mockups/` (README there links the live canvas). No routes, roles, or destinations changed — the six `NAV_AREAS` are only regrouped.

**Coach/admin sidebar:** `SidebarNav` now renders the full sidebar interior (brand row with `public/logo-mark.png`, grouped nav, footer slot). Two overline groups «Operación»/«Club» via new `NavArea.group` + `getGroupedAreas(role)`; active state = `--color-nav-active-bg` tint + 3px brand bar + `--color-nav-accent` icon + charcoal semibold (both new tokens in `style.css`, defensively duplicated `:root`/`@theme` with dark overrides; color never the only channel). Feature 030 contracts preserved (dual ≥44px controls, auto-expand, `aria-current`). New `useSidebarCollapsed` (localStorage `tyr:nav-collapsed:v1`, default collapsed 768–1023px) drives a 72px icon rail with tooltips; new `useNavBadges` surfaces real pending counts (results-to-import on Competencias, unsent newsletters on Familias) reusing PendingInbox's exact query keys — zero extra requests; badge → amber dot + tooltip count in rail mode. `UserMenu` gained `sidebar`/`sidebarRail` variants and lives in the sidebar foot at ≥md (header keeps it <md, testid `user-menu-trigger-header`); the `g`-chord/`n`/`?` shortcuts hook + dialog moved from `UserMenu` to `AppShell` (asserted single mount). `QuickCreate` is now a labeled primary «Crear» button (min-h-12).

**Parent portal:** new `ParentBottomNav` (5 slots: Inicio/Calendario/Entrenos/Resumen/Perfil, `md:hidden`, exact-first longest-prefix active resolution) and `ParentSidebar` (drawer/static interior: athlete switcher rows via `useActiveAthlete`, iconed nav with the same active-pill language, Mi perfil/Cerrar sesión, consent chip via `useMyConsentStatus`), wired in `AppShell`; drawer chrome, forced-light theme and `AthleteSwitcher` header untouched.

**Coach home:** greeting header («Hola, {nombre}» + ISO week/sessions/next-race subtitle, parts omitted while loading), then existing tiles row (with `NextRaceTile` gaining a «Clase A/B/C» tier chip + `TAPER_GUIDANCE` line), new `WeekStrip` (current club-TZ week, today highlight, session pills, executed check), restyled `PendingInbox` («Pendientes» card) and `MeasurementAlerts`, and new `AttendanceMiniChart` (last 4 executed sessions from `attendance_summary`, pct = presentes+tardes/total, single-hue bars, sr-only summary). Cold-start skeletons, absent-aggregate omissions, and admin gating all preserved.

Built by a 9-agent workflow (parallel implementation → integration → validate → adversarial review); the review pass fixed 17 verified findings (WCAG AA contrast on teal, 48px target floors, 3 Playwright specs asserting the old copy, es-CO pluralization). Suite: 309 files / 3915 vitest tests green, `tsc --noEmit` clean.

**Status:** ✅ Complete — deploy pending. Frontend-only, no migration, no new dependency.

---

## Implementation status — AI Insights Tab Review (specs/036-ai-insights-tab-review)

A UX-audit-driven bugfix pass on the athlete AI Insights tab (`AthleteAIAnalysisTab.tsx` + its five sub-tabs: Panorama, Histórico, Evolución, Distribución, Analizar con IA — a 5→3 sub-tab collapse was explicitly rejected mid-review and stays out of scope), run as 5 serialized waves (one workflow per wave, strict file ownership between parallel agents, one integration agent per wave). Two decisions taken with the user override `spec.md`/`plan.md`: **stay on Gemini** (`google`/`gemini-3.1-flash-lite`, not the Anthropic migration `research.md` assumed — production never ran Anthropic for this pipeline) and **do not collapse the sub-tabs** (Open Question 3 was never approved).

**Wave 1 (US3 state isolation + US4 fallback marking):** `key={athlete.id}` on the tab's mount in `AthleteDetailPage.tsx` (and, closing the feature, the same fix mirrored onto `MyAthleteDetailPage.tsx`'s parent-only mount — not reachable by clicking today on either surface since both apps only reach a different athlete's page by detouring through a list route that unmounts the page first, but the two mount sites are otherwise symmetric and the parent one had been missed) forces a clean remount on athlete switch — without it, `AthleteAIAnalysisTab`'s `useState` (sub-tab, selected insight, active run, HITL step, newsletter selection) leaked from one athlete to the next. `activeRunId` is now cleared on run completion (previously pinned the timeline above the sub-tabs forever). `is_fallback` insights (deterministic placeholder text from a failed LLM call) are badge-marked and excluded from newsletter selection in both `InsightsTimeline` (checkbox suppressed) and `HeroLastInsightCard` (its own, separate "Agregar al boletín" button suppressed too — a second route to the same defect the checkbox alone didn't cover) and rejected server-side with 422 by `POST .../attach-insights` even if a client sent the id directly. Backend: `AthleteInsightOut` and the season-summary use case both now set `is_fallback` (neither did before Wave 1 — the flag existed in the model but two of three write paths never populated it). Migration `463c1f0ccb38`.

**Wave 2 (US5 truth on screen):** one label helper survives — `validaLabel` (`lib/insights.ts`, roman numerals, e.g. "Válida III") — replacing the retired arabic-numeral `getValidaLabel` (`lib/raceCalendar.ts`) that produced colliding labels for two same-numbered races in different series. The tab's race identity contract is now `event_id`/`event_date`/`series_kind` end-to-end (both `AthleteInsightOut` and the TS type), resolved server-side through the existing FK so two Departmental Championships render as distinguishable chips (`CD · 12 jun`). `insights_history.list_athlete_insights` now orders by `event_date DESC` server-side (season-aggregate rows sort last); the client must not re-sort. `POST .../runs` returns 409 for a second concurrent run on the same athlete+válida; `POST .../season-summary`'s dedup lock now runs before the LLM call, so a double submit is a 409, not a 500 after spending budget. **Out-of-band privacy fix**: `forbidden_names` (the guardrail stopping the LLM from naming the minor or their family) was **always empty in production** — the query selected a non-existent `UserModel.full_name` column, and the resulting `AttributeError` was swallowed by a bare `except` that only logged a warning. Rebuilt from `first_name`/`last_name` (athlete + linked parents), the `except` narrowed to `SQLAlchemyError` so a future break is loud, not silent. `stale_run_id` deleted from both sides (it was frontend-only dead weight — never actually declared server-side despite `tasks.md` describing a backend field).

**Wave 3 (US2 analysis quality):** eval migrated off the v1 pipeline onto the real v2 `invoke_per_valida`, with 3 new sub-rubrics (repeated figures, analytical connectors, lap-muletilla). Result: **composite 0.651, below the 0.75 blocking gate** — see "still open" below.

**Wave 4 (US6 devices + a11y):** the tab is now lazy-loaded from both `AthleteDetailPage.tsx` and `MyAthleteDetailPage.tsx` (main bundle −92 kB raw / −24.8 kB gzip, real measurement); microcopy pass (coach subtitle, "Revisión paso a paso", "Máximo 4 a la vez"); a round of touch-target/copy fixes under T090–T097, several later found still non-compliant by Wave 5's repaired e2e sweep (see below).

**Wave 5 (US7 end-to-end safety net + feature close):** the module had 0% real coverage of its own HITL-derivation logic and launch→approve flow (everything mocked at the unit level) and exactly one e2e spec touching the tab at all (three Copa-vs-Championship picker scenarios). Added: 4 new self-contained Playwright specs (`e2e/ai-insights-{coach,hitl,newsletter,parent}.spec.ts`, 9 tests, all `page.route()`-mocked, zero backend dependency, synthetic athlete names only) covering the coach happy path, the full launch→timeline→HITL-approve→history flow, HITL reject/edit (previously untested even at the unit level — `HITLApprovalCard.test.tsx` asserted the "Editar" button existed but never clicked it), the newsletter sticky bar end-to-end (through to a real, navigable newsletter resource), the parent view as a privacy boundary (not just a layout difference — DOM absence + a network safety net asserting coach-only endpoints are never even requested), and the US3 athlete-switch regression at the outermost (browser) level. Backend gained admin-role tests for the 6 endpoints that lacked them and parent-denial tests for `/distribution`/`/evolution` — plus, found while auditing US7's own acceptance criteria at close, one more denial-test gap on `GET .../insights/{id}` (its only prior parent-role test covered "insight not active", not "insight belongs to a different child"), closed and proven load-bearing against the shared `verify_athlete_access` dependency. `useRaceRun.ts`'s 304-not-modified branch, event dedupe by `seq`, and `resetEvents` gained unit tests; `resetEvents` was kept (unlike two other unused hooks, `useRunResult`/`useInvalidateRun`, which stay unwired but undeleted pending a product decision) since a co-equal task in the same wave required testing it and it has an obvious near-term use. Two real, previously-unknown bugs were found and fixed in `HITLApprovalCard.tsx` while writing its "Editar" flow test: (1) `handleSaveEdit` decided whether to close the edit dialog by reading `mutation.isError` from a stale closure captured before the click, so it was structurally always `false` — a failed save silently closed the dialog as if it had succeeded; fixed by having `submit()` return a success boolean instead. (2) the existing error banner rendered in the component's background `<section>`, which Radix marks `aria-hidden` once the edit Dialog's portal opens, so a coach whose save failed while the dialog was open never saw why; fixed by rendering a second copy of the error text inside the dialog itself.

**Feature close (same wave, integration pass):** re-ran the full backend suite (3670 passed, 196 failed + 5 errors — all reconciled against three pre-existing buckets: `MYSQL_HOST=mysql` not resolving on the host, WeasyPrint missing `libgobject-2.0-0`, and 3 unrelated bugs in `test_ai_factory.py`/`test_calendar_audiences.py`/`test_calendar_models.py`; zero residue caused by this feature) and the full frontend suite (4025/4026, the one failure being the pre-existing `datetime.test.ts` UTC-5 assumption). Diagnosed and fixed the actual cause of an earlier "Playwright doesn't work in this sandbox" misdiagnosis: `frontend/.env.local`'s `VITE_API_BASE_URL=` (empty string) survived `??`'s null/undefined-only fallback, leaving axios on a relative baseURL that never matched any spec's `:8000`-only route predicate — fixed by pinning `VITE_API_BASE_URL` in `playwright.config.ts`'s own `webServer.env`, making the e2e suite self-contained. Repaired `e2e/target-size.spec.ts`'s 4 pre-existing (feature-028) tests, broken by fixture dates fixed in calendar year 2026 rotting into the past as the real clock advanced past them (bumped to 2099, with a comment explaining why so it doesn't happen again) — this was a test-fixture bug, not a `page.route()` sandbox limitation. With the sweep actually running, it surfaced 17 real, previously-"likely but never confirmed" 16px/35px/36px/44px touch-target violations owned by this feature (shadcn `size="sm"` buttons, native `<select>`s, a bare-padding text link, an icon-only Sheet-adjacent trigger, all short of the project's 48px floor — the shared `Button` component's own "default" size is only 44px, so `size="lg"` or an explicit `min-h-12` override is required either way) across `HeroLastInsightCard.tsx`, `SeasonSummaryButton.tsx`, `LaunchAnalysisForm.tsx`, `DistributionChart.tsx`, `ComparatorPanel.tsx` (fixed at the single shared `TAP_TARGET_CLASSES` constant, `44px→48px`, correcting all 4 of its call sites at once) and `AthleteAIAnalysisTab.tsx`'s newsletter action bar — all fixed and re-verified via a live Playwright re-run showing zero feature-036-owned entries left in the violation dump. `target-size.spec.ts` still fails 8 of 9 tests, but now purely on **pre-existing, shared, out-of-this-feature's-blast-radius** controls confirmed unchanged by this feature via `git diff` (`AppShell`'s `SidebarNav.tsx`, `AthleteDetailPage.tsx`'s own top-of-page chrome shared by every tab, and `components/ui/sheet.tsx`'s shared close button, used by 6+ unrelated features) — deliberately left alone rather than expanding this feature's blast radius into shared/sitewide components at the very end of the review. `hero-valida-info-trigger` (a parent-only 16×16 inline info icon) was also left alone: it exactly mirrors a pre-existing sitewide convention (`ParentSessionCard.tsx`'s `InfoIcon`, byte-identical classes), so fixing only the feature-036 copy would create a one-off inconsistency rather than fix a systemic pattern. Two more obsolete `@pytest.mark.xfail` markers were found and removed in `test_season_summary_endpoint.py` (same smell as the two the wave's own task named in `test_persist_insight_per_valida_v2.py`, now genuinely resolved and left un-marked) — 6 more in `test_guardrails_race_v2.py` were left alone since that file has zero relation to this feature. T071 (launch→HITL→approve) and T075 (athlete switch) were proven load-bearing by live sabotage: reverting the `handleRunComplete` fix and removing `key={athlete.id}` each turned the corresponding spec red for exactly the expected reason, then both were restored and reverified green.

**Still open, by design, for someone else to resolve:**
- **T059 — the golden-eval gate**: composite score **0.651 < 0.75**, blocking. Case 010 hit the shared `guardrails.py` veto regexes (negation-blind — "no necesita más horas" trips the same rule as "necesita más horas") and fell back to a 16-word deterministic placeholder; excluding it, the other ten still average ≈0.696. Needs a dedicated prompt-iteration pass (or a negation-aware veto rewrite, or loosened `expected_themes` matching) with its own eval budget — not resolved this feature.
- **Open Question 1 (spec.md)**: other clubs' minors' real names in the coach-only Distribution chart (sourced from a public federation PDF) — deferred by explicit user decision (D2), data behavior untouched, only the UI's false claims about it were corrected.
- **Open Question 2 (spec.md)**: `GET /insights/{id}` doesn't filter `metrics_snapshot` by role, so a parent calling the API directly (not through the SPA) can read `race_time_ms`/`podium_gap_ms` that the UI deliberately hides per Principle V. Confirmed unchanged this feature — still a client-side-only mitigation, not a backend filter.
- Newsletter attach has no visible confirmation surface yet: `POST attach-insights` persists `selected_race_insight_ids` on the newsletter row, but nothing downstream (`AthleteNewsletterRead`, the frontend type, any `email_blocks` builder, the PDF template) reads it back — a coach who successfully attaches an insight has no page anywhere that shows its content landed. Outside this feature's owned files (backend schema + frontend newsletter types); flagged for whoever owns that feature next.
- `PdfDownloadButton.tsx` (`components/ai/`) is a complete, backend-connected, tested-quality component mounted nowhere in the tab; wiring it into the coach run-timeline block is a one-line addition for whoever owns `AthleteAIAnalysisTab.tsx` next.

**Status:** 🟡 Functionally complete and verified (all 5 waves' own acceptance criteria hold, full backend+frontend suites green modulo pre-existing/environmental failures, all-new e2e specs green and proven load-bearing) but **not deployed**: everything is uncommitted on `main` by explicit user choice (Decision D6), the golden-eval gate (T059) is still red, and Render's `RACE_AI_PROVIDER`/`RACE_AI_MODEL` were never verified against the Gemini correction (D1) before this review started. No new migration beyond `463c1f0ccb38` (adds `is_fallback`). `tasks.md` checkboxes for waves 2–5 still need marking (Wave 1's are already `[X]`) — left to the user per this task's instructions not to edit `tasks.md`.

---

## Implementation status — AI Insights v3 (specs/037-ai-insights-v3-causal)

Causal, field-relative, prescriptive replacement for the per-válida AI
analysis contract (supersedes `docs/10-race-results/spec-insights-per-valida-v2.md`
§4's 3-section markdown output). Full architecture, `InsightV3` contract,
prechecks, expected-vs-actual method, and rollback in
`docs/10-race-results/spec-insights-v3.md`; bug-fix details in
`docs/technical-notes.md` (2026-09-02 entry).

| Wave | Scope | Status |
|---|---|---|
| 1 | Data & fixes: `valida_num` population, recommendation-regex relaxation, `athlete_ref` from `Athlete.sex`, per-role model config, `field_metrics.py`, `load_athlete_context` node + loaders, `answer` endpoint + migration, `recall_memory` → `coach_dialogue` | ✅ Complete 2026-09-02 |
| 2 | LLM layer + frontend contract: `InsightV3` + v3 prompts + `invoke_v3`, deterministic prechecks + critic v3, season-summary-as-graph-run + consent gate + athlete-scoped chat tool, `RACE_AI_PROMPT_VERSION` switch, frontend types/api/hooks/MSW/fixtures | ✅ Complete 2026-09-02 |
| 3 | UI: `InsightV3Card` (+ sub-blocks) integrated into timeline/hero/HITL, `CoachAnswerForm`, `AthleteAnalystChatPanel`, `SeasonSummaryButton` run-timeline wiring | ✅ Complete 2026-09-02 |
| 4 | Quality: golden eval v3 (`golden_v3/`, `scorer_v3.py`, `judge_v2.md`), privacy audit (PASS on all six points), docs, backend gaps (451 gate on `start_athlete_run`, `role="chat"`, plural `structured_drafts`) | ✅ Complete 2026-09-02 — SC-1 real-dataset regeneration and the real golden run (`pytest -m golden`, needs `RACE_AI_API_KEY`) still pending |

**Known gaps carried forward from Waves 1-2** (see
`spec-insights-v3.md`'s runbook section for the full list):
`start_athlete_run` still lacks the AI-consent 451 gate that `start_run`
and the season endpoint already have; `chat.py` does not pass
`role="chat"` explicitly to `build_chat_llm` (harmless, same default);
`ActionCategory.tactics` degrades to `technique` in the v2-compat
`AnalysisOutput.recommendations` copy only; `hitl_gate_review`'s
`structured_draft` payload exposes only the lowest válida of a
multi-válida run; the v3 season prompt relies on the `trend` field plus
prechecks rather than a hard N=1 veto; critic model provenance is not
persisted separately from the analyst's (single `model` column).

**Status:** 🚧 Waves 1-4 complete and integrated on the working tree
(uncommitted); pending SC-1 verification on the local dataset and the real
golden eval run in CI.
