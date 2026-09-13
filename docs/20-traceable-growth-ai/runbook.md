# Operational Runbook — traceable growth AI (feature 042)

> **Audience**: coach, admin, on-call.
> **Scope**: `backend/app/services/ai/anthro/` (the structured per-measurement / PHV
> pipeline) and the shared, stack-neutral factory it sits on
> (`backend/app/services/llm/factory.py`, `calls.py`, `pricing.py`, `observability.py`,
> `observability_metadata.py`). This is **not** a second copy of
> `docs/10-race-results/runbook-ops.md` §8/§9 — that document already covers bringing
> local Langfuse up, its bootstrap mechanics, and troubleshooting the compose stack in
> full; read it first if you have never done that. This runbook covers only what's
> specific to the growth-AI half of feature 042: which entry points actually produce a
> trace today, what `LANGFUSE_STRUCTURAL_METADATA` changes, the five persisted
> `critic_verdict` states and what a coach sees for each, rolling back the analysis
> prompt, and the golden-eval CI gate.

---

## 1. Turning local Langfuse on

### 1.1 One-time setup — shared with the race stack, no new compose file

Feature 042 added **no new Langfuse compose file or project**. It reuses the same
`docker-compose.langfuse.yml` / `docker-compose.langfuse.env` pair the race stack already
uses (`docs/10-race-results/runbook-ops.md` §8.2–§8.3) — one local Langfuse project,
one set of keys, shared by both AI stacks. If Langfuse isn't running locally yet, do the
one-time setup there, then come back here.

```bash
docker compose -f docker-compose.langfuse.yml --env-file docker-compose.langfuse.env up -d
curl http://localhost:3001/api/public/health
```

### 1.2 Variables, by name

| Variable | Default | Notes |
|---|---|---|
| `LANGFUSE_ENABLED` | `false` | Master switch, both stacks. |
| `LANGFUSE_BASE_URL` | `http://localhost:3001` | `http://host.docker.internal:3001` from a Dockerized backend. |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | `""` | Copied from `docker-compose.langfuse.env`'s `LANGFUSE_INIT_PROJECT_*` pair. |
| `LANGFUSE_STRUCTURAL_METADATA` | `false` | New in feature 042 — see §3. Independent of `LANGFUSE_ENABLED`; only meaningful when tracing is also on. |

Env vars are read at process start — restart the backend (`uvicorn` or the container)
after flipping any of these, they are not hot-reloaded.

### 1.3 What the UI shows

Open a trace at `http://localhost:3001/project/<project_id>/traces/<trace_id>` and expand
a `generation` node: model, provider, latency, and `usageDetails` (input/output/total
tokens) are populated. `input`/`output` on every node read `"[redacted]"` — that is
expected in every configuration, see §2.3.

### 1.4 Hard rule — production startup failure

`Settings` fails to start (the process never comes up, not a runtime warning) if any of
these three conditions hold in production. Each names the offending variable so the exact
Render log line tells you which one to unset:

| Condition | Exact validator message |
|---|---|
| `LANGFUSE_ENABLED=true` and `APP_ENV=production` | `LANGFUSE_ENABLED=true PROHIBIDO en producción (trazas solo en desarrollo local; privacidad de menores).` |
| `LANGFUSE_STRUCTURAL_METADATA=true` and `APP_ENV=production` | `LANGFUSE_STRUCTURAL_METADATA=true PROHIBIDO en producción (privacidad de menores).` |
| `claude-cli` is the **effective** provider of either stack in production (`AI_PROVIDER=claude-cli`, or `RACE_AI_PROVIDER` empty and `AI_PROVIDER=claude-cli`) | `AI_PROVIDER='claude-cli' PROHIBIDO en producción (...)` or `RACE_AI_PROVIDER='claude-cli' PROHIBIDO en producción (...)` |

Never set `LANGFUSE_ENABLED` or `LANGFUSE_STRUCTURAL_METADATA` on Render. There is no
override — this is a `model_validator`/`field_validator` on `Settings`, checked before the
app can serve a single request.

---

## 2. Reading a trace

### 2.1 The entry points that actually open a trace today — verified against the code, not the plan

Feature 042's plan describes seven `app/services/ai/` text generations moving onto one
LangChain transport: PHV explainer (family/coach), per-measurement analysis, session
assistant clarify/draft, monthly report + blocks, and family newsletter v2. **Only the
first two of those are wired for Langfuse tracing.** They run through
`app/services/ai/anthro/pipeline.py::run_analysis`, which opens exactly one
`llm_tracing(trace_name=f"anthro-{use_case}", ...)` span per pipeline run, covering
whichever of the analyst/critic/reanalysis LLM calls that run actually makes:

