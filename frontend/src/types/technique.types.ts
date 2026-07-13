/** Tipos del módulo Técnica y Gymkhana (feature 018 + 019). */

// ---------------------------------------------------------------------------
// Enums / literals
// ---------------------------------------------------------------------------

export type AgeBand = "7-9" | "10-12" | "13-15";
export type Difficulty = "facil" | "media" | "avanzada";
export type SessionSegment = "calentamiento" | "principal" | "vuelta_calma";
export type SkillProgressStatus = "introducido" | "en_progreso" | "dominado";

// ---------------------------------------------------------------------------
// Taxonomy
// ---------------------------------------------------------------------------

export interface SkillRef {
  code: string;
  slug: string;
  name: string;
}

export interface SkillRead extends SkillRef {
  /** Orden de presentación en la UI. */
  order?: number | null;
}

export interface MaterialRead {
  slug: string;
  name: string;
  /** true when this represents "sin material". */
  is_none: boolean;
}

// ---------------------------------------------------------------------------
// Circuit diagrams — feature 019 (Phase A)
// ---------------------------------------------------------------------------

/**
 * Controlled vocabulary for gymkhana circuit elements.
 * Phase A: no free-text label (controlled set only, FR-023 / O-5).
 */
export type CircuitElementKind =
  | "cone"
  | "line"
  | "gate"
  | "mine"
  | "arrow"
  | "beam"
  | "ring";

/**
 * One element placed on the canvas.
 * - `rotation` defaults to 0 when absent.
 * - `style` is meaningful only for `kind === 'line'`:
 *     'dashed' → trayecto guía / libre
 *     'solid'  → trayecto técnico (precision)
 * - `label` is absent in Phase A (controlled set enforced by kind + optional #n).
 *   Phase B allows a short coach-authored label (non-PII, anti-PII validated).
 */
export interface CircuitElement {
  kind: CircuitElementKind;
  /** Canvas units; 0 ≤ x ≤ layout.width. */
  x: number;
  /** Canvas units; 0 ≤ y ≤ layout.height. */
  y: number;
  /** Degrees clockwise from 12 o'clock; default 0. */
  rotation?: number;
  /** Line variant only: 'dashed' = guía/libre | 'solid' = técnico. */
  style?: "dashed" | "solid";
  /**
   * Phase B only: short coach-authored label (max 40 chars, non-PII).
   * Validated client-side by piiGuard and server-side by Pydantic (FR-019).
   * Phase A: absent (controlled set only — FR-023/O-5).
   */
  label?: string;
}

/**
 * Complete layout document stored in `technique_exercises.layout_json`.
 * Persisted as MySQL native JSON; round-trips as JSON-text on SQLite tests.
 * Empty `elements` array is valid.
 */
export interface GymkhanaLayout {
  /** Canvas width in logical units (> 0). */
  width: number;
  /** Canvas height in logical units (> 0). */
  height: number;
  elements: CircuitElement[];
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

export interface ExerciseListItem {
  id: number;
  slug: string;
  name: string;
  summary: string;
  difficulty: Difficulty;
  is_game: boolean;
  is_gymkhana: boolean;
  age_bands: AgeBand[];
  skills: SkillRef[];
  materials: MaterialRead[];
  is_seeded: boolean;
  is_hidden: boolean;
}

export interface CatalogFilters {
  skill?: string;
  age_band?: AgeBand;
  difficulty?: Difficulty;
  /** CSV of material slugs: returns exercises whose required materials ⊆ this set. */
  materials?: string;
  include_hidden?: boolean;
  is_game?: boolean;
}

export interface CatalogList {
  items: ExerciseListItem[];
  total: number;
}

// ---------------------------------------------------------------------------
// Exercise detail
// ---------------------------------------------------------------------------

export interface ExerciseDetail extends ExerciseListItem {
  how_to: string;
  layout_ascii: string | null;
  layout_alt: string | null;
  /** Structured SVG layout (feature 019). Null for non-gymkhana or not-yet-backfilled rows. */
  layout_json: GymkhanaLayout | null;
  confidence: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Session assembly (US3)
// ---------------------------------------------------------------------------

export interface SessionItemInput {
  exercise_id: number;
  segment: SessionSegment;
  position: number;
}

export interface AssembleSessionInput {
  scheduled_date: string;
  scheduled_start_time: string;
  duration_min: number;
  location: string;
  technical_focus: string;
  objectives: string;
  convocados_athlete_ids: number[];
  items: SessionItemInput[];
  /**
   * Phase B (O-6): combined free-form circuit layout.
   * Persisted in a hidden synthetic technique_exercises row (is_hidden=True,
   * is_gymkhana=True). Null / absent when no composer circuit is attached.
   */
  combined_layout?: GymkhanaLayout | null;
  /**
   * Phase B (O-6): re-edit path — id of the existing synthetic exercise to UPDATE.
   * When absent, a new synthetic exercise is created.
   * MUST NOT appear in items (server-managed, not a catalog exercise).
   */
  combined_exercise_id?: number | null;
}

export interface TechniqueSessionItem {
  exercise_id: number;
  name: string;
  segment: SessionSegment;
  position: number;
  age_bands: AgeBand[];
  skills: SkillRef[];
  /**
   * Phase B (O-6): true for the hidden synthetic combined-circuit item
   * (sentinel position 9999). UI lists MUST filter this out — it is not a
   * real catalog exercise the coach picked.
   */
  is_hidden: boolean;
  is_gymkhana: boolean;
}

export interface AssembleSessionResult {
  training_session_id: number;
  mixes_age_bands: boolean;
  items: TechniqueSessionItem[];
  /**
   * Phase B (O-6): id of the hidden synthetic exercise created (or updated) to
   * persist the combined GymkhanaLayout. Null when no combined_layout was sent.
   * Store this to pass back as combined_exercise_id on re-edit.
   */
  combined_exercise_id?: number | null;
}

// ---------------------------------------------------------------------------
// Attach exercises to an existing session (feature 032, T007)
// contracts/attach-technique-to-session.md
// ---------------------------------------------------------------------------

export interface AttachExercisesInput {
  items: SessionItemInput[];
}

export interface AttachExercisesResult {
  mixes_age_bands: boolean;
  items: TechniqueSessionItem[];
}

// ---------------------------------------------------------------------------
// Per-athlete skill progress (US4)
// ---------------------------------------------------------------------------

export interface SkillProgressEvent {
  id: number;
  skill: SkillRef;
  status: SkillProgressStatus;
  coach_note: string | null;
  season: number;
  recorded_at: string;
}

export interface CurrentSkillProgress {
  skill: SkillRef;
  status: SkillProgressStatus;
  recorded_at: string;
  coach_note: string | null;
}

export interface AthleteProgress {
  athlete_id: number;
  current: CurrentSkillProgress[];
  history: SkillProgressEvent[];
}

export interface ProgressInput {
  skill_id: number;
  status: SkillProgressStatus;
  coach_note?: string;
  season: number;
}

// ---------------------------------------------------------------------------
// Curation (US5)
// ---------------------------------------------------------------------------

export interface ExerciseCreateInput {
  name: string;
  summary: string;
  how_to: string;
  difficulty: Difficulty;
  is_game: boolean;
  is_gymkhana: boolean;
  layout_ascii?: string | null;
  layout_alt?: string | null;
  age_bands: AgeBand[];
  skill_slugs: string[];
  material_slugs: string[];
}

export interface ExerciseUpdateInput extends Partial<ExerciseCreateInput> {}
