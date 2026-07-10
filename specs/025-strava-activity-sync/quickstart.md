# Quickstart Validation: Strava Activity Sync

**Plan**: [plan.md](plan.md) | **Contract**: [contracts/api.md](contracts/api.md) | **Data model**: [data-model.md](data-model.md)

Validation guide — proves the feature end-to-end. Implementation details live in `tasks.md`.

## Prerequisites

- Strava API app (exists — client_id `22676`): "Authorization Callback Domain" set to the API host (`localhost` for dev); self-service upgrade to 10 athletes clicked for pilot.
- Env vars set (see data-model.md §4): `STRAVA_ENABLED=true`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_WEBHOOK_VERIFY_TOKEN`, `STRAVA_TOKEN_ENCRYPTION_KEY` (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`), `STRAVA_RECONCILE_TOKEN` (`openssl rand -hex 32`).
- Local stack: `docker compose up` (runs migrations + seed) or `cd backend && alembic upgrade head && uvicorn app.main:app --reload`.
- For real-webhook testing locally: an HTTPS tunnel (e.g. `ngrok http 8000`) as `callback_url`. All automated tests mock Strava — no tunnel needed for CI.

## Scenario 1 — Consent gate + OAuth connect (US1 / FR-001, FR-002)

1. Login as parent (`padre@trochayruta.com`), open athlete profile → Strava card shows "Conectar" **disabled** with consent helper (no consent yet).
2. Grant `external_activity_sync` consent via consent wizard.
3. `POST /api/athletes/{id}/strava/connect` → `200` with `authorize_url`; open it, authorize on Strava → redirected back → connection card shows **Conectado**.
4. Negative: repeat step 3 for an athlete WITHOUT consent → `403` Spanish message. Parent of another family → `403`.

Expected DB: one `strava_connections` row, `status=active`, tokens NOT readable (encrypted bytes), `consent_id` set.

## Scenario 2 — Webhook ingest (US1 / FR-003, FR-005, SC-001)

1. Simulate subscription validation: `GET /api/integrations/strava/webhook?hub.mode=subscribe&hub.challenge=abc&hub.verify_token=<token>` → `200 {"hub.challenge":"abc"}`. Wrong token → `403`.
2. Simulate event: `POST /api/integrations/strava/webhook` with `{"object_type":"activity","aspect_type":"create","object_id":123,"owner_id":<strava_athlete_id>,...}` (Strava API mocked to return an activity fixture WITH `start_latlng`/`map` fields) → immediate `200`.
3. Verify: `strava_activities` row exists; GPS fields absent from DB and from `GET /api/activities` response; `training_session_id` NULL (unlinked default).
4. Replay the same event → still exactly one row (idempotency, SC-003).
5. `aspect_type=delete` event → row flagged `removed_upstream`, not deleted.
6. Deauth event (`object_type=athlete`, `updates.authorized:"false"`) → connection `disconnected`, profile card reflects it.

## Scenario 3 — Reconcile fallback (FR-004, SC-002)

1. Create a connection; do NOT send any webhook. Mock `GET /athlete/activities` returning 2 activities.
2. `POST /api/integrations/strava/reconcile` with header `X-Reconcile-Token` → `200 {"connections_processed":1,"activities_upserted":2,...}`.
3. Missing/wrong header → `403`.
4. Mock refresh-token 401 → connection `status=broken`; profile shows "Reconectar".
5. Run reconcile twice → no duplicates.

## Scenario 4 — Coach linking (US2 / FR-007, FR-008, SC-005)

1. Login as coach (`entrenador@trochyruta.com`) → `/activities` review page lists unlinked activities grouped by date, unlinked first.
2. Open link dialog on an activity → suggestions show same-day club sessions first (`GET .../session-suggestions`).
3. Pick a session → `PATCH /api/activities/{id}/link {"training_session_id": N}` → badge turns green; count interactions ≤3.
4. Session detail page shows the linked activity (FR-009). Re-link to another session → previous association gone. Unlink (`null`) → back to unlinked.
5. Negative: same PATCH as parent → `403`; session from another club → `422`.

## Scenario 5 — Parent visibility & privacy (US3 / FR-011, FR-012, SC-006)

1. Login as parent → athlete profile shows child's activities (date, duration, distance, FC media/máx in Spanish).
2. `GET /api/athletes/{other_family_athlete}/activities` → `403`.
3. Assert NO response from any endpoint contains `lat`, `lng`, `polyline`, `map`, `description` keys (automated privacy test `tests/privacy/test_strava_privacy.py`).
4. Grep captured logs from Scenarios 1–4: no athlete names, no activity titles — numeric IDs only.

## Automated runs

```bash
# Backend — all new suites + regressions
cd backend && pytest tests/routers/test_strava_integration.py tests/routers/test_activities.py \
  tests/services/test_strava_ingest.py tests/services/test_strava_oauth.py \
  tests/privacy/test_strava_privacy.py && pytest

# Frontend — review page, dialog, hooks, connection card + axe
cd frontend && npx vitest run src/routes/activities src/hooks/activities src/components/activities && npx tsc --noEmit
```

Expected: all green; jest-axe zero violations on `ActivityReviewPage` and `LinkSessionDialog`; query-count test on review list passes (no N+1).

## Production smoke (post-deploy)

1. Render env vars set; migration applied (`alembic upgrade head` via entrypoint).
2. Create the real webhook subscription (one-time): `POST https://www.strava.com/api/v3/push_subscriptions` with prod callback → verify Strava's validation GET succeeded (logs) and subscription id stored/noted.
3. Connect ONE real pilot athlete; record a short ride; confirm it appears ≤15 min (SC-001); confirm GitHub Actions reconcile run is green next morning (SC-002 path).
