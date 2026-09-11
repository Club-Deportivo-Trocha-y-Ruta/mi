# Quickstart — validating feature 042 (traceable growth AI)

**Feature**: `specs/042-traceable-growth-ai/` · **Branch**: `feat/042-traceable-growth-ai`

This is the **validation** guide, not an implementation guide. The structured insight's fields,
the nine accounting columns, the trace tag set and the allow-listed metadata keys are fixed in
[`spec.md`](spec.md) and in the binding lead decisions the planning artifacts encode; nothing is
re-derived here. This document only says **what to run, in what order, and what proves each user
story done**. Where a contract or data-model file is still being written alongside this one, the
scenario points at the spec requirement (`FR-###`) instead of a file path — pin the exact
fixture/schema names against `data-model.md` and `contracts/` once they land, and treat any name
below as illustrative of the convention, not a frozen path.

Three rules apply while running it:

- **No secrets in the transcript.** Never open, print or paste `.env`, `.env.production` or any
  credential file. Refer to variables by name only — `AI_API_KEY`, `AI_ANALYST_MODEL`,
  `LANGFUSE_SECRET_KEY`, `JWT_SECRET_KEY`, `TEST_DATABASE_URL` — never by value, including in shell
  history you paste into a report.
- **No minor's data in the transcript.** Every scenario below is written as fields, counts and
  synthetic identifiers, never as a real athlete's name, birth date or measurement. Use only the
  club's own synthetic fixtures (`AthleteFactory`-style pytest builders, or the seeded demo
  athlete resolved by `frontend/e2e/helpers/demo-athlete.ts` — never a hand-picked real athlete id).
- **Structured insights are minors' data too.** A generated `qué_cambió` / `qué_significa` string is
  exactly as sensitive as the free prose it replaces — never paste one into a bug report or commit
  message; describe it by field name and word count instead ("summary_line was 132 chars, within
  budget").

---

## 1. Prerequisites

### 1.1 Backend

```bash
cd backend && source .venv/bin/activate
```

Invoke pytest as `.venv/bin/python -m pytest` (the `pytest` shim on `PATH` is broken in this
environment — same note as `specs/041-multi-coach-governance/quickstart.md`).

| Lane | Command | Notes |
|---|---|---|
| default (offline) | `.venv/bin/python -m pytest` | `FakeLLMProvider` / `GenericFakeChatModel`, aiosqlite in memory, `LANGFUSE_ENABLED=false` and `AI_PROVIDER=google` / `RACE_AI_PROVIDER=""` pinned by `conftest.py` before the app import — no network reached unless a test opts in (FR-038). |
| `mysql` (opt-in) | `TEST_DATABASE_URL="mysql+aiomysql://<user>:<pass>@127.0.0.1:3306/<name>_test" .venv/bin/python -m pytest -m mysql` | Database name **must** end in `_test` (`tests/conftest.py` guard). Needed for the nine new `athlete_ai_explanations` columns and any dialect-specific `on_duplicate_key_update` overwrite test — the default lane runs aiosqlite and cannot exercise those. |
| `golden` (opt-in, blocking in CI) | `.venv/bin/python -m pytest -m golden` | Runs **both** the race analyst golden eval and the anthropometry golden eval — they share the existing `golden` marker (no new marker is introduced). Needs a real `AI_API_KEY`/`RACE_AI_API_KEY`; skip with an explicit reason if absent, never silently pass (spec Edge Cases). Filter to one: `pytest -m golden -k anthropometry` or `pytest -m golden -k race`. |
| `integration` (opt-in) | `.venv/bin/python -m pytest -m integration` | Unaffected by this feature; re-run only if a shared-factory change (wave 1) touches a real provider builder. |
| migration | `alembic upgrade head` | One new revision, `down_revision = 45cd705c6b54` (current head). `CLAUDE.md`'s Alembic-head line is corrected to name this new revision as part of wave 4 (FR-037). |

**Provider config for local runs** — set by name, never by pasting a key:

| Variable | Values relevant here | Notes |
|---|---|---|
| `AI_PROVIDER` | `google` (default), `anthropic`, `openai`, `claude-cli`, `fake` | `claude-cli` drives the actual Claude Code CLI via the developer's own subscription login — **local-only**; a `Settings` validator now hard-fails startup if `AI_PROVIDER` (or the race stack's effective provider) is `claude-cli` and `APP_ENV=production` (scenario 6, FR-037). |
| `AI_USE_LANGCHAIN` | `true` (default) / `false` | Routes the five migrated use cases (session assistant clarify + draft, monthly report, monthly report blocks, family newsletter) through the new LangChain adapter or the previous SDK-provider path. Run the default offline lane once with each value (scenario 1). |
| `AI_ANALYST_MODEL` / `AI_CRITIC_MODEL` | `""` (default, falls back to `AI_MODEL`) | Per-role models for the anthropometry pipeline's two LLM calls. |
| `AI_ANTHRO_PROMPT_VERSION` | `anthropometry_analyst_v1` (default) | Selects the anthropometry analyst/critic prompt pair; bump to roll a new prompt without touching code. |
| `LANGFUSE_ENABLED` / `LANGFUSE_STRUCTURAL_METADATA` | both `false` by default, both **hard-forbidden** when `APP_ENV=production` | See §1.4 and scenario 6. |

