# AI Insights v3 — causal, field-relative, prescriptive

Feature `037-ai-insights-v3-causal`. Supersedes the analytical contract of
`spec-insights-per-valida-v2.md` §4 (the 3-section markdown output). Keeps
v2's privacy, HITL and per-válida persistence decisions.

Source of truth for scope and acceptance criteria:
`specs/037-ai-insights-v3-causal/spec.md`, `plan.md`, `data-model.md`,
`tasks.md`. This document summarizes the shipped architecture for readers
who do not need the full spec-kit trail.

## Problem

The v2 per-válida analysis only saw race rows (position, time, gaps, podium
times, age, LTAD group, maturation label, last 3 summaries) and produced
generic LTAD boilerplate with the numbers swapped. The coach's verdict:
"muy básicos, no me están dando un valor agregado". Five data sources
already in the platform never reached the model: training attendance/RPE/
rubrics, anthropometry (PHV offset), the technique/strength/interval
catalog, field size and gap-to-field metrics per race, and cup-vs-
championship series semantics. A prompt that was mostly prohibitions and no
worked method produced repeated, non-causal text. See `spec.md` §Problem
statement for the full list of bugs found (including the `valida_num=None`
data bug that forced every insight to "Confianza baja").

## Coach decisions

Confirmed in the 2026-09-02 interview (`spec.md` §Coach decisions):

- Value expected from an insight: causes (training → race), field-relative
  performance, catalog-linked prescription, and a dialogue question — all
  four, not a subset.
- Data allowed to reach the AI provider (anonymized): race + anthropometry
  + training (attendance, RPE, rubrics, coach session feedback).
- Model: strong analyst on Gemini free tier (`gemini-3.8-flash`), cheap
  critic (`gemini-3.1-flash-lite`).
- Output format: one headline finding + 2-4 evidence-backed observations +
  2-3 catalog-linked actions + one coach question, as structured JSON
  rendered as cards (not free markdown).

## Architecture

### Graph v3 topology

```
validate_input
  └─ ok → load_race_data → load_athlete_context (NEW) → anonymize (ext.)
        → compute_metrics (ext.: field_context) → recall_memory (ext.: coach_dialogue)
        → analyst_agent (v3 structured, valida | season) → critic_agent (v3: prechecks + LLM)
        → hitl_gate_review → rehydrate_names → persist_insight (v3) → render_outputs → notify_coach → END
```

`analysis_kind` (new field on the run request) is `"valida"` or `"season"`.
Season runs use the same graph: the analyst renders
`prompts/race_season_summary_v3.md` once instead of once per válida, the
critic reviews one draft, and persistence writes `valida_num=0`,
`use_case="season_summary_v3"`. This replaces v2's synchronous,
critic/HITL-free season summary (`spec.md` problem 5).

### New/changed modules

| Module | Responsibility |
|---|---|
| `app/services/race/field_metrics.py` | Pure pandas. Field size, percentile, gap to P1/P3/median, expected-vs-actual position (see below), championship label. No DB access, no names. |
| `app/services/race/ai/athlete_context.py` | Loaders: `load_anthro_context`, `load_training_window`, `load_catalog_context`, `load_club_forbidden_names`, `age_band_from_age`. |
| `app/services/race/ai/nodes/load_athlete_context.py` | Graph node; resolves the reference date (anchored event, or season end for `analysis_kind="season"`), calls the loaders above. Best-effort: any loader failure sets its key to `None` and appends to `errors[]` — never fails the run. |
| `app/services/race/ai/prechecks.py` | Deterministic critic rules (see below); `run_prechecks(...) -> PrecheckResult`, exposes `sanitized_draft` with unknown `catalog_ref`s stripped. |
| `app/services/race/insight_v3.py` | `InsightV3` Pydantic contract, `render_insight_v3_markdown()`, `extract_numeric_tokens()`, `PRINCIPLE_LABELS` (closed list from `docs/01-marco-teorico.md`). |
| `app/services/race/prompts/race_analyst_v3.md`, `race_season_summary_v3.md`, `race_critic_v3.md` | New prompts (method-driven, few-shot). v2 prompt files stay for eval history and rollback. |
| `app/services/race/agents/analyst.py::invoke_v3` | Structured output (`with_structured_output(InsightV3)`) with a JSON-repair retry, concurrency capped at 2 (free-tier RPM). |
| `app/services/race/agents/critic.py::invoke_v3` | Runs prechecks first, then the LLM critic (only for ground-truth contradiction and tone). |
| `app/services/race/agents/_llm.py::build_chat_llm(role=...)` | Resolves `RACE_AI_ANALYST_MODEL` / `RACE_AI_CRITIC_MODEL` for `role="analyst"/"critic"`; `role="chat"` still resolves through `RACE_AI_MODEL` (no per-role variable). |

