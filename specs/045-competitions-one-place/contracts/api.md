# API contract changes (045)

The URL prefixes stay as they are. Every changed route keeps its RBAC and needs at least one denied-path test (spec FR-060).

## Changed responses

### `GET /api/athletes/{athlete_id}/race-analysis/history?series_kind=cup|championship|all`
- Progresión calls this with `series_kind=all`.
- **`HistoryPoint`**:
  - `percentile` is now time-based (data-model §1).
  - Adds `gap_to_podium_pct`.
  - `field_size` = Parrilla.
  - `timed_finishers` comes from the engine.
- **Parent**: the response **omits** `gap_to_winner_pct` and `gap_to_podium_pct`.
- **Denied**: a parent asking for an athlete who is not theirs → 404/403 (unchanged).

### `GET /api/athletes/{athlete_id}/race-analysis/evolution?metric=…`
- **Every value comes from the engine**:
  - `percentile` is time-based and gated at n ≥ 5;
  - `field_size` = Parrilla.
- **Parent**: `metric=podium_gap_ms` (or any winner or podium metric) → **403**, and each point omits `gap_pct`.

### `GET /api/athletes/{athlete_id}/race-analysis/distribution`
- **Coach only**, as today.
- The athlete's percentile now comes from the engine.

### Race results reads (`results_read.py`: coach competition detail + parent competition page)
- Each row gains `metrics: MetricSet | null`.
- **Parent variant**: only `field_size`, `timed_finishers`, `position`, `percentile` and `gap_to_median_pct`.

### Athlete insight detail (`routers/athlete_race_analysis.py`)
- **Parent**: the parent redaction adds `gap_to_p3_hhmmss` and every other structured gap-to-leader, P1, P3 or podium field. This part was delivered in phase 0b.

### HITL approval payload (run or insight served to the coach for approval)
- **New field**: `family_gap_mentions: string[]`, with at most 3 snippets of 80 characters or fewer.
- **Parent**: never included.

### `GET /api/dashboard/coach-summary` (`CoachSummaryOut`)
- **Adds**:
  - `identity_decisions_pending: int | null`
  - `imports_in_progress: int | null`
  - `analyses_awaiting_approval: int | null`
- `null` means "unavailable", in which case the row is omitted and never shown as zero.

## Changed behaviour

### `POST /api/race-analysis/imports/{id}/commit` and `…/commit-pending`
- **Gate**: pending candidates **of this import** only (research R-08).
- **Blocked**: `409` with the body
  ```json
  {"detail": "identity_pending", "pending_for_import": 3, "review_path": "/competitions/imports?seccion=identidades&import=<id>"}
  ```
- **Tests**:
  - a pending candidate about another import → commit succeeds;
  - a candidate spanning both imports → blocked;
  - a candidate about a new competitor of this import → blocked.

## New endpoints

### `GET /api/race-analysis/imports/{import_id}`
- **Coach/admin**; club-scoped.
- **Returns**: `{id, status, source_filename, parse_meta, created_at, event_id, season}`, enough to rehydrate the wizard.
- **Parent** → 403. **Another club** → 404.

### `POST /api/race-analysis/imports/{import_id}/discard`
- **Coach/admin**.
- `pending|dry_run` → `discarded`, answering `200` with the import.
- `committed` → `409`. `discarded` again → `200` (idempotent).
- **Parent** → 403.

### `POST /api/race-analysis/runs/{run_id}/dismiss-stale`
- **Coach/admin**.
- Marks a stale run as fresh and writes an audit event, answering `200`.
- **Not stale** → `409`. **Parent** → 403.

### `GET /api/race-analysis/pending-analyses?season=YYYY&state=awaiting_approval|stale`
- **Coach/admin**; club-scoped. Serves the analyses list in «Temporada» (research R-11).
- **Returns**: `[{run_id, insight_id|null, athlete_id, athlete_ref, event_id|null, event_label, state, updated_at}]`.
  - `athlete_ref` is the display name the coach UI already uses. It is never logged.
  - For each `state`, the items are exactly the ones counted by `analyses_awaiting_approval` or `insights_stale` (SC-005).
- **Parent** → 403. **Unknown `state`** → 422.

### HITL step payload (`GET /api/race-analysis/runs/{run_id}/status`, awaiting-HITL event)
- The event that carries the draft for approval adds `family_gap_mentions: string[]` (data-model §8).
