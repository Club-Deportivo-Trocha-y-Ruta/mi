# Tasks: Strava Activity Sync with Coach-Gated Session Linking

**Input**: Design documents from `/specs/025-strava-activity-sync/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: INCLUDED — Constitution Principle II (NON-NEGOTIABLE) mandates pytest + vitest + jest-axe coverage with happy AND negative paths, plus privacy invariants for minors' data.

**Organization**: Grouped by user story. Each task carries its assigned specialized agent and model. **Constraint (user): subagents never run on `fable` — only `sonnet` (design/code/tests) or `haiku` (mechanical edits).**

## Format: `[ID] [P?] [Story] Description — Agent: <agent> | Model: <model>`

- **[P]**: Parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 (auto-sync), US2 (coach linking), US3 (parent visibility)

## Path Conventions

Web app: `backend/app/`, `backend/tests/`, `frontend/src/` (per plan.md Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration surface + dependency plumbing; no behavior yet

- [X] T001 Add `strava_*` settings block to `backend/app/config.py` (all 9 settings from data-model.md §4, prod validators requiring client credentials + Fernet key + reconcile token when `strava_enabled=true`, following the `email_provider`/`ai_*` validator pattern) — Agent: fastapi-architect | Model: sonnet
- [X] T002 [P] Promote `cryptography` to direct dependency in `backend/requirements.txt` and document why (Fernet token encryption) in the requirements comment — Agent: devops-engineer | Model: haiku
- [X] T003 [P] Add `STRAVA_*` env vars to `.env.example` and to the production env-var table in `CLAUDE.md` (values redacted, generation commands in comments per quickstart.md) — Agent: devops-engineer | Model: haiku
- [X] T004 [P] Implement `backend/app/services/strava/token_store.py` — Fernet encrypt/decrypt helpers with module docstring (inputs/outputs/side effects), raising a clear config error when key missing — Agent: security-engineer | Model: sonnet

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data layer + RBAC every story depends on

**⚠️ CRITICAL**: No user story work until this phase completes

- [X] T005 [P] Create `StravaConnection` model in `backend/app/models/strava_connection.py` per data-model.md §1 (status enum with `values_callable`, UNIQUE `athlete_id`, UNIQUE `strava_athlete_id`, VARBINARY token columns) — Agent: database-architect | Model: sonnet
- [X] T006 [P] Create `StravaActivity` model in `backend/app/models/strava_activity.py` per data-model.md §2 (UNIQUE `strava_activity_id`, composite index `(training_session_id, start_date_utc)`, enums `upstream_state`/`ingest_source` with `values_callable`, NO GPS/location/description columns) — Agent: database-architect | Model: sonnet
- [X] T007 Add `external_activity_sync: Mapped[bool]` (default False) to `backend/app/models/parental_consent.py`, mirroring the `psychological_assessment` pattern from feature 017 — Agent: database-architect | Model: sonnet
- [X] T008 Generate Alembic migration `backend/alembic/versions/xxxx_add_strava_sync_tables.py` on head `d3e4f5a6b7c8` (two new tables + consent column; verify single head after) — Agent: database-architect | Model: sonnet
- [X] T009 [P] Create Pydantic schemas in `backend/app/schemas/strava.py` (`ConnectionStatusOut`, `AuthorizeUrlOut`, `ActivityOut` — exact ActivityOut shape from contracts/api.md §C including nested `link`, no coordinate fields —, `LinkUpdateIn`, `SessionSuggestionOut`, `ReconcileResultOut`, webhook event schema) — Agent: fastapi-architect | Model: sonnet
- [X] T010 [P] Add `can_view_activity`, `can_link_activity`, `athlete_activity_scope` helpers to `backend/app/services/permissions.py` (admin bypass; coach via `user_club_role`; parent via `parent_athlete_ids`; docstrings) — Agent: fastapi-architect | Model: sonnet
- [X] T011 Register new models in `backend/app/models/__init__.py` + wire empty routers `strava_integration.py`/`activities.py` into `backend/app/main.py` behind `strava_enabled` flag — Agent: fastapi-architect | Model: sonnet
- [X] T012 [P] Foundational tests: model constraints + migration head check in `backend/tests/models/test_strava_models.py` (uniqueness collisions, enum values, consent column default false) — Agent: qa-engineer | Model: sonnet

**Checkpoint**: Schema + RBAC ready — user stories can start

---

## Phase 3: User Story 1 — Connect once, activities flow in automatically (Priority: P1) 🎯 MVP

**Goal**: Per-athlete OAuth (consent-gated), webhook ingest + reconcile fallback; activities appear unlinked under each athlete

**Independent Test**: quickstart.md Scenarios 1–3 — connect one athlete, deliver a (mocked) webhook event, run reconcile; activity visible once, GPS-free, unlinked

### Backend — integration core

- [X] T013 [P] [US1] Implement `backend/app/services/strava/oauth.py` — authorize-URL builder (`scope=activity:read_all`), signed 15-min `state` (athlete_id + user_id + nonce), code→token exchange, refresh-with-rotation via httpx — Agent: integration-engineer | Model: sonnet
- [X] T014 [P] [US1] Implement `backend/app/services/strava/client.py` — httpx Strava API client: base URL from settings, bearer auth with auto-refresh (6 h expiry), 429/`X-RateLimit-*` awareness, `get_activity`, `list_athlete_activities(after, per_page)`, `deauthorize`; module docstring — Agent: integration-engineer | Model: sonnet
- [X] T015 [US1] Implement `backend/app/services/strava/ingest.py` — idempotent upsert by `strava_activity_id`, **GPS/location/description stripping before persistence**, `summary_complete` detection, webhook event dispatch (create/update/delete/deauth per contracts/api.md §B), logs numeric IDs only (correlation IDs, never titles/names) — Agent: integration-engineer | Model: sonnet
- [X] T016 [US1] Implement `backend/app/services/strava/reconcile.py` — per-connection watermark pull (`after = last_sync_at − lookback`), pagination, re-fetch of `summary_complete=false` rows, token-refresh failure → `status=broken`, numeric-only result summary — Agent: integration-engineer | Model: sonnet

### Backend — HTTP surface

- [X] T017 [US1] Implement router `backend/app/routers/strava_integration.py`: `GET/POST /api/athletes/{id}/strava/connect(ion)`, `DELETE` disconnect (best-effort upstream deauth), OAuth `GET /api/integrations/strava/callback` (state validation, scope check, conflict redirect `error=cuenta_en_uso`), consent gate 403 with Spanish copy — per contracts/api.md §A — Agent: fastapi-architect | Model: sonnet
- [X] T018 [US1] Add webhook endpoints to `strava_integration.py`: validation GET (constant-time verify_token, echo `hub.challenge`, no DB work) + event POST returning `200 {}` immediately with processing deferred via `BackgroundTasks`/`TaskDispatcher` — per contracts/api.md §B — Agent: fastapi-architect | Model: sonnet
- [X] T019 [US1] Add `POST /api/integrations/strava/reconcile` (constant-time `X-Reconcile-Token` compare → 403) to `strava_integration.py`, calling reconcile service — Agent: fastapi-architect | Model: sonnet
- [X] T020 [P] [US1] Add minimal read endpoint `GET /api/athletes/{athlete_id}/activities` (coach/admin scope only at this phase) in `backend/app/routers/activities.py` with `selectinload`, so US1 is demo-able — Agent: fastapi-architect | Model: sonnet

### Backend — US1 tests

- [X] T021 [P] [US1] Router tests `backend/tests/routers/test_strava_integration.py`: consent-gate 403, connect 200 + authorize_url shape, callback happy/invalid-state/expired-state/scope-downgrade/account-conflict, disconnect 204, webhook GET echo + bad token 403, webhook POST immediate 200, reconcile 403 without header — Agent: qa-engineer | Model: sonnet
- [X] T022 [P] [US1] Service tests `backend/tests/services/test_strava_oauth.py` + `test_strava_ingest.py`: token exchange/refresh rotation (httpx mocked), idempotent double-delivery no-op, GPS stripping, delete→`removed_upstream`, deauth→`disconnected`, reconcile watermark + broken-token path — Agent: qa-engineer | Model: sonnet

### Frontend — connection + list

- [X] T023 [P] [US1] API module `frontend/src/api/stravaActivities.ts` (connection CRUD, activities list, typed per contracts §A/§C) — Agent: react-ui-engineer | Model: sonnet
- [X] T024 [US1] Hooks `frontend/src/hooks/activities/useStravaConnection.ts` + `useAthleteActivities.ts` (TanStack Query, existing `useAthlete` pattern, invalidation on connect/disconnect) — Agent: react-ui-engineer | Model: sonnet
- [X] T025 [US1] Component `frontend/src/components/activities/ConnectionStatusBadge.tsx` + connection card section in `frontend/src/routes/athletes/AthleteDetailPage.tsx` — states none/active/broken/disconnected + consent-missing disabled CTA, copy español neutro, 48 px targets, loading/empty/error states — Agent: react-ui-engineer | Model: sonnet
- [X] T026 [US1] Activities list section (`ActivityCard.tsx`) on `AthleteDetailPage.tsx`: date, duration, distance, FC media/máx, trainer flag, unlinked/linked badge; no map/location UI anywhere — Agent: react-ui-engineer | Model: sonnet
- [X] T027 [P] [US1] Frontend tests: `ConnectionStatusBadge.test.tsx`, `useStravaConnection.test.ts`, AthleteDetailPage connection-card states (MSW) + jest-axe on the card/dialog surfaces — Agent: qa-engineer | Model: sonnet

### Ops — delivery guarantee

- [X] T028 [P] [US1] GitHub Actions workflow `.github/workflows/strava-reconcile.yml` (daily cron 09:00 UTC + `workflow_dispatch`, curl with `--max-time 300 --retry 2`, secret `STRAVA_RECONCILE_TOKEN`) per contracts/api.md §E — Agent: devops-engineer | Model: haiku

**Checkpoint**: US1 fully functional — connect, sync, view unlinked activities. MVP deployable.

---

## Phase 4: User Story 2 — Coach links activity to training session (Priority: P2)

**Goal**: Coach review view + coach/admin-only link/re-link/unlink with same-day suggestions

**Independent Test**: quickstart.md Scenario 4 — coach links in ≤3 interactions; parent PATCH → 403; session detail shows linked activity

### Backend

- [X] T029 [US2] Extend `backend/app/routers/activities.py`: `GET /api/activities` (paginated review list, filters `linked/athlete_id/date range`, unlinked-first ordering, `selectinload` athlete+session), `GET /api/activities/{id}/session-suggestions` (±1 day, same club, same-day + attendance ranking), `PATCH /api/activities/{id}/link` (coach/admin only via `can_link_activity`, cross-club 422), `GET /api/training-sessions/{session_id}/activities` (reuses `can_view_session`) — per contracts §C — Agent: fastapi-architect | Model: sonnet
- [X] T030 [P] [US2] Router tests `backend/tests/routers/test_activities.py`: link/re-link/unlink happy paths, parent/athlete 403, cross-club session 422, suggestions ranking (same-day + attendance first), pagination, unlinked-first order, **query-count assertion** (no N+1, Constitution IV) — Agent: qa-engineer | Model: sonnet

### Frontend

- [X] T031 [US2] Lazy route `/activities` in `frontend/src/App.tsx` (`React.lazy` + Suspense, `ProtectedRoute` coach/admin) + page `frontend/src/routes/activities/ActivityReviewPage.tsx`: date-grouped list, unlinked amber / linked green / `removed_upstream` red "Eliminada en Strava" badges, filters — Agent: react-ui-engineer | Model: sonnet
- [X] T032 [US2] `frontend/src/components/activities/LinkSessionDialog.tsx` — suggestions radio list + calendar search fallback, confirm in 1 click (≤3 interactions total), focus trap + Escape, RHF+Zod — plus hooks `useActivityReview.ts`/`useLinkActivity.ts` (mutation invalidates review list, athlete activities, session activities) — Agent: react-ui-engineer | Model: sonnet
- [X] T033 [US2] Linked-activities section in `frontend/src/routes/training/SessionDetailPage.tsx` (per-athlete, empty state when none) — Agent: react-ui-engineer | Model: sonnet
- [X] T034 [P] [US2] Frontend tests: `ActivityReviewPage.test.tsx` (grouping, badges, filter, MSW), `LinkSessionDialog.test.tsx` (suggestion pick, unlink, error state), jest-axe zero violations on page + dialog — Agent: qa-engineer | Model: sonnet

**Checkpoint**: US1 + US2 independently functional

---

## Phase 5: User Story 3 — Parent visibility, own child only (Priority: P3)

**Goal**: Parents consult their children's activities read-only; privacy floor verified

**Independent Test**: quickstart.md Scenario 5 — parent sees own child only; other family 403; responses GPS-free

- [X] T035 [US3] Extend `GET /api/athletes/{athlete_id}/activities` to parent scope via `parent_athlete_ids` (read-only, link state visible, no link actions) + parent-scoped rows in `GET /api/training-sessions/{id}/activities` following `filter_media_for_parent` precedent — Agent: fastapi-architect | Model: sonnet
- [X] T036 [US3] Parent-facing activities section (reuse `ActivityCard`, no link controls) in the parent athlete view (`frontend/src/routes/parents/` per `ParentSessionDetailPage` convention) with copy español neutro — Agent: react-ui-engineer | Model: sonnet
- [X] T037 [P] [US3] RBAC tests in `backend/tests/routers/test_activities.py`: parent own-child 200, other-family 403, athlete-role behavior, link state read-only — Agent: qa-engineer | Model: sonnet
- [X] T038 [P] [US3] Privacy invariant suite `backend/tests/privacy/test_strava_privacy.py`: no `lat/lng/polyline/map/description` key in ANY endpoint response; model has no GPS attributes; log capture from ingest/reconcile contains no athlete names or activity titles (numeric IDs only) — Agent: data-privacy-guard | Model: sonnet
- [X] T039 [P] [US3] Frontend test: parent view scoping + jest-axe on parent activities section — Agent: qa-engineer | Model: sonnet

**Checkpoint**: All three stories functional

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T040 [P] Security audit of OAuth state signing, constant-time comparisons, Fernet key handling, webhook spoofing surface (unknown `owner_id`, replay), token-in-log absence — findings as actionable list — Agent: security-engineer | Model: sonnet
- [X] T041 [P] Full privacy audit (Ley 1581): consent gate honored end-to-end, data minimization confirmed in DB schema + API + logs + no third-party prompt exposure — Agent: data-privacy-guard | Model: sonnet
- [X] T042 Run full quickstart.md validation (Scenarios 1–5 + automated runs: `pytest` complete, `vitest` complete, `tsc --noEmit`, `ruff`) and fix regressions — Agent: qa-engineer | Model: sonnet
- [X] T043 [P] Documentation: `docs/15-strava-sync/` (family connection guide in Spanish incl. "mantén tus actividades privadas en Strava" recommendation, coach review-flow guide, ops runbook: webhook subscription creation, athlete-cap upgrade path, env vars) — Agent: technical-writer | Model: sonnet
- [X] T044 [P] Update `CLAUDE.md` implementation-status table (new 025 row) + `docs/implementation-status.md` — Agent: technical-writer | Model: haiku
- [X] T045 Pre-deploy checklist: Render env vars set, migration on Render, webhook subscription created against prod callback, GitHub secret `STRAVA_RECONCILE_TOKEN` configured, post-deploy smoke (`/health` + one authenticated endpoint + SC-001 pilot ride) — Agent: release-manager | Model: sonnet

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately; T002/T003/T004 parallel after T001 exists (T004 reads settings)
- **Foundational (Phase 2)**: needs Phase 1. T005/T006/T007 parallel → T008 (migration needs all models) → T011; T009/T010/T012 parallel with T008
- **US1 (Phase 3)**: needs Phase 2. Blocks nothing else structurally, but US2/US3 read `strava_activities` rows US1 creates
- **US2 (Phase 4)**: needs Phase 2 only (link column exists from T006) — can run parallel with US1 if staffed; demo requires US1 data
- **US3 (Phase 5)**: needs T020 (endpoint it extends) and T026 (component it reuses)
- **Polish (Phase 6)**: needs all desired stories; T040/T041/T043/T044 parallel; T042 then T045 last

### Within US1

T013/T014 parallel → T015 → T016; T017 needs T013; T018/T019 need T015/T016; T021/T022 after their targets; frontend T023 → T024 → T025/T026 → T027; T028 anytime after T019

### Parallel Opportunities

- Phase 2: T005 + T006 + T007 simultaneously (different files), then T009 + T010 + T012 alongside T008
- US1: backend chain (integration-engineer) ∥ frontend chain (react-ui-engineer) ∥ T028 (devops)
- US2 ∥ US1-frontend if two implementers available
- Phase 6: T040 + T041 + T043 + T044 simultaneously

### Agent/Model Summary

| Agent | Tasks | Model |
|---|---|---|
| fastapi-architect | T001, T009–T011, T017–T020, T029, T035 | sonnet |
| database-architect | T005–T008 | sonnet |
| integration-engineer | T013–T016 | sonnet |
| react-ui-engineer | T023–T026, T031–T033, T036 | sonnet |
| qa-engineer | T012, T021, T022, T027, T030, T034, T037, T039, T042 | sonnet |
| security-engineer | T004, T040 | sonnet |
| data-privacy-guard | T038, T041 | sonnet |
| devops-engineer | T002, T003, T028 | haiku (T028/T002/T003 mechanical) |
| technical-writer | T043 (sonnet), T044 (haiku) | mixed |
| release-manager | T045 | sonnet |

**Never `fable` on subagents** (user constraint). `haiku` only where the task is mechanical single-file work.

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 → Phase 2 → Phase 3 (US1)
2. **STOP & VALIDATE**: quickstart Scenarios 1–3 + pilot athlete real ride
3. Deployable increment: coach already sees real HR/duration data even without linking

### Incremental Delivery

1. Setup + Foundational → schema live (migration is additive, safe on prod)
2. US1 → validate → deploy (MVP)
3. US2 → validate → deploy (coach linking)
4. US3 → validate → deploy (families)
5. Polish → audits + docs + prod webhook subscription → SC-001/SC-002 monitoring via `ingest_source` split

### Notes

- Commit after each task or logical group (Conventional Commits, descripción en español)
- All Strava HTTP mocked in tests — no network in CI
- Any bug found during T042 lands with a regression test (Constitution II)
