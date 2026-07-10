# Operational Runbook — Strava Activity Sync (specs/025)

> **Audience**: coach, admin, on-call.
> **Scope**: OAuth connection, webhook ingest, reconcile fallback, and coach-gated
> session linking (`backend/app/services/strava/`, routers `strava_integration.py`
> + `activities.py`).
> Related docs: [`guia-familias.md`](guia-familias.md) (family-facing),
> [`guia-entrenador.md`](guia-entrenador.md) (coach review flow),
> [`../../specs/025-strava-activity-sync/`](../../specs/025-strava-activity-sync/) (design artifacts).

---

## 1. Environment variables

Set in Render → service `mi-2yzi` → **Environment**. Full comments/generation
commands in `.env.example` §"Strava Activity Sync".

| Variable | Required when `STRAVA_ENABLED=true` | Notes |
|---|---|---|
| `STRAVA_ENABLED` | — | Master switch. `false` (default) makes Strava routers respond as disabled — no code path touches Strava. |
| `STRAVA_CLIENT_ID` | Yes | From the app dashboard (`https://www.strava.com/settings/api`). Club app: client_id `22676`. |
| `STRAVA_CLIENT_SECRET` | Yes | Same dashboard. Treat as a credential — never in docs, logs, or commits. |
| `STRAVA_WEBHOOK_VERIFY_TOKEN` | Yes | Any random string chosen by us; echoed back on the subscription handshake (§2). |
| `STRAVA_TOKEN_ENCRYPTION_KEY` | Yes | Fernet key encrypting stored access/refresh tokens. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Losing this key makes every stored token unrecoverable** — back it up alongside other secrets, not just in Render. |
| `STRAVA_RECONCILE_TOKEN` | Yes | Shared secret for `POST /api/integrations/strava/reconcile`, constant-time compared. Generate: `openssl rand -hex 32`. Also set as the GitHub Actions repo secret `STRAVA_RECONCILE_TOKEN` (§3). |
| `STRAVA_API_BASE_URL` | No (has default) | `https://www.strava.com/api/v3`. **Must move to `https://api-v3.strava.com` before 2027-01-04** (Strava-announced deprecation) — update this var, no code change needed. |
| `STRAVA_OAUTH_BASE_URL` | No (has default) | `https://www.strava.com/oauth`. |
| `STRAVA_REDIRECT_URI` | Yes in prod | Must equal `<backend-host>/api/integrations/strava/callback` — the API host, never the frontend. The dev default (`localhost`) fails a production validator check if left unchanged. Must also match the "Authorization Callback Domain" configured in the Strava app dashboard exactly (domain only, no path, no scheme). |
| `STRAVA_RECONCILE_LOOKBACK_HOURS` | No (default `48`) | Safety margin subtracted from the `last_sync_at` watermark on each reconcile pass — absorbs clock drift and short outages without re-scanning the athlete's whole history. |

Prod config validator (`backend/app/config.py`) raises at startup if any of the
required-when-enabled vars above are empty and `STRAVA_ENABLED=true` — a
misconfigured deploy fails fast instead of silently no-op-ing.

## 2. One-time setup: webhook subscription

Strava allows **one webhook subscription per application** — not per environment,
not per athlete. Create it once for production; local/dev testing mocks Strava
and does not need a live subscription (see quickstart.md).

```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=<STRAVA_CLIENT_ID> \
  -F client_secret=<STRAVA_CLIENT_SECRET> \
  -F callback_url=https://mi-2yzi.onrender.com/api/integrations/strava/webhook \
  -F verify_token=<STRAVA_WEBHOOK_VERIFY_TOKEN>
```

Strava immediately issues a `GET` to `callback_url` with `hub.mode`,
`hub.challenge`, `hub.verify_token` — the app's public handler
(`GET /api/integrations/strava/webhook`) must echo `{"hub.challenge": "<value>"}`
with HTTP 200 **within 2 seconds** and no DB work, or the subscription creation
fails. Confirm success in the `curl` response — Strava returns the created
subscription `id`; note it (no local record of the id is kept — Strava is the
source of truth).

**Verify an existing subscription**:

