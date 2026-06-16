# API Contract: Race Series + Series-Type-Aware Event/Import

**Feature**: 014-cup-vs-championship-series
**Base path**: `/api/race-analysis`
**Auth**: coach/admin (`require_role([admin, coach])`) for all write endpoints.

All schemas Pydantic v2, `extra="forbid"` on write bodies. No minor PII fields.

---

## 1. NEW — `GET /race-series`

List series, used by the frontend to populate the series picker (replaces the
hardcoded `COPA_VALLE_SERIES`).

Query params:
| Param | Type | Required | Notes |
|---|---|---|---|
| season | int | no | filter by `season_year` |
| kind | `cup`\|`championship` | no | filter by series kind |

Response `200` — `RaceSeriesListResponse`:
```json
{
  "items": [
    { "id": 2, "name": "Copa Valle de Ciclomontañismo", "season_year": 2026,
      "organizer": "Liga Vallecaucana de Ciclismo", "kind": "cup",
      "event_count": 5 },
    { "id": 9, "name": "Campeonato Departamental 2026", "season_year": 2026,
      "organizer": "Liga Vallecaucana de Ciclismo", "kind": "championship",
      "event_count": 1 }
  ],
  "total": 2
}
```

---

## 2. NEW — `POST /race-series`

Create a series (needed to create a championship before its event).

Body — `RaceSeriesCreate`:
```json
{
  "name": "Campeonato Nacional 2026",
  "season_year": 2026,
  "kind": "championship",
  "organizer": "Federación Colombiana de Ciclismo"
}
```
Rules:
- `name` 1..150; `season_year` 2020..2100; `kind` ∈ {cup, championship}.
- `organizer` optional (≤150).
- `points_scheme_code` is **not** client-supplied; server defaults to
  `copa_valle_2026` (D5).

Responses:
- `201` → `RaceSeriesRead` (same shape as list item).
- `409` → `(name, season_year)` already exists.
- `422` → validation error.

---

## 3. CHANGED — `POST /race-events`

Body `RaceEventCreate` (modified):
| Field | Before | After |
|---|---|---|
| series_id | required | required |
| sequence_number | required 1..99 | **optional**; ignored/forced to `1` when series is championship; required 1..N when series is cup |
| is_championship | client bool | **derived from series.kind** (client value ignored) |
| name, event_date, location, status, conditions, create_calendar_event | unchanged | unchanged |

Server logic:
1. Load target series; read `series.kind`.
2. If `kind=championship`:
   - If the series already has ≥1 event → **`409`** with message
     "Un campeonato representa un único evento anual; esta serie ya tiene su evento."
   - Force `sequence_number=1`, `is_championship=true`.
3. If `kind=cup`:
   - `sequence_number` required; uniqueness within series enforced as today (`409`
     on duplicate).
   - `is_championship=false`.

Responses: `201` `RaceEventRead` · `409` (championship-already-has-event OR
duplicate cup round) · `422`.

---

## 4. CHANGED — `POST /import/parse` (results import, step 1)

New Form field:
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| series_kind | `cup`\|`championship` | no | `cup` | backward-compatible |

Behavior:
- `series_name` is now **honored** (bug fix): the series is resolved/created by
  `(series_name, season, series_kind)` — no longer hardcoded to Copa Valle.
- `series_kind=championship` → `valida_num` is ignored and the created/target event
  uses `sequence_number=1`, `is_championship=true`; the championship single-event
  invariant (§3 rule 2) applies on commit (`409` if a second event would be created).
- `series_kind=cup` → unchanged behavior; `valida_num` required as today.
- `detect_revision` receives the real `series_name` (not the `_SERIES_NAME` literal).

Responses: unchanged set (`200` parse response, `409` duplicate SHA, `422` parse
failure) plus `409` if a championship series would receive a second event.

---

## 5. CHANGED — `GET /race-events/{id}/standings`

- If the event's series is `kind=cup` → unchanged season standings payload.
- If the event's series is `kind=championship` → standings are **not applicable**;
  endpoint returns an empty standings payload (no categories) or `404`-style
  "no standings for championship". The frontend hides the standings/ranking tab for
  championships.

---

## 6. UNCHANGED but newly correct — season panorama

`GET` season panorama (`/competitions/insights/season/:year` backend) now excludes
all `kind=championship` results from the cumulative ranking (SQL filter
`rs.kind='cup'`). No contract shape change; the numbers simply no longer include
championships.

---

## Error message catalog (es-CO, user-facing)

| Code | Condition | Message |
|---|---|---|
| 409 | 2nd event in championship series | "Un campeonato representa un único evento anual; esta serie ya tiene su evento." |
| 409 | duplicate cup round | "Ya existe una válida con este número en la temporada. Elige otro número." (existing) |
| 409 | duplicate series | "Ya existe una serie con ese nombre para la temporada." |
