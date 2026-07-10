# Research: Strava Activity Sync with Coach-Gated Session Linking

**Date**: 2026-07-10 | **Plan**: [plan.md](plan.md)

Sources: Strava official developer docs fetched 2026-07-10 (`developers.strava.com/docs/{webhooks,getting-started,rate-limits,changelog}`), Strava Community Hub reliability threads, prior deep-research pass (2026-07-10) over 20 sources, and codebase exploration of `backend/app` + `frontend/src`.

## 1. Integration hub: Strava only (no per-brand integrations)

- **Decision**: Integrate exclusively with the Strava API v3. Garmin, Magene, and iGPSport reach Strava through the athletes' existing device→Strava links.
- **Rationale**: Strava is the single common denominator already in use by every family. Garmin's Activity API requires a separate Garmin Connect Developer Program approval; Magene and iGPSport have no public multi-tenant APIs (iGPSport users typically bridge via Garmin Connect or manual export). One integration covers all three brands with zero athlete-side behavior change.
- **Alternatives considered**:
  - *Garmin Connect Activity API direct*: official push API, but only covers Garmin devices; separate OAuth approval process; still leaves Magene/iGPSport out. Rejected for v1.
  - *Manual FIT/GPX upload*: no external dependency, but breaks the "no manual step" core requirement. Deferred as a separate future feature (also the fallback if Strava API costs become prohibitive).
  - *Aggregators (Terra, Open Wearables, icusync-style)*: paid per-user pricing, overkill for ≈30 athletes, adds a data processor for minors' data (Ley 1581 concern). Rejected.

## 2. Inbound sync: webhook push + reconcile pull (never webhook-only)

- **Decision**: Subscribe to Strava Webhook Events API for near-real-time ingest, AND run a daily reconcile pull (`GET /athlete/activities` per connection, `after=` last-sync watermark) that guarantees eventual delivery.
- **Rationale**:
  - Webhook facts (official docs): POST `https://www.strava.com/api/v3/push_subscriptions` (client_id, client_secret, callback_url ≤255 chars, verify_token); validation GET must echo `{"hub.challenge": "..."}` with HTTP 200 **within 2 seconds**; event POST payload = `object_type` (activity|athlete), `aspect_type` (create|update|delete), `object_id`, `owner_id`, `subscription_id`, `event_time`, `updates` (changed fields; `authorized: false` on deauth); events must be ACKed 200 within 2 s, retried up to 3 total attempts; **one subscription per application**, receiving events for all authorized athletes.
  - Reliability: multiple Strava Community Hub threads document webhooks arriving minutes late, never firing for some athletes, and first-fetch payloads with null fields; Strava's own docs advise async processing and tolerate duplicate delivery. Spec SC-001 (95% ≤ 15 min) rides on webhooks; SC-002 (100% ≤ 24 h) requires the pull fallback.
  - Render free tier sleeps after ~15 min. A webhook POST that hits a cold instance may exceed Strava's 2 s window on attempt 1; Strava's 3 retries make delivery likely once warm, and the daily reconcile catches anything missed.
- **Alternatives considered**:
  - *Webhook-only*: fails SC-002 given documented gaps + Render cold starts. Rejected.
  - *Poll-only (no webhook)*: simple, but burns rate limit proportionally to polling frequency and can't meet SC-001's 15-minute freshness without aggressive polling. Rejected as primary; it IS the fallback.

## 3. Webhook event contract details that shape the design

- `aspect_type=create` → fetch full activity (`GET /activities/{id}`), upsert.
- `aspect_type=update` → `updates` hash carries `title`, `type`, `private` changes; re-fetch and update in place.
- `aspect_type=delete` → flag stored activity `removed_upstream=true` (never hard-delete; FR-013 preserves session links for coach review).
- `object_type=athlete` + `updates.authorized=false` → athlete deauthorized from Strava's side → mark connection `disconnected` (FR-014). Note: changelog (2026-06-01) added a dedicated deauthorization endpoint; the webhook remains the notification channel.
- Duplicate/out-of-order delivery is expected → ingest is idempotent by unique `strava_activity_id` (see data-model.md).

## 4. OAuth per athlete