### InsightV3 contract

Defined in `backend/app/services/race/insight_v3.py`, mirrored in
`frontend/src/types/insightV3.types.ts`. Full field-by-field shape (enums,
length limits) is in `specs/037-ai-insights-v3-causal/data-model.md`
§InsightV3 — not duplicated here. Summary of the top-level shape:

- `headline` — the single strongest finding (≤ 200 chars).
- `field_reading` — percentile, expected vs. actual position, gap to P3,
  series label; `null` when the race has no computable field metrics.
- `trend` — `improving | stable | declining | mixed | first_reference`.
- `observations` (2-4) — each with a `claim`, 1-3 `evidence` items copied
  verbatim from the data, an `EvidenceDomain`, and a confidence label.
- `actions` (2-3) — category, priority, horizon, optional `catalog_ref`
  (technique skill / strength block / interval template id that must exist
  in the DB), `derived_from` pointing at an observation index.
- `watch_signals` (0-2), `coach_question` (exactly one, ends in `?`),
  `data_gaps` (0-3), `principles_cited` (0-3, from the closed
  `PRINCIPLE_LABELS` list).

`render_insight_v3_markdown()` projects the JSON into the same markdown
sections v2 produced (`## Hallazgo principal`, `## Lectura del pelotón`,
`## Observaciones`, `## Acciones`, `## Señales a vigilar`, `## Pregunta
para el coach`, `## Vacíos de datos`) so `summary_text`, the newsletter, and
chat context keep working unchanged. Actions are never re-parsed from that
markdown — they travel typed end to end into `recommendations_json`,
closing the v2 bug where a bullet ending in `.` silently dropped a
recommendation.

### Prechecks (deterministic critic, `app/services/race/ai/prechecks.py`)

Runs before the LLM critic, free of provider cost:

- Schema validity of the parsed `InsightV3`.
- Numeric grounding: every number in `headline`, each observation `claim`
  and `evidence[]` must exist in `grounding_numbers[valida_num]` (the set
  of numeric tokens present in the rendered prompt), tolerant to format
  (`8.6%`, `8,6 %`, `0:35:30`, `2:49`, `35:30`, plain integers).
- Forbidden names (club athletes + parents).
- LTAD rules: cadence < 60 rpm, hours/week > age, > 5 training days/week,
  supplements, structured intervals or HR-max test prescribed for an
  athlete under 13, medical-diagnosis wording, outcome-goal phrasing
  ("podio", "ganar").
- `catalog_ref` existence — unknown refs are dropped from
  `sanitized_draft`, not just flagged.
- `coach_question` well-formed (non-empty, ends with `?`).
- Observation overlap with the athlete's previous insights (Jaccard on
  token sets against `coach_dialogue` headlines) — flags near-duplicate
  text across válidas.

Each issue carries an internal category (`PrecheckCategory`); only
`privacy` and `ltad` force `must_block`. `grounding`, `catalog`, and
`style` issues degrade confidence but do not block the run.

