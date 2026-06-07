# Phase 1 — Data Model: Session Create/Edit Flow & UX Overhaul

No database schema changes. The `training_sessions` table already contains every field this
feature persists (the `session_kind` enum and `objectives` columns were added in migration
`d4e5f6a7b8c9`, Phase 1.9). This document records the entities the feature touches and the
client-only draft entity.

## Existing entity — TrainingSession (no migration)

Relevant persisted fields (from `backend/app/models/training_session.py`):

| Field | Type | Notes for this feature |
|---|---|---|
| `id` | int PK | — |
| `club_id` | int FK | inferred from coach membership on create |
| `created_by_user_id` | int FK | coach/admin |
| `status` | enum `SessionStatus` | `planned`/`executed`/`cancelled` — **unchanged** lifecycle |
| `scheduled_date` | date | Step 1, required |
| `scheduled_start_time` | time | Step 1, required (HH:MM) |
| `duration_min` | int (15–240) | Step 1, `DurationPicker` |
| `location` | str(200) | Step 1, required |
| `technical_focus` | str(200) | Step 1, required |
| `description` | text(2000) | Step 1 |
| `session_kind` | enum `SessionKind` | **NEW wiring**: Step 1 chips; was dropped before |
| `objectives` | text(1000) | **NEW wiring**: Step 1; was dropped before |
| `route_text` | str(500) | Step 3 |
| `strava_url` | str | Step 3; shared strict regex |
| `route_file_path` | str | set by existing `/route-file` upload endpoint |
| `coach_notes` | text(2000) | **NEW in form**: Step 3 (already accepted by backend) |
| `updated_at` | datetime | used for concurrent-edit detection (FR-019) |
| `executed_at` | datetime? | unchanged |

### Enum — SessionKind

Values (Spanish, stored via `values_callable` convention): `entrenamiento`,
`actividad_conjunta`, `salida`, `otro`. Surfaced as `ToggleGroup` chips with labels:
Entrenamiento / Actividad conjunta / Salida / Otro.

### Validation rules (Zod ↔ Pydantic parity)

| Field | Rule |
|---|---|
| `scheduled_date` | required, ISO date |
| `scheduled_start_time` | required, `HH:MM` |
| `duration_min` | int 15–240 |
| `location` | required, ≤200 |
| `technical_focus` | required, ≤200 |
| `description` | ≤2000 (required client-side, optional server-side — keep client required) |
| `session_kind` | one of the 4 enum values; defaults to `entrenamiento` |
| `objectives` | optional, ≤1000 |
| `route_text` | optional, ≤500 |
| `strava_url` | optional; **shared** regex `^https://www\.strava\.com/activities/\d+$` |
| `coach_notes` | optional, ≤2000 |
| `convocados_athlete_ids` | ≥1 |

## Existing entity — SessionAttendance (call-up)

Created on session create (one row per called-up athlete, placeholder status `ausente`).
This feature manages selection only (Step 2); post-execution rubric/attendance is out of
scope. On edit, convocatoria changes go through the existing
`PUT /training-sessions/{id}/attendance` (`bulkSetConvocatoria`).

## Client-only entity — SessionDraft (localStorage, not persisted server-side)

| Field | Type | Notes |
|---|---|---|
| `version` | string | schema version (`v1`) for forward-compat |
| `values` | form values | full RHF values snapshot |
| `step` | int | wizard step to resume on |
| `updatedAt` | ISO string | for staleness comparison in edit mode |

- **Key**: `tyr:session-draft:v1:{userId}:{new|<sessionId>}` (scoped per user + target).
- **Lifecycle**: written debounced on change; offered for restore on mount; cleared on
  successful save or explicit discard.
- **Privacy**: may contain athlete ids → sensitive; never logged; cleared on save/discard.

## State transitions (unchanged)

`planned → executed` (execute endpoint) and `planned → cancelled` (delete/cancel endpoint)
remain as-is. The wizard edits fields of a `planned` session; it does not transition state.
Editing an `executed`/`cancelled` session surfaces which fields are read-only and never
silently re-opens state (FR-018).