- **Decision**: Standard authorization-code flow per athlete connection. Authorize URL `https://www.strava.com/oauth/authorize` (`client_id`, `response_type=code`, `redirect_uri`, `approval_prompt=auto`, `scope=activity:read_all`), token exchange at `https://www.strava.com/oauth/token`. Access tokens expire every 6 hours (`expires_in: 21600`); refresh via `grant_type=refresh_token` with rotation (store the newest refresh token returned).
- **Scope choice — `activity:read_all`**: minors' accounts should keep activities private/followers-only on Strava (we will recommend exactly that in the family guide); plain `activity:read` cannot read private activities, which would silently drop most rides. `read_all` is required for utility; privacy is enforced on OUR side by never persisting GPS/location fields (§7).
- **State parameter**: signed, short-lived state token (itsdangerous-style HMAC via existing `jwt_secret_key` or `secrets` + DB nonce) binding the callback to `{athlete_id, initiating_user_id}`; expired/invalid state → 400. Prevents CSRF and cross-athlete token binding.
- **Alternatives considered**: club-level single Strava account aggregating athletes — violates Strava ToS (accounts are personal), destroys per-athlete ownership. Rejected.

## 5. Strava app provisioning constraints (operational prerequisite)

- Facts (2026 docs/changelog): a Strava developer app starts in **single-player mode** (only the app owner's account can authorize). Since 2026-06-01 there is **self-service expanded access up to 10 athletes** in the API Settings Dashboard; beyond 10 athletes requires applying through the Developer Program form (demand justification, API Agreement, brand guidelines). App registration requires a Strava subscription on the owning account. Rate limits: default 200 req/15 min + 2 000/day overall; 100/1 000 non-upload; upgraded tier 400/4 000. Headers `X-RateLimit-*`/`X-ReadRateLimit-*`; 429 on breach; 15-min windows reset at :00/:15/:30/:45, daily at midnight UTC.
- **Current state (verified 2026-07-10, owner's dashboard)**: the club's Strava API app ALREADY EXISTS — client_id `22676`, "Nivel estándar", category Performance, linked to club "Club Deportivo Trocha y Ruta", owner account has an active Strava subscription. Current caps: **1 athlete allowed / 1 connected**; default rate limits (200/2 000 general, 100/1 000 read). The dashboard offers the self-service "Actualizar" upgrade to 10 athletes + upgraded limits (400/4 000 general, 200/2 000 read).
- **Decision**: Phase the rollout — trigger the self-service upgrade to 10 athletes (dashboard button, no application needed), pilot with ≤10 connected athletes, and apply through the Developer Program form for full-club capacity in parallel. Subscription cost already absorbed (owner is a subscriber).
- **Impact on design**: none structural — the athlete cap is a Strava-side quota, not a code change. Connection UI surfaces a friendly Spanish error when Strava rejects authorization due to the cap.
- **API base URL**: moves to `https://api-v3.strava.com` on 2027-01-04 → base URL is a setting (`STRAVA_API_BASE_URL`), never hardcoded. Club Activities endpoints (deprecated 2026-09-01) are not used.

## 6. Reconcile trigger without a scheduler

- **Context**: the backend has NO scheduler (no APScheduler/Celery/cron; only per-request `BackgroundTasks` via `TaskDispatcher`). Render free tier sleeps, so an in-process loop is unreliable.
- **Decision**: expose `POST /api/integrations/strava/reconcile` protected by a shared-secret header (`X-Reconcile-Token`, constant-time compare, new `STRAVA_RECONCILE_TOKEN` env var), triggered by a **GitHub Actions scheduled workflow** (daily, `curl` with generous timeout to absorb the ~50 s cold start). The endpoint iterates active connections, pulls `GET /athlete/activities?after=<watermark>&per_page=50`, upserts idempotently, advances the watermark, and refreshes tokens as needed.
- **Rationale**: zero new vendors (repo already on GitHub), free, wakes the sleeping service, observable in Actions history. Budget math: 30 connections × ~2 calls/day ≈ 60 calls/day ≪ 1 000 non-upload daily limit.
- **Alternatives considered**:
  - *Render Cron Job service*: clean but a paid add-on on this account setup. Rejected for cost.
  - *In-process APScheduler*: dies while the free-tier instance sleeps; silently skips runs. Rejected.
  - *cron-job.org / external pinger*: works but adds an unmanaged third party. GitHub Actions preferred (already trusted infra).

## 7. Privacy & minors (Ley 1581) — data minimization

- **Decision**: persist ONLY summary fields: external id, athlete FK, start datetime (UTC + local), sport type, elapsed/moving time, distance, average/max heart rate, total elevation gain, device/trainer flag, upstream state. **Never persist** `start_latlng`, `end_latlng`, `map.polyline`, segment efforts, photos, or activity description. Activity `name` (title) IS stored (coach context) but is excluded from logs and from any AI-provider prompt (none in scope).
- **Rationale**: GPS start/end points expose minors' home locations. Not storing them is stronger than not displaying them (FR-012) and removes an entire breach class. Logs use numeric IDs only (`strava_activity_id`, `athlete_id`) with correlation IDs — no titles, no names.
- **Consent gate**: new boolean `external_activity_sync` on `parental_consents` (same pattern as `psychological_assessment`, feature 017). The connect flow is blocked (HTTP 403 with Spanish guidance) until an active consent row for the athlete has the flag true.

## 8. Token storage: encryption at rest

- **Decision**: introduce Fernet (from `cryptography`, already a transitive dependency — promote to direct requirement) via a small `services/strava/token_store.py`. New env var `STRAVA_TOKEN_ENCRYPTION_KEY` (32-byte urlsafe base64; generated with `Fernet.generate_key()`); prod config validator requires it when `strava_enabled=true`. Access + refresh tokens stored encrypted; decrypted only in-process at call time.
- **Rationale**: codebase precedent (SHA-256 one-way hashing for reset tokens) doesn't apply — Strava tokens must be recoverable to be used. OAuth bearer credentials for minors' data warrant at-rest encryption per the constitution's security gate.
- **Alternatives considered**: plaintext columns (rejected — credential leak = full activity-history access for every minor); full KMS (overkill for this deployment; env-var key matches the platform's existing secret-management level).

## 9. Coach linking model

- **Decision**: link lives ON the activity (`training_session_id` nullable FK + `linked_by_user_id` + `linked_at`), one session per activity max, mutable only by coach/admin through `PATCH /api/activities/{id}/link`. The endpoint suggests candidate sessions (same club, `scheduled_date` within ±1 day of activity start, same-day first) but never auto-links — FR-008 and the explicit user requirement ("solo el entrenador").
- **Prior art**: intervals.icu/TrainingPeaks auto-pair planned↔actual by date+sport; deliberately NOT copied — auto-matching is the documented source of wrong-session pairings, and the coach wants manual control. Suggestion-only keeps the speed benefit (SC-005: ≤3 interactions) without the failure mode.

## 10. Frontend surfaces

- **Decision**: (a) coach review page `/activities` — lazy route, unlinked-first ordering, date grouping, link dialog with suggested sessions; (b) athlete profile — connection status card (conectado/desconectado/conexión rota + reconectar CTA) and activity list section; (c) session detail — linked-activities section per athlete; (d) parent views reuse the athlete-profile section scoped by existing `parent_athlete_ids` RBAC.
- **Rationale**: follows the established `api/ → hooks/<domain>/ → routes/<domain>/` + shadcn pattern; review page mirrors the existing "process a batch quickly" UX of the race-results review flows. All copy español neutro; connection card states cover the FR-014 broken-connection case (no silent failure, Principle III).

## All NEEDS CLARIFICATION resolved

Technical Context contains no NEEDS CLARIFICATION markers. Open operational (non-design) prerequisites carried into tasks: (1) ~~create the Strava API app~~ DONE — app exists (client_id `22676`, subscribed owner account); (2) click the self-service "Actualizar" upgrade (1 → 10 athletes) and later apply for Developer Program full capacity; (3) set the app's "Authorization Callback Domain" to the production domain; (4) generate and set `STRAVA_TOKEN_ENCRYPTION_KEY`, `STRAVA_RECONCILE_TOKEN`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_WEBHOOK_VERIFY_TOKEN` in Render env.