### 1.2 Frontend

```bash
cd frontend && npm ci && npm run typecheck
```

### 1.3 Dev stack (needed for the modal, the tab and any manual scenario)

`docker compose up` → API on `:8000`, MySQL on `:3306`, MailHog UI on `http://localhost:8025`.
WeasyPrint on macOS needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (unaffected by this
feature, listed for completeness since scenario 10 touches the same dev stack).

### 1.4 Local Langfuse tracing

Full setup is `docs/10-race-results/runbook-ops.md` §8 — do not duplicate it here, just the delta
this feature adds:

```bash
cp docker-compose.langfuse.env.example docker-compose.langfuse.env   # if not already done
docker compose -f docker-compose.langfuse.yml --env-file docker-compose.langfuse.env up -d
curl http://localhost:3001/api/public/health
```

Set `LANGFUSE_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` in the backend's own
`.env` from the pair `docker-compose.langfuse.env` bootstraps, then restart the backend — these are
read at process start, not hot-reloaded. `LANGFUSE_STRUCTURAL_METADATA=true` is the new,
independent second switch (default `false`) for scenario 5's allow-listed fields; it does not
enable content capture — inputs, outputs and prompts are **always** `"[redacted]"`, on every trace,
regardless of either switch (runbook §8.6, FR-018).

After this feature, §8.5's "what is traced" table gains four new trace names beyond the three race
ones (`race-analysis`, `race-chat`, `race-eval-judge`): one for the anthropometry analysis, one for
the PHV explanation, one for the session assistant (clarify + draft as two steps of one trace, or
two traces — confirm against the shipped contract), one shared name covering the monthly report and
its blocks, and one for the family newsletter — seven traced entry points in total once wave 3
lands (FR-017). Wave 4 updates the runbook table; until then, treat the table above as the
authoritative list of what to expect.

### 1.5 Synthetic fixtures

No hand-picked real athlete. Backend tests build synthetic athletes and measurement series with the
existing pytest factories; manual/Playwright scenarios use the seeded demo athlete resolved by
`frontend/e2e/helpers/demo-athlete.ts` (lowest-id seeded athlete with measurements) — never an id
typed in from memory.

---

## 2. Command index

### 2.1 Backend, by wave (waves are disjoint by file ownership — `architecture.md` §11.7)

| Wave | Command |
|---|---|
| W1 — shared factory, adapter, tracing, config | `.venv/bin/python -m pytest tests/services/llm tests/test_ai_providers.py tests/test_ai_factory.py tests/test_ai_config.py -q` plus `pytest -m golden -k race` (zero behavioural diff on the race analyst) |
| W2 — anthropometry v2 pipeline, cache columns, modal renderer | `.venv/bin/python -m pytest tests/services/ai/anthro tests/test_ai_record_explainer.py tests/test_ai_phv_explainer.py tests/routers/test_ai_record_router.py -q` plus `pytest -m golden -k anthropometry` and `pytest -m mysql -k explanation` |
| W3 — migrated use cases behind the switch, growth summary field, `GrowthTab` line | `.venv/bin/python -m pytest tests/test_ai_monthly_report.py tests/test_ai_use_cases_concurrency.py tests/routers/test_growth_summary.py -q` with `AI_USE_LANGCHAIN` set to each of `true`/`false` |
| W4 — docs | no test gate; `docs/20-traceable-growth-ai/{design.md,qa.md,runbook.md}` exist, `CLAUDE.md`'s Alembic-head line and env-var list are current |
| whole suite | `.venv/bin/python -m pytest -q` · lint: `ruff check` |

