# API Contracts: Structured Interval Training

**Feature**: `026-structured-interval-training` · Router: `backend/app/routers/intervals.py`, prefix `/api/intervals`

**Global RBAC**: every endpoint requires `Depends(require_role([UserRole.admin, UserRole.coach]))` **and** club scope (coach must belong to the target session's/template's club via `user_club_role`). Parent/athlete tokens → `403` on all routes (FR-018). Errors follow the existing envelope (`detail` string or machine-readable `detail.code`).

Español neutro applies to every user-visible message string below.

---

## Structures

### `POST /api/intervals/structures`

Create a structure attached to a session (US1).

Request:
```json
{
  "training_session_id": 42,
  "target_age_band": "13-15",
  "age_gate_confirmed": false,
  "blocks": [
    { "position": 1, "block_type": "warmup",   "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 70, "repeat_group": null, "repeat_count": null },
    { "position": 2, "block_type": "work",     "duration_s": 120, "target_zone": "Z2", "target_cadence_rpm": 75, "repeat_group": 1, "repeat_count": 2 },
    { "position": 3, "block_type": "recovery", "duration_s": 60,  "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_group": 1, "repeat_count": 2 },
    { "position": 4, "block_type": "cooldown", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 65, "repeat_group": null, "repeat_count": null }
  ]
}
```

Responses:
- `201` → `StructureOut` (below).
- `404` session not found; `403` wrong club/role.
- `409` session already has a structure (use `PUT`).
- `422` validation, machine-readable codes:
  - `{"detail": {"code": "cadence_below_minimum", "message": "La cadencia mínima es 60 rpm para todas las categorías.", "positions": [3]}}` (FR-004)
  - `{"detail": {"code": "age_gate_z3_blocked", "message": "Intensidad Z3 o superior no está disponible para la categoría 10-12.", "positions": [2]}}` (FR-006, no override)
  - `{"detail": {"code": "age_gate_confirmation_required", "message": "Confirmá explícitamente la estructura para la categoría 10-12 antes de guardar."}}` (FR-007 — client re-submits with `age_gate_confirmed: true` after the dialog)
  - `invalid_repeat_group` (repeat_count < 2, inconsistent counts within a group)

`StructureOut`:
```json
{
  "id": 7,
  "training_session_id": 42,
  "target_age_band": "13-15",
  "age_gate_confirmed": false,
  "age_gate_confirmed_by": null,
  "age_gate_confirmed_at": null,
  "blocks": [ { "id": 12, "position": 1, "block_type": "warmup", "duration_s": 300, "target_zone": "Z1", "target_cadence_rpm": 70, "repeat_group": null, "repeat_count": null } ],
  "total_planned_duration_s": 960,
  "created_at": "2026-07-10T14:00:00Z",
  "updated_at": "2026-07-10T14:00:00Z"
}
```

### `GET /api/intervals/sessions/{session_id}/structure`
`200` → `StructureOut` · `404` if the session has no structure (frontend renders the empty/create state).

### `PUT /api/intervals/structures/{structure_id}`
Full replace of band + blocks; same body (minus `training_session_id`) and same `422` codes as create. `200` → `StructureOut`. Side effect: if the session has a linked activity, dispatches deferred recompute (`triggered_by=structure_change`).

### `DELETE /api/intervals/structures/{structure_id}`
`204`. Cascades blocks + match results; **laps are preserved** (D7).

---

## Templates (US4)

### `POST /api/intervals/templates`
Body: `name`, `target_age_band`, `mesocycle_phase`, `competition_proximity`, `blocks[]` (same block shape + same `422` validation codes — a template can never hold sub-60 cadence or an invalid repeat group; Z3+ blocks are allowed on a `10-12`-tagged template only at attach-time evaluation? **No** — Z3+ on a `10-12` template is rejected at save (`age_gate_z3_blocked`), keeping the library clean at the source). `201` → `TemplateOut` (same shape as `StructureOut` + tags + `is_archived`, minus session/link fields).

### `GET /api/intervals/templates?age_band=&mesocycle_phase=&competition_proximity=&include_archived=false`
`200` → `{ "items": [TemplateOut], "total": n }`, club-scoped, filterable by the three tags (US4-AC2). Blocks `selectinload`ed.

