# Phase 1 Data Model: Prefill results import from an existing competition

Date: 2026-06-16 · Branch: `015-prefill-import-from-competition`

> **No persistence changes.** This feature adds **no** tables, columns, enums, or migrations (FR-012). It defines a frontend **read/view-model** composed from existing backend reads. Documented below for design clarity.

## Source entities (existing — read only)

### RaceEvent (`race_events`) — via `GET /race-events/{id}` → `RaceEventRead`
| Field | Type | Use in prefill |
|---|---|---|
| `id` | int | competition identity / link scope |
| `series_id` | int (FK, non-null) | resolve the series (kind + name + season) |
| `sequence_number` | int | `válida #` (cup only; hidden for championship) |
| `name` | str | event name (locked) |
| `event_date` | date | event date (locked) |
| `location` | str? | city (locked) |
| `is_championship` | bool | hide `válida #`; badge consistency |
| `status` | enum scheduled\|completed\|cancelled | gating of the import CTA (existing behavior) |
| `climate`, `temperature_c`, `surface_condition`, `altitude_msnm`, `weather_notes` | optional | prefill conditions (remain **editable**) |

### RaceSeries (`race_series`) — via `GET /race-series` → `RaceSeriesRead[]`, filtered by `series_id`
| Field | Type | Use in prefill |
|---|---|---|
| `id` | int | match against `event.series_id` |
| `name` | str | series name (locked) |
| `season_year` | int | season (locked) |
| `kind` | enum `cup` \| `championship` | **derive** "Tipo de competencia"; drives `válida #` visibility |

## View-model: `ImportPrefill` (new, frontend-only)

Produced by `useImportPrefill(raceEventId)` by composing the two reads above.

```ts
type ImportPrefillStatus = "loading" | "ready" | "blocked" | "error";

interface ImportPrefill {
  status: ImportPrefillStatus;
  raceEventId: number;
  // present when status === "ready"
  values?: {
    series_kind: "cup" | "championship"; // derived from series.kind — NOT user-editable
    series_name: string;                 // locked
    season: number;                      // locked
    valida_num: number | null;           // locked; null when championship
    event_name: string;                  // locked
    event_date: string;                  // locked (ISO yyyy-mm-dd)
    location: string;                    // locked
    conditions?: {                       // prefilled but EDITABLE
      climate?: string;
      temperature_c?: number;
      surface_condition?: "seca" | "humeda" | "barro" | "lluvia" | "mixta";
      altitude_msnm?: number;
      weather_notes?: string;
    };
  };
  // present when status === "blocked" (FR-009)
  editMetadataHref?: string; // `/competitions/${raceEventId}/edit`
}
```

### Derivation rules
- `series_kind = series.kind` (never chosen in-flow — FR-005).
- `valida_num = is_championship ? null : event.sequence_number`; the field is **hidden** when championship (FR-008).
- All identity fields are **locked/read-only** (FR-004); conditions stay editable (existing behavior).

### State transitions
```
mount(raceEventId)
  → loading
      → ready    (event loaded AND series resolved from series_id)
      → blocked  (series_id cannot be resolved to a series → FR-009; offer editMetadataHref)
      → error    (event fetch failed / 404 → existing error handling)
standalone wizard (raceEventId == null)
  → no ImportPrefill produced; wizard behaves exactly as today (FR-007)
```

## Validation rules (unchanged Zod schema)
- The existing `ImportWizard` Zod schema is reused. `series_kind` is set programmatically via `reset()`; `valida_num` required only for `cup` (existing refinement). Prefill does not relax or alter validation — it pre-populates and locks the identity inputs.

## Invariants
- **Privacy**: `ImportPrefill` carries only competition-level metadata already visible on the detail "Información" card; no minor PII (name/DOB/medical) is read, derived, logged, or rendered (FR-013).
- **No new metadata**: no field beyond those already stored on `race_events` / `race_series` is introduced (FR-012).
- **Link integrity**: prefilled values are the stored values, so the import resolves to the same `(series_id, sequence_number)` and links to the exact competition (FR-003).
