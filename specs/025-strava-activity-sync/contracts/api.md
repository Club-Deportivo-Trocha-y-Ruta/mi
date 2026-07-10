# API Contract: Strava Activity Sync

**Date**: 2026-07-10 | **Plan**: [../plan.md](../plan.md) | **Data model**: [../data-model.md](../data-model.md)

All user-facing endpoints require Bearer JWT (existing auth). Machine-facing endpoints (webhook, OAuth callback, reconcile) are public-path but protected as noted. All error bodies follow the existing `{"detail": "..."}` FastAPI convention with Spanish user-facing messages.

## A. Connection management (router `strava_integration.py`)

### GET `/api/athletes/{athlete_id}/strava/connection`
Roles: admin, coach (athlete's club), parent (own child).
- `200`: `{ "status": "active"|"disconnected"|"broken"|"none", "connected_at": ..., "disconnected_at": ..., "authorized_by": "<display name>", "consent_ok": bool, "last_sync_at": ... }`
- `403` outside RBAC scope; `404` athlete not found.

### POST `/api/athletes/{athlete_id}/strava/connect`
Roles: admin, coach (athlete's club), parent (own child). Starts OAuth.
- Guard: active `parental_consents` row with `external_activity_sync=true` for the athlete → else `403 {"detail": "Falta el consentimiento del acudiente para sincronizar actividades externas."}`
- Guard: `strava_enabled=false` → `503`.
- `200`: `{ "authorize_url": "https://www.strava.com/oauth/authorize?client_id=...&redirect_uri=...&response_type=code&approval_prompt=auto&scope=activity:read_all&state=<signed>" }`
- `state` = signed short-lived token binding `{athlete_id, user_id, nonce}`; TTL 15 min.

### GET `/api/integrations/strava/callback?code=...&state=...&scope=...`
Public (Strava redirect target; the app's "Authorization Callback Domain" must equal the API host).
- Validates `state` (signature + TTL) → `400` on failure.
- Verifies granted `scope` contains `activity:read_all` → else redirect to frontend with `error=scope`.
- Exchanges `code` at `POST {strava_oauth_base_url}/token`; stores encrypted tokens; upserts connection (`status=active`); records `strava_athlete_id` from token response's `athlete.id`.
- Conflict — `strava_athlete_id` already bound to another athlete → redirect with `error=cuenta_en_uso`.
- Success → `302` to frontend `/athletes/{athlete_id}?strava=conectado`.

### DELETE `/api/athletes/{athlete_id}/strava/connection`
Roles: admin, coach (athlete's club), parent (own child). Family-initiated disconnect (FR-014).
- Sets `status=disconnected`, `disconnected_at=now`; calls Strava deauthorize endpoint (best-effort; failure logged, still disconnected locally). Activities remain.
- `204` on success; `404` no connection.

## B. Machine endpoints (router `strava_integration.py`)

### GET `/api/integrations/strava/webhook?hub.mode=subscribe&hub.challenge=...&hub.verify_token=...`
Public — Strava subscription validation.
- `hub.verify_token == settings.strava_webhook_verify_token` (constant-time) → `200 {"hub.challenge": "<echo>"}` (MUST respond < 2 s; no DB work).
- Mismatch → `403`.

### POST `/api/integrations/strava/webhook`
Public — Strava event delivery. **Returns `200 {}` immediately**; all processing deferred to BackgroundTasks (2 s ACK rule).
Payload (per Strava): `{ "object_type": "activity"|"athlete", "aspect_type": "create"|"update"|"delete", "object_id": long, "owner_id": long, "subscription_id": int, "event_time": long, "updates": {...} }`
Deferred processing:
- Unknown `owner_id` (no active connection) → ignore silently.
- `activity`/`create` or `update` → fetch `GET {api}/activities/{object_id}`, strip GPS/location/description fields, idempotent upsert by `strava_activity_id` (`ingest_source=webhook`).
- `activity`/`delete` → set `upstream_state=removed_upstream` (keep row + link).
- `athlete` with `updates.authorized == "false"` → connection `status=disconnected`.
- Duplicate deliveries: upsert is idempotent; replay of the same event is a no-op (test-covered).

### POST `/api/integrations/strava/reconcile`
Header `X-Reconcile-Token: <settings.strava_reconcile_token>` (constant-time compare) → else `403`. Triggered by GitHub Actions daily schedule (also manually invocable).
- For each `active` connection: refresh token if `token_expires_at` near; `GET {api}/athlete/activities?after=<last_sync_at - lookback>&per_page=50` (paginate); upsert each (`ingest_source=reconcile`); re-fetch activities flagged `summary_complete=false`; advance `last_sync_at`. Refresh failure → `status=broken`.
- `200`: `{ "connections_processed": n, "activities_upserted": n, "connections_broken": n }` (numeric only — no PII).

## C. Activities & linking (router `activities.py`)

### GET `/api/activities`
Roles: admin, coach. Coach review list (FR-010).
Query: `linked=true|false|all` (default `all`), `athlete_id?`, `date_from?`, `date_to?`, `page?`, `page_size?` (≤100).
- `200`: paginated `{ "items": [ActivityOut], "total": n, ... }`, ordered `start_date_utc DESC`, unlinked-first when `linked=all`.
- `ActivityOut`: `{ id, athlete_id, athlete_name, name, sport_type, start_date_local, elapsed_time_s, moving_time_s, distance_m, total_elevation_gain_m, average_heartrate, max_heartrate, is_trainer, upstream_state, summary_complete, link: { training_session_id, session_label, linked_by, linked_at } | null }`
- **NEVER present**: any coordinate, polyline, or location field (privacy test asserts).

### GET `/api/athletes/{athlete_id}/activities`
Roles: admin, coach (club), parent (own child — FR-011). Same `ActivityOut` shape, paginated, athlete-scoped.
- `403` for parent requesting another family's athlete.

### GET `/api/activities/{id}/session-suggestions`
Roles: admin, coach. Candidate sessions for linking (FR-008).
- `200`: `{ "suggestions": [ { training_session_id, scheduled_date, session_kind, location, technical_focus, same_day: bool, athlete_in_attendance: bool } ] }` — same club, `scheduled_date` within ±1 day of `start_date_local`, ordered: same-day + attendance first.

### PATCH `/api/activities/{id}/link`
Roles: admin, coach (athlete's club) ONLY (FR-007).
Body: `{ "training_session_id": int | null }` — int links/re-links, `null` unlinks.
- Guards: session exists + same club as athlete → else `422 {"detail": "La sesión no pertenece al club del atleta."}`; parent/athlete role → `403`.
- `200`: updated `ActivityOut`.

### GET `/api/training-sessions/{session_id}/activities`
Roles: per existing `can_view_session` RBAC (parents see only their children's rows — reuses `filter`-style scoping).
- `200`: `{ "items": [ActivityOut] }` for activities linked to the session (FR-009).

## D. Frontend contracts (view-model expectations)

- Connection card states: `none` → CTA "Conectar con Strava"; `active` → "Conectado" + last_sync; `broken` → warning + "Reconectar"; `disconnected` → neutral + "Reconectar". Consent missing → CTA disabled with helper text linking to consent wizard.
- Review page: groups by `start_date_local` date; unlinked badge amber, linked badge green, `removed_upstream` badge red "Eliminada en Strava" (constitution III color semantics).
- Link dialog: suggestion list (radio) + full calendar search fallback; confirm = 1 click → total ≤3 interactions from review row (SC-005).

## E. GitHub Actions workflow contract

`.github/workflows/strava-reconcile.yml`: `schedule: cron "0 9 * * *"` (04:00 Colombia) + `workflow_dispatch`; single step `curl -X POST -H "X-Reconcile-Token: ${{ secrets.STRAVA_RECONCILE_TOKEN }}" --max-time 300 --retry 2 https://mi-2yzi.onrender.com/api/integrations/strava/reconcile` — generous timeout absorbs Render cold start (~50 s).
