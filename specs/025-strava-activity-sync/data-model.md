# Data Model: Strava Activity Sync

**Date**: 2026-07-10 | **Plan**: [plan.md](plan.md) | **Migration**: new revision on head `d3e4f5a6b7c8`

## Entity overview

```text
parental_consents ──(gates)──► strava_connections ──1:N──► strava_activities ──N:0..1──► training_sessions
      ▲                              │ 1:1                        │ N:1
      └── athletes ◄─────────────────┴────────────────────────────┘
```

## 1. `strava_connections` (NEW)

One row per athlete↔Strava-account authorization. At most one ACTIVE connection per athlete.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INT PK autoincrement | | |
| `athlete_id` | INT FK → `athletes.id` | NOT NULL, UNIQUE | 1:1 with athlete (re-connect updates row) |
| `strava_athlete_id` | BIGINT | NOT NULL, UNIQUE | Strava's `owner_id`; webhook routing key |
| `status` | ENUM (`values_callable`) | NOT NULL, default `active` | `active` / `disconnected` / `broken` |
| `access_token_enc` | VARBINARY(512) | NOT NULL | Fernet-encrypted |
| `refresh_token_enc` | VARBINARY(512) | NOT NULL | Fernet-encrypted; rotated on refresh |
| `token_expires_at` | DATETIME (UTC) | NOT NULL | from `expires_at` epoch in token response |
| `scope_granted` | VARCHAR(100) | NOT NULL | e.g. `activity:read_all`; detect scope downgrades |
| `authorized_by_user_id` | INT FK → `users.id` | NOT NULL | who ran the connect flow (FR-001) |
| `consent_id` | INT FK → `parental_consents.id` | NOT NULL | consent row that gated the connection (FR-002) |
| `connected_at` | DATETIME | NOT NULL | |
| `disconnected_at` | DATETIME | NULL | set on family disconnect or upstream deauth |
| `last_sync_at` | DATETIME | NULL | reconcile watermark (`after=` param, minus safety margin) |
| `last_error` | VARCHAR(255) | NULL | machine-readable last failure (no PII) |
| `created_at` / `updated_at` | DATETIME | NOT NULL | repo convention |

**State transitions** (`status`):
- `active → disconnected`: family disconnect (platform) or webhook `updates.authorized=false` (Strava side). Sets `disconnected_at`; ingestion stops; activities remain.
- `active → broken`: refresh-token failure (401 on refresh) or scope downgrade detected. Profile shows "conexión rota — reconectar".
- `disconnected|broken → active`: re-run of the connect flow (same row updated, new tokens, `disconnected_at` cleared).

**Validation rules**:
- Connect flow REQUIRES an active (non-withdrawn) `parental_consents` row for the athlete with `external_activity_sync = true` → else 403.
- `strava_athlete_id` uniqueness rejects binding one Strava account to two athletes (shared-account edge case: first bind wins, second gets a Spanish-language error).

## 2. `strava_activities` (NEW)