### 2.2 Frontend

```bash
npx vitest run src/components/athletes/growth src/schemas/ai.schemas.test.ts src/hooks/ai
npx vitest run -t "a11y"          # jest-axe: the measurement modal's AI card, GrowthTab
npm run typecheck && npm run build
npx playwright test e2e/growth.spec.ts e2e/anthropometry.spec.ts
```

---

## 3. Scenarios

Run in order; each states its steps, the expected result and the success criterion it discharges.

### Scenario 1 — The offline lane stays green under both transports (US2 · SC-006, FR-025, FR-038)

```bash
.venv/bin/python -m pytest -q                              # AI_USE_LANGCHAIN default (true)
AI_USE_LANGCHAIN=false .venv/bin/python -m pytest -q       # previous SDK-provider path
```

**Expected**: both runs are green, no network reached, and the five migrated use cases (session
assistant clarify/draft, monthly report, monthly report blocks, family newsletter) produce
byte-identical outputs against the fake model in both runs — their existing test files are
unmodified by this feature and pass under either flag value (SC-006). `FakeLLMProvider.last_request`
still exposes the rendered prompt, so the ~40 existing privacy assertions
(`test_pii_never_reaches_llm`, `test_coach_audience_user_message_has_no_pii`, …) keep working
unchanged (FR-038).

---

### Scenario 2 — A structured, grounded reading for one measurement (US1 · SC-002, SC-003, SC-008)

Seed a synthetic athlete with, in three separate runs: (a) one measurement, (b) two measurements 10
weeks apart, (c) two measurements 30 weeks apart with a height delta above instrument noise. With
`AI_ENABLED=true` and `AI_PROVIDER=fake` (or `google` against a stubbed model), request the analysis
for the latest measurement (coach audience, then family audience — the endpoint mirrors the
existing `audience` query parameter already on `GET/POST /athletes/{id}/phv-explanation`; confirm
the exact parameter name against the shipped contract).

**Expected**

- (a) The stored insight declares the baseline in `data_gaps` (no previous measurement, no velocity)
  and states nothing about trend; `confidence` reflects the missing history.
- (b) `velocity_confidence = "early_signal"`; the text never calls the velocity typical, high or low
  for the stage (FR-004).
- (c) `velocity_confidence = "reliable"`; the velocity is classified against the growth summary's
  `expected_velocity_range_cm_year`, and a value above the upper bound reads "por encima de lo
  típico", never with alarming language (FR-007).
- In every case: `summary_line` ≤ 140 chars, `changes` (1–4), `meaning` (1–4), `next_weeks` (1–3),
  `warning_signs` (0–2), `data_gaps` (0–3), each item plain prose with no Markdown; `confidence.level`
  ∈ {high, medium, low} with a `reason` ≤ 200 chars (FR-001). Coach text ≤ 110 words, family text
  ≤ 180 words, español neutro, "su hijo/hija" in family text and "tu deportista" in coach text
  (FR-002).
- The family response contains no number besides significant height/weight deltas — no cm/year, no
  months to PHV (US3 AC1).
- Regenerating on the same record a second time produces a `summary_line` that differs from the
  first — continuity, not repetition (FR-010, acceptance scenario 9 of US1).
- **In the UI**: open the measurement dialog as coach — `summary_line` and any warning signs are
  visible collapsed; "Ver análisis completo" (`aria-expanded`, `aria-controls`) reveals `meaning` and
  `next_weeks`; the family read-only card shows only the collapsed teaser plus the neutral
  provenance line, no model/provider name (FR-026, FR-029).
- **Timing (SC-008)**: the coach-audience call completes within 45 s at the 95th percentile with the
  configured models; opening the Crecimiento tab fires no extra request beyond the existing
  `growth-summary` call.

**Automated equivalent**: the anthropometry pipeline's node/graph tests (per-node `state -> dict`,
happy path, analyst-failure fallback), the golden eval's grounding and uncertainty-calibration cases
(sub-8-week, 10-week, 30-week, age-edge), and the frontend renderer's discriminated-union tests.

---

### Scenario 3 — A flagged draft never reaches a family (US1 AS6, US3 · SC-002, SC-004, FR-013, FR-016)

With a fake model configured to return a draft containing a population comparison (or any rule from
the deterministic-check catalogue that blocks delivery outright — FR-011), request the coach
analysis for a synthetic measurement.

