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

> Optional, dev-only observer for per-call token/latency detail on LLM
> calls from **both** AI stacks of the monorepo (feature 042). It never
> runs in production — `Settings.forbid_langfuse_in_prod` raises at
> startup if `LANGFUSE_ENABLED=true` and `APP_ENV=production`. It does not
> replace the audit trail of record (§2 for race, `athlete_ai_explanations`
> for the app stack); it only adds a drill-down view for local debugging.

**Module moved (feature 042, T011)**: the Langfuse client, the
redact-always mask and the no-op degradation used to live entirely in
`app/services/race/observability.py`. They now live in
`app/services/llm/observability.py` — a shared, stack-neutral module so
`app/services/ai/` can trace without depending on the `race` package.
`app/services/race/observability.py` is kept only as a **thin
compatibility shim** that re-exports the same public functions
(`get_callbacks`, `llm_tracing`, `trace_id_for`, `shutdown`,
`keyed_session_id`, `anonymous_session_id`) and proxies the module's
mutable process state (`_client`, `_warned_missing_keys`, …) to the real
module. The shim exists because roughly 30 tests across the three W1
shims (`race/agents/_llm.py`, `race/agents/pricing.py`,
`race/observability.py`) `monkeypatch` those exact module paths
(`plan.md` Complexity Tracking) — deleting them in the same wave that
introduced the shared factory was rejected as unnecessary risk to the
blocking race golden eval. **It is scheduled for removal in a later
feature**, once those tests are moved to import from
`app.services.llm.observability` directly — not in feature 042. Import
from `app.services.race.observability` still works today and behaves
identically to importing from `app.services.llm.observability`, but new
code should prefer the real module.

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

Traced via `llm_tracing(...)` (imported from either
`app.services.llm.observability` directly, or the
`app.services.race.observability` shim — same function, see the module
note above) — grep the codebase for `llm_tracing(` to get the current,
authoritative list of call sites. As of feature 042 there are **five**,
spanning both stacks:

| Trace name | Entry point | Stack | Content |
|---|---|---|---|
| `race-analysis` | `app/services/race/ai/runner.py` — graph start and HITL resume share one trace (deterministic trace id derived from the external run id) | race | always redacted |
| `race-chat` | `app/services/race/agents/chat.py` | race | always redacted — the chat prompt carries real athlete names |
| `race-eval-judge` | `app/services/race/eval/judge.py` (both v1 and v2 judges) | race | always redacted |
| `anthro-{use_case}` | `app/services/ai/anthro/pipeline.py::run_analysis` — the single orchestrator behind **both** `POST /athletes/{id}/phv-explanation` (PHV explanation, `use_case` = `phv_explainer`/`phv_explanation_coach` per audience) and `POST` per-measurement analysis (`use_case` = `anthropometric_record_analysis`/`anthropometric_record_explainer_coach`) — see `app/routers/ai.py`. One trace covers the whole pipeline run (context → analyst → critic → optional revision) via a single `config` threaded through every step. | app | always redacted |
| `anthro-eval-judge` | `app/services/ai/anthro/eval/judge.py` (golden eval judge) | app | always redacted |

**Not traced, on purpose — read this before assuming coverage**: the
plan's design intent was for all seven `app/services/ai/` generation
paths to gain Langfuse visibility once they moved onto the LangChain
transport. What actually shipped is narrower. Five of those seven —
session assistant clarify, session assistant draft, monthly report,
monthly report blocks, and family newsletter v2 — are bridged onto the
shared LangChain transport via `LangChainProvider`
(`app/services/ai/providers/langchain_provider.py`) behind
`AI_USE_LANGCHAIN`, but `LangChainProvider.complete()` calls
`self._chat_model.ainvoke(messages)` **without a `config=`** — by design,
per that module's own docstring: "the five bridged use cases have no
per-request Langfuse scope to thread today" (contrast the anthro
pipeline above, which does thread `config` through every step). No
Langfuse callback is attached, so **these five entry points produce no
trace today, in any configuration, including `AI_USE_LANGCHAIN=true` and
`LANGFUSE_ENABLED=true`.** The migration bridged their *transport*
(FR-025 — same prompts, same outputs, same tests, rollback switch), not
their *observability*; adding tracing to them is not something this
runbook can point at a shipped code path for. If you need per-call
token/latency detail on one of these five, it is not available via
Langfuse yet — use `AI_LOG_PROMPTS` (never in production) or the
`TokenUsage` already returned in `LLMResponse` and logged by the caller.