The LLM critic (`race_critic_v3.md`, flash-lite) receives the precheck list
so it does not repeat those checks — it only judges contradiction with
ground truth and tone. `must_block` is set from precheck
`privacy`/`ltad` issues or an LLM `high`-severity contradiction.

### Expected-vs-actual method (`field_metrics.py`)

For a race with finishers `F`, each finisher's `prior_index` is the mean
`gap_pct` of their finished results earlier in the same season (any
series, any category — `gap_pct` is category-relative). Finishers without
a prior result are excluded. If fewer than 50% of finishers have a prior
index, `expected_position` is `None` and the insight states the data gap
instead of inventing a number (spec AC-2.2). Otherwise:

```
expected_position = round(1 + rank_among_with_prior × (field_size - 1) / max(len(with_prior) - 1, 1))
delta_vs_expected = expected_position - actual_position   # positive = better than expected
field_strength = mean(prior_index of with_prior)           # lower = stronger field
```

All values round to 1 decimal; competitor ids never leave `field_metrics.py`
— the model only ever sees positions and percentages. Championships are
labelled as such and never compared position-to-position with cup válidas
(gap % and percentile are the comparable metrics instead, AC-2.3).

### Privacy

Everything reaching the provider is anonymized before the analyst node
runs (existing `anonymize` node, extended to scrub `training_window`'s
`coach_feedback` text with `club_forbidden_names` — all club athletes and
their parents, a superset of the per-run `forbidden_names`). Weight, BMI,
z-scores, nutritional status, and arm span never enter `anthro_context` —
enforced by the loader shape itself (`athlete_context.py`), not by a
downstream filter. Other minors, when they appear at all, are aggregates
only (field size, percentile, field strength) — never named, pseudonymised
individually, or ranked (AC-2.4). Coach feedback text is truncated to 200
chars, max 3 items, before it reaches the prompt.

Parent-mode server-side omission (unchanged privacy boundary from v2,
extended to the v3 shape): `AthleteInsightDetailOut` in parent mode omits
`structured.field_reading.expected_position` /
`.delta_vs_expected`, `coach_question`, training-domain observation
evidence, and `coach_answer_*`.

## Rollback

`RACE_AI_PROMPT_VERSION` env var overrides `Settings.race_ai_prompt_version`
(default `race_analyst_v3`), which controls the `prompt_version` used by
both per-válida launch routers. Setting it to `race_analyst_v2` reverts to
the v2 markdown pipeline without a code deploy — the v2 prompt, analyst
path, and rendering code all remain in the codebase for this purpose. The
season summary always runs `race_season_summary_v3` regardless of this
flag (there is no v2 season prompt to roll back to; v2's season summary was
a bare reuse of the per-válida prompt, not a dedicated one).

## Eval

Golden eval v3 (`specs/037-ai-insights-v3-causal/tasks.md` T401 — Wave 4,
**not yet implemented** as of 2026-09-02) will add
`backend/evals/race_analyst/golden_v3/case_001..008.json` (fictional
inputs including training window, anthropometry, field metrics),
`app/services/race/eval/scorer_v3.py`, `prompts/judge_v2.md`, and switch
`tests/evals/test_race_analyst_eval.py` to the v3 path via
`RACE_EVAL_VERSION` (default `v3` once shipped). The rule scorer will check
schema validity, numeric grounding, catalog-ref existence, forbidden
terms, non-template headlines, and coach-question presence; the judge
rubric adds "causal insight" and "field reading" dimensions. Threshold
stays composite ≥ 0.75, same CI gate
(`.github/workflows/race-eval.yml`) as v2. Until this lands, CI still
guards the v2 golden set (`backend/evals/race_analyst/golden/`,
`eval/scorer.py`, `eval/judge.py`) — it does not exercise the v3 output
shape.

## Runbook — operating v3

### New environment variables

