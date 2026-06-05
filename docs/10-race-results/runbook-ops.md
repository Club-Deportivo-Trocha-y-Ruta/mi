# Operational Runbook — race-analyst v2 (F8A)

> **Audience**: coach, admin, on-call.
> **Scope**: agentic race-results v2 module (LangGraph + Gemini) in production.
> **Default MVP**: observability via audit DB (`athlete_ai_insights`, `agent_runs`,
> `agent_run_events`) + admin endpoint `/api/race-analysis/admin/ai-usage`.
> Langfuse self-hosted is deferred to optional F8B.

---

## 1. Access

### 1.1 Render (FastAPI backend)

- Dashboard URL: <https://dashboard.render.com>
- Service: `mi-2yzi` (Oregon, free tier, Docker).
- Real-time logs: **Logs** tab of the service (full-text search).
- Remote shell: **Shell** tab (not suitable for queries — use MySQL client).
- Sensitive variables: **Environment** tab (all listed in
  project `CLAUDE.md`).

### 1.2 MySQL Hostinger (database)

- Host: see `MYSQL_HOST` variable in Render env.
- Recommended client: `mysql` CLI or DBeaver with SSL.
- Credentials: `MYSQL_USER` / `MYSQL_PASS` in Render env.
- Quick connection from local:

  ```bash
  mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p "$MYSQL_DB"
  ```

> Hostinger Shared has an IP allowlist on some plans; if the
> connection fails with `Host '...' is not allowed`, the coach must add
> the outgoing IP from hPanel → MySQL Remote.

### 1.3 Render — login

1. Render account: use `juadigab@gmail.com` (shared with project admin).
2. If sleeping, first frontend request takes ~50s on cold start.

---

## 2. Key metrics

### 2.1 Admin endpoint

`GET /api/race-analysis/admin/ai-usage?days=30` — requires JWT with `admin` role.

Returns:

```json
{
  "window_days": 30,
  "run_count": 24,
  "cost_usd_total": 0.012,
  "latency_ms_p50": 18200,
  "latency_ms_p95": 32100,
  "fail_rate": 0.04,
  "by_prompt_version": [
    {"prompt_version": "race_analyst_v1", "run_count": 24, "cost_usd_total": 0.012}
  ]
}
```

This is the **primary operational source** — matches the logic of the
budget guard (both read `metrics_snapshot_json.aggregate.cost_usd_total`).

### 2.2 Raw SQL queries

Costs and latencies last 7 days per run (drill-down):

```sql
SELECT
  generated_at,
  use_case,
  prompt_version,
  JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.cost_usd_total') AS cost_usd,
  JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.latency_ms_total') AS latency_ms,
  coach_approved
FROM athlete_ai_insights
WHERE generated_at >= NOW() - INTERVAL 7 DAY
ORDER BY generated_at DESC
LIMIT 100;
```

Active / failed runs last 7 days:

```sql
SELECT status, COUNT(*) AS n
FROM agent_runs
WHERE started_at >= NOW() - INTERVAL 7 DAY
GROUP BY status;
```

Hung runs (>30 min without finishing):

```sql
SELECT external_run_id, status, started_at, requested_by_user_id
FROM agent_runs
WHERE status IN ('running', 'awaiting_hitl')
  AND started_at < NOW() - INTERVAL 30 MINUTE
ORDER BY started_at;
```

Events of a specific run (debugging):

```sql
SELECT seq, event_type, node_name,
       JSON_EXTRACT(payload_json, '$.error') AS error
FROM agent_run_events
WHERE run_id = (SELECT id FROM agent_runs WHERE external_run_id = 'XXX')
ORDER BY seq;
```

---

## 3. Common alerts

### 3.1 LLM (Gemini) down

**Symptoms**:
- `fail_rate` in `/ai-usage` > 0.20.
- Render logs with many `agent run XXX failed: APIError` or similar.

**Diagnosis**:
1. Check Google AI status: <https://status.cloud.google.com>.
2. Confirm `AI_API_KEY` hasn't expired (Google AI Studio dashboard).
3. If Google is OK, review quotas (rate limits of model `gemini-2.5-flash-lite`).

**Mitigation**:
- **Temporary disable**: set `AI_ENABLED=false` in Render → Save → auto-redeploy.
  This makes `POST /runs` respond 503 with message "AI not available" — the
  coach sees a clear toast and stops spawning runs that will fail.
- **Fallback**: the graph has a `fallback.py` node that generates basic
  deterministic analysis if the LLM fails; runs degrade but are not lost.

### 3.2 Hung run >30 min

**Symptom**: query from §2.2 returns rows.

**Common cause**:
- FastAPI worker was restarted (Render redeploy) while a run
  was active — the LangGraph SQLite-local checkpointer in the worker
  is lost and there is no continuation.

**Mitigation**:
1. Cancel manually (zero impact for users — the coach retries):

   ```sql
   UPDATE agent_runs
   SET status='cancelled',
       finished_at = NOW(),
       error_message = 'manual cancel: orphaned post-restart'
   WHERE external_run_id = 'XXX' AND status IN ('running', 'awaiting_hitl');
   ```

2. If this happens frequently, consider migrating the checkpointer to Redis
   (TODO documented in `app/services/race/ai/runner.py`).

### 3.3 Eval fails in CI

**Symptom**: GitHub Actions pipeline with eval framework (F7) in red.

**Diagnosis**:
1. Check `evals/race_analyst/results/last_run.md` — shows which golden
   fixtures diverged.
2. Compare with baseline (prior commit) to identify the responsible change
   (prompt, weights, Gemini model version bump).

**Mitigation**:
- If the divergence is expected (intentional improvement): update
  baseline + document in PR.
- If it's a regression: revert the prompt commit or adjust.

