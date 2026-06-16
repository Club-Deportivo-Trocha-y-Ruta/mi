# Contract: Prefill data sourcing (no new API)

This feature introduces **no** new backend endpoint. It composes two existing reads through a new hook `useImportPrefill(raceEventId)`.

## Consumed endpoints (existing, unchanged)

### 1. `GET /api/race-analysis/race-events/{id}` → `RaceEventRead`
Used fields: `series_id`, `sequence_number`, `name`, `event_date`, `location`, `is_championship`, `status`, conditions (`climate`, `temperature_c`, `surface_condition`, `altitude_msnm`, `weather_notes`).
- RBAC: coach/admin (`require_role([admin, coach])`).
- Frontend hook: `useRaceEvent(id)` (`hooks/race/useRaceEvents.ts`).

### 2. `GET /api/race-analysis/race-series` → `{ items: RaceSeriesRead[], total }`
Used to resolve the series for `event.series_id`. `RaceSeriesRead` fields: `id`, `name`, `season_year`, `kind` (`cup`|`championship`).
- Optional query `season` may narrow the list.
- RBAC: coach/admin.
- Frontend hook: `useRaceSeries(...)` (`hooks/race/useRaceSeries.ts`), API client `api/raceSeries.ts`.

## Composition contract (`useImportPrefill`)
```
input:  raceEventId: number
output: ImportPrefill  // see data-model.md

steps:
  1. event   = useRaceEvent(raceEventId)
  2. series  = useRaceSeries(...).find(s => s.id === event.series_id)
  3. if event in error/404            → status "error" (reuse existing error UI)
     else if !series                  → status "blocked" (+ editMetadataHref) [FR-009]
     else                             → status "ready" (+ derived values)
```

## Submission contract (existing `/parse`, unchanged)
The locked prefilled values feed the **existing** `POST /imports/parse` form fields:
`series_name ← series.name`, `season ← series.season_year`, `series_kind ← series.kind`,
`valida_num ← event.sequence_number` (cup only), `event_name ← event.name`,
`event_date ← event.event_date`, `location ← event.location`, conditions as edited.

Because these equal the stored values, `/parse` resolves the same `(series_id, sequence_number)` and links results to the exact competition via its revision/`parent_event_id` path. **No parse-behavior change** (FR-011).

## Privacy contract
Both reads return competition-level metadata only; the prefill view-model excludes anything athlete-identifying. No minor PII is fetched, derived, rendered, or logged before the dry-run match step (FR-013, Constitution privacy gate).
