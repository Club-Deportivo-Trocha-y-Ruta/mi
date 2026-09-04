# Contract — `GET /api/athletes/{athlete_id}/growth-summary`

**Router**: `backend/app/routers/growth.py` (mounted under `/api` like today's `/growth-reference`; path is athlete-scoped so it can also live in `routers/anthropometry.py` — implementer's choice, one place).
**Auth**: bearer JWT; dependency `verify_athlete_access` (admin: any; coach: athletes of their clubs; parent: linked athletes only).
**Schema**: `app/schemas/growth.py::GrowthSummaryOut` (mirror in `frontend/src/schemas/growth.schemas.ts` with Zod, and `types/growth.types.ts`).

## Response `200`

```json
{
  "athlete_id": 2,
  "computed_at": "2026-09-04",
  "records_count": 3,
  "latest_evaluation_date": "2026-08-14",
  "stage": "Post-PHV",
  "maturity_offset": 1.2,
  "age_at_phv": 12.9,
  "months_from_phv": 16.4,
  "velocity": {
    "cm_per_month": 0.31,
    "cm_per_year": 3.7,
    "window_days": 101,
    "interval_short": false,
    "expected_cm_per_year": [1.0, 4.0]
  },
  "measurement": {
    "status": "ok",
    "interval_days": 120,
    "next_due_date": "2026-12-12",
    "days_overdue": null
  },
  "alerts": [],
  "latest": {
    "record_id": 41,
    "growth_source": "WHO",
    "height": { "value": 150.0, "z_score": -1.66, "percentile": 4.8, "band": "riesgo_retraso_talla" },
    "bmi": { "value": 21.9, "z_score": 0.70, "percentile": 75.7, "band": "adecuado" },
    "weight": null
  }
}
```

Field semantics and derivations: see `data-model.md` §3. Values above are illustrative, not from a real athlete.

### Variants

| Situation | Response |
|---|---|
| No records | `200` with `records_count: 0`, `stage: null`, `velocity: null`, `measurement.status: "never"`, `latest: null`, `alerts: []` |
| One record | `velocity: null`; everything else populated |
| Two records < 30 days apart | `velocity.interval_short: true`; `rapid_growth` never in `alerts` |
| Age at latest evaluation outside 61.5–228.5 months | `latest.height` / `latest.bmi` = `null`; stage still populated |
| Latest row not yet recomputed | `latest.growth_source: null` (or `"CDC"`); client shows "referencia anterior" note |

## Errors

| Code | When | Body |
|---|---|---|
| `401` | no/invalid token | standard |
| `403` | parent not linked to the athlete; coach outside the athlete's club | `{"detail": "No tienes acceso a este atleta"}` (existing dependency text) |
| `404` | athlete does not exist | `{"detail": "Atleta no encontrado"}` |

## Non-functional

- One SQL query for the two latest records (`ORDER BY evaluation_date DESC LIMIT 2`) plus the athlete already loaded by the dependency; p95 ≤ 500 ms.
- No names, birth dates or notes in the response beyond `athlete_id`; nothing logged except the athlete id on error.
- Response is not persisted on the device (query key excluded from `persistAllowList`).

## Tests (backend, `tests/routers/test_growth_summary.py`)

1. coach of the club → 200, full body; 2. admin → 200; 3. linked parent → 200; 4. unlinked parent → 403; 5. unknown athlete → 404; 6. no records → `never` variant; 7. one record → `velocity: null`; 8. short interval → `interval_short` true and no `rapid_growth`; 9. rapid growth (≥ 0.6 cm/month over ≥ 30 days) → alert present; 10. Circa stage → `circa_phv` alert and `interval_days: 30`; 11. privacy invariant: response JSON contains no `first_name`/`last_name`/`birth_date` keys.