| Trace name | `use_case` value | Triggered from |
|---|---|---|
| `anthro-phv_explainer` | `phv_explainer` | PHV explanation, family audience |
| `anthro-phv_explanation_coach` | `phv_explanation_coach` | PHV explanation, coach audience |
| `anthro-anthropometric_record_analysis` | `anthropometric_record_analysis` | Per-measurement analysis, family audience |
| `anthro-anthropometric_record_explainer_coach` | `anthropometric_record_explainer_coach` | Per-measurement analysis, coach audience |

(`app/services/ai/anthro/eval/judge.py` opens a fifth, `anthro-eval-judge`, only while
running the golden eval — see §7.)

**The other five use cases — session assistant clarify, session assistant draft, monthly
report, monthly report blocks, family newsletter v2 — open no Langfuse span at all**,
even with `LANGFUSE_ENABLED=true` and even though they run through the same
`AI_USE_LANGCHAIN` adapter. They call `LangChainProvider.complete()`
(`app/services/ai/providers/langchain_provider.py`), whose own docstring states the
reason: *"Sin `config=`: los cinco casos de uso puenteados no tienen un scope de Langfuse
por-request que enhebrar hoy"* ("without `config=`: the five bridged use cases have no
per-request Langfuse scope to thread today"). If you go looking for a `session-clarify` or
`newsletter-v2` trace in the Langfuse UI, it will never appear — this is not a
misconfiguration to chase, it's how the adapter is currently built. If you need per-call
token/latency/model detail for one of those five, Langfuse cannot give it to you today —
use `athlete_ai_explanations` / the request log instead (§2.4).

The race stack's own three traces (`race-analysis`, `race-chat`, `race-eval-judge`) are
unrelated to this feature and are already documented in
`docs/10-race-results/runbook-ops.md` §8.5.

### 2.2 Tags and the keyed session id

Each `anthro-*` trace carries tags `use_case:<use_case>` and `audience:<family|coach>`,
and a session id from `observability.keyed_session_id(f"{use_case}:{athlete.id}:{target_record.id}")`
— an HMAC-SHA256 keyed by `settings.jwt_secret_key` (never the plain
`sha256`-truncated `anonymous_session_id` the race chat trace used before feature 042; that
helper is still used elsewhere but is enumerable by brute force and is not the one this
pipeline uses). It is stable across backend restarts by deliberate owner choice, so the
same athlete/record keeps grouping into the same Langfuse session across a redeploy — the
tradeoff being that anyone who can read both the Langfuse volume and `JWT_SECRET_KEY`
could recompute it; a per-process salt would be stronger but would break that grouping.

Coach- and admin-facing API responses (`GET .../phv-explanation`,
`GET .../measurements/{record_id}/explanation`) include a `trace_id` field taken straight
from the persisted `langfuse_trace_id` column — `null` for a parent viewer, and `null`
whenever `LANGFUSE_ENABLED=false` (there is nothing to link to). When it is present, jump
straight to `http://localhost:3001/project/<project_id>/traces/<trace_id>`.

### 2.3 What is NOT there — redact-always, in every configuration

`input` and `output` on every observation are **always** `"[redacted]"` — this is not a
switch, not affected by `LANGFUSE_STRUCTURAL_METADATA`, and true in every environment
tracing can legally run in (local only). You cannot read the analyst's prompt, the
athlete's context block, the critic's verdict text, or the rendered analysis from a
trace — ever. What a trace *does* show: token counts (`usageDetails`: input/output/total),
model, provider, latency per call, the trace name/tags/session id above, and — only with
`LANGFUSE_STRUCTURAL_METADATA=true` — the closed set of operational fields in §3. A trace
tells you a call happened, how long it took, roughly what it cost, and which
`critic_verdict` it produced; it never tells you what was said.

### 2.4 What to use instead when you need more

The audit trail of record for this feature is the row itself, in
`athlete_ai_explanations`:

```sql
SELECT
  use_case, audience, schema_version, critic_verdict, prompt_version,
  tokens_in, tokens_out, cost_usd, latency_ms, langfuse_trace_id, generated_at
FROM athlete_ai_explanations
WHERE athlete_id = <ID> AND anthropometric_record_id = <ID>
ORDER BY generated_at DESC;
```

