# Deploy Checklist — Feature 025: Strava Activity Sync

**Preparation date:** 2026-07-10
**Target:** Render Free Tier — Oregon — Branch `main` — service `mi` (`https://mi-2yzi.onrender.com`)
**Auto-deploy:** enabled on push to `main`
**Migration:** `a4b5c6d7e8f9` (down_revision `d3e4f5a6b7c8`) — single head confirmed locally (`alembic heads`)
**Related docs:** [spec.md](spec.md) · [plan.md](plan.md) · [data-model.md](data-model.md) · [contracts/api.md](contracts/api.md) · [quickstart.md](quickstart.md) · `docs/15-strava-sync/` (ops runbook, if already published by T043)

---

## 0. Read this first — boot-failure risk specific to this feature

Unlike prior releases, this one has a **whole-app boot risk**, not just a
feature risk. `backend/app/config.py` has a `model_validator` that raises on
startup (crashes the whole container, not just Strava) when:

- `STRAVA_ENABLED=true` **and** any of `STRAVA_CLIENT_ID`,
  `STRAVA_CLIENT_SECRET`, `STRAVA_WEBHOOK_VERIFY_TOKEN`,
  `STRAVA_TOKEN_ENCRYPTION_KEY`, `STRAVA_RECONCILE_TOKEN` is empty.
- `STRAVA_ENABLED=true` **and** `STRAVA_REDIRECT_URI` still contains
  `localhost` (the dev default) in `APP_ENV=production`.

**Sequencing rule for this deploy**: ship the code with
`STRAVA_ENABLED=false` first (the Strava routers only mount when the flag is
true — `app/main.py`), confirm the service boots clean, **then** set the
remaining Strava secrets and flip `STRAVA_ENABLED=true` in a second env-var
update. Never set `STRAVA_ENABLED=true` in the same batch as an incomplete
secret set.

---

## PRE-DEPLOY

- [ ] Feature complete: all US1–US3 tasks in `tasks.md` done through T042 (quickstart Scenarios 1–5 pass)
- [ ] Backend tests green:
  ```bash
  cd backend && pytest tests/routers/test_strava_integration.py tests/routers/test_activities.py \
    tests/services/test_strava_ingest.py tests/services/test_strava_oauth.py \
    tests/privacy/test_strava_privacy.py && pytest
  ```
- [ ] Frontend tests green:
  ```bash
  cd frontend && npx vitest run src/routes/activities src/hooks/activities src/components/activities && npx tsc --noEmit
  ```
- [ ] `ruff` (backend) and `eslint` (frontend) clean
- [ ] `cd backend && alembic heads` shows exactly one head: `a4b5c6d7e8f9`
- [ ] Migration tested locally against a **recent Hostinger prod dump**:
  ```bash
  alembic upgrade head        # -> a4b5c6d7e8f9
  alembic downgrade -1        # -> d3e4f5a6b7c8 (drops strava_connections, strava_activities,
                               #    parental_consents.external_activity_sync + ENUM types)
  alembic upgrade head        # -> a4b5c6d7e8f9 again, no error
  ```
  Downgrade is destructive (DROP TABLE) by design per the migration docstring — acceptable
  pre-launch (no real Strava data exists yet), but re-verify with fresh data once the pilot
  athlete is connected (see Rollback section).
- [ ] New env vars listed and values prepared (see table below) — **do not commit real secrets**
- [ ] Breaking changes: **none**. Additive migration only (2 new tables + 1 nullable-by-default
      boolean column); new routers are conditionally mounted (`if settings.strava_enabled`), so
      the deploy is a no-op for existing functionality until the flag flips.
- [ ] `AI_LOG_PROMPTS=false` unaffected — this feature has no AI surface
- [ ] Operational prerequisites (one-time, outside the codebase):
  - [ ] Strava API app dashboard → **Authorization Callback Domain** set to `mi-2yzi.onrender.com`
        (must match the host in `STRAVA_REDIRECT_URI`, NOT the frontend domain)
  - [ ] Strava API app dashboard → self-service **"Actualizar"** upgrade clicked (1 → 10 athletes),
        so the pilot connection in this checklist doesn't hit the single-athlete cap
  - [ ] Family/guardian consent flow reachable in prod (`external_activity_sync` scope) — the pilot
        athlete's guardian must grant it before the SC-001 smoke step below
- [ ] Coach notified of the deploy window (see Communication section) — no training session or
      Copa Valle race day overlapping the window (next race: **V — 01-ago — Palmira**; confirm the
      chosen date/time against the weekly training schedule with the coach before locking it in)

### New environment variables (Render → Environment)

