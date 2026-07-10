# Implementation Plan: Strava Activity Sync with Coach-Gated Session Linking

**Branch**: `main` (feature developed on current branch per user request) | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/025-strava-activity-sync/spec.md`

## Summary

Athletes' cycling computers (Garmin, Magene, iGPSport) already sync to Strava. This feature connects each athlete's Strava account to the platform once (OAuth, guardian-consent-gated), ingests every new activity automatically (webhook push + reconcile pull fallback), stores a privacy-minimized summary (no GPS/route data ever persisted), and gives the coach a review view where only coach/admin can link an activity to a specific training session. Parents see their own children's activities read-only.

Technical approach (from research.md): Strava is the single integration hub — one Strava API app, one webhook subscription, per-athlete OAuth tokens (encrypted at rest with Fernet), webhook endpoint ACKs in <2 s and defers processing to the existing `TaskDispatcher`/`BackgroundTasks` pattern, and a secret-protected reconcile endpoint triggered by a GitHub Actions schedule covers the documented webhook-reliability gaps (SC-002: 100% within 24 h).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, httpx (Strava REST calls), `cryptography` (Fernet token encryption — already a transitive dependency, promoted to direct); frontend: Vite, shadcn/ui + Tailwind, TanStack Query, Zustand, RHF + Zod

**Storage**: MySQL 8.4 (Hostinger prod). Two new tables (`strava_connections`, `strava_activities`) + one new boolean consent column on `parental_consents`. New Alembic migration on head `d3e4f5a6b7c8`

**Testing**: Backend pytest + httpx.AsyncClient + aiosqlite (existing conftest pattern, `respx`/manual httpx mocking for Strava API); frontend Vitest + Testing Library + MSW + jest-axe

**Target Platform**: Render free tier (Docker, Oregon) — sleeps after ~15 min; webhook/cron calls incur ~50 s cold start (see Constraints)

**Project Type**: Web application (existing FastAPI monolith + React SPA)

**Performance Goals**: Webhook ACK < 2 s (Strava hard requirement, including cold-start mitigation via immediate-200 design); coach review list p95 ≤ 500 ms; ingest of one activity ≤ 2 Strava API calls

**Constraints**: Strava rate limits 200 req/15 min, 2 000/day (100/1 000 non-upload read); access tokens expire every 6 h (refresh-token rotation); ONE webhook subscription per app; Strava app athlete cap (single-player by default → self-service expansion to 10 athletes → Developer Program form beyond 10); API base URL moves to `https://api-v3.strava.com` on 2027-01-04 (configurable setting from day one); minors privacy — no GPS/route/location data persisted or displayed, no PII in logs

**Scale/Scope**: ≈10–30 connected athletes, ≤10 activities/athlete/week → ≈300–1 200 ingest API calls/month, far under rate limits. Backend: 2 models, 1 service package, 2 routers (~10 endpoints). Frontend: 1 review page, athlete-profile section, session-detail section, connection wizard

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | How this plan satisfies it |
|---|---|---|
| I | Code Quality & Maintainability | New `backend/app/services/strava/` package with module docstrings (inputs/outputs/side effects); passes `ruff` + `mypy`, frontend `eslint` + `tsc --noEmit`. No duplication: reuses `TaskDispatcher`, `permissions.py` helpers, existing consent model, existing hook/API-module frontend pattern |
| II | Testing (NON-NEGOTIABLE) | Router + service tests with happy path AND negative paths (403 parent link attempt, invalid webhook verify_token, replayed webhook event → idempotent, expired state token, revoked connection). Privacy invariant tests: no athlete name/PII in log output, no GPS fields in any API response. Frontend: vitest for review page/link dialog/hooks, jest-axe on page + dialog. Bug-fix regression rule acknowledged |
| III | UX Consistency | All end-user copy in español neutro (Colombia). shadcn/ui components only; RHF + Zod for the connect wizard; loading/empty/error states for every async surface (incl. "conexión rota — reconectar" state); 48 px touch targets; WCAG 2.1 AA + axe gate |
| IV | Performance | Webhook handler returns 200 immediately, processing deferred (BackgroundTasks) — satisfies Strava 2 s rule and keeps p95 low. List endpoints eager-load athlete + session relations (`selectinload`) with a query-count test. Frontend: review page lazy-loaded route (`React.lazy`), bundle budget respected. Render cold start documented: webhook retries (3×) + daily reconcile guarantee delivery despite sleep |
| V | Youth Psychological Assessment Safeguards | Not applicable (no psychological instrument). Related quality gates still enforced: guardian consent gate (new `external_activity_sync` boolean on `parental_consents`, same pattern as `psychological_assessment`), Ley 1581 minors privacy (no GPS stored/displayed, no PII in logs/third-party prompts), RBAC in `permissions.py` exercised by tests |