`structured_json` holds the full `AnthropometryInsightV1` payload (summary, changes,
meaning, next steps, warning signs, confidence, data gaps) — that is where you read what
the model actually said, not Langfuse.

---

## 3. `LANGFUSE_STRUCTURAL_METADATA`

Off by default, and — like `LANGFUSE_ENABLED` — a hard production startup failure when
on (§1.4). It does **not** touch `input`/`output` (still always redacted, §2.3); it only
lets one specific, closed set of fields travel on the `metadata` channel of a trace,
via a marker type (`observability_metadata.py::StructuralMetadata`) whose constructor
rejects — raises, does not silently drop — any key outside the allow-list:

```
athlete_id_hash, record_id_hash, user_id_hash, club_id,
delta_height_significant, delta_weight_significant,
weeks_since_prev_measurement_bucket, num_previous_measurements_bucket,
guardrail_rule_ids, guardrail_scrub_count,
precheck_rule_ids, precheck_violation_count,
critic_verdict, cache_outcome, use_case, model, provider, prompt_version, role,
tokens_in, tokens_out, tokens_total, latency_ms, cost_usd
```

Every identifier in that list is a **keyed hash**, never a raw id. Notably absent —
deliberately, per the feature's privacy audit — are `sex`, `age_group`,
`maturation_status`, `category`, any PHV offset/phase, and any raw delta magnitude: for a
club of ~20 minors, `sex × age_group` alone already produces a mean equivalence-class size
of 5 (the same threshold `monthly_report.py` treats as unsafe), and no rounding or
bucketing rescues those fields as trace metadata at this club's size. A second,
independent rule inside `StructuralMetadata` blocks two or more of
`sex`/`age_group`/`maturation_status`/`category` from ever traveling together, so a future
PR that adds one of them in isolation cannot silently combine it with another. **Do not
add a key to this list without rereading `contracts/trace-metadata-allowlist.md` in full**
— the short list is the point, not an oversight to "complete."

**Restated explicitly, because it is easy to assume otherwise**: turning this flag on
changes nothing about *retention*. It only widens what the `metadata` channel of an
already-created trace may carry; the traces themselves still live in the same
unbounded, un-purged local Docker volumes described in §6, for exactly as long as they
did before. There is no separate retention policy for structural-metadata traces versus
plain ones.

---

## 4. Operational signals — reading `critic_verdict`

Five values are ever persisted to `athlete_ai_explanations.critic_verdict`. Only
`approved` and `revised` are ever shown to a family — the other three are filtered to a
parent exactly like "no analysis yet" (`204` on the GET endpoints, `null`
`latest_ai_analysis` on the growth summary) at three independent backend layers, so a
family literally never receives the marker copy below.

| `critic_verdict` | What happened | Coach sees | Family sees |
|---|---|---|---|
| `approved` | The critic reviewed the analyst's draft and found nothing to change. (If prechecks flagged a non-blocking style/data issue, confidence is forced to `"low"` but the verdict stays `approved`.) | The structured card, no marker. | Full analysis. |
| `revised` | The critic found only mechanical issues (tone, minor privacy phrasing) and adopted its own rewrite directly — no second analyst call. | The structured card (the critic's rewrite), no marker. | Full analysis (the critic's rewrite). |
| `flagged` | The critic reviewed the draft and **objected** to it (`verdict="reject"`) — something substantive, not mechanical. The analyst is **not** re-invoked for a `reject` (only a `revise` verdict spends the one allowed reanalysis). The row still stores the analyst's *original, unmodified* draft. | *"Con observaciones — revisa el contenido antes de compartirlo con la familia."* | Nothing — treated as "no analysis yet." |
| `fallback` | Either (a) the analyst failed twice in a row (bad/unparseable JSON, timeout), or (b) the analyst's draft hit a `must_block` precheck rule (e.g. a forbidden name, a leaked diagnostic label). In both cases the critic is **never called** — spending that call could not change the outcome — and a deterministic, non-LLM template insight is persisted instead. | *"Análisis de respaldo — el modelo de IA no respondió a tiempo. La familia no lo verá hasta que regeneres uno aprobado."* | Nothing. |
| `skipped` | The analyst succeeded, but the **critic call itself** failed, timed out, or returned unparseable JSON. The analyst's draft is still used, with confidence forced to `"low"`. | *"Sin revisión — el control de calidad no se ejecutó."* | Nothing. |