| Variable | Required when | Notes |
|---|---|---|
| `STRAVA_ENABLED` | always | Master switch. Deploy with `false` first — see §0 |
| `STRAVA_CLIENT_ID` | `STRAVA_ENABLED=true` | From existing Strava app, client_id `22676` |
| `STRAVA_CLIENT_SECRET` | `STRAVA_ENABLED=true` | Strava app dashboard → API settings |
| `STRAVA_WEBHOOK_VERIFY_TOKEN` | `STRAVA_ENABLED=true` | Any random string you choose; echoed back on subscription handshake — generate with `openssl rand -hex 16` |
| `STRAVA_TOKEN_ENCRYPTION_KEY` | `STRAVA_ENABLED=true` | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **back this up**; losing it makes all stored tokens unrecoverable (forces every family to reconnect) |
| `STRAVA_RECONCILE_TOKEN` | `STRAVA_ENABLED=true` | Shared secret for `POST /api/integrations/strava/reconcile`: `openssl rand -hex 32` — **must match** the GitHub secret below exactly |
| `STRAVA_API_BASE_URL` | optional | Default `https://www.strava.com/api/v3` is correct until 2027-01-04; leave unset |
| `STRAVA_OAUTH_BASE_URL` | optional | Default `https://www.strava.com/oauth` is correct; leave unset |
| `STRAVA_REDIRECT_URI` | `STRAVA_ENABLED=true` in prod | MUST be `https://mi-2yzi.onrender.com/api/integrations/strava/callback` — prod boot fails if it still contains `localhost` |
| `STRAVA_RECONCILE_LOOKBACK_HOURS` | optional | Default `48` is fine; leave unset |

---

## DEPLOY

- [ ] Merge to `main` (PR approved by user)
- [ ] **Step A** — Set `STRAVA_ENABLED=false` explicitly in Render (or leave unset; it defaults to
      false) before the push, so the first deploy is a clean no-secrets boot
