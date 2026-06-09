# Contract: Race-Event Group Runs

Base: `/api/race-analysis/race-events/{race_event_id}` — Auth: Bearer JWT, roles `coach | admin` (`require_role`), `AI_ENABLED` gated.

## POST /runs — launch group analysis

Request body:
```json
{
  "athlete_ids": [12, 15],        // optional; omit/null = all club athletes with results in event
  "explain_mode": false
}
```

Responses:
- **200 OK** (also for partial starts):
```json
{
  "race_event_id": 42,
  "season": 2026,
  "valida_num": 3,
  "started_count": 9,
  "skipped_count": 2,
  "items": [
    {"athlete_id": 12, "athlete_display_name": "Juan P.", "run_id": "a1b2…", "outcome": "started", "detail": null},
    {"athlete_id": 15, "athlete_display_name": "Sofía R.", "run_id": null, "outcome": "backpressure",
     "detail": "Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos."},
    {"athlete_id": 18, "athlete_display_name": "Mateo G.", "run_id": null, "outcome": "already_running",
     "detail": "Ya hay un análisis en curso para este deportista."}
  ]
}
```
- **422**: event has no committed club results → `{"detail": "La competencia no tiene resultados importados."}`
- **503**: budget guard tripped before any run started (existing `BudgetExceededError` mapping)
- **429**: zero runs could start, all blocked by backpressure
- **404 / 401 / 403**: standard

Behavior:
1. Resolve event → `season = race_series.season_year`, `valida_num = race_events.sequence_number` (404 if event missing, 422 if `sequence_number` null or no results).
2. Resolve members: distinct `race_results.athlete_id` for event, `deleted_at IS NULL`, intersected with `athlete_ids` filter when given.
3. `check_budget(db)` once up front (503 short-circuit).
4. For each member: skip with `already_running` if an active run exists for `(athlete, season, valida)`; else `submit_run()` with `StartRunRequest(athlete_id, season, valida_nums=[valida_num], explain_mode)`; catch `RunBackpressureError` → `backpressure` item; unexpected per-athlete failure → `error` item (others continue).
5. Every started run is a **standard run**: same HITL gate, events, persistence, staleness, usage metrics as today (FR-003, FR-009, FR-014).

## GET /runs?active_only=true — list runs for refresh recovery

Response **200**:
```json
{
  "race_event_id": 42,
  "runs": [
    {"run_id": "a1b2…", "athlete_id": 12, "athlete_display_name": "Juan P.",
     "state": "awaiting_hitl", "started_at": "2026-06-09T18:02:11Z", "stale": false}
  ]
}
```
- `active_only=false` additionally returns terminal runs of the last 7 days for the event.
- Resolution mirrors `run_staleness.invalidate_runs_for_event()` (input_json season/valida match + athlete-in-event).
- Roles `coach | admin`; 404 unknown event.

## Frontend consumers
- `launchGroupAnalysis(raceEventId, body)` / `getRaceEventRuns(raceEventId, {activeOnly})` in `src/api/raceAnalysis.ts`.
- `useGroupAnalysis(raceEventId)` hook: mutation + recovery query (key `["race-analysis", "event-runs", raceEventId]`) + per-run `useRunStatus` aggregation; invalidates `["club-insights-by-race", raceEventId]` when any run completes.
