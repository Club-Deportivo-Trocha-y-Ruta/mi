# Contract — `GET /api/athletes/{athlete_id}/race-analysis/distribution`

**Status**: CHANGED (race identity `valida_num` → `event_id`; invalid empty fallback removed)
**Consumers**: Distribution chart only (`api/athleteRaceAnalysis.ts`)

## Request

```
GET /api/athletes/{athlete_id}/race-analysis/distribution?event_id=21
Authorization: Bearer <jwt>
```

| Param | In | Type | Rules | Change |
|---|---|---|---|---|
| `athlete_id` | path | int | `ge=1` | — |
| `event_id` | query | int | required, `ge=1` | **replaces** `valida_num` |

**RBAC**: admin/coach/parent-of-athlete. `display_name` populated only for coach/admin
(`include_display_name`); parents receive pseudonyms only (FR-013).

## Response `200` — `DistributionResponse`

Shape unchanged **except** the race-identity field:

```json
{
  "season": 2026,
  "event_id": 21,
  "category_id": 7,
  "category_code": "INFANTIL-A",
  "sample_size": 12,
  "mean_ms": 2731000.0,
  "stddev_ms": 96000.0,
  "athlete_time_ms": 2680000,
  "athlete_z_score": -0.53,
  "athlete_percentile": 70.0,
  "points": [ { "pseudonym": "C2531", "time_ms": 2604000, "is_self": false, "display_name": null } ],
  "curve":  [ { "x_ms": 2604000.0, "density": 1.2e-6 } ],
  "confidence": "high"
}
```

### No-comparable-data (DNF / field too small) — still `200`, valid payload

`category_id`/`category_code` are real (the athlete's own result row is always found via
`event_id`); `athlete_time_ms` may be `null`, `curve=[]`, `confidence="low"`. The frontend renders
the friendly "no data for this race" state (FR-002). **Never** returns `category_id=0` /
`category_code=""` (the schema-violating fallback is removed).

## Errors

| Status | When |
|---|---|
| `401` | missing/invalid token |
| `403` | parent of a different athlete |
| `404` | `event_id` is not a race this athlete competed in (clean 404, no identifying data in body) |
| `422` | `event_id` missing / `< 1` |

**Regression guard**: this endpoint MUST NOT raise `500` for the championship or any no-data race
(SC-001/SC-002). A pre-fix `valida_num=99` request produced `ResponseValidationError` (500); the
test asserts the fixed `event_id` request returns `200`.

## Acceptance mapping

FR-001 (no error/blank) · FR-002 (friendly no-data) · FR-006 (championship's own category) ·
FR-008 (working races unchanged) · FR-013/014 (privacy preserved).
