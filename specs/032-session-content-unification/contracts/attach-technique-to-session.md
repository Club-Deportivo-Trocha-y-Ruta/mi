# Contract — Attach Technique Exercises to an Existing Session

**Endpoint**: `POST /api/technique/sessions/{training_session_id}/exercises`

**Purpose**: Close the one real backend gap this feature depends on (research.md R1): today `POST /api/technique/sessions` only *creates a new* training session; there is no way to attach technique exercises to a session that already exists. This endpoint is a new sibling of the existing `GET /api/technique/sessions/{training_session_id}/exercises` (same router, same resource, same path prefix) and reuses the `TechniqueSessionExercise` table exactly as-is — **no migration**.

## Request

`POST /api/technique/sessions/{training_session_id}/exercises`

| Param | In | Type | Required | Notes |
|---|---|---|---|---|
| `training_session_id` | path | int | yes | Must belong to the coach's club. |
| body | body | `AttachExercisesRequest` | yes | See below. |

```json
{
  "items": [
    { "exercise_id": 42, "segment": "principal", "position": 0 },
    { "exercise_id": 57, "segment": "calentamiento", "position": 0 }
  ]
}
```

- `items`: at least 1 (`Field(min_length=1)`), reusing the existing `AssembleItem` schema verbatim (`backend/app/schemas/technique.py:360-365`) — `exercise_id: int`, `segment: calentamiento|principal|vuelta_calma`, `position: int` (the submitted `position` is advisory only — see Idempotency below; the server always appends after the current max position within each segment, so clients may safely send `0` for every new item).
- Auth: Bearer JWT. Roles: `coach`, `admin` (403 otherwise, via the existing `_require_coach_or_admin` dependency already on this router, `backend/app/routers/technique.py:80-98`). Club scoping: `training_session_id` must resolve to a session owned by one of the coach's clubs (mirrors `_coach_club_id`, `technique.py:186-201`) — a session from another club is treated as **not found** (404), never a 403 that would leak its existence, matching the project's established convention (e.g. `services/strength/blocks.py` docstrings: "a block from another club is treated as not found... never as a permission error leaking existence").

## Response `201 application/json`

```json
{
  "mixes_age_bands": false,
  "items": [
    {
      "exercise_id": 42,
      "name": "Frenado progresivo en curva",
      "segment": "principal",
      "position": 3,
      "age_bands": ["10-12", "13-15"],
      "skills": [{ "code": "B", "slug": "frenado", "name": "Frenado" }],
      "is_hidden": false,
      "is_gymkhana": false
    }
  ]
}
```

- `items` is the **full current list** of the session's technique exercises after the attach (not only the newly-inserted delta) — identical shape to `GET .../exercises`, so the frontend can replace its cache wholesale with one response, no merge logic needed.
- `mixes_age_bands`: `true` when the union of age bands across **all** exercises now attached to the session (old + new) spans more than one band — same informational notice already computed by `_compute_mixes_age_bands` (`backend/app/services/technique/assembler.py:226-251`) for the create flow (`AssembleSessionResponse.mixes_age_bands`). This is **not a safety gate** — it never blocks the write (research.md R9); it exists purely so the inline picker can show the same notice the create flow already shows, for parity.

## Idempotency (FR-009: retry must not duplicate)

`TechniqueSessionExercise` has no unique constraint on `(training_session_id, exercise_id, segment)` (`backend/app/models/technique_exercise.py:256-293`, only an index on `training_session_id`). The service function backing this endpoint (new: `attach_exercises_to_session` in `backend/app/services/technique/assembler.py`) must therefore de-duplicate in application code:

1. Load the session's existing `TechniqueSessionExercise` rows.
2. For each submitted item, skip it (no insert, no error) if a row with the same `(exercise_id, segment)` already exists for this session.
3. For genuinely new items, assign `position = current_max_position_in_that_segment + 1` (or `0` if the segment is empty), in submission order, then insert.
4. Return the full current list (step 1's rows + newly inserted rows), matching `get_session_exercises`'s existing `(segment, position)` ordering (`assembler.py:555-573`).

This makes a client retry of an already-succeeded-but-response-lost call a safe no-op: the second identical request returns 201 with the same final state, zero new rows.

## Errors

| Code | Condition | Body |
|---|---|---|
| 401 | missing/invalid token | standard error envelope |
| 403 | role not coach/admin | standard error envelope |
| 404 | `training_session_id` unknown, or belongs to another club | `{"detail": "Sesión de entrenamiento {id} no encontrada."}` |
| 422 | `items` empty, or any `exercise_id` unknown (reuses `_load_exercises_by_ids`, `assembler.py:197-223`) | `{"detail": "Ejercicios no encontrados: [...]"}` |

## Non-functional

- p95 ≤ 1500 ms (transactional write; Constitution IV budget for writes). No N+1: exercise resolution is one `IN` query (`_load_exercises_by_ids`), existing-row check is one `SELECT`, response reload is the same eager-loaded query `get_session_exercises` already uses.
- Logged with correlation ID; no athlete/session PII beyond numeric IDs already implied by the URL (minors privacy — this endpoint never touches athlete data at all, only exercise↔session links).
- Test obligations (Constitution II): happy path (attach 2 new items, assert 201 + full list); RBAC-negative (parent/athlete → 403); not-found-negative (foreign-club session → 404); validation-negative (unknown `exercise_id` → 422, empty `items` → 422); **idempotency test** — call twice with the identical body, assert the second call returns 201 with the same item count (no duplicate rows), which is the regression test this contract exists to guarantee (FR-009).

## Frontend consumer

New hook `useAttachTechniqueItems(sessionId)` (TanStack Query mutation) in `frontend/src/hooks/technique/useTechnique.ts`, alongside the existing `techniqueKeys` factory (`:36-47`) — on success, invalidates `techniqueKeys.sessionExercises(sessionId)` (key already defined at `:43-44`, currently only populated by the read-only `useSessionExercises` hook, `:111-118`). Consumed by the new inline technique picker living in the session's Plan section (contracts/unified-attach-flow.md).
