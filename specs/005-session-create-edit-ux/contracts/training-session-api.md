# Phase 1 — API Contract Delta: Training Session Create/Edit

Only the **minimal backend contract changes** required by this feature are listed. All other
endpoints are reused unchanged. No new endpoints, no migration.

## Changed — `POST /api/training-sessions` (create)

Request body `TrainingSessionCreate` gains two fields (both optional):

```jsonc
{
  "scheduled_date": "2026-06-20",
  "scheduled_start_time": "08:00",
  "duration_min": 90,
  "location": "Pista XCO La Buitrera",
  "technical_focus": "Frenada en descenso",
  "description": "…",
  "session_kind": "entrenamiento",   // NEW — enum: entrenamiento|actividad_conjunta|salida|otro; default entrenamiento
  "objectives": "…",                  // NEW — optional, max 1000 chars
  "route_text": "…",                  // existing, optional
  "strava_url": "https://www.strava.com/activities/123", // existing; strict regex
  "coach_notes": "…",                 // existing (already accepted) — now surfaced in UI
  "convocados_athlete_ids": [1, 2, 3],
  "send_notification": false
}
```

Response `TrainingSessionRead` MUST now echo `session_kind` and `objectives` (previously
absent). RBAC unchanged (admin/coach only). Validation errors return 422.

## Changed — `PATCH /api/training-sessions/{id}` (update)

Request body `TrainingSessionUpdate` gains the same two optional fields
(`session_kind`, `objectives`). Partial-update semantics preserved
(`model_dump(exclude_unset=True)`). When changed, both fields appear in the parent
update-notification diff with Spanish labels ("Tipo de sesión", "Objetivos").

## Reused unchanged — route file

`POST /api/training-sessions/{id}/route-file` (multipart, `.gpx`/`.fit`, magic-byte + size
validation server-side). The wizard calls this immediately after create (or against the
known id in edit mode). On failure, the already-saved session is NOT rolled back; the client
surfaces a retryable error.

## Reused unchanged — convocatoria & notifications

- `PUT /api/training-sessions/{id}/attendance` (`bulkSetConvocatoria`) for edit-mode call-up
  changes, with `send_notification`.
- Parent notifications on create/update remain driven by `send_notification`; the client
  reports the outcome (success / failure-retry / no-recipients) to the coach. The backend
  already dispatches asynchronously and logs ids-only.

## Read serialization

`TrainingSessionRead` and `TrainingSessionReadParent` MUST include `session_kind` and
`objectives` (neither is sensitive; parent view continues to omit `coach_notes` and
`route_file_path`).

## Contract tests (backend, pytest)

1. Create with `session_kind="salida"` + `objectives="…"` → 201, response echoes both;
   GET detail returns the same (round-trip). **Fails on current code.**
2. PATCH `session_kind`/`objectives` → 200, persisted; GET reflects change.
3. Omitting `session_kind` on create → defaults to `entrenamiento`.
4. `objectives` > 1000 chars → 422.
5. Privacy: create/update with notification does not write any athlete name to logs.
6. Parent GET includes `session_kind`/`objectives`, still omits `coach_notes`/
   `route_file_path`.