### `PUT /api/intervals/templates/{template_id}` · `PATCH /api/intervals/templates/{template_id}/archive`
Standard edit / soft-archive. Editing a template never mutates sessions that used it (copy-on-attach).

### `POST /api/intervals/templates/{template_id}/attach`
Body: `{ "training_session_id": 42, "age_gate_confirmed": false }`.
Clones template blocks into a new structure for the session. Runs the **full structure validation against the template's band and the blocks** at attach time (spec edge case: attaching a Z3+ template to a 10-12 session → `age_gate_z3_blocked`; sub-Z3 onto 10-12 → `age_gate_confirmation_required` unless confirmed).
`201` → `StructureOut` · `409` if the session already has a structure.

---

## Matching (US2)

### `GET /api/intervals/sessions/{session_id}/match?activity_id={id}`

The detail-view payload (FR-017). `activity_id` optional when exactly one linked activity exists.

`200`:
```json
{
  "structure_id": 7,
  "activity": { "id": 91, "start_date_local": "2026-07-08T16:05:00", "elapsed_time_s": 3720, "sport_type": "Ride" },
  "status": "computed",
  "computed_at": "2026-07-08T18:00:12Z",
  "engine_version": 1,
  "tolerance_pct": 30,
  "blocks": [
    { "flat_index": 0, "block_type": "warmup", "repeat_iteration": null, "planned_duration_s": 300,
      "target_zone": "Z1", "target_cadence_rpm": 70,
      "lap_index": 0, "lap_elapsed_time_s": 312, "lap_moving_time_s": 300,
      "lap_average_heartrate": 128.4, "lap_average_speed_m_s": 4.1, "status": "cumplido" }
  ],
  "extra_laps": [ { "lap_index": 6, "elapsed_time_s": 45, "average_heartrate": null } ],
  "summary": { "cumplido": 5, "fuera_tolerancia": 1, "sin_dato": 0, "extra": 1 }
}
```

Other `status` values (all `200`, UI-designed states — never raw errors):
- `"no_activity"` — session has no linked activity (spec edge case #1).
- `"computing"` — deferred job dispatched, result row not yet present.
- `"failed"` — last run failed (e.g., Strava 429/5xx); payload carries `"retry_available": true`.

`404` session/structure not found · `403` parent/athlete or wrong club.

Lap data appears **only** inside this response — there is no standalone laps listing endpoint (privacy surface minimization).

### `POST /api/intervals/structures/{structure_id}/recalculate`

Body: `{ "activity_id": 91 }` (optional under the same single-activity rule). Re-fetches laps from Strava (replace-all for that activity), recomputes, upserts the result (`triggered_by=manual`, FR-015).
`202` → `{ "status": "computing" }` (deferred) · `409` no linked activity · `429` passthrough advisory if Strava rate-limited at dispatch time.

### Side-contract on existing endpoint (edit, not new)

`PATCH /api/activities/{activity_id}/link` (feature 025, `routers/activities.py`): after a successful link where the target session has a structure, dispatches the deferred match job (`triggered_by=link`). Response shape unchanged — consumers unaffected. Unlink (`training_session_id: null`) leaves laps intact and deletes nothing; the match row for that pair is deleted (its pairing no longer exists).

---

## Instructivo (US3)

### `GET /api/intervals/sessions/{session_id}/instructivo?brand=garmin|magene|igpsport`

`200` → `application/pdf`, `Content-Disposition: attachment; filename="instructivo_{brand}_{session-date}.pdf"` (in-memory `Response` pattern from `reports.py`).
Content: session header, flattened block table (order, tipo, duración, zona FC, cadencia), brand-specific configuration steps (D8), and the mandatory "desactivá la vuelta automática (auto-lap)" step for every brand.
`404` if the session has no structure (spec edge case: the frontend disables the button in that state, server still guards) · `422` unknown brand.

---

## New Strava client method (internal contract)

`StravaClient.get_activity_laps(activity_id: int) -> list[dict]` — `GET {strava_api_base_url}/activities/{activity_id}/laps` through the existing `_request()` choke point (token refresh, `StravaRateLimited` on 429, `StravaNotFoundError` on 404). Consumed exclusively by `services/intervals/match_runner.py`, which allow-lists `lap_index`, `elapsed_time`, `moving_time`, `average_heartrate`, `average_speed` and drops everything else before persistence (privacy invariant D4).
