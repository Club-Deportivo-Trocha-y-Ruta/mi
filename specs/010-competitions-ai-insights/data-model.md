# Data Model: 010-competitions-ai-insights

**No new tables. No Alembic migration.** This feature composes existing entities and adds API-level (Pydantic/TS) shapes only.

## Existing entities (reused, unchanged schema)

### agent_runs (`AgentRun`, backend/app/models/agent_run.py)
- Carrier of every analysis run. Relevant columns: `external_run_id` (UUID hex, the API `run_id`), `status` enum (`running | awaiting_hitl | completed | rejected | failed | cancelled`), `input_json` (`{athlete_id, season, valida_nums, explain_mode}`), `stale_since`, `requested_by_user_id`.
- **Event linkage is derived**, not stored: a run belongs to event E iff `input_json.season == E.series.season_year` AND `E.sequence_number ∈ input_json.valida_nums` AND the athlete has a result in E. Same resolution already used by `run_staleness.invalidate_runs_for_event()` — the new list endpoint reuses that logic.

### athlete_ai_insights (`AthleteAiInsight`)
- Per-(athlete, season, valida_num) versioned insights; `is_active=1` partial-unique; `coach_approved`; `agent_run_id` FK; `metrics_snapshot_json`.
- **Extended content, same columns**: `summary_text` gains a "Contexto de temporada" section; `metrics_snapshot_json` gains `season_comparative` + `progression_assessment` keys (JSON column — additive, no migration). Old insights lack the keys → render without season block (FR-013).

### race_results / race_events / race_series
- Source of group resolution and season comparatives. Group membership query: results of event E where `athlete_id IS NOT NULL AND deleted_at IS NULL`. Season context query: athlete's results across events of the same `race_series.season_year` with `sequence_number < E.sequence_number` (prior válidas) — single query in `compute_metrics`/`load_race_data`.

## New API-level shapes (Pydantic — backend/app/schemas/race_ai.py)

### GroupRunLaunchRequest
| Field | Type | Rules |
|---|---|---|
| `athlete_ids` | `list[int] \| None` | Optional subset filter (retry failed/pending). None = all club athletes with results in the event. |
| `explain_mode` | `bool = False` | Passed through to each run. |

### GroupRunItem
| Field | Type | Notes |
|---|---|---|
| `athlete_id` | `int` | |
| `athlete_display_name` | `str` | Masked per existing privacy conventions where applicable |
| `run_id` | `str \| None` | Set when the run started |
| `outcome` | enum `started \| backpressure \| budget_exceeded \| already_running \| no_results \| error` | `already_running`: an active run exists for the same (athlete, season, valida) |
| `detail` | `str \| None` | es-CO message for non-started outcomes |

### GroupRunLaunchResponse
| Field | Type |
|---|---|
| `race_event_id` | `int` |
| `season` | `int` |
| `valida_num` | `int` |
| `items` | `list[GroupRunItem]` |
| `started_count` / `skipped_count` | `int` |

State rule: HTTP 200 even with partial starts (typed per-item outcomes). HTTP 503 only when budget guard blocks before anything starts; HTTP 429 only when zero items could start due to backpressure; HTTP 422 when the event has no committed results; 404 unknown event; 401/403 per RBAC.

### RaceEventRunsResponse (refresh recovery)
| Field | Type |
|---|---|
| `race_event_id` | `int` |
| `runs` | `list[RaceEventRunItem]` — `{run_id, athlete_id, athlete_display_name, state: RunState, started_at, stale: bool}` |
- Query param `active_only: bool = true` (states `running | awaiting_hitl`).

### ChatRequest (extended — additive)
- `race_event_id: int | None = None` added. When set, chat tools constrain results/insights retrieval to that event and seed the session with the event label. `athlete_id` remains independently usable; both may combine.

### Analysis enrichment (services/race schemas)
- `SeasonComparativeEntry`: `{valida_num, event_label, position, race_time_ms, field_size, delta_position, delta_time_ms}` — computed in Python.
- `progression_assessment`: enum `improving | stable | declining | mixed | first_reference`; derivation rule: positions across prior válidas vs current (strictly better → improving; strictly worse → declining; equal ±0 → stable; otherwise mixed; no priors → first_reference).
- `AnalysisInput` += `season_comparative: list[SeasonComparativeEntry]`, `progression_assessment: str`. Prompt template must instruct: never invent comparisons when `first_reference` (FR-007, SC-002).

## New TS shapes (frontend/src/types/raceAnalysis.types.ts)
Mirrors of `GroupRunLaunchRequest/Response`, `GroupRunItem`, `RaceEventRunsResponse`; `ChatRequestBody += race_event_id?: number | null`.

## State transitions (group view — derived, not persisted)
```
GroupAnalysisPanel state = aggregate of member runs:
  any running/awaiting_hitl → "en progreso" (launch disabled, FR-012)
  all terminal, ≥1 failed/rejected → "parcial" (retry-failed enabled, FR-011)
  all completed → "completado"
  no runs → "listo para lanzar" (or disabled if !hasResults, FR-002)
```