**Expected**

- The deterministic check blocks the draft before persistence; the single allowed revision attempt
  either produces an approved rewrite or, failing that, the deterministic fallback text is stored
  with `confidence.level = "low"` and a fallback flag (FR-013).
- If the stored verdict ends as `flagged`, `rejected`-and-unrevised, or `fallback`: the **coach**
  sees the analysis marked "Con observaciones" and can regenerate (FR-016); the **family** card and
  the Crecimiento-tab summary line both show the shared placeholder — "Aún no hay análisis disponible
  para esta medición. El entrenador lo generará pronto." — and nothing else from the AI (US3 AS2).
- `GrowthSummaryOut.latest_ai_analysis` is `null` for the parent's request in this state — verify by
  calling `GET /api/athletes/{id}/growth-summary` with the parent's token and asserting the field is
  absent/null, not merely hidden client-side (decision: null "when consent absent, AI disabled, or
  nothing approved/revised for the family audience").
- Repeat with the PHV explanation card in parent mode with no cached content: it shows the **same**
  passive message as the measurement card, not a blank state (US3 AS3).

**Automated equivalent**: the guardrail-rejection graph-integration test, the RBAC/audience-filter
tests on the growth-summary and explanation endpoints, and the frontend's shared-placeholder test on
both read-only AI cards.

---

### Scenario 4 — Staleness is a server fact, not a guess (US4 · SC-005, FR-027)

1. Generate an analysis for a synthetic athlete's latest measurement. Confirm the Crecimiento tab's
   summary line reads current (no "Desactualizado"), with the measurement date and a working link
   into that record's dialog.
2. **Correct** that same measurement (edit height or weight) after generation. Reload the tab:
   the line now reads "Desactualizado", the previous summary stays visible in a muted style, and
   `latest_ai_analysis.is_stale = true` because `record.updated_at > generated_at`.
3. Instead (or in addition), add a **newer** measurement without generating its analysis. Reload:
   the line is still "Desactualizado", now because a newer measurement exists than the one analysed.
4. Confirm any history row whose analysis has at least one warning sign shows the "Con señal para
   revisar" marker, on desktop and mobile widths, and rows without a warning sign show none (FR-028).
5. In family mode, repeat step 2/3: no "Desactualizado" wording appears; the summary line keeps
   showing the older analysis with its own honest date, and no link renders when there is nothing to
   open (US4 acceptance scenario 2, family variant).

**Automated equivalent**: the growth-summary service test computing `is_stale`, and a `GrowthTab` /
`LatestAnalysisLine` component test asserting the badge and the muted-style fallback.

---

### Scenario 5 — Every generation traces once, redacted, with the right tags (US2 · SC-001, FR-017…FR-021)

With the local Langfuse stack up (§1.4) and `LANGFUSE_ENABLED=true`, `AI_USE_LANGCHAIN=true`, run
each of the seven traced use cases once against a synthetic athlete: the per-measurement analysis,
the PHV explanation, the session assistant's clarify step, the session assistant's draft step, the
monthly report, one monthly-report block, and the family newsletter.

**Expected**

- Exactly **one trace per generation** appears in the Langfuse UI, named for its use case, with steps
  for context preparation, each model call, review (where applicable) and persistence.
- Every input/output/metadata payload on every observation reads `"[redacted]"` — confirm by opening
  each trace, not by trusting the switch (FR-018).
- Tags are limited to generation name, audience (where applicable), prompt version, provider and
  model; no numeric score carries text (FR-019).
- The session identifier is a 16-hex-character string (HMAC-SHA256 of the real session id, keyed
  from `JWT_SECRET_KEY` with a domain separator) — same construction the race-chat trace now uses
  (FR-024); confirm it is **not** the previous truncated plain SHA-256.
- With `LANGFUSE_STRUCTURAL_METADATA` still `false`: traces carry only tags, token usage and timing —
  no metadata dict at all.
- Flip `LANGFUSE_STRUCTURAL_METADATA=true`, restart, regenerate the coach analysis once more: the
  trace now additionally carries a metadata dict whose keys are **exactly** the audited allow-list —
  model, provider, prompt version, tokens, latency, cost, rule names/counts, review verdict code,
  cache hit/miss, fallback flag, retry/validation counts, content-free size buckets, hashed
  identifiers — and **never** sex, age group, category, maturation phase, offsets, velocity, deltas,
  nutritional status, dates, coach free text, session titles or any text fragment (FR-020). Any
  athlete/record/user id inside the metadata is a hashed string, never the raw integer.
- Stop the Langfuse containers, leave `LANGFUSE_ENABLED=true`, run one generation: it completes
  normally, exactly one warning is logged for the process, no retry storm (FR-021, Edge Cases).

**Automated equivalent**: `test_structural_metadata_keys_within_allowlist`,
`test_structural_metadata_never_contains_biological_fields`,
`test_structural_metadata_ids_are_hashed_not_raw`, the tag-allowlist test per trace name, and the
`build_mask(frozenset())` redact-always unit test.

---

### Scenario 6 — Three settings that must never reach production (US6 · SC-009)

For each of the three, start the app with `APP_ENV=production` and confirm a **startup failure**
whose message names the offending variable — never a silent no-op:

1. `LANGFUSE_ENABLED=true`
2. `LANGFUSE_STRUCTURAL_METADATA=true`
3. `AI_PROVIDER=claude-cli` (repeat for `RACE_AI_PROVIDER=claude-cli`)

**Expected**: all three fail 100 % of the time, each with a distinct, variable-naming error message
(SC-009). Also confirm `APP_ENV=production` with all three unset and every other required variable
present boots cleanly — the validators must not be so broad they reject a legitimate production
config.

**Automated equivalent**: `Settings` validator unit tests, one per forbidden setting, mirroring the
existing `forbid_langfuse_in_prod` pattern.

---

### Scenario 7 — Every generation is accounted for, and the race budget is untouched (US2 · SC-001, FR-022, FR-023)

1. Generate one coach-audience analysis for a synthetic measurement. Read the corresponding
   `athlete_ai_explanations` row (via a debug query or a test, never by printing a minor's data) and
   confirm all nine new columns are populated: `schema_version` (`"v2"`), `structured_json`,
   `critic_verdict`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`,
   `langfuse_trace_id` (empty string in a production-shaped config, populated locally with tracing
   on).
2. Call `GET /api/race-analysis/admin/ai-usage?days=30` as the requesting coach: the per-coach
   breakdown now includes this generation's cost with a `stack` label of `app`, alongside any
   `race`-stack spend for the same coach — the two never merge into one number.
3. Generate several more analyses to push this stack's 30-day spend past what would trip
   `RACE_AI_BUDGET_USD_30D` if it were shared: confirm no `503` is ever returned for this stack (no
   cap exists for it, FR-023) and that a subsequent race-analysis run's own budget check is
   unaffected by the growth-stack spend (query the race budget guard's own 30-day sum and confirm it
   only counts `agent_runs`/race rows).

**Automated equivalent**: the widened `spend_by_user_last_30d` test asserting per-coach `stack`
totals sum to the grand total within `1e-6`, and a property test that the race budget guard's query
never joins `athlete_ai_explanations`.

---

### Scenario 8 — The golden eval blocks a bad prompt or model change (US5 · SC-003)

```bash
cd backend && source .venv/bin/activate
.venv/bin/python -m pytest -m golden -k anthropometry -v
.venv/bin/python -m pytest -m golden -k race -v          # unchanged, re-run as the cumulative gate
```

**Expected**: the anthropometry run reports a composite score per case (twelve synthetic cases) and
overall, using the same weights as the race analyst (grounding 0.30, uncertainty calibration 0.20,
privacy/developmental safety 0.20, tone/format 0.15, actionability 0.15) and fails the run below a
composite of 0.75. Every sub-8-week case is not classified as typical/high/low; every uncorroborated
phase crossing is not stated as confirmed (US1 acceptance scenarios 2 and 4, restated as golden
assertions). The race analyst's own golden eval score is unchanged from its pre-feature baseline —
the shared-factory extraction in wave 1 must not move it.

**CI**: `.github/workflows/anthropometry-eval.yml`, cloned from `race-eval.yml`, triggers on changes
under the anthropometry pipeline's prompts/eval paths and is blocking.

---

### Scenario 9 — The mysql lane proves the new columns round-trip (FR-022, SC-002)

```bash
TEST_DATABASE_URL="mysql+aiomysql://<user>:<pass>@127.0.0.1:3306/<name>_test" \
  .venv/bin/python -m pytest -m mysql -q
```

**Expected**: a v2 row persists and reads back `structured_json` intact (including nested
`confidence`/`data_gaps`), `critic_verdict` round-trips through its enum (`approved | revised |
flagged | fallback | skipped`), and regenerating the same record's analysis overwrites in place via
`on_duplicate_key_update` rather than accumulating rows. This is the aiosqlite gap the default lane
cannot close — MySQL-specific upsert syntax only runs here.

---

### Scenario 10 — Touch targets, focus and a11y hold on the AI surfaces (US6 · SC-007)

```bash
cd frontend
npx vitest run -t "a11y"
npx playwright test e2e/growth.spec.ts e2e/anthropometry.spec.ts
```

**Expected**

- "Regenerar análisis", "Copiar" and the measurement dialog's close control each measure at least
  48×48 px.
- Tab cycles focus within the open measurement dialog; Escape closes it; focus returns to the row
  that opened it (FR-031).
- The AI disclaimer uses the neutral informational colour token, never amber; the "Con
  observaciones"/"Desactualizado" badges use amber correctly as conditional-attention states, paired
  with a text label, never a bare colored dot.
- The budget/concurrency hint renders above every generate/regenerate control on both AI cards
  *before* the tap, and disables the control while the budget is exhausted or a run is in progress —
  same pattern as the other AI launch points (FR-032).
- jest-axe reports **zero violations** on the measurement dialog and on `GrowthTab` (both coach and
  family render paths).
- Playwright: generate → render → reopen the same record from cache (no second generation call) —
  the collapsed teaser and the expanded detail both match what was generated, and reopening reads
  from the cached row rather than re-invoking the LLM.

---

### Scenario 11 — A pre-feature free-prose row still renders, forever (US1 acceptance scenario 10, FR-026)

Using an existing (or freshly seeded, schema-version-`NULL`) `athlete_ai_explanations` row with only
`text` populated and no `structured_json`:

1. Open that measurement's dialog as coach: the free-prose `text` renders via the unchanged
   ReactMarkdown path, no expander, no critic badge, no error, and — importantly — **no automatic
   regeneration** is triggered just by viewing it.
2. Open the same measurement as the linked parent: identical rendering behaviour, family-appropriate
   framing unchanged from before this feature.
3. Regenerating that record (as coach) always produces a current-schema (`v2`) response — confirm the
   next read of that record now takes the structured path. This is the de facto v1→v2 upgrade path;
   there is no backfill job and none is expected.

**Automated equivalent**: the versioning test asserting a v1 row (no `schema_version`, no
`structured_json`) serialises and renders unchanged, and a v2 row with corrupt `structured_json`
falls back to prose rather than raising.

---

## 4. Wave gate checklist

Gates are cumulative — each wave re-runs the prior wave's, and wave 1's race golden eval is re-run
once more at the end of wave 3, the last point where a shared-factory regression could surface.

| Wave | Owns | Exit gate |
|---|---|---|
| **W1** — shared factory, LangChain adapter, Langfuse tracing, config | `app/services/llm/*` (new); `race/agents/_llm.py`, `race/agents/pricing.py`, `race/observability.py` (become thin shims); `app/services/ai/factory.py`; `app/services/ai/providers/langchain_provider.py` (new); `app/services/llm/observability_metadata.py` (new); `app/config.py` | `ruff check`; default `pytest`; `pytest -m golden -k race` green with zero behavioural diff; provider-inheritance-matrix and Anthropic-no-temperature regression tests added; `test_factory_openai_not_implemented` fixed; redact-always mask unit-tested; allow-list snapshot test passing |
| **W2** — anthropometry v2 pipeline + eval + cache columns + modal renderer | `app/services/ai/anthro/*` (new: `context.py`, `analyst.py`, `critic.py`, `prechecks.py`, `guardrails_step.py`, `persist.py`, `pipeline.py`, `schemas.py`, `prompts/anthropometry_analyst_v1.md`, `prompts/anthropometry_critic_v1.md`); `app/services/ai/anthro/eval/*` (new, reuses `race/eval/scorer.py::composite_score`); `backend/evals/anthropometry_analyst/*` (new); `app/models/ai_explanation.py`; one Alembic revision (`down_revision=45cd705c6b54`); `app/routers/ai.py`; `app/schemas/ai.py`; the measurement-modal and PHV-card structured-renderer branches | `pytest -m golden -k anthropometry` ≥ 0.75, blocking; `pytest -m mysql` for the nine columns; denied-path tests (parent → 403, no consent → 451, `AI_ENABLED=false` → 503); privacy assertion at the new prompt seam (forbidden-names list never in the rendered prompt); `data-privacy-guard` audit of the widened context **and** of `backend/evals/anthropometry_analyst/`; jest-axe zero violations on the modal |
| **W3** — remaining five use cases behind the switch + growth-tab UI | `app/routers/monthly_reports.py`; `app/routers/athlete_monthly_newsletters.py`; `app/dependencies.py` (session assistant); `app/routers/growth.py` + `app/schemas/growth.py` (`latest_ai_analysis` field); `GrowthTab.tsx`; `LatestAnalysisLine.tsx` (new); `src/api/ai.ts`, `src/schemas/ai.schemas.ts`, `src/hooks/ai/*` | every existing test in the five bridged use cases passes under **both** values of `AI_USE_LANGCHAIN`; consent-gate denied-path test on the new growth-summary field; jest-axe on `GrowthTab`; Playwright generate → render → reopen-from-cache; wave 1's race golden eval re-run clean |
| **W4** — docs | `docs/01-marco-teorico.md` §1 subsection; `docs/20-traceable-growth-ai/{design.md,qa.md,runbook.md}`; `docs/10-race-results/runbook-ops.md` §8/§9; `docs/implementation-status.md`; `docs/technical-notes.md`; `CLAUDE.md` (Alembic head, new env vars) | docs match shipped behaviour; runbook restates that `LANGFUSE_STRUCTURAL_METADATA` does not change the no-retention-policy story for local trace data; theory subsection carries a references list with author, year, source |

---

## 5. Post-deploy smoke

1. `GET /health` → `200`.
2. `GET /api/athletes/{id}/growth-summary` with a coach token → `200`, `latest_ai_analysis` present
   or `null` per the athlete's actual state, never an error.
3. Open the Crecimiento tab for one real athlete in production: `LatestAnalysisLine` renders (or the
   "sin análisis" state), and the measurement dialog's AI card opens without error.
4. Confirm `LANGFUSE_ENABLED` and `LANGFUSE_STRUCTURAL_METADATA` are unset (or `false`) on the
   production environment — Render must never have either flipped on.
5. Confirm `AI_PROVIDER` and `RACE_AI_PROVIDER` on Render are **not** `claude-cli` (by name, never by
   opening the dashboard's value into a shared transcript).
6. `GET /api/race-analysis/admin/ai-usage?days=30` with an admin token → `200`, the `stack` breakdown
   present.
7. Render cold start shows the "starting server" state, never a bare spinner, before any of the
   above.

---

## 6. Traceability

| Story | Scenario | Success criterion |
|---|---|---|
| US1 — a structured, grounded reading | 2, 11 | SC-002, SC-003, SC-008 |
| US2 — every generation is traceable and accounted for | 1, 5, 6, 7 | SC-001, SC-006, SC-009 |
| US3 — families never see a flagged reading | 2, 3 | SC-002, SC-004 |
| US4 — the tab says whether the reading is current | 4 | SC-005 |
| US5 — a golden eval guards prompt/model changes | 8 | SC-003 |
| US6 — touch, focus and colour rules | 6, 10 | SC-007, SC-009 |

---

## 7. Known gaps at plan time

1. **Contracts and data-model are not yet in `specs/042-traceable-growth-ai/`** as this document is
   written — the endpoint's exact `audience` parameter name for the per-measurement analysis, the
   precise Pydantic/Zod field names, and the final Playwright spec file names should be confirmed
   against `data-model.md` and `contracts/` once `/speckit-tasks` produces them; treat any name above
   as the intended convention, not a verified path.
2. **SC-005** ("the coach can tell from the tab without opening any dialog") has no fully automatable
   assertion for the "without opening any dialog" clause beyond the component test asserting the
   summary line and stale badge render in the tab's own DOM tree — record a short moderated check
   (open the tab, answer "is this current and does anything need review?" without clicking into a
   measurement) the same way feature 041's SC-002 was recorded, in `docs/20-traceable-growth-ai/qa.md`.
3. **The seven-trace count in scenario 5** assumes the session assistant's clarify and draft steps
   land as two distinct trace names sharing one flow; if the shipped contract instead traces them as
   one generation with two steps, adjust the count to six and note the change in
   `docs/20-traceable-growth-ai/runbook.md` rather than silently editing this file after the fact.