```bash
curl -G https://www.strava.com/api/v3/push_subscriptions \
  -d client_id=<STRAVA_CLIENT_ID> \
  -d client_secret=<STRAVA_CLIENT_SECRET>
```

**Delete/recreate** (needed if `callback_url` or `verify_token` change, e.g.
Render service renamed):

```bash
curl -X DELETE https://www.strava.com/api/v3/push_subscriptions/<subscription_id> \
  -F client_id=<STRAVA_CLIENT_ID> \
  -F client_secret=<STRAVA_CLIENT_SECRET>
```

Then repeat the creation call with the new values.

## 3. GitHub Actions reconcile schedule

Webhooks are the fast path (SC-001: 95% of activities visible ≤15 min); the
daily reconcile pull is the reliability guarantee (SC-002: 100% ≤24 h) that
covers Strava's documented webhook gaps and Render free-tier cold starts.

Workflow: `.github/workflows/strava-reconcile.yml` — `cron: "0 9 * * *"`
(04:00 Colombia) + `workflow_dispatch` for manual runs. Single step:

```bash
curl -X POST -H "X-Reconcile-Token: ${{ secrets.STRAVA_RECONCILE_TOKEN }}" \
  --max-time 300 --retry 2 \
  https://mi-2yzi.onrender.com/api/integrations/strava/reconcile
```

**Required GitHub repo secret**: `STRAVA_RECONCILE_TOKEN` (Settings → Secrets
and variables → Actions) — must equal the Render env var of the same name.

**Manually trigger**: GitHub → Actions tab → "Strava Reconcile" workflow →
"Run workflow". Useful after a suspected missed webhook batch or when
validating a fresh deploy.

**Check a run**: Actions tab → "Strava Reconcile" → latest run → step log
shows the endpoint's JSON response:

```json
{"connections_processed": 4, "activities_upserted": 6, "connections_broken": 0}
```

`connections_broken > 0` means at least one athlete's refresh token failed —
see §5.2.

## 4. Registering guardian consent (until self-service exists)

The connect flow is gated on an active `parental_consents` row with
`external_activity_sync = true` for the athlete (FR-002). **There is currently
no parent-facing UI checkbox for this specific consent** — it must be
registered directly against the database after the family authorizes
(verbally or in writing), the same interim pattern used for
`psychological_assessment` (feature 017). This is an acknowledged product gap,
not a documentation omission — track it before treating this as final.

```sql
-- Find the athlete's current (non-withdrawn) consent row.
SELECT id, athlete_id, external_activity_sync, withdrawn_at
FROM parental_consents
WHERE athlete_id = <ATHLETE_ID> AND withdrawn_at IS NULL
ORDER BY consented_at DESC
LIMIT 1;

-- Grant the flag on that row.
UPDATE parental_consents
SET external_activity_sync = TRUE
WHERE id = <CONSENT_ROW_ID>;
```

If the athlete has no active consent row at all, do not fabricate one here —
the family must complete the club's regular consent flow first (onboarding or
renewal), then apply the `UPDATE` above.

After this, the athlete's profile "Conectar con Strava" button becomes
enabled (`consent_ok: true` from `GET /api/athletes/{id}/strava/connection`).

## 5. Common alerts

### 5.1 Athlete cap reached — Strava rejects a new authorization

**Symptom**: family completes the Strava-side authorization screen but the
redirect back shows an error, or Strava's authorize page itself refuses the
athlete before showing the consent screen.

**Cause**: the club's Strava app starts in single-player mode and currently
allows a limited number of distinct authorized athletes.

**Current state (as of pilot)**: app client_id `22676` — self-service upgrade
from 1 → 10 athletes is available with no application (dashboard button).
Beyond 10 athletes requires the Strava **Developer Program** application
(demand justification, API Agreement, brand guidelines review — not
instantaneous).

**Fix, in order**:
1. Confirm current cap: `https://www.strava.com/settings/api` → API Settings
   Dashboard, on the club's owning account.
2. If still under 10: click the self-service **"Actualizar"** button — takes
   effect immediately, no review.
3. If already at 10 and the club is scaling past pilot size: submit the
   Developer Program form from the same dashboard. This has an external
   review timeline — plan connections for new athletes around it, don't block
   on same-day approval.
