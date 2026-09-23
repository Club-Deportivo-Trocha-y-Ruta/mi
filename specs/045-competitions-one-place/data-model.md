# Data Model: Competitions in one place (045)

This feature adds **one** persisted change: the `race_imports.status` value `discarded`. Everything else is a derived shape (computed at read time) or a response-schema change.

## 1. MetricSet (derived, never persisted)

The engine produces one MetricSet per result (`field_metrics.py`, R-01).

| Field | Type | Rule | Coach | Family |
|---|---|---|---|---|
| `field_size` («Parrilla») | int | FINISHED + MINUS_LAPS in the category | ✓ | ✓ |
| `timed_finishers` | int | FINISHED with `race_time_ms` | ✓ | ✓ (context only) |
| `position` | int \| null | official position | ✓ | ✓ |
| `percentile` («Percentil») | float \| null | `round(100 × (1 − (t − t_min) ÷ (t_max − t_min)))` over timed finishers. `null` if `timed_finishers < 5`, if the athlete is not FINISHED with a time, or if `t_max == t_min` | ✓ | ✓ |
| `gap_to_median_pct` («Brecha vs. mediana») | float \| null | `100 × (t − median) ÷ median` over timed finishers; same `null` rules | ✓ | ✓ |
| `gap_to_winner_pct` («Brecha vs. 1.ª posición») | float \| null | against the official P1 time; `null` when no P1 time exists | ✓ | **never** |
| `gap_to_podium_pct` («Brecha vs. podio») | float \| null | against the official P3 time; `null` when no P3 time exists | ✓ | **never** |
| `gap_to_podium_ms` | int \| null | existing `gap_to_p3_ms` | ✓ | **never** |

**Invariants**:
- **Single source**: every consumer gets these values from the engine and recomputes nothing.
- **Enforced server-side for families**: parent-facing responses omit `gap_to_winner_pct`, `gap_to_podium_pct` and `gap_to_podium_ms`. They are removed from the payload, not merely hidden.
- **Minimum field**: `MIN_FIELD = 5` applies inside the engine.

**Entry points**:
- `compute_field_metrics(...)` (existing, per athlete and season) returns MetricSets keyed by `event_id`.
- `compute_category_metrics(event_id, category_id, rows)` (new) returns MetricSets keyed by `result_id`. It serves the competition detail.

## 2. HistoryPoint (response; `schemas/athlete_race_analysis.py`)

Existing fields are kept (`percentile` changes meaning to time-based). Added:
- `gap_to_podium_pct: float | None`, coach only.

The family variant is serialized without `gap_to_winner_pct` or `gap_to_podium_pct` (they are excluded, not nulled).

`series_kind` is already on each point. Progresión requests `series_kind=all`, and the client splits cups (the line) from championships (the cards).

## 3. EvolutionPoint (response)

`percentile`, `gap_pct` and `gap_to_median_pct` come from the engine. `field_size` follows the Parrilla rule (MINUS_LAPS is now included). `EvolutionMetric.PERCENTILE` returns the engine value. For parents, the winner and podium metrics are rejected with 403 and never computed.

## 4. Competition results row (response; `results_read.py`)

Each result row gains an optional `metrics: MetricSet | null`, filled by `compute_category_metrics`. The parent variant carries the family subset only.

## 5. RaceImport (persisted; `models/race_import.py`)

| Field | Change |
|---|---|
| `status` | Enum **gains `discarded`**. Set only by `POST …/imports/{id}/discard` when the status is `pending` or `dry_run`; discarding a `committed` import is refused (409) |

**State machine**: `pending → dry_run → committed`. `pending | dry_run → discarded`. `* → failed` stays as it is today.

**Migration**: add `discarded` to the enum. The downgrade first updates `discarded` rows to `failed` and then drops the value. The down-revision is the current single head (verify with `alembic heads`; `b4e8d2f61a93` on 2026-09-23).

Rehydration uses the existing `parse_meta_json`, `storage_path` and `status`, with no new columns.

## 6. Identity gate (derived)

`pending_for_import(import) = {c ∈ pending candidates | c.left_record.key ∈ K ∨ c.right_record.key ∈ K}`, where `K` is the set of record keys of the import's rows (R-08).

Commit is allowed iff `pending_for_import` is empty **and** the existing rebuild-needed check passes. There are no schema changes.

## 7. CoachSummaryOut (response; `schemas/dashboard.py`)

| Field | New? | Source |
|---|---|---|
| `consents_pending`, `insights_stale`, `weekly_load` | existing | unchanged |
| `identity_decisions_pending` | new | count of candidates with `state == pending` (the whole queue, for the inbox badge) |
| `imports_in_progress` | new | imports whose status is `pending` or `dry_run` |
| `analyses_awaiting_approval` | new | `AgentRun.status == awaiting_hitl` for the club's athletes |

Coach and admin only; the existing endpoint RBAC applies.

## 8. HITL approval payload (response)

The run/insight payload served to the coach for approval gains:
- `family_gap_mentions: list[str]`. It holds at most 3 matched snippets of 80 characters or fewer, taken from the **family-visible** text fields, that mention the leader, the winner, P1, P3, first or third place, or the podium.

The list is empty when there are no mentions, and it is never sent to parents.

## 9. Stale analysis acknowledgement

`POST /api/race-analysis/runs/{run_id}/dismiss-stale` calls `run_staleness.mark_run_fresh` and records an audit event with `actor`, `run_id` and `action=dismiss_stale`. No schema changes.

## 10. Bitácora change notice (UI state)

This reuses the stage-log `coach_note`. The editor offers «Insertar aviso de cambios» until the coach inserts the notice or dismisses the offer. The dismissal is remembered per coach in `localStorage` (key `tyr:045-notice-dismissed:v1:{userId}`) and holds no athlete data.
