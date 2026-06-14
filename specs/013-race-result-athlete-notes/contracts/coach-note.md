# API Contract: Coach Per-Athlete Race Note

**Feature**: 013-race-result-athlete-notes
**Base**: `/api/race-analysis` (same router as race results)
**Auth**: Bearer JWT. **RBAC**: `require_role([coach, admin])` on every endpoint below. Parents/athletes → 403.

The note is attached to one `race_results` row (one rider × one válida). The row's `result_id` is the
`result_id` already returned by the results read path.

---

## 1. Set / replace the note (upsert)

```
PUT /api/race-analysis/race-results/{result_id}/coach-note
```

**Path**: `result_id` (int) — id of the per-athlete `race_results` row.

**Request body** (`CoachNoteUpdate`):

```json
{ "coach_note": "Falla mecánica en la vuelta 2; venía 3.º." }
```

- `coach_note` (string, required): stripped server-side; `1 ≤ len(stripped) ≤ 500`.

**Responses**:

| Status | When | Body |
|---|---|---|
| `200 OK` | Note created or replaced | `ResultRow` (with `coach_note`, `coach_note_updated_at`) |
| `422 Unprocessable Entity` | empty/whitespace-only or > 500 chars | validation error (localized in UI) |
| `409 Conflict` / `422` | `result_id` row has `athlete_id IS NULL` (non-club competitor) | error detail |
| `404 Not Found` | `result_id` does not exist or is soft-deleted | error detail |
| `403 Forbidden` | caller is not coach/admin | error detail |
| `401 Unauthorized` | no/expired token | error detail |

**Side effects**: sets `coach_note`, `coach_note_author_id = current_user.id`, `coach_note_updated_at = now()`.
Idempotent on the (rider, válida) pair — a second PUT replaces, never duplicates (FR-002).

---

## 2. Clear the note

```
DELETE /api/race-analysis/race-results/{result_id}/coach-note
```

**Responses**:

| Status | When | Body |
|---|---|---|
| `200 OK` | Note cleared (or already absent — idempotent) | `ResultRow` (with `coach_note = null`) |
| `404 Not Found` | `result_id` does not exist or is soft-deleted | error detail |
| `403 Forbidden` | caller is not coach/admin | error detail |

**Side effects**: sets `coach_note = NULL`, `coach_note_author_id = NULL`, `coach_note_updated_at = NULL`.

---

## 3. Read (existing endpoint, extended)

```
GET /api/race-analysis/race-events/{race_event_id}/results
```

Already returns `EventResultsRead` → `categories[].rows[]` of `ResultRow`. **Extended** so each `ResultRow`
includes (coach/admin only — endpoint is already RBAC-gated):

```jsonc
{
  "position": 3,
  "competitor_id": 412,
  "display_name": "…",
  "athlete_id": 88,
  "is_our_club": true,
  "status": "finished",
  "race_time_ms": 1325400,
  "points_awarded": 18,
  "bib_number": 27,
  "coach_note": "Falla mecánica en la vuelta 2; venía 3.º.",   // null when no note
  "coach_note_updated_at": "2026-06-14T12:40:00Z"               // null when no note
}
```

The `result_id` needed to address the PUT/DELETE is exposed on the row (the read path already carries it
internally; ensure `ResultRow` exposes `result_id` for the client to target the note endpoints).

---

## Frontend client contract

`frontend/src/api/raceResults.ts`:

```ts
export async function setResultCoachNote(
  resultId: number, body: { coach_note: string }, opts?: { signal?: AbortSignal },
): Promise<RaceResultRow> {
  const { data } = await apiClient.put<RaceResultRow>(
    `${BASE}/race-results/${resultId}/coach-note`, body, { signal: opts?.signal });
  return data;
}

export async function clearResultCoachNote(
  resultId: number, opts?: { signal?: AbortSignal },
): Promise<RaceResultRow> {
  const { data } = await apiClient.delete<RaceResultRow>(
    `${BASE}/race-results/${resultId}/coach-note`, { signal: opts?.signal });
  return data;
}
```

`useSetResultCoachNote` / `useClearResultCoachNote` (TanStack Query `useMutation`) use optimistic updates:
`onMutate` → `cancelQueries(raceResultsKeys.byEventFiltered(...))`, snapshot, `setQueryData` patching the
row's `coach_note`; `onError` rolls back; `onSettled` returns `invalidateQueries(byEventFiltered)` so the
mutation stays pending until refetch (honest feedback over 3G — FR-011/SC-006).

## Privacy invariants (testable)

- The note text reaching the AI is **scrubbed of real names + pseudonymized** before any prompt (same path
  as `weather_notes`). Raw note + real names never appear in prompts or logs (`AI_LOG_PROMPTS=false`).
- `coach_note` appears in **zero** parent/athlete-facing responses (no such endpoint exposes it; RBAC gate
  on the results router).
