# API Contract Delta — National Championship Support (Series Level)

**Feature**: 023-national-championship-level | **Date**: 2026-07-08

No new endpoints. Additive field changes only. All routes keep existing auth (coach/admin write, authenticated read) and status codes.

## 1. `POST /api/race-analysis/race-series` (modified)

**Request** — `RaceSeriesCreate` gains optional `level`:

```jsonc
{
  "name": "Campeonato Nacional MTB 2026",
  "season_year": 2026,
  "kind": "championship",
  "organizer": "Federación Colombiana de Ciclismo",   // client-provided, NOT overridden
  "level": "national"                                  // NEW, optional, default "departmental"
}
```

**Rules**:
- `level` omitted → `departmental` (full backward compatibility; pre-023 clients unaffected).
- `level` invalid value → **422**.
- `level` accepted for any `kind` but only surfaced in UI for championships.
- Existing 409 (name+season duplicate) unchanged.

**Response** — `RaceSeriesRead` gains required `level`:

```jsonc
{
  "id": 12,
  "name": "Campeonato Nacional MTB 2026",
  "season_year": 2026,
  "organizer": "Federación Colombiana de Ciclismo",
  "kind": "championship",
  "level": "national",          // NEW — always present
  "event_count": 0
}
```

## 2. `GET /api/race-analysis/race-series` (modified response only)

Each list item includes `level`. No new query params (filtering by level not required — FR-012 filters by kind, which matches both levels).

## 3. Results import upload (modified)

`POST /api/race-imports/upload` (multipart) gains optional form field:

| Field | Type | Default | Rule |
|---|---|---|---|
| `series_level` **(NEW)** | string enum `departmental\|national` | `departmental` | Only consulted when a **new** series is created by `_get_or_create_series`; ignored when resolving an existing series. Invalid value → 422. |

**Behavior change (FR-006)**: when `_get_or_create_series` creates a **championship** series, the organizer default `"Liga Vallecaucana de Ciclismo"` is NOT applied (organizer = NULL unless provided by another mechanism). Cup creation keeps today's defaults, byte-identical.

**Unchanged**: `/parse` → `/dry-run` → `/commit` flow, competition-linked import (feature 015 prefill via explicit `series_id`), all response schemas.

## 4. `GET /api/athletes/{id}/race-analysis/races` and evolution serializer (modified label values only)

No schema change — the `label` string values become level-aware:

| Case | Before | After |
|---|---|---|
| Departmental championship | `"Cto. Dep. — Ginebra"` | `"Cto. Dep. — Ginebra"` (unchanged) |
| National championship | *(would render "Cto. Dep. — Pereira")* | `"Cto. Nal. — Pereira"` |
| Cups | `"Válida IV — Cali"` | unchanged |

## 5. Notifications (body copy, not an API)

Race-insight emails/in-app referencing a championship event use the level-correct label:

| Series level | Label |
|---|---|
| departmental | `Campeonato Departamental` (regression-guarded) |
| national | `Campeonato Nacional` |

Tier semantics (`RaceTier.CD`) unchanged for both.

## Explicit non-changes (guard rails)

- `GET/POST /api/race-events*`: no schema change (`is_championship`, `sequence_number` derivation untouched).
- Standings / season panorama endpoints: responses byte-identical with or without national championship results (SC-004).
- Monthly report endpoints (feature 022): grouping contract untouched; national event appears as its own jornada with `awards_points=false` via existing logic.
- No endpoint mutates `level` after creation.