- [ ] Push to `main` → auto-deploy starts (or trigger Manual Deploy if urgent)
- [ ] Monitor Render Dashboard → `mi` → **Events**/**Logs** during build
- [ ] Confirm migration applied without error in entrypoint logs:
  ```
  Aplicando migraciones...
  INFO  [alembic.runtime.migration] Running upgrade d3e4f5a6b7c8 -> a4b5c6d7e8f9, add strava sync tables (feature 025)
  Iniciando servidor...
  ```
- [ ] Confirm `Your service is live` with `STRAVA_ENABLED=false` — this proves the app boots clean
      independent of Strava config (isolates any Strava-secret issue from a general deploy issue)
- [ ] **Step B** — In Render Dashboard → Environment, set the remaining `STRAVA_*` secrets from the
      table above, then set `STRAVA_ENABLED=true`. Save → Render restarts the service automatically
      (env-var-only change, no rebuild, but still incurs a cold boot)
- [ ] Watch the restart logs for a clean boot — if the Settings validator raises, the service will
      crash-loop; the log line will name the missing/invalid field (e.g.
      `STRAVA_REDIRECT_URI usa el valor por defecto de desarrollo...`)

---

## POST-DEPLOY (cold-start ~50 s on first hit — wake the instance before timing anything)

- [ ] `curl -s https://mi-2yzi.onrender.com/health` → `{"status":"ok"}` (absorb the cold start here first)
- [ ] `GET /docs` → 200; confirm `strava-integration` and `activities` tags are present (only
      appear once `STRAVA_ENABLED=true` — absence here means the flag or a router import failed)
- [ ] `POST /api/auth/login` with coach test credential → 200 + token:
  ```bash
  TOKEN=$(curl -s -X POST https://mi-2yzi.onrender.com/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"entrenador@trochyruta.com","password":"Coach2026!"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  ```
- [ ] Main feature endpoint (coach review list, should be empty at this point):
  ```bash
  curl -s -H "Authorization: Bearer $TOKEN" https://mi-2yzi.onrender.com/api/activities | python3 -m json.tool
  ```
  → `200 {"items": [], "total": 0, ...}`
- [ ] Verify migrated tables on Hostinger (no missing-column errors):
  ```sql
  SELECT version_num FROM alembic_version;                 -- a4b5c6d7e8f9
  SHOW TABLES LIKE 'strava_%';                              -- strava_connections, strava_activities
  SHOW COLUMNS FROM parental_consents LIKE 'external_activity_sync';  -- present, tinyint(1), default 0
  ```

### One-time webhook subscription creation (do this AFTER the service is confirmed live with `STRAVA_ENABLED=true`)

Strava allows **exactly one** push subscription per app — check for a stale one before creating:

```bash
# 1. Check for an existing subscription (e.g. from a failed prior attempt)
curl -G https://www.strava.com/api/v3/push_subscriptions \
  -d client_id=<STRAVA_CLIENT_ID> -d client_secret=<STRAVA_CLIENT_SECRET>
# If one exists with the wrong callback_url or a stale verify_token, delete it first:
# curl -X DELETE https://www.strava.com/api/v3/push_subscriptions/<id> \
#   -d client_id=<STRAVA_CLIENT_ID> -d client_secret=<STRAVA_CLIENT_SECRET>

# 2. Wake the Render instance so the validation GET below responds within Strava's 2 s window
curl -s https://mi-2yzi.onrender.com/health > /dev/null

# 3. Create the subscription — Strava synchronously GETs the callback_url during this call
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=<STRAVA_CLIENT_ID> \
  -F client_secret=<STRAVA_CLIENT_SECRET> \
  -F callback_url=https://mi-2yzi.onrender.com/api/integrations/strava/webhook \
  -F verify_token=<STRAVA_WEBHOOK_VERIFY_TOKEN>
```

- [ ] Response includes a subscription `id` — **record it** (e.g. in this file's Release History
      entry below); there is no dashboard listing beyond the GET call above
- [ ] Render logs show the inbound validation `GET /api/integrations/strava/webhook` and a fast
      `200 {"hub.challenge": "..."}` — if it timed out (cold start > 2 s), delete and retry step 3
      immediately after the wake-up curl, with no delay in between
- [ ] `X-Reconcile-Token` mismatch check: `curl -X POST https://mi-2yzi.onrender.com/api/integrations/strava/reconcile` (no header) → `403`

### GitHub secret

- [ ] Repo → **Settings → Secrets and variables → Actions** → `STRAVA_RECONCILE_TOKEN` set to the
      **exact same value** as Render's `STRAVA_RECONCILE_TOKEN`
- [ ] Manually run `.github/workflows/strava-reconcile.yml` via **Actions → Run workflow**
      (`workflow_dispatch`) once, before waiting for the 09:00 UTC schedule — expect `200
      {"connections_processed": 0, "activities_upserted": 0, "connections_broken": 0}` (no
      connections yet) and a green run

### Tail logs 10 min

- [ ] No anomalous 5xx on `/api/integrations/strava/*` or `/api/activities*`
- [ ] Confirm log lines from ingest/reconcile contain **numeric IDs only** — no athlete names, no
      activity titles (privacy invariant, `tests/privacy/test_strava_privacy.py` covers this in CI,
      spot-check prod logs once for real)

### SC-001 / SC-002 pilot validation (do this once the pilot family's consent is granted)

- [ ] Connect **one real pilot athlete**: parent grants `external_activity_sync` consent → `POST
      /api/athletes/{id}/strava/connect` → open `authorize_url` → authorize on Strava → connection
      card shows **Conectado**
- [ ] Athlete (or coach on their behalf) records/uploads a short ride to Strava
- [ ] Note the Strava upload timestamp; confirm the activity appears in
      `GET /api/athletes/{id}/activities` within **15 minutes** (SC-001) — GPS fields absent from
      the response
- [ ] Next morning, confirm the scheduled GitHub Actions reconcile run (04:00 Colombia) is green —
      this is the SC-002 (24 h fallback) path, exercised even if the webhook already delivered

---

## COMMUNICATION

Coach notification (adapt dates before sending):

> Release Strava Activity Sync desplegado. Ahora pueden conectar la cuenta de Strava de un atleta
> desde su perfil (requiere consentimiento del acudiente) y las actividades sincronizadas
> aparecerán automáticamente. Solo tú (entrenador) puedes enlazarlas a una sesión específica desde
> `/activities`. Por favor prueba con [atleta piloto] esta semana y repórtame cualquier falla a
> [contacto].
>
> Nota: el primer ingreso del día puede tardar unos 50 segundos (el servidor gratuito se duerme
> tras 15 min de inactividad) — es normal, no es una falla.

---

## ROLLBACK (if needed)

Two levels, pick the smaller one first:

**Option A — soft disable (preferred, no migration touched)**
- Render Dashboard → Environment → set `STRAVA_ENABLED=false` → save (auto-restart). Routers
  unmount, ingestion stops, but no data is lost and no downgrade runs. Use this for any Strava-side
  behavioral issue (bad OAuth flow, webhook spam, rate-limit trouble).
- **Also unsubscribe the webhook** while disabled, to stop Strava retrying a route that will 404:
  `curl -X DELETE https://www.strava.com/api/v3/push_subscriptions/<id> -d client_id=... -d client_secret=...`

**Option B — full rollback (code + migration)**
- Render Dashboard → Deploys → **"Rollback to previous"**.
- The migration downgrade (`alembic downgrade -1` from `a4b5c6d7e8f9`) **DROPs**
  `strava_connections`, `strava_activities`, and `parental_consents.external_activity_sync` — this
  is destructive. Per the non-negotiable constraint on irreversible/destructive migrations:
  - Requires a **verified Hostinger backup** taken before rollback
  - Requires **explicit coach approval** if any pilot athlete's activity data would be lost
  - Coordinate with `engineering-lead` before running it
- Delete the webhook subscription (same DELETE call as Option A) so Strava stops posting events to
  a route that no longer exists after rollback.
- Notify the coach immediately, explain what data (if any) was lost.

---

## Release history

| Date | Outcome | Notes |
|---|---|---|
| _pending_ | _pending_ | First deploy of feature 025. Update this row after the release. |

---

## POST-MORTEM NOTES (fill in only if there was an incident)

What happened, why, what to do to prevent recurrence.
