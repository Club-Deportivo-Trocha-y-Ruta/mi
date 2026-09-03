/**
 * Tipos TypeScript de la Bitácora (StageLog), feature 038.
 *
 * Mirror 1:1 de los Pydantic schemas en
 * `backend/app/services/training/stage_log.py`, según
 * `specs/038-newsletter-bitacora-redesign/data-model.md` §1-2.
 *
 * Privacidad (CLAUDE.md §Privacidad de menores): ningún campo contiene
 * nombre real, fecha de nacimiento ni dato médico de un menor —
 * `athlete_first_name` es un alias de estudio ya redactado por el backend,
 * nunca el nombre legal completo.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export const WaypointKind = {
  FIRST_SESSION: "first_session",
  RACE: "race",
  STREAK: "streak",
  BADGE: "badge",
  BEST_SESSION: "best_session",
  NEXT_RACE: "next_race",
} as const;
export type WaypointKind = (typeof WaypointKind)[keyof typeof WaypointKind];

export const BlockState = {
  AI: "ai",
  EDITED: "edited",
  STATIC: "static",
  HIDDEN: "hidden",
  EMPTY: "empty",
} as const;
export type BlockState = (typeof BlockState)[keyof typeof BlockState];

export const SummitKind = {
  RACE: "race",
  TRAINING: "training",
} as const;
export type SummitKind = (typeof SummitKind)[keyof typeof SummitKind];

export type StageLogConfidence = "low" | "medium" | "high";

export type StageBlockRef =
  | "attendance"
  | "technical"
  | "race"
  | "badges"
  | "streak";

/** Bloques regenerables vía `POST /{id}/regenerate-block` (contracts/api.md). */
export type RegenerableBlock =
  | "stage_title"
  | "summit_caption"
  | "observations"
  | "next_segment_text"
  | "family_compass"
  | "analyst_reading";

/** Bloques que se pueden ocultar en `hidden_blocks`. */
export type HideableBlock = "analyst_reading" | "photos" | "badges" | "coach_note";

// ---------------------------------------------------------------------------
// Sub-modelos
// ---------------------------------------------------------------------------

export interface Waypoint {
  kind: WaypointKind;
  date: string; // ISO date
  label: string;
  sublabel: string | null;
  icon: string;
  is_future: boolean;
}

export interface EffortWeek {
  week_label: string;
  sessions_planned: number;
  sessions_attended: number;
  mean_rpe: number | null;
}

export interface Summit {
  kind: SummitKind;
  title: string;
  detail: string | null;
  caption: string | null;
  date: string | null; // ISO date
}

export interface Observation {
  claim: string;
  evidence: string;
  block_ref: StageBlockRef;
}

export interface AnalystReading {
  headline_family: string;
  action_family: string;
  valida_label: string;
  /** Solo presente en el DTO coach — `to_parent_dto` lo elimina. */
  source_insight_id: number;
}

export interface NextRace {
  label: string;
  date: string; // ISO date
  venue: string | null;
  priority_label: string | null;
}

export interface NextSegment {
  focus_groups: string[];
  next_race: NextRace | null;
  text: string | null;
}

export interface FamilyCompass {
  conversation_question: string;
  monthly_challenge: string;
  what_to_watch: string;
}

export interface BadgeView {
  code: string;
  label: string;
  icon: string;
  earned_at: string | null; // ISO date
}

export interface PhotoView {
  thumbnail_url: string;
  caption: string | null;
}

// ---------------------------------------------------------------------------
// StageLog (raíz)
// ---------------------------------------------------------------------------

export interface StageLog {
  schema_version: 2;
  stage_number: number;
  period_label: string;
  is_current_month: boolean;
  athlete_first_name: string;
  athlete_reference: string;
  stage_title: string;
  trail: Waypoint[];
  summit: Summit | null;
  observations: Observation[];
  analyst_reading: AnalystReading | null;
  effort_profile: EffortWeek[];
  next_segment: NextSegment | null;
  family_compass: FamilyCompass | null;
  badges: BadgeView[];
  photos: PhotoView[];
  coach_note: string | null;
  /** Coach DTO only — ausente en `to_parent_dto`. */
  block_states: Record<string, BlockState>;
  /** Coach DTO only — ausente en `to_parent_dto`. */
  grounding_violations: string[];
}

/**
 * Vista de StageLog para el padre: mismo shape que `StageLog` pero sin
 * `block_states`, `grounding_violations` ni `analyst_reading.source_insight_id`
 * (backend `to_parent_dto`, data-model.md §1).
 */
export type ParentStageLog = Omit<
  StageLog,
  "block_states" | "grounding_violations" | "analyst_reading"
> & {
  analyst_reading: Omit<AnalystReading, "source_insight_id"> | null;
};

// ---------------------------------------------------------------------------
// StageNarrative (salida del LLM, persistida en ai_narrative v2)
// ---------------------------------------------------------------------------

export interface AnalystReadingText {
  headline_family: string;
  action_family: string;
}

export interface StageNarrative {
  stage_title: string;
  summit_caption: string | null;
  observations: Observation[];
  next_segment_text: string | null;
  family_compass: FamilyCompass;
  analyst_reading: AnalystReadingText | null;
  model: string;
  prompt_version: string;
  confidence: StageLogConfidence;
}

// ---------------------------------------------------------------------------
// Overrides de estudio (coach)
// ---------------------------------------------------------------------------

/** `stage_overrides` — `{block: value}` para PATCH y preview local. */
export interface StageOverrides {
  stage_title?: string;
  summit_caption?: string;
  observations?: Observation[];
  analyst_reading?: AnalystReadingText;
  next_segment_text?: string;
  family_compass?: FamilyCompass;
}