### 3.4 Cost spikes — budget guard active

**Symptom**:
- Coach reports 503 error "Monthly AI budget exceeded: $X of $Y".
- Render logs contain `ERROR ... race_ai_budget_exceeded: ...`.

**Diagnosis**:
1. Confirm real spending:

   ```bash
   curl -H "Authorization: Bearer $ADMIN_JWT" \
     "https://mi-2yzi.onrender.com/api/race-analysis/admin/ai-usage?days=30"
   ```
2. Drill-down by prompt_version to see which version consumes:
   see `by_prompt_version` field in response.

**Mitigation** (in order of preference):
1. **Wait**: if spending is due to legitimate traffic and little time remains before
   the 30d window rolls over, just wait.
2. **Temporarily raise the threshold**: set
   `RACE_AI_BUDGET_USD_30D=40` in Render → redeploy (takes ~1 min).
3. **Investigate leak**: if cost jumped 10x without more users, check:
   - Is there a retry loop from some feature flag?
   - Did `AI_MAX_TOKENS` increase? (check in env var)
   - Does an athlete have hundreds of competitors per GROUP that inflates the prompt?

> **Cooldown**: the guard only logs/notifies once per hour even if there are
> 100 rejected requests. If you need to reset the cooldown (debugging),
> restart the service (`Manual Deploy`).

### 3.5 PII leak detected

> **Critical**: personal data of minors exposed in any output
> (logs, frontend, email, exports).

**Procedure**:
1. **Immediate containment**: set `AI_LOG_PROMPTS=false` (must always be
   `false` in prod; the Settings validator enforces this).
2. **Audit logs**: download Render logs from the last 7 days and grep for
   full name/surname patterns. Delete logs if Render allows it
   (free tier does not allow delete — escalate to paid if necessary).
3. **Invalidate cache of affected insights**:

   ```sql
   UPDATE athlete_ai_insights
   SET archived_at = NOW()
   WHERE athlete_id = <affected_ID>;
   ```
4. **Notify affected parties**: contact the coach + parents of the affected athlete(s)
   via direct channel (not automatic email — the content is sensitive).
5. **Post-mortem**: document in `docs/10-race-results/` and add a
   regression test that covers the leak path.

---

## 4. Restart procedure

### 4.1 Production (Render)

- **Clean restart**: Render Dashboard → service `mi-2yzi` → Manual Deploy
  → "Deploy latest commit". Takes ~3-5 min (build + Alembic migration + start).
- **Auto-deploy**: every push to `main` triggers automatic redeploy.
- **Quick rollback**: Dashboard → Deploys → click on previous deploy →
  "Redeploy". NOTE: Alembic migrations are not automatically reverted
  — if the rollback crosses a new migration, run `alembic downgrade`
  manually via Shell.

### 4.2 Local (docker compose)

```bash
docker compose down
docker compose up --build
```

`entrypoint.sh` runs `alembic upgrade head` before starting uvicorn.
In `development` environment the seed also runs.

---

## 5. Backups

### 5.1 Hostinger MySQL

- **Automatic backup**: Hostinger performs daily full DB backup
  (7 days retention on shared plan).
- **Restore**: hPanel → MySQL → Backups → Restore. CAUTION: the
  restore replaces the entire DB.
- **Manual backup before critical changes**:

  ```bash
  mysqldump -h "$MYSQL_HOST" -u "$MYSQL_USER" -p \
    --single-transaction --quick \
    "$MYSQL_DB" > backup_$(date +%Y%m%d_%H%M).sql
  ```

### 5.2 Criticality by table

| Table | Criticality | Recovery |
|---|---|---|
| `athlete_ai_insights` | **High** — data for coach + AI audit. | Restore from backup. |
| `agent_runs` | Medium — run history; can be regenerated (with cost). | Restore + advisory to coach. |
| `agent_run_events` | **Low (ephemeral)** — only polling/SSE. Grows fast; archive/truncate >90d. | No restore needed. |
| `anonymization_mappings` | Medium — deleting = losing traceability. | Restore. |

### 5.3 Recommended recurring task

Truncate `agent_run_events` >90 days, monthly:

```sql
DELETE FROM agent_run_events
WHERE created_at < NOW() - INTERVAL 90 DAY;
```

---

## 6. Post-deploy smoke test

After each Render redeploy, run E2E smoke (script
`backend/scripts/smoke_test_prod.py`):

```bash
cd backend
source .venv/bin/activate
export RACE_SMOKE_BASE_URL=https://mi-2yzi.onrender.com
export RACE_SMOKE_TOKEN=<jwt-coach>
export RACE_SMOKE_ADMIN_TOKEN=<jwt-admin>

python -m scripts.smoke_test_prod \
  --athlete-id 17 \
  --season 2026
```

Exit codes:
- `0` — OK (run executed + insight persisted + cost_usd > 0).
- `1` — failure (timeout, network error, validation, cost==0).

For full `--help`: `python -m scripts.smoke_test_prod --help`.

> In local with fake AI (`AI_PROVIDER=fake`), run with `--skip-cost-check`
> because the mock provider does not accumulate cost.

---

## 7. Quick glossary

- **F8A**: phase 8 option A — audit-only observability via DB
  (default MVP).
- **F8B**: phase 8 option B — Langfuse self-hosted (deferred,
  optional, see `v2-agentic-design.md`).
- **Budget guard**: module `app/services/race/ai/budget_guard.py` that
  blocks new runs if 30d spending >= `RACE_AI_BUDGET_USD_30D`.
- **HITL**: Human-In-The-Loop — `hitl_gate_review` node that pauses the
  graph waiting for coach approval.
- **Hung run**: status=`running` or `awaiting_hitl` for >30 min without
  new event in `agent_run_events`.
