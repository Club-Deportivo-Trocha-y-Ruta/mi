/**
 * Zod schemas and mapper for the Session AI Assistant (Feature 006).
 *
 * - `sessionAnswersSchema`: validates the answers object keyed by question_id.
 * - `mapDraftToFormValues`: converts a `SessionDraftResponse` to
 *   `TrainingSessionFormValues`, resolving `athlete_call_up` criterion to
 *   concrete `convocados_athlete_ids` using the passed roster.
 *
 * Athlete classification (matches backend thresholds):
 *   birth_date → age = today − birth_date (decimal years)
 *   age < 13   → grupo_10_12
 *   age < 16   → grupo_13_15
 */
import { z } from "zod";

import type { SessionDraftResponse } from "@/api/sessionAssistant";
import type { AthleteOut } from "@/types/athlete.types";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

// ---------------------------------------------------------------------------
// Answer schema (one answer per question)
// ---------------------------------------------------------------------------

export const sessionAnswerSchema = z.object({
  question_id: z.string().min(1),
  selected_labels: z.array(z.string()),
  other_text: z.string().max(300, "Máximo 300 caracteres").nullable().optional(),
});

export type SessionAnswerFormValue = z.infer<typeof sessionAnswerSchema>;

/**
 * A map from question_id to its current answer state.
 * Used by SessionAssistantPanel to track all answers before calling /draft.
 */
export const sessionAnswersSchema = z.record(z.string(), sessionAnswerSchema);

export type SessionAnswersMap = z.infer<typeof sessionAnswersSchema>;

// ---------------------------------------------------------------------------
// Draft mapper
// ---------------------------------------------------------------------------

/**
 * Compute decimal age from a birth date string ("YYYY-MM-DD") as of today.
 */
function ageDecimal(birthDateStr: string): number {
  const birth = new Date(birthDateStr);
  const now = new Date();
  const msPerYear = 1000 * 60 * 60 * 24 * 365.25;
  return (now.getTime() - birth.getTime()) / msPerYear;
}

/**
 * Resolve an `AthleteCallUpCriterion` to a list of athlete ids,
 * using the roster provided (athletes with birth_date).
 *
 *   todos_convocados → all roster ids
 *   grupo_10_12      → athletes with age < 13
 *   grupo_13_15      → athletes with age ≥ 13 and < 16
 *   ninguno          → []
 */
export function resolveAthleteCallUp(
  criterion: SessionDraftResponse["athlete_call_up"],
  roster: AthleteOut[],
): number[] {
  switch (criterion) {
    case "todos_convocados":
      return roster.map((a) => a.id);
    case "grupo_10_12":
      return roster.filter((a) => ageDecimal(a.birth_date) < 13).map((a) => a.id);
    case "grupo_13_15":
      return roster
        .filter((a) => {
          const age = ageDecimal(a.birth_date);
          return age >= 13 && age < 16;
        })
        .map((a) => a.id);
    case "ninguno":
    default:
      return [];
  }
}

/**
 * Convert a `SessionDraftResponse` from the backend into
 * `TrainingSessionFormValues` ready for `reset(values, { keepDirtyValues: true })`.
 *
 * Fields not present in the draft (null/undefined) fall back to the supplied
 * `currentValues` so the wizard form stays fully populated.
 */
export function mapDraftToFormValues(
  draft: SessionDraftResponse,
  roster: AthleteOut[],
  currentValues: TrainingSessionFormValues,
): TrainingSessionFormValues {
  const convocados = resolveAthleteCallUp(draft.athlete_call_up, roster);

  return {
    // Carry forward existing values for fields the draft doesn't provide
    ...currentValues,

    // Fields always present in draft
    technical_focus: draft.technical_focus,
    duration_min: draft.duration_min,
    session_kind: draft.session_kind,

    // Optional fields — fall back to current if draft is null
    objectives: draft.objectives ?? currentValues.objectives,
    description: draft.description ?? currentValues.description,
    location: draft.location ?? currentValues.location,

    // Dates — only overwrite if the draft provided a value
    scheduled_date: draft.scheduled_date ?? currentValues.scheduled_date,
    scheduled_start_time:
      draft.scheduled_start_time ?? currentValues.scheduled_start_time,

    // Athlete call-up resolved locally from criterion
    convocados_athlete_ids:
      convocados.length > 0 ? convocados : currentValues.convocados_athlete_ids,

    // coach_notes: keep current (draft notes are advisory, shown separately)
    coach_notes: currentValues.coach_notes,

    // route_text / strava_url: keep current
    route_text: currentValues.route_text,
    strava_url: currentValues.strava_url,
  };
}
