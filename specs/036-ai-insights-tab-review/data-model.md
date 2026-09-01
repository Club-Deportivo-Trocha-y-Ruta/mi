# Data Model: AI Insights Tab — Full-Stack Review

**Feature**: `036-ai-insights-tab-review` | **Date**: 2026-08-31

This feature is a review/fix feature: it modifies existing entities rather than introducing a new domain. Only deltas are listed; unchanged columns are omitted.

## AthleteAiInsight (`athlete_ai_insights`) — MODIFIED

Source: `backend/app/models/athlete_ai_insight.py`.

### New column (US4, T020–T023)

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `is_fallback` | `BOOLEAN` | NOT NULL | `FALSE` (server_default) | `TRUE` ⇔ the row was persisted by the **failure path** of `services/race/ai/fallback.py` (`deterministic_fallback`). The N=1 variant (`deterministic_fallback_n1`) is a legitimate analysis and stays `FALSE`. |

- **Migration**: single Alembic revision; run `alembic heads` first (dangling head `e5f6a7b8c9d0` from feature 007 must not become a branch point). Includes the one-off backfill: `UPDATE ... SET is_fallback = TRUE WHERE summary_text LIKE '<fallback constant>%'` — safe because the text is a compile-time constant, not user input.
- **Derived UI behaviour**: `is_fallback=TRUE` ⇒ marked badge, newsletter checkbox suppressed, retry affordance; attach endpoint rejects the ID server-side (T026).

### Existing columns re-interpreted (US5, T030)

| Column | Change |
|---|---|
| `valida_num` | Stays as storage (`0` = season aggregate, `NULL` = n/a), but **stops being the label source**. The retired `99` convention is dead: no reads may branch on it. |
| `event_id` | Already exists (FK `race_event`, nullable). Becomes the **authoritative race identity** in every API response; responses gain the event's date and `race_series.kind` so the frontend derives labels from one helper. |
| `model` | No schema change; **write path fixed** (T060): persist the provider/model actually used, not the hardcoded `"gemini-2.5-flash-lite"`. Historical rows keep wrong values unless the club decides to annotate (Open Question 5). |

### Validation rules

- An insight row with `is_fallback=TRUE` MUST NOT be attachable to a newsletter (router-level guard, not just UI).
- Active-insight uniqueness (`uq_insights_active_terna`) is untouched.

## AgentRun (`agent_runs`) — behaviour only, no schema change

Source: `backend/app/models/agent_run.py`. Status enum: `running | awaiting_hitl | completed | rejected | failed | cancelled`.

### State transitions added (US3, T016)

| From | To | Trigger |
|---|---|---|
| `running` (older than threshold) | `failed` | Startup reconciliation in `main.py` lifespan — the in-memory registry died with the previous process (Render redeploy/spin-down). `error_message` explains the cause. |
| `awaiting_hitl` (older than threshold) | `failed` | Same reconciliation. Per research R2, the sqlite HITL checkpoint is ephemeral on Render free tier; a pending decision cannot be resumed after a deploy. |

Threshold: configurable, default generous enough to never race a live run (e.g. ≥ 2× the max expected pipeline duration). Client side (T017) mirrors this with a hard polling ceiling in `useRaceRun.ts`.

## Frontend state (US3) — no persistence

`AthleteAIAnalysisTab` component state (`newsletterSelection: Set<number>`, `activeRunId`, accumulated HITL events, sub-tab selection) is scoped to one athlete by construction after T010: `key={athlete.id}` forces full remount on athlete change. Invariant: **no piece of tab state may outlive `athlete.id`**.

## Contract-only fixes (no DB change)

| Type | File | Fix |
|---|---|---|
| `SeasonSummaryResponse` (TS) | `frontend/src/api/athleteRaceAnalysis.ts:111-125` | Align to the real backend schema (`backend/app/schemas/athlete_race_analysis.py:571`): `insight_id`, `season`, `summary_text`, `prompt_version`, `generated_at`, `validas_analyzed`. Remove phantom `run_id`/`status`/`started_at`. The call is synchronous. |
| `ClubInsightByRaceItem.stale_run_id` | `backend/app/schemas/athlete_race_analysis.py:470` + frontend badge | T041 decision: populate it or delete field + UI. Never-rendered badge today. |
| Insight list/detail responses | backend schema + `frontend/src/lib/insights.ts` | Gain `event_id`, race date, `series_kind`; label derivation collapses into one helper (roman format, T032). |
