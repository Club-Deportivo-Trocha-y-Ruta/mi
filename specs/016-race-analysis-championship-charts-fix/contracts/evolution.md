# Contract — `GET /api/athletes/{athlete_id}/race-analysis/evolution`

**Status**: CHANGED (additive: `EvolutionPoint` gains `series_kind` + `label`)
**Consumers**: Evolution chart only

## Request — unchanged

```
GET /api/athletes/{athlete_id}/race-analysis/evolution?season=2026&metric=podium_gap_ms
Authorization: Bearer <jwt>
```

| Param | In | Type | Rules |
|---|---|---|---|
| `athlete_id` | path | int | `ge=1` |
| `season` | query | int | `ge=2020`, `le=2100` |
| `metric` | query | enum | `podium_gap_ms`(default) \| `ranking` \| `time_ms` \| `percentile` |

## Response `200` — `EvolutionResponse`

```json
{
  "season": 2026,
  "metric": "podium_gap_ms",
  "series": [
    { "event_id": 11, "sequence_number": 4, "valida_num": 4, "series_kind": "cup",
      "label": "Válida IV — Cali", "event_date": "2026-05-17", "value": 41000.0, "unit": "ms" },
    { "event_id": 21, "sequence_number": 1, "valida_num": 1, "series_kind": "championship",
      "label": "Cto. Dep. — Ginebra", "event_date": "2026-06-12", "value": 53000.0, "unit": "ms" }
  ],
  "confidence": "high"
}
```

**New fields per point** (additive):

| Field | Type | Purpose |
|---|---|---|
| `series_kind` | `"cup" \| "championship"` | Frontend labels the championship as its own marker (FR-011). |
| `label` | `str` (`min_length=1`) | Server-built display label; chart never re-derives identity from a round number. |

- `event_id` is the unique key — two `sequence_number=1` races (cup Válida I + championship) no
  longer merge on the categorical axis (FR-009).
- `event_date` drives chronological order; the championship lands between the May and August cup
  rounds (FR-010). Ordering already exists server-side.
- DNF/DNS/DSQ → `value=null` (listed below the chart, behavior unchanged).

## Errors — unchanged (`401`/`403`/`404`/`422`).

## Acceptance mapping

FR-009 (championship as one distinct point) · FR-010 (chronological by date) · FR-011 (labeled as
championship, not a cup round) · SC-003.
