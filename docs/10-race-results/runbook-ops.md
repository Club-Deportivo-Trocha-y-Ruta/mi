# Operational Runbook — race-analyst v2 (F8A)

> **Audience**: coach, admin, on-call.
> **Scope**: agentic race-results v2 module (LangGraph + Gemini) in production.
> **Default MVP**: observability via audit DB (`athlete_ai_insights`, `agent_runs`,
> `agent_run_events`) + admin endpoint `/api/race-analysis/admin/ai-usage`.
> Local-only Langfuse tracing is available as an optional dev tool — see §8.

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

## 8. Local LLM tracing (Langfuse)

> Optional, dev-only observer for per-call token/latency detail on race-AI
> LLM calls (`app/services/race/observability.py`). It never runs in
> production — `Settings.forbid_langfuse_in_prod` raises at startup if
> `LANGFUSE_ENABLED=true` and `APP_ENV=production`. It does not replace the
> audit trail of record (§2); it only adds a drill-down view for local
> debugging.

### 8.1 Prerequisites

- Docker Desktop running.
- Backend running locally, either host `uvicorn` or `docker compose up`.

### 8.2 One-time setup

1. `cp docker-compose.langfuse.env.example docker-compose.langfuse.env`
2. Generate the secrets and replace the placeholders in that file:
   - `NEXTAUTH_SECRET`, `SALT`: `openssl rand -base64 32`
   - `ENCRYPTION_KEY`: `openssl rand -hex 32`
   - `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`: `pk-lf-` + `openssl rand -hex 16`
   - `LANGFUSE_INIT_PROJECT_SECRET_KEY`: `sk-lf-` + `openssl rand -hex 24`
3. Copy that same public/secret key pair into the backend's own `.env` as
   `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`, and set
   `LANGFUSE_ENABLED=true`. The backend authenticates against the project
   that Langfuse bootstraps headlessly on first boot (`LANGFUSE_INIT_*`
   vars) — no need to open the UI to generate keys.

### 8.3 Bring up / verify

```bash
docker compose -f docker-compose.langfuse.yml --env-file docker-compose.langfuse.env up -d
curl http://localhost:3001/api/public/health
```

UI: <http://localhost:3001> (login with `LANGFUSE_INIT_USER_EMAIL` /
`LANGFUSE_INIT_USER_PASSWORD` from `docker-compose.langfuse.env`). Restart
the backend after flipping `LANGFUSE_ENABLED` — env vars are read at
process start, not hot-reloaded.

### 8.4 Backend env vars

| Var | Host `uvicorn` | Docker backend |
|---|---|---|
| `LANGFUSE_BASE_URL` | `http://localhost:3001` (default) | set via `LANGFUSE_BASE_URL_DOCKER` in the shell before `docker compose up` → mapped to `http://host.docker.internal:3001` in `docker-compose.yml` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | from `.env` | same pair, passed through `docker-compose.yml` |

There is no content-capture toggle — see §8.6.

### 8.5 What is traced

Traced via `observability.llm_tracing(...)` — grep the codebase for
`llm_tracing(` to get the current, authoritative list of entry points:

| Trace name | Entry point | Content |
|---|---|---|
| `race-analysis` | `app/services/race/ai/runner.py` — graph start and HITL resume share one trace (deterministic trace id derived from the external run id) | always redacted |
| `race-chat` | `app/services/race/agents/chat.py` | always redacted — the chat prompt carries real athlete names |
| `race-eval-judge` | `app/services/race/eval/judge.py` (both v1 and v2 judges) | always redacted |

Not traced: the monthly-report and newsletter AI paths run on the separate
`app/services/ai/` stack, which has no `llm_tracing` call — they have no
Langfuse visibility.

Only Langfuse-SDK spans are exported to the collector — a `should_export_span`
filter drops any third-party OpenTelemetry span (e.g. MCP/`gen_ai` spans
emitted by the local `claude-cli` provider) so Langfuse only ever shows the
spans this integration explicitly created, never an incidental trace from
whatever the LLM SDK instruments on its own.

### 8.6 Privacy / redaction semantics

There is no content-capture toggle. Inputs, outputs and metadata of every
observation are **always** sent as `"[redacted]"` — this is not
configurable, on any trace, at any time.

- **Why**: even the pseudonymized analyst/critic prompt still carries
  quasi-identifiers of a minor (birth date, category, race position,
  times, age, maturity/PHV data) that could re-identify the athlete on
  their own; and rehydrated conversational memory in the chat path can
  contain real names. Redact-always removes the judgment call of which
  fields are "safe enough" to send.