| Variable | Default | Effect |
|---|---|---|
| `RACE_AI_ANALYST_MODEL` | `gemini-3.8-flash` | Model for the analyst role only. Empty → falls back to `RACE_AI_MODEL`, then to the per-provider default in `_llm.py`. |
| `RACE_AI_CRITIC_MODEL` | `gemini-3.1-flash-lite` | Model for the critic role only. Same fallback chain as above. |
| `RACE_AI_TRAINING_WINDOW_DAYS` | `28` | Days before the race (or season start, for `analysis_kind="season"`) aggregated into `training_window`. |
| `RACE_AI_PROMPT_VERSION` | `race_analyst_v3` | Per-válida launch prompt version. Set to `race_analyst_v2` for an immediate rollback (see above). |

`RACE_AI_MODEL` (legacy, existing) still governs the `chat` role, and is
the fallback for analyst/critic when their dedicated variables are empty.
`RACE_AI_PROVIDER` (`google` default) is unchanged — the per-role
variables only pick a model within the already-selected provider.

### Known gaps carried into later work

Recorded verbatim from the Wave 2 integration status
(`specs/037-ai-insights-v3-causal/tasks.md`, "Status 2026-09-02") because
they are operationally relevant:

- `start_athlete_run` in `routers/athlete_race_analysis.py` still lacks
  the AI-consent 451 gate (only `start_run` and the season endpoint have
  it).
- `chat.py` does not pass `role="chat"` explicitly to `build_chat_llm`
  (harmless — it is the same default).
- `ActionCategory.tactics` degrades to `technique` in the v2-compat
  `AnalysisOutput.recommendations` copy; the original value is preserved
  in `structured_json` and `recommendations_json`.
- The `hitl_gate_review` payload exposes `structured_draft` only for the
  lowest válida of a multi-válida run.
- The v3 season prompt has no explicit N=1 hard veto — it relies on the
  `trend="first_reference"` instruction plus prechecks.
- Critic model provenance is not persisted separately from the analyst's
  (single `model` column on `athlete_ai_insights`).

## References

- `specs/037-ai-insights-v3-causal/spec.md` — problem statement, coach
  decisions, user stories, acceptance criteria, success criteria.
- `specs/037-ai-insights-v3-causal/plan.md` — full architecture, phase
  breakdown, risks.
- `specs/037-ai-insights-v3-causal/data-model.md` — `InsightV3`,
  `AnthroContext`, `TrainingWindow`, `FieldMetrics` field-by-field shapes,
  DB columns, API deltas.
- `specs/037-ai-insights-v3-causal/tasks.md` — task-level status (Waves
  1-2 done, Wave 3 UI and Wave 4 quality tracked there).
- `backend/app/services/race/insight_v3.py`,
  `backend/app/services/race/field_metrics.py`,
  `backend/app/services/race/ai/prechecks.py`,
  `backend/app/services/race/ai/athlete_context.py`.
- `docs/10-race-results/spec-insights-per-valida-v2.md` — superseded v2
  contract (privacy/HITL/persistence decisions still apply).


## SC-1 verification runbook (2026-09-02)

```bash
cd backend && source .venv/bin/activate
PYTHONPATH=. python scripts/regenerate_athlete_insights_v3.py --athlete-id <id> --season 2026 --season-summary
```

Requires the local backend on `:8000` with `RACE_AI_*` configured. The script
signs a coach token locally, launches one run per race (plus the season
summary when asked), waits for each run and prints headline, trend,
confidence, evidence/actions counts, catalog links, coach question, data
gaps, critic verdict and cost — never names. Runs blocked by the critic stay
in `hitl_waiting` for the coach; they are not auto-approved.

Extra setting introduced by this verification: `RACE_AI_V3_TIMEOUT_SECONDS`
(default 120) — per-call timeout of the v3 analyst/critic, independent from
the 30 s `AI_TIMEOUT_SECONDS` of the session-assistant stack.
