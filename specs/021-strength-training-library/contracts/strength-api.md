# API Contract: /api/strength (021)

Router `backend/app/routers/strength.py`, registered in `main.py` as `prefix="/api/strength", tags=["strength"]`. **All endpoints** require `require_role([UserRole.admin, UserRole.coach])` + JWT. Errors follow FastAPI `{"detail": "..."}` with Spanish user-facing messages. Entity shapes: see [data-model.md](../data-model.md).

## Catalog

### `GET /exercises`

Query params (all optional, AND-combined):

| Param | Type | Meaning |
|---|---|---|
| `q` | string | Free-text LIKE over name+summary (FR-005) |
| `equipment` | `sin_equipo` \| `equipo_gym` | Facet |
| `age_band` | `10-12` \| `13-15` | Facet (exercise matches if band ∈ its bands) |
| `movement_category` | enum | Facet |
| `include_hidden` | bool=false | Curation only |

**200** → `{ "items": [ExerciseOut], "total": int }`. `ExerciseOut`: `id, slug, name, summary, equipment, equipment_detail, movement_category, age_bands: [str], suggested_duration_min, suggested_reps, is_seeded, is_hidden`. List omits `how_to/common_errors/illustration_*` (card view; detail fetches full).

### `GET /exercises/{exercise_id}`

**200** → `ExerciseDetailOut` = ExerciseOut + `how_to, common_errors, illustration_ascii, illustration_alt`. **404** if missing or hidden (non-admin).

## Blocks

### `POST /blocks`

Body: `{ name, target_age_band, duration_target_min?=30, entries: [ { exercise_id, position, duration_min, reps?, is_age_override?=false, override_note? } ] }`

- **201** → `BlockOut`: `id, name, target_age_band, duration_target_min, total_duration_min, is_archived, entries: [EntryOut], created_at`. `EntryOut` embeds `exercise: ExerciseOut`.
- **422** `AGE_BAND_GUARDRAIL` — entry whose exercise bands ∌ `target_age_band` sent without `is_age_override=true`. Detail explains which exercise and why (FR-011). Client shows `AgeBandGuardrailDialog`; resubmit with override to proceed (recorded).
- **404** — unknown/hidden exercise_id.

### `GET /blocks` → **200** `{ items: [BlockOut], total }` (club-scoped, `is_archived=false` default; `?include_archived=true`).

### `GET /blocks/{block_id}` → **200** `BlockOut` | **404**.

### `PUT /blocks/{block_id}`

Same body as POST (full replace of entries; same guardrail semantics). **200** `BlockOut`.

### `PATCH /blocks/{block_id}/archive`

Body `{ is_archived: bool }` → **200**. Archived blocks stay attached to sessions (read-only there).

## Session attachment

### `POST /blocks/{block_id}/attach`

Body `{ training_session_id }` → **201** `{ id, training_session_id, block_id, position, attached_at }`.
**409** if already attached (unique pair). **404** unknown session/block. Session must belong to coach's club.

### `DELETE /blocks/{block_id}/attach/{training_session_id}` → **204**.

### `GET /sessions/{training_session_id}/blocks`

**200** → `{ items: [BlockOut] }` — blocks attached to a session, for session plan rendering (FR-012/FR-013).

## Progress notes

### `GET /athletes/{athlete_id}/progress`

**200** → `{ items: [ { exercise_id, exercise_name, status, coach_note, season, recorded_at } ] }` — latest row per exercise. **403** athlete outside coach's club. No athlete PII beyond path id (FR-020).

### `POST /athletes/{athlete_id}/progress`

Body `{ exercise_id, status, coach_note?, season }` → **201** (append-only). **403** club scope. **404** unknown exercise.

## Error codes summary

| Status | When |
|---|---|
| 401 | No/expired JWT |
| 403 | Role ∉ {coach, admin}; athlete/session outside club |
| 404 | Missing exercise/block/session |
| 409 | Duplicate attach |
| 422 | Validation; `AGE_BAND_GUARDRAIL` without override flag |

## Non-goals (v1)

No `POST/PUT /exercises` (custom exercise curation — deferred, research D9). No DELETE anywhere (soft-hide/archive only). No athlete/parent access.
