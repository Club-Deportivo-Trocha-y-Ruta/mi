/** Tipos del módulo Técnica y Gymkhana (feature 018). */

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
  confidence: number | null;
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
}

export interface TechniqueSessionItem {
  exercise_id: number;
  name: string;
  segment: SessionSegment;
  position: number;
  age_bands: AgeBand[];
  skills: SkillRef[];
}

export interface AssembleSessionResult {
  training_session_id: number;
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