One row per Strava activity of a connected athlete. Idempotency anchor: `UNIQUE(strava_activity_id)`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INT PK autoincrement | | |
| `strava_activity_id` | BIGINT | NOT NULL, UNIQUE | webhook `object_id`; upsert key (FR-005) |
| `athlete_id` | INT FK → `athletes.id` | NOT NULL, INDEX | denormalized from connection at ingest |
| `connection_id` | INT FK → `strava_connections.id` | NOT NULL | provenance |
| `name` | VARCHAR(255) | NOT NULL, default `''` | title; NEVER logged, NEVER sent to AI |
| `sport_type` | VARCHAR(50) | NOT NULL | Strava `sport_type` string (open set — no enum) |
| `start_date_utc` | DATETIME | NOT NULL, INDEX | |
| `start_date_local` | DATETIME | NOT NULL | session-suggestion matching uses local date |
| `elapsed_time_s` | INT | NOT NULL | |
| `moving_time_s` | INT | NULL | |
| `distance_m` | FLOAT | NULL | |
| `total_elevation_gain_m` | FLOAT | NULL | |
| `average_heartrate` | FLOAT | NULL | null when no HR sensor data |
| `max_heartrate` | FLOAT | NULL | |
| `is_trainer` | BOOLEAN | NOT NULL default false | indoor/trainer flag |
| `upstream_state` | ENUM (`values_callable`) | NOT NULL default `present` | `present` / `removed_upstream` (FR-013) |
| `ingest_source` | ENUM (`values_callable`) | NOT NULL | `webhook` / `reconcile` (observability, SC-001/SC-002) |
| `summary_complete` | BOOLEAN | NOT NULL default true | false when first delivery had null fields (FR-015); reconcile re-fetches |
| `training_session_id` | INT FK → `training_sessions.id` | NULL, INDEX | the coach link; NULL = unlinked (valid permanent state) |
| `linked_by_user_id` | INT FK → `users.id` | NULL | set with link (FR-007) |
| `linked_at` | DATETIME | NULL | |
| `first_seen_at` / `updated_at` | DATETIME | NOT NULL | `first_seen_at` vs `start_date_utc` measures sync latency (SC-001) |

**Explicitly ABSENT columns** (privacy by schema — research §7): `start_latlng`, `end_latlng`, `map_polyline`, `description`, photos, segment data. Ingest strips them before persistence; a privacy test asserts the model has no such attributes and no API response contains them.

**Link invariants** (FR-007, FR-009):
- At most one `training_session_id` per activity; re-link overwrites, unlink sets NULL (+ clears `linked_by_user_id`/`linked_at`).
- Link mutation restricted to coach (same club as athlete) / admin — enforced in `services/permissions.py` (`can_link_activity`), covered by 403 tests for parent/athlete roles.
- Linked session must belong to the athlete's club; activity athlete need not be on the session attendance list (coach may link anyway — their call), but the suggestion ranking prefers sessions where the athlete has attendance.
- `upstream_state=removed_upstream` keeps the link; review view badges it "eliminada en Strava" for coach decision (FR-013).

## 3. `parental_consents` (MODIFIED)

| Change | Detail |
|---|---|
| ADD COLUMN | `external_activity_sync` BOOLEAN NOT NULL DEFAULT FALSE — same pattern as `psychological_assessment` (feature 017). Existing rows default false: every family must opt in explicitly before connecting. |

## 4. Settings (config.py additions)

| Setting (env var) | Default | Notes |
|---|---|---|
| `strava_enabled` (`STRAVA_ENABLED`) | `false` | master switch; routers return 404-style disabled response when off |
| `strava_client_id` / `strava_client_secret` | — | app credentials; prod validator requires when enabled |
| `strava_api_base_url` | `https://www.strava.com/api/v3` | switch to `https://api-v3.strava.com` before 2027-01-04 |
| `strava_oauth_base_url` | `https://www.strava.com/oauth` | |
| `strava_webhook_verify_token` (`STRAVA_WEBHOOK_VERIFY_TOKEN`) | — | echoed check on subscription validation GET |
| `strava_token_encryption_key` (`STRAVA_TOKEN_ENCRYPTION_KEY`) | — | Fernet key; prod validator requires when enabled |
| `strava_reconcile_token` (`STRAVA_RECONCILE_TOKEN`) | — | shared secret for `POST /reconcile` (constant-time compare) |
| `strava_reconcile_lookback_hours` | `48` | watermark safety margin |

## 5. Indexes & query notes

- Coach review list: `WHERE athlete_id IN (club athletes) AND training_session_id IS NULL ORDER BY start_date_utc DESC` → composite index `(training_session_id, start_date_utc)` + existing `athlete_id` index; relations eager-loaded via `selectinload` (constitution IV, query-count test required).
- Session detail: index on `training_session_id` serves `GET /training-sessions/{id}/activities`.
- Webhook routing: `strava_athlete_id` UNIQUE index on connections resolves `owner_id → athlete` in O(1).
