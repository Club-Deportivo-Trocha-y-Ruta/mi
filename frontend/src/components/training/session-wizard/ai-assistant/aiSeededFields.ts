/**
 * Helper to track which wizard form fields were pre-filled by the AI assistant.
 *
 * Usage:
 *   1. After `reset(draftValues, { keepDirtyValues: true })`, call
 *      `buildAiSeededSet(draftValues)` to get the initial seeded set.
 *   2. Pass the set down to `StepGeneral` (and future steps).
 *   3. On each render, call `clearDirtySeeds(seededSet, dirtyFields)` to
 *      remove the marker for any field the coach has already edited.
 *
 * Notes:
 *   - `toggle-group.tsx` type="multiple" support confirmed (Radix ToggleGroup
 *     accepts `type="multiple"` via `ToggleGroupPrimitive.Root` props).
 *   - We track field names as a `Set<string>` for O(1) membership tests.
 */

import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";
import type { SessionDraftResponse } from "@/api/sessionAssistant";

/** Fields that the AI can seed (subset of `TrainingSessionFormValues`). */
export type SeededFieldName = keyof TrainingSessionFormValues;

/**
 * Build the initial set of AI-seeded field names from a draft response.
 * Only includes fields where the draft actually provided a non-null value.
 */
export function buildAiSeededSet(draft: SessionDraftResponse): Set<SeededFieldName> {
  const seeded = new Set<SeededFieldName>();

  seeded.add("technical_focus");
  seeded.add("duration_min");
  seeded.add("session_kind");

  if (draft.objectives !== null && draft.objectives !== undefined) {
    seeded.add("objectives");
  }
  if (draft.description !== null && draft.description !== undefined) {
    seeded.add("description");
  }
  if (draft.location !== null && draft.location !== undefined) {
    seeded.add("location");
  }
  if (draft.scheduled_date !== null && draft.scheduled_date !== undefined) {
    seeded.add("scheduled_date");
  }
  if (
    draft.scheduled_start_time !== null &&
    draft.scheduled_start_time !== undefined
  ) {
    seeded.add("scheduled_start_time");
  }
  if (draft.athlete_call_up !== "ninguno") {
    seeded.add("convocados_athlete_ids");
  }

  return seeded;
}

/**
 * Return a new Set with fields removed where RHF's `dirtyFields` shows
 * the coach has edited the field after the AI pre-fill.
 *
 * `dirtyFields` uses Partial<Record<keyof T, true | ...>> — we treat any
 * truthy entry as "dirty".
 */
export function clearDirtySeeds(
  seeded: Set<SeededFieldName>,
  dirtyFields: Partial<Record<SeededFieldName, unknown>>,
): Set<SeededFieldName> {
  const next = new Set(seeded);
  for (const field of seeded) {
    if (dirtyFields[field]) {
      next.delete(field);
    }
  }
  return next;
}