Only Langfuse-SDK spans are exported to the collector — a `should_export_span`
filter drops any third-party OpenTelemetry span (e.g. MCP/`gen_ai` spans
emitted by the local `claude-cli` provider) so Langfuse only ever shows the
spans this integration explicitly created, never an incidental trace from
whatever the LLM SDK instruments on its own.

### 8.6 Privacy / redaction semantics

Inputs and outputs of every observation are **always** sent as
`"[redacted]"` — this is not configurable, on any trace, at any time,
regardless of `LANGFUSE_STRUCTURAL_METADATA` (see below). What changed in
feature 042 is the session-id derivation and the (still off-by-default)
metadata channel.

- **Why redact-always**: even the pseudonymized analyst/critic prompt
  still carries quasi-identifiers of a minor (event date, category, race
  position, times, age, maturity/PHV data) that could re-identify the
  athlete when crossed with public official results; and the analyst's
  recalled memory (rehydrated summaries) can contain real names.
  Redact-always removes the judgment call of which fields are "safe
  enough" to send.
- **Session ids are now an HMAC, not a bare hash (feature 042, FR-024)**:
  `observability.anonymous_session_id` (plain SHA-256, truncated to 16
  hex chars) is **enumerable** — a club this size has on the order of a
  few hundred athlete/record combinations, well under 10,000 hashes, so
  anyone with the Langfuse volume and the DB could brute-force it back to
  an athlete. It is kept, unchanged, only for backward compatibility;
  every call site that previously used it now uses
  `observability.keyed_session_id` instead, which derives an HMAC-SHA256
  keyed on `settings.jwt_secret_key` (domain-separated from both the race
  pseudonym anonymizer and from `anonymous_session_id` itself, so leaking
  one derivation doesn't weaken the others) — not invertible without that
  server secret. This covers **`race-chat`** as well (FR-024 explicitly
  required the race chat trace to move onto the same keyed helper as the
  new app-stack traces), plus `race-eval-judge` and every `anthro-*`
  trace. `race-analysis` is unaffected — its session id is the run's own
  external UUID, not a derived hash of anything athlete-identifying.
  `keyed_session_id` is stable across process restarts by explicit owner
  decision (a per-process salt would be stronger but would break grouping
  of one athlete's traces across a backend redeploy).
- **`LANGFUSE_STRUCTURAL_METADATA` (default `false`, feature 042)**: with
  the flag off — the only legal value in production — behaviour is
  byte-for-byte identical to before this feature: the `metadata` argument
  on every observation is omitted entirely. Turning it on locally lets a
  narrow, **closed allow-list** of operational fields survive the mask —
  see `app/services/llm/observability_metadata.py::ALLOWED_METADATA_KEYS`
  for the exact key names (model/provider/prompt_version/role, token
  counts, latency, cost, guardrail/precheck rule ids and counts, critic
  verdict, cache outcome, and a small set of *keyed-hash-only*
  identifiers such as `athlete_id_hash`). It is a strict allow-list
  enforced at construction time (`StructuralMetadata.__init__` raises on
  any key outside it, and rejects two or more quasi-identifiers —
  `sex`/`age_group`/`maturation_status`/`category` — combined in the same
  call, since that combination alone can shrink an equivalence class
  below a safe size for a club this size). **Turning it on does NOT
  change the no-retention story below in any way** — it only ever adds a
  few extra key/value pairs to the same local, unmanaged trace volumes;
  it never touches `input`/`output`, which stay `"[redacted]"`
  unconditionally, and it does not add any new retention policy, export
  path, or off-machine destination for that data.
  `Settings.forbid_langfuse_structural_metadata_in_prod` makes
  `LANGFUSE_STRUCTURAL_METADATA=true` a hard startup failure under
  `APP_ENV=production`, exactly like `LANGFUSE_ENABLED=true` itself —
  never set it on Render.
- **What is still stored locally**: run UUIDs (`race-analysis` session
  id), the keyed-HMAC session id described above for every other trace,
  trace tags (provider, prompt version, analysis kind), token counts
  (`usageDetails`: input/output/total), and — only with
  `LANGFUSE_STRUCTURAL_METADATA=true` — the allow-listed operational
  metadata above. None of this is athlete-identifying on its own.
- **Where it lives / retention**: traces persist in the local Docker
  volumes (`langfuse_postgres_data`, `langfuse_clickhouse_data`, …) with
  no retention policy configured, before or after feature 042 — they
  accumulate until purged. See §8.10 for the purge command and the
  recommended cadence.
- `LANGFUSE_ENABLED=true` in production is a hard startup failure — never
  set it on Render.

### 8.7 Reading token usage

In the UI, open a trace and expand a `generation` node — it shows tokens
in/out, total, model, and latency per LLM call, alongside the `[redacted]`
input/output. Sessions correspond to the run id (`race-analysis`), the
keyed-hash chat session id (`race-chat`), the keyed-hash eval `case_id`
(`race-eval-judge`, `anthro-eval-judge`), or the keyed hash of
`{use_case}:{athlete_id}:{record_id}` (every `anthro-*` trace — see
§8.5). Verified live on 2026-09-10 against a local Langfuse v4 instance: a
traced call showed `usageDetails` (input/output/total tokens) populated
while `input`/`output` read `[redacted]`, as expected.

As an API alternative to the UI, the Langfuse v2 observations API requires
the query param `fields=core,basic,usage,io,model` to return the usage and
model fields at all — without it, a bare request omits them.

### 8.8 Drill-down from a DB run

`agent_runs.langfuse_trace_id` is populated by
`routers/race_analysis.py::_finalize_run` whenever tracing is enabled —
this covers `race-analysis`. Since feature 042, the same pattern applies
to the app stack's traced entry points: `athlete_ai_explanations`
carries its own nullable `langfuse_trace_id` column, populated by
`app/services/ai/anthro/pipeline.py::run_analysis` (via
`persist.py`) for `anthro-{use_case}` runs — one of the nine new columns
added by this feature (`docs/20-traceable-growth-ai/` covers the full
column list). Given a trace id from either table, open:

```text
http://localhost:3001/project/<LANGFUSE_INIT_PROJECT_ID>/traces/<trace_id>
```

(`LANGFUSE_INIT_PROJECT_ID` defaults to `race-analyst-dev`, set in
`docker-compose.langfuse.env`).

### 8.9 Cost caveat

Langfuse infers USD cost from its own model price list and may not
recognize project-specific model ids (`gemini-3.8-flash`,
`claude-cli` at $0 local-subscription cost) — treat any cost figure shown
in its UI as approximate. The source of truth for cost is the shared
`app/services/llm/pricing.py` (feature 042; `agents/pricing.py` is now a
thin shim over it, same reasoning as `observability.py` in §8 intro) +
`athlete_ai_insights.metrics_snapshot_json` for race (§2) or
`athlete_ai_explanations.cost_usd` for the app stack (§9). Neither of
those DB columns is ever populated *from* Langfuse — Langfuse's own cost
figure is display-only, local to its UI/API.

### 8.10 Stop / reset / purge cadence

```bash
docker compose -f docker-compose.langfuse.yml down       # stop, keep data
docker compose -f docker-compose.langfuse.yml down -v     # reset, wipes volumes
```

There is no automatic retention or expiry job — feature 042 did not add
one, and none existed before it (§8.6). Traces accumulate in the local
Docker volumes indefinitely until someone runs the `down -v` above.
Recommended cadence for a local dev machine: purge whenever you start a
fresh round of debugging (so old traces from a stale prompt version don't
get mixed into a search), and at minimum whenever `docker volume ls`
shows `langfuse_clickhouse_data`/`langfuse_postgres_data` growing large
enough to matter for local disk space — there is no compliance reason to
purge on any fixed schedule, since every trace is already redact-always
and never leaves the local machine. If you need a specific past trace
for a post-mortem, extract what you need from the UI/API first — `down
-v` is not reversible.

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
- **No trace for a session-assistant / monthly-report / newsletter-v2
  call, even with `LANGFUSE_ENABLED=true` and `AI_USE_LANGCHAIN=true`**:
  not a bug — see §8.5. Those five entry points run on the shared
  LangChain transport but are not wired to a Langfuse scope; only
  `anthro-{use_case}` (PHV explanation, per-measurement analysis) and the
  three `race-*`/`anthro-eval-judge` traces produce anything to look at.

---

## 9. Quick glossary

- **F8A**: phase 8 option A — audit-only observability via DB
  (default, in production).
- **Local Langfuse tracing**: optional dev-only observer, see §8. Never
  runs in production.
- **Budget guard**: module `app/services/race/ai/budget_guard.py` that
  blocks new runs if 30d spending >= `RACE_AI_BUDGET_USD_30D`. **Scoped to
  the race stack only** — see the app-stack spend note directly below.
- **HITL**: Human-In-The-Loop — `hitl_gate_review` node that pauses the
  graph waiting for coach approval.
- **Hung run**: status=`running` or `awaiting_hitl` for >30 min without
  new event in `agent_run_events`.
- **App-stack spend, and why it's a separate series from the budget
  guard (feature 042, FR-022/FR-023)**: `GET
  /api/race-analysis/admin/ai-usage` — the same endpoint documented in
  §2.1 — now returns `by_coach` rows for **two** stacks side by side,
  each tagged with a `stack` field: `stack="race"` (the pre-existing
  series, sourced from `athlete_ai_insights`/`agent_runs`) and
  `stack="app"` (feature 042; every generation from
  `app/services/ai/` — PHV explainer, per-measurement analysis, session
  assistant, monthly report + blocks, newsletter v2 — sourced from
  `athlete_ai_explanations`). **If you're paged for a budget alert,
  check which series it's about before reacting**: only `stack="race"`
  ever counts toward `RACE_AI_BUDGET_USD_30D`, and only `stack="race"`
  spend can ever trigger the §3.4 "budget guard active" 503. The
  `stack="app"` series has **no spending cap at all** — by explicit owner
  decision, it is never refused and never blocks a request, no matter
  how high its `cost_usd_total` climbs. Raising
  `RACE_AI_BUDGET_USD_30D` (§3.4) has zero effect on `stack="app"` spend,
  and a spike in `stack="app"` spend can never be the cause of a
  `race_ai_budget_exceeded` log line. Note also that the top-level
  `run_count`/`cost_usd_total` fields of the same response stay
  race-only (unchanged by this feature) — only the `by_coach` list
  gained the second stack.

---

## 10. Course profile (feature 043)

> Scope: the seven `/course*` endpoints on the race-events router (variants,
> category setups, description), and their downstream effects on results and
> the AI analysis. Design detail (data model, GPX algorithm, AI integration):
> `docs/10-race-results/course-profile-design.md`.

### 10.1 Re-uploading a GPX to correct a wrong lap count

The coach cannot edit a stored variant's geometry directly — the original
file is never retained (Ley 1581: it is the coach's personal recording).
Every correction is a **re-upload**:

1. Coach re-records or locates the same GPX file.
2. In the Circuito tab, open the variant's "Reemplazar archivo" action
   (`VariantsCard`) — this calls `PUT /{race_event_id}/course/variants/{variant_id}/file`.
3. If the platform mis-detected the lap count (common on a recording with a
   GPS glitch near the start/finish, or a genuinely irregular loop that
   doesn't close within 30 m), set **"Vueltas grabadas"** to the real number
   of laps in that recording before confirming. This forces
   `recorded_laps` on the request, which makes `process_gpx` use
   `method="manual"` and cut the lap at `total_distance / recorded_laps`
   instead of running the closure search — it is the *only* way to
   recompute, because nothing from the original upload survives between
   requests.
4. The response is the full `CourseRead`; check `variants[].detection` in
   the payload (or the dialog's confirmation copy) for
   `laps_detected`/`lap_distance_km` to confirm the correction took.
5. `id` stays the same — any category setup already pointing at this
   variant keeps pointing at it; only the geometry/distance/gain figures
   change.

If the coach instead uploads a **different** recording of the same route by
mistake, the response is `409 duplicate_recording` when its SHA-256 matches
a variant already stored for this válida — that is expected, not a bug; the
fix is to use the intended file, or `PUT .../file` if the intent really was
to replace.

### 10.2 Reading a 409 or 422 from a support report

Full message table: `specs/043-race-course-profile/contracts/course-api.md`
§6. Operationally, group them like this when triaging a "no pude subir el
GPX" report:

| Status | Codes | What it means for the operator |
|---|---|---|
| 415 | `unsupported_media_type` | Browser sent a content-type outside the allow-list (`application/gpx+xml`, `application/xml`, `text/xml`, `application/octet-stream`). Ask what app exported the file — some non-standard exporters use an unrecognized MIME type; the extension check in the next row is usually enough on retry. |
| 422 | `not_gpx`, `malformed`, `no_track_points`, `no_position`, `too_few_points` | The file isn't a well-formed GPX with usable track points. Ask the coach to open the file in a map tool (e.g. the device's own app) to confirm it actually has a recorded track, not just a route/waypoints file. |
| 422 | `xml_unsafe` | The file tripped the `defusedxml` guard (DTD, external entity, or similar). This should never happen with a normal GPS device export — if it does, treat the file as suspicious rather than asking the coach to retry it as-is. |
| 422 | `compressed_not_allowed` | The upload is a `.zip`/`.gz`, detected by magic bytes regardless of the `.gpx` extension on the filename. Ask the coach to extract it first. |
| 413 | `file_too_large` | Over 5 MB. A multi-hour recording at 1 Hz can hit this; suggest recording just the lap(s) needed, or splitting the file before upload. |
| 422 | `too_short` | Lap came out under 300 m — usually means the closure search found a false near-start point almost immediately. Check whether `recorded_laps` needs to be set manually (§10.1). |
| 422 | `too_long` | Lap came out over 15 km — usually a recording with no valid closure at all, so the whole file was treated as one "lap". Same fix: set `recorded_laps` explicitly. |
| 409 | `duplicate_recording` | This exact file (by SHA-256) is already stored as another variant of this válida. Not an error to "fix" — either that upload already happened, or the coach meant a different file. |
| 409 | `variant_label_taken` | Another variant of this válida already has that name. Ask for a different label, or confirm whether they meant to rename/replace the existing one instead of creating a new variant. |
| 409 | `variant_in_use` | Attempted delete of a variant referenced by at least one category setup; the response names the categories. Point the coach at the setups table to reassign those categories to a different variant first. |
| 422 | `variant_not_in_event` | A `PUT /course/setups` payload referenced a variant id from a different válida — almost always a stale client cache; a page reload before retrying usually resolves it. |
| 404 | `course_not_available` | Normal for a parent whose child has no relation (roster or results) to this válida — not a bug to escalate. |

A generic `{"detail": {"code": ..., "message": ...}}` body backs all of
these (same shape as the existing conditions `PATCH`); the `code` field is
what you match against this table, not the HTTP status alone (several codes
share a status).

### 10.3 Regenerating the golden-eval baseline after the course cases

Two new v3 golden cases ship with this feature —
`backend/evals/race_analyst/golden_v3/case_010_course_present.json` and
`case_011_course_absent.json`. They run through the exact same golden lane
as every other v3 case; there is no separate procedure for them. Follow the
existing regeneration steps in §3.3 ("Eval fails in CI") — run
`pytest tests/evals/test_race_analyst_eval.py -m golden` locally with a real
`RACE_AI_API_KEY`, inspect `evals/race_analyst/results/last_run.md`, and if
the divergence (now including these two new cases) is an intentional
prompt/weights change rather than a regression, update the stored baseline
and document it in the PR. As of this writing that real run — the one that
must confirm composite ≥ 0.75 with both new cases included and refresh the
baseline file — is still a **developer follow-up before this feature
merges**: it has not been executed in the implementation environment (no
`RACE_AI_API_KEY` available there; the eval module's own `_skip_no_api`
guard skips it silently rather than failing).