**Quality Gates & Compliance**: Strava tokens are third-party credentials → encrypted at rest (Fernet, new `STRAVA_TOKEN_ENCRYPTION_KEY` env var, prod validator requires it when `strava_enabled=true`). Webhook + callback endpoints are unauthenticated by nature → protected by `verify_token` / signed `state` / constant-time secret comparison respectively. No new AI surface. Structured logs with correlation IDs for ingest job, never logging activity titles (may contain names) — log only numeric IDs.

**Gate result (pre-Phase 0)**: PASS — no violations, Complexity Tracking empty.

**Gate result (post-Phase 1 re-check)**: PASS — design artifacts introduce no new dependencies beyond `cryptography` (promoted transitive) and no architecture deviations. GitHub Actions schedule is CI-infra, not a runtime dependency; simpler alternatives documented in research.md §6.

## Project Structure

### Documentation (this feature)

```text
specs/025-strava-activity-sync/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md           # Phase 1 output — REST contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py                          # + strava_* settings block
│   ├── models/
│   │   ├── strava_connection.py           # NEW — StravaConnection
│   │   ├── strava_activity.py             # NEW — StravaActivity
│   │   └── parental_consent.py            # + external_activity_sync: Mapped[bool]
│   ├── schemas/
│   │   └── strava.py                      # NEW — Pydantic schemas (connection, activity, link)
│   ├── routers/
│   │   ├── strava_integration.py          # NEW — OAuth connect/callback, webhook, reconcile
│   │   └── activities.py                  # NEW — review list, athlete list, link/unlink
│   ├── services/
│   │   ├── permissions.py                 # + can_view_activity / can_link_activity helpers
│   │   └── strava/                        # NEW package
│   │       ├── __init__.py
│   │       ├── client.py                  # httpx Strava API client (token refresh, rate-limit aware)
│   │       ├── oauth.py                   # authorize URL, state signing, token exchange
│   │       ├── token_store.py             # Fernet encrypt/decrypt of stored tokens
│   │       ├── ingest.py                  # idempotent upsert, webhook event processing
│   │       └── reconcile.py               # pull-based catch-up (per-connection listing)
│   └── dependencies.py                    # + get_strava_client factory
├── alembic/versions/
│   └── xxxx_add_strava_sync_tables.py     # NEW — head after d3e4f5a6b7c8
└── tests/
    ├── routers/test_strava_integration.py # NEW
    ├── routers/test_activities.py         # NEW
    ├── services/test_strava_ingest.py     # NEW
    ├── services/test_strava_oauth.py      # NEW
    └── privacy/test_strava_privacy.py     # NEW — no-GPS / no-PII invariants

frontend/
├── src/
│   ├── api/
│   │   └── stravaActivities.ts            # NEW — API module
│   ├── hooks/activities/                  # NEW — useAthleteActivities, useActivityReview,
│   │                                      #        useLinkActivity, useStravaConnection
│   ├── components/activities/             # NEW — ActivityCard, LinkSessionDialog,
│   │                                      #        ConnectionStatusBadge
│   ├── routes/
│   │   ├── activities/ActivityReviewPage.tsx   # NEW — coach review view (lazy route)
│   │   ├── athletes/AthleteDetailPage.tsx      # + activities section + connection card
│   │   └── training/SessionDetailPage.tsx      # + linked-activities section
│   └── App.tsx                            # + lazy route /activities (coach/admin)
└── .github/workflows/
    └── strava-reconcile.yml               # NEW — daily schedule → POST /reconcile
```

**Structure Decision**: Extends the existing FastAPI modular-monolith + React SPA layout. Backend integration logic isolated in `services/strava/` (mirrors `services/notification/` and `services/ai/` precedents); public HTTP surface split between `strava_integration.py` (machine-facing: OAuth callback, webhook, reconcile) and `activities.py` (user-facing: lists + linking). Frontend follows the established `api/ → hooks/<domain>/ → routes/<domain>/` convention.

## Complexity Tracking

> No constitution violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
