# Contract: Cleanup Duplicate Competition endpoint

## `DELETE /api/race-analysis/race-events/{race_event_id}/cleanup`

Remove a **no-results** competition together with its linked calendar event (if any), in one
transaction. Coach-only. Inverse of feature 008's associate-to-calendar, plus a guarded delete.

### Auth / RBAC
- Requires a valid JWT.
- `require_role([UserRole.coach])` → **coach only**. Admin/parent/athlete → `403`.

### Path parameters
| Name | Type | Description |
|------|------|-------------|
| `race_event_id` | integer | Id of the competition (`race_events.id`) to remove. |

### Request body
None.

### Responses
| Status | Condition | Body |
|--------|-----------|------|
| `204 No Content` | Success. Competition removed; linked calendar event (if present) removed; audiences/attendances cascaded. | empty |
| `403 Forbidden` | Caller is not a coach. | `{ "detail": "..." }` |
| `404 Not Found` | No competition with `race_event_id` (e.g., already removed — stale list). | `{ "detail": "Evento de carrera con id=… no existe." }` |
| `409 Conflict` | Competition holds imported results → protected, cannot be removed by this flow. | `{ "detail": "No se puede eliminar: tiene resultados ingestados." }` |

### Side effects
- Deletes the linked `CalendarEvent` (if `race_events.calendar_event_id` set), cascading its
  `event_audiences` and `event_attendances` rows.
- Deletes the `race_events` row.
- No `race_results` rows are read-for-guard only and never modified.
- Single DB transaction (atomic). Logs emit IDs only.

### Notes
- Idempotency: a second call returns `404` (already gone).
- The existing admin-only `DELETE /api/race-analysis/race-events/{race_event_id}` is unchanged and
  still refuses when results **or** a calendar link exist.

---

## Frontend contract

### API client — `frontend/src/api/raceEvents.ts`
```ts
// DELETE /api/race-analysis/race-events/{id}/cleanup  → 204
export async function cleanupDuplicateRaceEvent(
  id: number,
  options?: { signal?: AbortSignal },
): Promise<void>;
```

### Hook — `frontend/src/hooks/race/useRaceEvents.ts`
```ts
// RBAC: coach only. Invalidates raceEventKeys.lists() + calendar tree
// (the cleanup removes a calendar event, so the calendar view must refresh).
export function useCleanupDuplicateRaceEvent(): UseMutationResult<
  void, unknown, { id: number }
>;
```
- `onSuccess` invalidates `raceEventKeys.lists()`, `CALENDAR_AVAILABLE_ROOT`, and `calendarQueryRoot`
  (`["calendar"]`).
- Error mapping reuses `getRaceEventErrorMessage` (409 → "tiene resultados", 403 → sin permiso,
  404 → no encontrado).

### UI — `CompetitionsListPage.tsx` (kebab action)
- New destructive item **"Eliminar duplicado"** in `ActionsKebab`, visible when
  `isCoach && !item.has_results`.
- Opens the reused `ConfirmDeleteDialog`:
  - title: `"Eliminar competencia duplicada"`
  - description (español neutro): states the competition **and** its evento de calendario asociado will
    be permanently removed, and that the action is irreversible.
  - confirmLabel: `"Eliminar duplicado"`.
- On 409 (results imported between open and confirm), surface the backend message in the dialog error
  slot; the action effectively becomes unavailable on the next list refresh.