4. Upgrading the athlete cap also raises rate limits (default 200 req/15 min
   + 2 000/day → 400/15 min + 4 000/day) — no action needed on our side, the
   client already reads `X-RateLimit-*` headers defensively.

### 5.2 Connection `broken` — refresh token failure

**Symptom**: `strava_connections.status = 'broken'` for one or more athletes;
profile card shows "Conexión rota — reconectar"; reconcile response shows
`connections_broken > 0`.

**Diagnosis**:

```sql
SELECT athlete_id, status, last_error, updated_at
FROM strava_connections
WHERE status = 'broken'
ORDER BY updated_at DESC;
```

`last_error` is machine-readable and PII-free (numeric/status-code level, no
tokens, no names).

**Common causes**: the family revoked club access from Strava's side
(`Settings → My Apps`), the athlete deactivated their Strava account, or the
refresh token was rotated out-of-band.

**Fix**: no server-side recovery — the family/coach must run the connect flow
again from the athlete's profile (same steps as first connection, guía
familias §3). There is nothing to "retry" from the backend; a broken
connection needs a fresh authorization.

### 5.3 Webhook not arriving (relying only on reconcile)

**Symptom**: activities only show up once a day (after the reconcile
schedule), never within minutes.

**Diagnosis**:
1. Confirm the subscription exists and points at the right URL (§2 verify
   call).
2. Check Render logs for `POST /api/integrations/strava/webhook` hits — if
   there are none at all, the subscription itself is the problem (recreate,
   §2). If there are hits but no resulting `strava_activities` rows, the
   `owner_id` in the payload doesn't match any `strava_athlete_id` — likely a
   connection that got disconnected/broken without the athlete profile
   reflecting it yet, or a stale subscription pointing at an old callback
   host.
3. Remember Render free tier sleeps after ~15 min idle — a webhook POST that
   hits a cold instance can miss Strava's 2 s ACK window on the first
   delivery; Strava retries up to 3 times, and the daily reconcile is the
   backstop regardless. This is expected, not a bug — SC-002 (100% within
   24 h) is designed around exactly this gap, not SC-001 (15 min) as a hard
   guarantee.

**Fix**: recreate the subscription if it's missing/misconfigured (§2); no fix
needed if this is just occasional cold-start latency covered by the reconcile
fallback.

### 5.4 Hostinger IP allowlist blocking a manual SQL check

Same caveat as the rest of the platform — see
[`../10-race-results/runbook-ops.md`](../10-race-results/runbook-ops.md) §1.2:
Hostinger Shared plans can allowlist by IP; a blocked local connection needs
adding the outgoing IP from hPanel → MySQL Remote.

## 6. Post-deploy checklist (first production rollout)

1. All env vars from §1 set on Render, `STRAVA_ENABLED=true`.
2. Migration applied: `alembic upgrade head` (runs automatically via
   `entrypoint.sh` on deploy; confirm `strava_connections` / `strava_activities`
   tables exist and `parental_consents.external_activity_sync` column exists).
3. Webhook subscription created against the **production** callback URL (§2)
   — not left pointing at a dev tunnel from earlier testing.
4. GitHub secret `STRAVA_RECONCILE_TOKEN` configured and equal to the Render
   value (§3).
5. Connect one real pilot athlete (with consent already registered, §4);
   record a short ride; confirm it appears within 15 minutes.
6. Confirm the next morning's scheduled GitHub Actions reconcile run is
   green (Actions tab).

## 7. Quick glossary

- **Reconcile**: the pull-based catch-up job (`POST .../reconcile`) that
  guarantees eventual delivery (SC-002) independent of webhook reliability.
- **Broken connection**: `strava_connections.status = 'broken'` — refresh
  token failed or scope was downgraded; requires the family/coach to
  reconnect, not an automated recovery.
- **Unlinked**: an activity with `training_session_id IS NULL` — a valid,
  permanent state, not a pending task.
- **`removed_upstream`**: the athlete deleted the activity on Strava; the
  platform keeps the row (and any session link) for the coach to review
  instead of hard-deleting it.
