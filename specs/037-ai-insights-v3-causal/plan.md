# Implementation Plan: AI Insights v3 — causal, field-relative, prescriptive

**Feature**: `037-ai-insights-v3-causal` · **Spec**: `spec.md` · **Date**: 2026-09-02
**Branch**: work happens on `main` working tree (036 follow-up is still uncommitted there; do not revert it).

## Technical context

- Backend: Python 3.13, FastAPI, SQLAlchemy 2 async, LangGraph 1.2 (`app/services/race/ai/graph.py`), Jinja prompts (`app/services/race/prompts/*.md`), Gemini via `langchain-google-genai` (`app/services/race/agents/_llm.py`).
- Frontend: React 19, shadcn/ui, TanStack Query, vitest + MSW + jest-axe.
- Models (verified 2026-09-02 against the configured key): analyst `gemini-3.8-flash`, critic `gemini-3.1-flash-lite`. Both free-tier.
- Constitution gates: tests mandatory; UX consistency (shadcn primitives, `mode="coach"|"parent"`); performance budget p95 ≤ 40 s per válida; youth safeguards (no diagnosis, no weight/BMI to provider, no outcome goals).
- Privacy: everything that reaches the provider is anonymised (pseudonym, forbidden names scrub incl. **all club athletes' names** for training feedback text); weight, BMI, nutritional status never leave the DB; other minors appear only as aggregates.

## Architecture

### Graph v3 topology

```
validate_input
  └─ ok → load_race_data → load_athlete_context (NEW) → anonymize (ext.) → compute_metrics (ext.: field_context)
        → recall_memory (ext.: coach dialogue) → analyst_agent (v3 structured, valida | season)
        → critic_agent (v3: deterministic prechecks + LLM) → hitl_gate_review → rehydrate_names
        → persist_insight (v3: structured_json + rendered summary_text) → render_outputs → notify_coach → END
```

`analysis_kind` ∈ {`valida`, `season`} chosen by the router. Season runs use the same nodes; the analyst renders `race_season_summary_v3.md` once, the critic reviews one draft, persistence writes `valida_num=0`, `use_case="season_summary_v3"`.

### State keys (add to `RaceAnalystState`, `total=False`)

```python
# Input (routers)
athlete_sex: str | None            # "M" | "F" → athlete_ref "el deportista" | "la deportista"
analysis_kind: str                 # "valida" (default) | "season"
prompt_version: str                # "race_analyst_v3" | "race_season_summary_v3"

# load_athlete_context
anthro_context: dict | None        # see data-model.md §AnthroContext (no weight/BMI/nutrition)
training_window: dict | None       # see data-model.md §TrainingWindow (28 d before event_date; season kind → whole season)
catalog_context: dict              # {"technique_skills": [{code,name,focus}], "strength_blocks": [{id,name,age_band}], "interval_templates": [{id,name,age_band,mesocycle_phase}]}
club_forbidden_names: list[str]    # all club athletes + their parents; superset of forbidden_names

# compute_metrics
field_context: dict                # {valida_key: FieldMetrics} — see data-model.md §FieldMetrics; keyed by event_id (str)

# recall_memory
coach_dialogue: list[dict]         # [{"generated_at", "valida_label", "headline", "coach_question", "coach_answer", "coach_rating"}] last 3 approved

# analyst_agent
per_valida_drafts_v3: dict[int, InsightV3]   # keyed by valida_num (0 for season)
grounding_numbers: dict[int, list[str]]      # numeric tokens present in the rendered prompt, per valida (for prechecks)

# critic_agent
precheck_issues: dict[int, list[CriticIssue]]
```

Existing keys (`per_valida_drafts`, `draft_analysis`, `per_valida_verdicts`, `confidence`) keep working: the v3 analyst also fills `per_valida_drafts[vn] = AnalysisOutput(raw_markdown=render_insight_v3_markdown(draft), recommendations=…)` so HITL, persist and render nodes stay backward compatible.

### Modules

| Module | Responsibility |
|---|---|
| `app/services/race/field_metrics.py` (NEW) | Pure pandas. `compute_field_metrics(results_df, events_df, athlete_competitor_id, season) -> dict[int, FieldMetrics]` and `prior_performance_index(...)`. No DB, no names. |
| `app/services/race/ai/athlete_context.py` (NEW) | `load_anthro_context(db, athlete_id, reference_date)`, `load_training_window(db, athlete_id, club_id, date_from, date_to)`, `load_catalog_context(db, club_id, age_band)`, `load_club_forbidden_names(db, club_id)`, `age_band_from_age(age_decimal) -> AgeBand`. |
| `app/services/race/ai/nodes/load_athlete_context.py` (NEW) | Node; resolves the reference date from the anchored event (or season end for `season`), calls the loaders, writes the keys above. Best-effort: any loader failure → key `None` + `errors[]` entry, never fails the run. |
| `app/services/race/ai/prechecks.py` (NEW) | Deterministic critic: `run_prechecks(draft: InsightV3, *, grounding_numbers, catalog_context, athlete_age, ltad_group, forbidden_names) -> list[CriticIssue]`. |
| `app/services/race/insight_v3.py` (NEW) | `InsightV3` Pydantic model + `render_insight_v3_markdown(draft, athlete_ref) -> str` + `extract_numeric_tokens(text) -> set[str]`. |
| `app/services/race/prompts/race_analyst_v3.md`, `race_season_summary_v3.md`, `race_critic_v3.md` (NEW) | Prompts. v2 files stay for the eval history and rollback. |
| `app/services/race/agents/analyst.py` | `invoke_v3(inputs: list[AnalystV3Input]) -> dict[int, (InsightV3, RunMetrics)]` using Gemini structured output (`llm.with_structured_output(InsightV3, method="json_schema")` — fall back to JSON parsing of text with one repair retry). |
| `app/services/race/agents/critic.py` | `invoke_v3(draft: InsightV3, ground_truth: str, precheck_issues) -> (CriticFeedback, RunMetrics)`. |
| `app/services/race/agents/_llm.py` | `build_chat_llm(role="analyst"|"critic"|"chat")` resolving `RACE_AI_ANALYST_MODEL` / `RACE_AI_CRITIC_MODEL` / `RACE_AI_MODEL`; `max_output_tokens` 4096 for analyst. |
| `app/services/race/agents/pricing.py` | Add `gemini-3.8-flash` (0.75 / 3.75 USD per 1M) and `gemini-3.5-flash-lite` (0.30 / 2.50). |
| `app/config.py` | `race_ai_analyst_model: str = "gemini-3.8-flash"`, `race_ai_critic_model: str = "gemini-3.1-flash-lite"`, `race_ai_training_window_days: int = 28`. `race_ai_model` (legacy) still wins for `chat` and as fallback when a role model is empty. |
| `alembic/versions/<rev>_ai_insights_v3_columns.py` | `athlete_ai_insights`: `structured_json JSON NULL`, `coach_answer_text VARCHAR(1000) NULL`, `coach_answer_at DATETIME NULL`, `coach_rating TINYINT NULL` (1 = útil, -1 = no útil). down_revision `463c1f0ccb38`. |
| `app/routers/athlete_race_analysis.py` | `POST /api/athletes/{athlete_id}/race-analysis/insights/{insight_id}/answer` body `{coach_answer_text?: str ≤1000, coach_rating?: 1|-1}` (coach/admin, athlete must belong to caller's club; parent → 403). Detail/list DTOs expose `structured` (parsed `InsightV3` or `null`), `coach_answer_text`, `coach_answer_at`, `coach_rating`. Season summary endpoint now launches a graph run (`analysis_kind="season"`) and returns `{run_id}` (202) — frontend polls like a válida run. |
| `app/routers/race_analysis.py` | `start_run` injects `athlete_sex`, `analysis_kind` (body field, default `valida`), `prompt_version="race_analyst_v3"`. AI consent gate: call `athlete_has_ai_processing_consent`; when false → 451 (same contract as `routers/ai.py:_ensure_ai_consent`). |
| `app/services/race/agents/chat.py` | Athlete scope: when `athlete_id` is passed without `race_event_id`, tools are baked to that athlete and a new tool `obtener_contexto_entrenamiento(desde, hasta)` returns `TrainingWindow` aggregates (no free text). |
| Frontend `components/athletes/ai/InsightV3Card.tsx` (NEW) | Renders `structured`: headline, field-reading chips, observations with evidence pills, actions checklist with catalog badge, watch signals, data gaps, coach question + `CoachAnswerForm` (coach only). |
| Frontend `components/athletes/ai/CoachAnswerForm.tsx`, `AthleteAnalystChatPanel.tsx` (NEW) | Answer + rating; chat scoped to athlete (reuses `CompetitionChatPanel` internals). |
| Frontend `InsightsTimeline.tsx`, `HeroLastInsightCard.tsx`, `HITLApprovalCard.tsx`, `AthleteAIAnalysisTab.tsx`, `SeasonSummaryButton.tsx` | Preview = `structured.headline` when present; drawer renders `InsightV3Card`; HITL renders the structured draft from `payload.structured_draft` (fallback to markdown); season button starts a run and shows the run timeline. |
| `backend/evals/race_analyst/golden_v3/` + `app/services/race/eval/scorer_v3.py` + `prompts/judge_v2.md` | Eval v3. `tests/evals/test_race_analyst_eval.py` runs v3 when `RACE_EVAL_VERSION=v3` (default v3). |

### Analyst prompt v3 — method, not prohibitions

Sections of `race_analyst_v3.md` (≈900 tokens of instructions + data):
1. Role + audience (coach, LTAD-literate) + `athlete_ref`.
2. **Method** (numbered): (a) read the field: percentile, expected vs actual, gap P1/P3/median, series kind; (b) contrast with the training window and maturation; (c) pick the single strongest finding → `headline`; (d) 2-4 observations, each with numeric evidence copied verbatim from the data; (e) 2-3 actions from the catalog, tied to observations, with horizon; (f) 0-2 watch signals; (g) exactly one coach question about something the data cannot tell; (h) declare data gaps honestly.
3. Inviolable rules (compact, 8 lines).
4. Data blocks (only those present): race row, field metrics, season table, conditions, anthro context, training window, coach dialogue, catalog.
5. One worked example on fictional data (few-shot) showing a causal headline, grounded evidence and a catalog-linked action.
6. Output: JSON matching `InsightV3` (schema enforced by structured output).

Word budgets: headline ≤ 30 words, observation claim ≤ 45, evidence item ≤ 20, action ≤ 40, total ≤ 450 words.

### Critic v3

1. Prechecks (Python, free): schema validity; every number in `evidence[]`, `headline` and `claim` ∈ `grounding_numbers[vn]` (tolerant to formatting: `8.6%`, `8,6 %`, `0:35:30`, `2:49`); forbidden names; LTAD rules (cadence <60, hours > age, days > 5, supplements, intervals/HR-max for <13, diagnosis words, outcome-goal phrases); `catalog_ref` exists; `coach_question` non-empty and ends with `?`; observation overlap with previous insights of the same athlete <85 % (Jaccard on token sets, using `coach_dialogue` headlines and `memory`).
2. LLM critic (`race_critic_v3.md`, flash-lite) only for contradiction with ground truth and tone; receives the precheck list so it does not repeat it. `must_block` only from prechecks category `privacy|ltad` or LLM `high` contradiction.
3. Confidence v3: `low` if fallback / must_block / any grounding violation; `medium` if any `med` issue or training window missing or anthro missing or season_n ≤ 1; else `high`.

### Expected-vs-actual (field_metrics)

For a race R in category C with finishers F: for each finisher f, `prior_index(f) = mean(gap_pct)` over f's finished results in the same season dated before R (any series, any category — gap_pct is category-relative). Finishers without prior → excluded. If `len(with_prior) / len(F) < 0.5` → `expected_position=None`. Else expected position of the athlete = 1 + count of finishers with prior whose `prior_index` < athlete's, rescaled to the full field size: `expected_position = round(1 + rank_among_with_prior * (len(F) - 1) / max(len(with_prior) - 1, 1))`. `delta_vs_expected = expected_position - actual_position` (positive = better than expected). `field_strength = mean(prior_index of with_prior)`; lower = stronger field. All values rounded to 1 decimal; ids never surface.

### Rendering `summary_text` from `InsightV3`

```
## Hallazgo principal
<headline>

## Lectura del pelotón
<one line: percentil, esperado vs real, gap P3>

## Observaciones
- <claim> — evidencia: <e1>; <e2>

## Acciones
- <text> (categoría=<cat>, prioridad=<prio>, horizonte=<h>[, catálogo=<kind>:<code>])

## Señales a vigilar
- …

## Pregunta para el coach
<question>

## Vacíos de datos
- …
```
Newsletter and any consumer of `summary_text` keep working. The regex `_REC_BULLET_RE` is relaxed to tolerate a trailing period and the extra `horizonte`/`catálogo` fields.

## Risks & mitigations

- Gemini structured output rejects nested schemas occasionally → fallback path: JSON in text + `json_repair`-style single retry + Pydantic validation; on failure → deterministic fallback v3 (headline "Análisis no disponible", `is_fallback=True`).
- Free-tier RPM (≈15) with 4 válidas × 2 agents in parallel → cap concurrency to 2 in `invoke_v3` and reuse the existing retry with backoff on 429.
- Training feedback text may name other minors → scrub with `club_forbidden_names`; also drop any token matching `[A-Z][a-z]+ [A-Z][a-z]+` not in a whitelist? No — keep scrub deterministic by names list; truncate each feedback to 200 chars; max 3 items.

## Phases

1. **Wave 1 — data & fixes** (parallel): fixes + config/model roles; field_metrics; athlete_context + node + anonymize; migration + DTOs + answer endpoint + recall_memory.
2. **Wave 2 — LLM layer + frontend contract** (parallel): InsightV3 + prompts + analyst v3 + persist; prechecks + critic v3 + confidence; routers (season via graph, consent gate, chat athlete scope); frontend types/api/hooks/MSW/fixtures.
3. **Wave 3 — UI** (parallel): InsightV3Card + timeline/drawer/hero/HITL; CoachAnswerForm + chat panel + season run wiring.
4. **Wave 4 — quality**: eval v3; privacy audit; docs (`docs/implementation-status.md`, `docs/technical-notes.md`, `docs/10-race-results/spec-insights-v3.md`); SC-1 real regeneration on local DB.