**Answering "why does this say Con observaciones?"**: it means an LLM critic reviewed the
draft and rejected it — not that something crashed. The product does not surface *why*
today: `critic_violations` (the critic's `problem`/`suggested_fix` text) is used to build
the reanalysis prompt on a `revise` verdict, but for a `reject` verdict it is discarded —
never persisted, never logged, never returned by any endpoint. There is currently no way,
in the app or in Langfuse (content is always redacted, §2.3), to see the specific
objection after the fact. The only remedy is to regenerate; if the new run comes back
`approved`/`revised` it overwrites the flagged row and becomes deliverable.

One caveat worth flagging to support: the `fallback` marker's copy ("no respondió a
tiempo") reads as if it's always a timeout, but as the table above shows it is also used
for a `must_block` precheck violation on a draft that *did* come back from the model. The
two causes are distinguishable only in Render logs at the moment of generation
(`anthro.pipeline: analista falló para use_case=%s; usando fallback` for a genuine analyst
failure vs. no matching log line for a precheck block) — not from the persisted row alone.

---

## 5. Rolling the analysis prompt version back

`AI_ANTHRO_PROMPT_VERSION` (default `anthropometry_analyst_v1`) selects which prompt
template `analyst.run_analyst` renders. **Today its validator accepts exactly one value**
— `{"anthropometry_analyst_v1"}` — so there is nothing to roll back *to* yet; the variable
exists as the rollback lever for the day a `v2` prompt ships, at which point
`Settings.validate_ai_anthro_prompt_version`'s allow-list grows by that one entry (per its
own comment: *"crece de a una entrada por revisión de prompt publicada"*). Setting any
value other than the currently-allowed set today is a hard startup failure:
`AI_ANTHRO_PROMPT_VERSION='<value>' inválido. Permitidos: ['anthropometry_analyst_v1'].`

When a rollback is available: change the variable and restart (Render redeploy, or
restart `uvicorn` locally — read at process start, not hot-reloaded). **`prompt_version`
is stamped per row, at generation time, into `athlete_ai_explanations.prompt_version`** —
a rollback only changes what *new* generations use. It never retroactively relabels rows
already persisted under the previous prompt version; a query grouped by
`prompt_version` (same shape as the race runbook's `by_prompt_version` breakdown) is the
only reliable way to tell which rows ran under which prompt.

This is independent of the race stack's own `RACE_AI_PROMPT_VERSION` (which does have a
live `v2`/`v3` choice today, see `docs/10-race-results/runbook-ops.md`) — the two
variables control two different prompts on two different stacks; do not conflate them.

---

## 6. Purge cadence for local trace data

Langfuse's local Docker volumes (`langfuse_postgres_data`, `langfuse_clickhouse_data`,
`langfuse_clickhouse_logs`, `langfuse_redis_data`, `langfuse_minio_data`) have **no
built-in retention policy** — traces accumulate indefinitely until someone purges them
manually. Because this stack is local-only and never touches production data, there is no
compliance-driven purge SLA; treat it as ordinary dev-machine hygiene:

- **Recommended cadence**: purge whenever you are done with a debugging session that
  needed real trace content, and at minimum monthly on a machine that runs the backend
  with `LANGFUSE_ENABLED=true` regularly.
- **Purge everything** (stop + wipe volumes):

  ```bash
  docker compose -f docker-compose.langfuse.yml down -v
  ```

- **Stop without losing history** (e.g. between work sessions, keep the trace archive):

  ```bash
  docker compose -f docker-compose.langfuse.yml down
  ```

There is no per-trace or per-age deletion tool in this setup — it is all-or-nothing via
`-v`. If you need to keep a specific trace's evidence before purging (e.g. for a bug
report), copy the token/latency numbers out of the UI or export the trace first; nothing
survives `down -v`.

---

## 7. When the anthropometry golden eval fails in CI

`.github/workflows/anthropometry-eval.yml` runs on any PR touching
`backend/app/services/ai/anthro/**`, `backend/app/services/llm/**`, or the eval fixtures
themselves, plus on manual `workflow_dispatch`. It is deliberately independent of the race
stack's own eval gate (`race-eval.yml`) in every dimension that could couple them — its
own workflow, its own `AI_API_KEY` secret (never `RACE_AI_API_KEY`), its own `AI_*`
env vars (never `RACE_AI_*`) — so a regression in one prompt can never redden the other
gate.

