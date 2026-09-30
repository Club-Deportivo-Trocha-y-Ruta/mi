# API contract: feature 048

All routes need authentication. Roles: `admin` and `coach`, unless stated otherwise. `verify_athlete_access` applies the club scope (feature 041): a coach of another club gets **403**; archived or unknown athletes return 404.

Error bodies use the `{"detail": "<code>", ...}` shape. The frontend owns the Spanish copy for each code.

## Changed: `POST /api/athletes/{athlete_id}/anthropometry`

The body is unchanged: `AnthropometryCreate`. Validation now also runs on the server:
- `weight_kg` 20–150
- `standing_height_cm` 100–220
- `sitting_height_cm` 50–120
- `arm_span_cm` 100–220 or null
- `evaluation_date` not in the future

New responses:
- **422 `sitting_ratio_impossible`**: sitting / standing is outside [0.40, 0.65].
- **409 `anthropometry_same_date_exists`**, with this body:

```json
{ "detail": "anthropometry_same_date_exists", "existing_record_id": 812, "same_values": true }
```

`same_values` compares weight, standing height, sitting height and arm span with the stored record. The frontend treats `same_values: true` during a retry as "already saved" (R4).

Everything else stays the same: 201 `AnthropometryOut`, the approaching-circa-PHV notification, and the `create` audit.

## Changed: `GET /api/athletes/{athlete_id}/anthropometry`

For coach and admin, each item gains:

```json
{ "can_modify": true, "plausibility_flags": ["height_decreased"] }
```

- **`can_modify`**: `user.role == admin` or `record.evaluated_by == user.id`.
- **`plausibility_flags`**: computed at read time against the previous record by date (R5).
- For parents, both keys are **omitted**, not null. A test asserts this.

## New: `PUT /api/athletes/{athlete_id}/anthropometry/{record_id}`

The body is the same shape and validation as POST: `AnthropometryUpdate`, which is `AnthropometryCreate` with every field required except `arm_span_cm` and `notes`. It is a full replacement of the editable fields.

| Status | When |
|---|---|
| 200 `AnthropometryOut` | Saved. Derived fields are recomputed, AI explanations for the record are deleted, and skinfold estimates are recomputed if the weight changed. |
| 403 `not_record_author` | The caller is neither the record's evaluator nor an admin. |
| 404 | The record is missing or belongs to another athlete (or the athlete is archived/unknown). |
| 409 `anthropometry_same_date_exists` | The new date collides with another record of the athlete. |
| 409 `{"detail": {"code": "athlete_too_young" \| "skinfold_interval_too_short", "next_allowed_date"?}}` | The date changed on a record with a skinfold set and breaks the 046 rules (same nested shape as the 046 wizard). The interval is checked in both directions: against earlier and later skinfold sets. In the forward case (the new date falls before a LATER set), `previous_set_date` carries the date of that LATER set and `next_allowed_date` = later set date + minimum interval. |
| 422 | Validation failed, as in POST. |

A PUT whose values are identical to the stored record is a no-op: no write, no audit, AI explanations kept.

Side effects:
- A `update` audit with `changed_fields`.
- One audit per deleted AI explanation.
- No notification is ever sent (R3).

## New: `DELETE /api/athletes/{athlete_id}/anthropometry/{record_id}`

| Status | When |
|---|---|
| 204 | Deleted, together with its skinfold set and AI explanations. |
| 403 `not_record_author` | The caller is not the evaluator or an admin. |
| 404 | Missing or foreign record. |

Side effects: a `delete` audit with `meta={"had_skinfolds": bool}`.

## New: `POST /api/athletes/{athlete_id}/anthropometry/plausibility`

This is a dry run. It writes nothing and produces no audit row, but it is registered in the route-policy map as non-mutating.

Request:

```json
{
  "evaluation_date": "2026-09-29",
  "weight_kg": 41.2,
  "standing_height_cm": 152.3,
  "sitting_height_cm": 78.1,
  "arm_span_cm": null,
  "record_id": null
}
```

- `record_id` is set when editing, so the record being edited is excluded from "previous".
- The request runs the same validation as POST. A 422 is returned only for hard-range violations.

Response 200:

```json
{
  "warnings": [
    { "code": "weight_change_large", "measure": "weight" },
    { "code": "sitting_ratio_atypical", "measure": "sitting_height" }
  ],
  "previous_evaluation_date": "2026-06-10"
}
```

`previous_evaluation_date` is null on a first evaluation.

## New: `GET /api/anthropometry/roster?date=YYYY-MM-DD`

This returns the non-archived athletes the caller may access, in a bounded number of queries. The query-count test asserts ≤ 4.

```json
[
  {
    "athlete_id": 17,
    "full_name": "…",
    "category": "Infantil",
    "sex": "F",
    "birth_date": "2013-04-02",
    "last_evaluation_date": "2026-06-10",
    "has_record_on_date": false,
    "skinfolds_eligible": true
  }
]
```

- `date` defaults to today and cannot be in the future (422).
- `skinfolds_eligible` requires age ≥ 9 at `date` and an open 90-day interval.
- The router is mounted at `/api/anthropometry` in `app/main.py`.

## Changed: `GET /api/body-composition/field-guide.pdf`

- The route and roles are unchanged.
- The document now opens with a "Antes de medir" section (the pre-check conditions) and one section per basic measure: Peso, Talla de pie, Talla sentado, Envergadura. Each section carries its illustration and «Dónde»/«Cómo» text, read from `backend/app/data/anthropometry_measures.json`.
- The skinfold sections follow, unchanged.
