# Runbook v2 — agentic race-analyst (operation, retention)

> **Audience**: coach, admin, on-call.
> **Scope**: operational cap, Gemini quota monitoring, rollback via redeploy
> and 180d retention job post `deprecated_at`.
> Complements the operational runbook `runbook-ops.md` (live alerts/metrics).

---

## 1. Activation and operation

v2 is **always active** (no feature flag). The only gate is `AI_ENABLED`
(already existing for all AI modules).

Operational cap (agreed with engineering-lead):

- Maximum **4 rounds/run** -> up to **12 LLM calls + 1 season summary** per analysis.
- Frames expected cost and allows projecting Gemini quota.

### Emergency rollback

Trigger: 5xx error > 5% on v2 endpoints, Gemini cost spike, PII leak.

- Render Dashboard -> **Deploys** tab -> click on the
  previous stable deploy -> **Redeploy**. Restores the binary without waiting for build.
- To disable AI in general (includes v1 and v2): set `AI_ENABLED=false`
  in Environment -> Save -> auto-redeploy (~3-5 min).
- After rollback, document incident in `docs/10-race-results/` and notify
  engineering-lead.

> Rollback does **not** delete rows in `athlete_ai_insights`. If a published
> row is problematic, mark `archived_at = NOW()` from MySQL
> (same procedure as `runbook-ops.md` section 3.5).

---

## 2. Gemini quota monitoring

### 2.1 Where to look

- Google AI Studio dashboard: <https://aistudio.google.com/app/apikey>
  -> select the project API key -> "Usage".
- Filter by model `gemini-2.5-flash-lite` (it is the only one used by the
  race-analyst v2 module; any consumption from another model is anomalous).

### 2.2 Gemini free tier limits (reference)

| Model | RPM | RPD | Tokens/day |
|---|---|---|---|
| `gemini-2.5-flash-lite` | 15 | 1500 | 1M |

> Values from the console at 2026-05-25. **Confirm in console before
> sizing** because Google periodically adjusts quotas.

### 2.3 Estimate vs operational cap

- 1 complete analysis = max 12 + 1 = **13 calls**.
- With 1500 theoretical free RPD, that is **~115 analyses/day** before
  hitting the free tier limit.
- **The practical gate is the budget guard** (`RACE_AI_BUDGET_USD_30D`,
  see `runbook-ops.md` section 3.4), not the Gemini quota per se.

### 2.4 Operational alert: 80% of quota

**Trigger**: daily consumption exceeds **1200 calls / day** (80% of 1500
in free tier) **for 2 consecutive days**.

**Action**:

1. Review `/ai-usage` (drill-down by `prompt_version`) — see if there is a
   regression or new feature consuming more.
2. Temporary cap: lower `RACE_AI_BUDGET_USD_30D` to slow down new
   executions, or reduce canary allowlist.
3. If consumption is legitimate and sustained: **migration plan to paid Gemini tier**
   ("Pay-as-you-go") — coordinate with engineering-lead. The change
   is done in Google Cloud Console; the existing API key works,
   only billing changes.
4. Post-migration, raise `AI_MAX_TOKENS` if needed and document
   new unit cost in `runbook-ops.md` section 3.4.

### 2.5 Quick manual polling

```bash
curl -H "Authorization: Bearer $ADMIN_JWT" \
  "https://mi-2yzi.onrender.com/api/race-analysis/admin/ai-usage?days=7"
```

If `run_count` x 13 calls/day approaches 1200, alert.

---

## 3. 180d retention post `deprecated_at`

### 3.1 Policy

- Rows in `athlete_ai_insights` with `deprecated_at` (insight superseded
  by a more recent version) retain their content for **180 days**
  for auditing.
- After 180 days the script `retention_ai_insights.py` redacts the
  `summary_text` field and marks `pii_scrubbed_at = NOW()` (idempotent: already-scrubbed rows are ignored).
- Rows are **not deleted** — records of "what was published and
  when" remain, with their textual content obfuscated.

### 3.2 Script

`backend/scripts/retention_ai_insights.py` (Typer CLI).

**Dry-run (default, safe)**:

```bash
cd backend
source .venv/bin/activate
python -m scripts.retention_ai_insights
```

Prints table of rows that would be redacted (without executing UPDATE).

**Apply**:

```bash
python -m scripts.retention_ai_insights --apply
```

Idempotent: filters by `pii_scrubbed_at IS NULL`, so running it twice
does not double-redact.

**Override threshold (debugging)**:

```bash
# Force 90d instead of 180d (internal use, not operational):
python -m scripts.retention_ai_insights --days 90 --apply
```

### 3.3 Scheduling (Render Free has no native cron)

Render Free tier does not expose cron jobs. Three options, in order of
operational preference:

**A. GitHub Actions schedule (recommended)**

Workflow `.github/workflows/retention-cron.yml` with `schedule: cron: '0 5 1 * *'`
(monthly, first day 05:00 UTC) that:

1. Checkout the repo.
2. Setup Python + venv.
3. Reads secret `DATABASE_URL` from GitHub Secrets.
4. Runs `python -m scripts.retention_ai_insights --apply`.

> To be defined when engineering-lead approves the workflow. Requires
> adding `MYSQL_*` or `DATABASE_URL` as GitHub Secrets.

**B. Protected admin endpoint**

Expose `POST /api/race-analysis/admin/retention/run` (RBAC admin)
that imports the script as a function. Triggered from external cron
(cron-job.org, uptime monitor). Advantage: does not expose DB credentials
outside Render. Disadvantage: requires additional backend development.

**C. Monthly manual**

Coach or devops runs the script from their machine with production
credentials from the .env on the first day of each month. Acceptable as a
bridge until A or B are implemented. Log each run in a notes file.

### 3.4 Post-run validation

```sql
-- Eligible rows that have not yet been scrubbed (should be 0
-- immediately after --apply):
SELECT COUNT(*)
FROM athlete_ai_insights
WHERE deprecated_at < NOW() - INTERVAL 180 DAY
  AND pii_scrubbed_at IS NULL;

-- Recently scrubbed rows (verifies the job ran):
SELECT id, athlete_id, deprecated_at, pii_scrubbed_at
FROM athlete_ai_insights
WHERE pii_scrubbed_at >= NOW() - INTERVAL 1 DAY
ORDER BY pii_scrubbed_at DESC
LIMIT 20;
```

---

## 4. Quick checklist by situation

| Situation | Steps |
|---|---|
| Activate v2 for 1 canary athlete | Env -> `V2_ENABLED=true`, `V2_ATHLETE_ALLOWLIST=<id>` -> Save -> smoke -> notify coach |
| Remove athlete from canary | Edit CSV in `V2_ATHLETE_ALLOWLIST` removing the id -> Save |
| Emergency rollback | `V2_ENABLED=false` or redeploy of previous stable deploy |
| Gemini quota 80% | Review `/ai-usage`, lower `RACE_AI_BUDGET_USD_30D`, plan migration to paid tier |
| Monthly retention | `python -m scripts.retention_ai_insights --apply` (or wait for cron) |
| PII leak | See `runbook-ops.md` section 3.5 — separate protocol |

---

## 5. References

- `runbook-ops.md` — alerts, queries and general procedures.
- `v2-agentic-design.md` — technical design of the LangGraph pipeline.
- `backend/scripts/retention_ai_insights.py` — retention script.
- `backend/app/models/athlete_ai_insight.py` — model with
  `deprecated_at`, `pii_scrubbed_at`, `summary_text`.
- Google AI Studio: <https://aistudio.google.com/app/apikey>.