### 7.1 The one blocker nobody has cleared yet

The job needs a GitHub Actions secret named **`AI_API_KEY`**, separate from the
pre-existing `RACE_AI_API_KEY`. Nobody has added it. Until a repo admin does, every run of
this workflow hard-fails at the same step with an explicit message, not a silent skip:

```
::error::AI_API_KEY no configurado en secrets de GitHub.
```

(exit code 1, before the eval even starts). If this workflow is red, check this first —
it is very likely the only reason, not a real regression.

### 7.2 Once the secret exists and the job actually runs

1. Threshold is `composite_score >= 0.75` per case (rule-based score weighted 0.4, LLM
   judge weighted 0.6 — same formula shape as the race eval, independent scorer). Any case
   below threshold fails the job.
2. Download the `anthropometry-eval-scoreboard-<run_id>` artifact
   (`backend/evals/anthropometry_analyst/results/last_run.md`) to see which golden cases
   diverged and by how much.
3. **Compare against `backend/evals/anthropometry_analyst/baseline.json` with the caveat
   that this baseline is itself a placeholder** — `"status": "PLACEHOLDER"`, generated
   without a real model key, with judge scores estimated at a flat conservative 0.70. It is
   not yet a real measured baseline; treat a small divergence from it as far less
   meaningful than the same divergence would be against a real baseline. The file embeds
   its own regeneration command:

   ```bash
   AI_API_KEY=$your_key pytest backend/tests/evals/test_anthropometry_analyst_eval.py \
     -m golden -k anthropometry -v
   ```

   Whoever regenerates it for real should replace the placeholder `avg_composite_score`/
   `avg_rule_score`/`avg_judge_score`/`per_case` fields with the actual scoreboard output,
   and drop the `"status": "PLACEHOLDER"` marker.
4. **Mitigation**, same order of preference as the race eval's playbook
   (`docs/10-race-results/runbook-ops.md` §3.3): if the divergence is an intentional
   improvement, update the baseline and say so in the PR; if it's a regression, revert the
   prompt/pipeline change or fix it before merging — this gate is blocking, not advisory.

### 7.3 Reproducing locally

```bash
cd backend
source .venv/bin/activate
export AI_API_KEY=<your key>          # or GOOGLE_API_KEY — never RACE_AI_API_KEY
export AI_PROVIDER=google
export AI_ANTHRO_PROMPT_VERSION=anthropometry_analyst_v1
pytest tests/evals/test_anthropometry_analyst_eval.py -m golden -k anthropometry -v
```

Without a real key configured, this suite does not fail — it **skips**, explicitly, with:

```
AI_API_KEY (o GOOGLE_API_KEY) no configurada — el juez del eval de antropometría (stack
app, nunca RACE_AI_*) no puede invocar un modelo real. Ver
specs/042-traceable-growth-ai/spec.md, edge case: "the developer runs the golden
evaluation without a real model key".
```

That is the same behavior `pytest -m golden` shows for every golden suite in this repo
today (35 skipped, each with an explicit reason — never a silent pass): a green local run
with no key configured proves nothing about prompt quality, only that the harness itself
is wired correctly.

---

## 8. Quick reference — settings this runbook covers

| Variable | Default | Stack | Production behavior |
|---|---|---|---|
| `AI_USE_LANGCHAIN` | `true` | app | Roll-back switch only — flipping to `false` restores the pre-042 native SDK providers for the five legacy use cases; the `anthro/` pipeline does not read this flag at all (it always calls the shared factory directly). |
| `AI_ANALYST_MODEL` / `AI_CRITIC_MODEL` | `""` (falls to `AI_MODEL`, then the provider default) | app | Per-role model override for the `anthro/` pipeline only — do not confuse with `RACE_AI_ANALYST_MODEL`/`RACE_AI_CRITIC_MODEL` on the race stack. |
| `AI_ANTHRO_PROMPT_VERSION` | `anthropometry_analyst_v1` | app | See §5 — only one legal value exists today. |
| `RACE_AI_TEMPERATURE` | `0.4` | race | Unrelated to this feature's own pipeline, which never sends `temperature` to Anthropic/claude-cli builders (§ builder docstrings — 4.6+ rejects non-default sampling params with a 400). |
| `LANGFUSE_ENABLED` | `false` | both | Hard production startup failure — §1.4. |
| `LANGFUSE_STRUCTURAL_METADATA` | `false` | both | Hard production startup failure — §1.4, §3. |
