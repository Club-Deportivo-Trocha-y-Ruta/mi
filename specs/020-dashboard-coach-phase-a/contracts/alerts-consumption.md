# Contract: Dashboard consumption of the EXISTING `GET /api/alerts`

Phase A introduces **no new API**. This documents the read-only consumption contract the dashboard now depends on. The backend endpoint is unchanged.

## Endpoint (existing)

`GET /api/alerts` — auth: coach/admin (`require_role([admin, coach])`).

- **Query params**: `club_id?: int` (optional). **Dashboard calls it with NO `club_id`.**
- **Scoping (server-side, unchanged)**:
  - coach → union of the coach's own clubs (`_coach_club_ids`); a coach with 0 clubs → empty `athletes` + zeroed counts.
  - admin → all clubs, or a single club if `club_id` given (unchanged; out of Phase A scope).
- **Response**: `AlertsSummary` (see `data-model.md`).

## Fields the dashboard relies on

| Field | Used for |
|---|---|
| `athletes[].measurement_status` | actionable filter, urgency sort, PHV vigency (V) |
| `athletes[].days_overdue` | urgency sort within `overdue`/`due_soon` |
| `athletes[].last_measurement_date` | "Última evaluación" card (max) |
| `athletes[].athlete_id` / `athlete_name` | list rows + `/athletes/{id}` links |
| `athletes[].current_phv_status` | existing status chip in list |
| `athletes[].growth_alerts` | rapid-growth block filter (`rapid_growth`) |
| `athletes[].growth_velocity_cm_month` | rapid-growth line |
| `athletes[].training_implications` | **NEW surface** in rapid-growth block (FR-007) |
| `athletes.length` | "Total atletas" + PHV total (A) |
| summary `overdue/due_soon/ok/never_measured` | existing summary chips |

## Guarantees the dashboard assumes (must hold / be tested)

- **G1 (scope)**: Response never contains an athlete outside the coach's clubs. Verified by cross-club isolation test (FR-005, NFR-003).
- **G2 (single round-trip)**: The dashboard issues this one request (shared `["alerts"]` cache) and **no** `GET /api/athletes/{id}`. Verified by N+1 regression test (FR-001/FR-002).
- **G3 (empty-safe)**: `athletes: []` is a valid response (0 clubs or 0 athletes) → explicit empty state, never seed/other-club fallback (FR-006).

## Non-changes

- No request schema, response schema, status codes, or RBAC change.
- No new endpoint, migration, or backend file touched.