- **What is still stored locally**: run UUIDs (`race-analysis` session id),
  a SHA-256-truncated hash of the chat session id
  (`observability.anonymous_session_id`), trace tags (provider, prompt
  version, analysis kind), and token counts (`usageDetails`: input/output/
  total). None of this is athlete-identifying on its own.
- **Where it lives / retention**: traces persist in the local Docker
  volumes (`langfuse_postgres_data`, `langfuse_clickhouse_data`, …) with no
  retention policy configured — they accumulate until purged. Purge with
  `docker compose -f docker-compose.langfuse.yml down -v` (§8.10).
- `LANGFUSE_ENABLED=true` in production is a hard startup failure — never
  set it on Render.

### 8.7 Reading token usage

In the UI, open a trace and expand a `generation` node — it shows tokens
in/out, total, model, and latency per LLM call, alongside the `[redacted]`
input/output. Sessions correspond to the run id (`race-analysis`/
`race-chat`) or the eval `case_id` (`race-eval-judge`). Verified live on
2026-09-10 against a local Langfuse v4 instance: a traced call showed
`usageDetails` (input/output/total tokens) populated while `input`/`output`
read `[redacted]`, as expected.

As an API alternative to the UI, the Langfuse v2 observations API requires
the query param `fields=core,basic,usage,io,model` to return the usage and
model fields at all — without it, a bare request omits them.

### 8.8 Drill-down from a DB run

`agent_runs.langfuse_trace_id` is populated by
`routers/race_analysis.py::_finalize_run` whenever tracing is enabled.
Given a trace id, open:

```text
http://localhost:3001/project/<LANGFUSE_INIT_PROJECT_ID>/traces/<trace_id>
```

(`LANGFUSE_INIT_PROJECT_ID` defaults to `race-analyst-dev`, set in
`docker-compose.langfuse.env`).

### 8.9 Cost caveat

Langfuse infers USD cost from its own model price list and may not
recognize project-specific model ids (`gemini-3.8-flash`,
`claude-cli` at $0 local-subscription cost) — treat any cost figure shown
in its UI as approximate. The source of truth for cost and for the 30-day
budget guard remains `agents/pricing.py` +
`athlete_ai_insights.metrics_snapshot_json` (§2).

### 8.10 Stop / reset

```bash
docker compose -f docker-compose.langfuse.yml down       # stop, keep data
docker compose -f docker-compose.langfuse.yml down -v     # reset, wipes volumes
```

### 8.11 Troubleshooting

- **`langfuse-web` healthy, `langfuse-worker` still starting right after
  boot**: expected — `langfuse-web` does not `depends_on` the worker
  (only `langfuse-web` runs the Prisma migrations on first start; waiting
  on the worker would deadlock, since the worker never turns healthy until
  that schema exists).
- **Healthcheck fails with "connection refused" when inspected via
  `docker exec`**: the Next.js server binds to the container's interface
  IP, not loopback — the compose healthchecks target the service name
  (`http://langfuse-web:3000/...`, `http://langfuse-worker:3030/...`), not
  `localhost`; don't "fix" this by editing them to `localhost`.
- **Backend log `LANGFUSE_ENABLED=true sin LANGFUSE_PUBLIC_KEY/
  LANGFUSE_SECRET_KEY — trazas deshabilitadas`**: keys missing or stale —
  re-copy the pair from `docker-compose.langfuse.env`.
- **No traces show up in the UI**: confirm `LANGFUSE_BASE_URL` actually
  reaches the container from where the backend runs (docker backend needs
  `host.docker.internal`, not `localhost`) and that
  `docker compose -f docker-compose.langfuse.yml ps` shows every service
  healthy.

---

## 9. Quick glossary

- **F8A**: phase 8 option A — audit-only observability via DB
  (default, in production).
- **Local Langfuse tracing**: optional dev-only observer, see §8. Never
  runs in production.
- **Budget guard**: module `app/services/race/ai/budget_guard.py` that
  blocks new runs if 30d spending >= `RACE_AI_BUDGET_USD_30D`.
- **HITL**: Human-In-The-Loop — `hitl_gate_review` node that pauses the
  graph waiting for coach approval.
- **Hung run**: status=`running` or `awaiting_hitl` for >30 min without
  new event in `agent_run_events`.
