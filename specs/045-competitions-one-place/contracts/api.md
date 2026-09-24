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
- **Coach/admin only.** A parent (own child included) → **403** before any query; the body never reaches a family because `points[].time_ms` lists every rider's time (owner decision, 2026-09-23).
- The athlete's percentile now comes from the engine.

### Race results reads (`results_read.py`: coach competition detail + parent competition page)
- Each row gains `metrics: MetricSet | null`.
- **Parent variant**: only `field_size`, `timed_finishers`, `position`, `percentile` and `gap_to_median_pct`.

### Athlete insights (`routers/athlete_race_analysis.py`: list and detail)
- **Parent**: the parent redaction adds `gap_to_p3_hhmmss` and every other structured gap-to-leader, P1, P3 or podium field. This part was delivered in phase 0b.
- **Parent, detail**: `metrics_snapshot` is an allow-list (`progression_assessment` only).
- **Parent, v3 rows** (`structured_json` present): `summary_text` (list and detail), `recommendations` and top-level `principles_cited` are **omitted** (keys absent, not null); `structured.principles_cited` stays. Pre-v3 and fallback rows keep their text. Coach/admin are unchanged (owner decision, 2026-09-23).

### HITL approval payload (run or insight served to the coach for approval)
- **New field**: `family_gap_mentions: string[]`, with at most 3 snippets of 80 characters or fewer.
- **Parent**: never included.

### `GET /api/dashboard/coach-summary` (`CoachSummaryOut`)
- **Adds**:
  - `identity_decisions_pending: int | null`
  - `imports_in_progress: int | null`
  - `analyses_awaiting_approval: int | null`
  - `unlinked_competitors_pending: int | null` — competitors still unlinked from a club athlete. It is the `total` of the «Sin enlazar» list at its defaults (`GET /api/race-competitors/?unlinked=true&club_filter=trocha`), computed from the same base query (`competitor_linking._unlinked_base_stmt` + the «Trocha y Ruta» club refinement), so count == list (FR-033, SC-005). Not club-id scoped (competitors carry no `club_id`; the club filter is the scope, like `identity_decisions_pending`). Coach/admin only; parents get 403. It only feeds the «Cargas e identidades» menu badge (`identity_decisions_pending + imports_in_progress + unlinked_competitors_pending`, each term skipped when `null`/absent) and has no «Pendientes» row.
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
- **Returns**: `{id, status, source_filename, parse_meta, created_at, event_id, season, parent_committed_at}`, enough to rehydrate the wizard. `parent_committed_at` has the same meaning as in the `/parse` response (when the previous version of the same válida was committed, for the revision notice); it is set only for a `pending`/`dry_run` import whose válida is already committed, `null` otherwise.
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
- **Returns**: `[{run_id, insight_id|null, athlete_id, athlete_ref, event_id|null, event_label, season|null, kind|null, state, updated_at}]`.
  - `athlete_ref` is the display name the coach UI already uses. It is never logged.
  - `kind` is `"valida"` | `"season_summary"` | `null` (owner decision 2026-09-23: season summaries can be re-run from «Temporada»). It is presentation only and never changes membership. For `stale` items it comes from the active insight (`valida_num == 0` or `use_case` starting with `season_summary` → `season_summary`; `valida_num > 0` or an `event_id` → `valida`). For `awaiting_approval` items it comes from `agent_runs.input_json` (`analysis_kind == "season"` or `valida_nums == [0]` → `season_summary`; an `event_id`, `analysis_kind == "valida"` or positive `valida_nums` → `valida`). With no signal it is `null`: it is never guessed.
  - «Re-ejecutar» (stale items only): `season_summary` with a `season` → `POST /api/athletes/{id}/race-analysis/season-summary` with `{season}` (exact season, not the current year); otherwise an item with `event_id` → `POST …/race-analysis/runs` with `{season, event_id}`; anything else offers only open and dismiss.
  - For each `state`, the items are exactly the ones counted by `analyses_awaiting_approval` or `insights_stale` (SC-005).
- **Parent** → 403. **Unknown `state`** → 422.

### HITL step payload (`GET /api/race-analysis/runs/{run_id}/status`, awaiting-HITL event)
- The event that carries the draft for approval adds `family_gap_mentions: string[]` (data-model §8).
