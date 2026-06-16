# Contract — `GET /api/athletes/{athlete_id}/race-analysis/races`

**Status**: NEW (this feature) · **Consumers**: Distribution chart race picker

Returns the races an athlete actually competed in during a season — the source of truth for the
picker (FR-003/004/005). Read-only.

## Request

```
GET /api/athletes/{athlete_id}/race-analysis/races?season=2026
Authorization: Bearer <jwt>
```

| Param | In | Type | Rules |
|---|---|---|---|
| `athlete_id` | path | int | `ge=1` |
| `season` | query | int | required, `ge=2020`, `le=2100` |

**RBAC**: admin, coach, and the parent of this athlete (reuse `verify_athlete_access`). Others → 403.

## Response `200` — `RaceParticipationResponse`

```json
{
  "season": 2026,
  "items": [
    { "event_id": 11, "sequence_number": 4, "series_kind": "cup",
      "event_date": "2026-05-17", "event_name": "Válida IV Cali", "location": "Cali",
      "label": "Válida IV — Cali" },
    { "event_id": 21, "sequence_number": 1, "series_kind": "championship",
      "event_date": "2026-06-12", "event_name": "Campeonato Departamental", "location": "Ginebra",
      "label": "Cto. Dep. — Ginebra" }
  ]
}
```

- `items` contains **only** races the athlete competed in (any status, incl. DNF), ordered by
  `event_date` ascending.
- A cup round and a championship that historically shared a round number appear as **two distinct
  items** with distinct `event_id` (SC-004).
- Contains no `athlete_id` / `competitor_id` / user ids.

## Errors

| Status | When |
|---|---|
| `401` | missing/invalid token |
| `403` | caller is a parent of a different athlete |
| `404` | `athlete_id` does not exist / not visible to caller |
| `422` | `season` out of range |

> The `200` body for an athlete with **zero** competed races is `{ "season": …, "items": [] }`
> (the frontend then shows only the synthetic "Temporada (todas)" entry + a friendly empty state).

## Acceptance mapping

FR-003 (lists competed races, excludes non-competed) · FR-004 (each tied to `event_id`, no
collision) · FR-005 (real name + round marker label) · SC-004 (zero ambiguous options).
