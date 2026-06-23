/** Tipos del módulo de ansiedad competitiva (feature 017). */

export type AnxietyInstrumentType = "csai2" | "csai2r" | "sas2";
export type AnxietyStatus = "pending" | "partial" | "completed";
export type AnxietySource = "llm" | "rule";
export type GroupPattern =
  | "somatic_high"
  | "cognitive_high"
  | "confidence_low"
  | "favorable";

export interface IssuedToken {
  token: string;
  expires_at: string;
}

export interface AssessmentCreated {
  id: number;
  athlete_id: number;
  instrument_type: AnxietyInstrumentType;
  status: AnxietyStatus;
  instrument_override: boolean;
  scheduled_at: string;
  warning: string | null;
  token: IssuedToken | null;
}

export interface BatchItemResult {
  athlete_id: number;
  created: boolean;
  assessment: AssessmentCreated | null;
  warning: string | null;
  error: string | null;
}

export interface BatchCreated {
  items: BatchItemResult[];
}

export interface AnswerItem {
  item_id: number;
  text: string | null;
}

export interface AnswerForm {
  instrument_type: AnxietyInstrumentType;
  intro: string;
  scale_min: number;
  scale_max: number;
  items: AnswerItem[];
}

export interface AnswerResult {
  status: "completed" | "partial";
  short_message: string;
}

export interface SubscaleRead {
  score: number | null;
  baseline: number | null;
  delta: number | null;
}

export interface Interpretation {
  resumen: string;
  por_dimension: {
    cognitiva: string;
    somatica: string;
    autoconfianza: string;
  };
  estrategias: string[];
  mensaje_para_el_atleta: string;
  banderas: string[];
}

export interface AssessmentRead {
  id: number;
  athlete_id: number;
  instrument_type: AnxietyInstrumentType;
  event_id: number | null;
  priority: "A" | "B" | "C" | null;
  scheduled_at: string;
  status: AnxietyStatus;
  is_partial: boolean;
  instrument_override: boolean;
  cognitive: SubscaleRead;
  somatic: SubscaleRead;
  selfconfidence: SubscaleRead;
  interpretation: Interpretation | null;
  interpretation_source: AnxietySource | null;
  flags: string[];
}

export interface InterpretationResponse {
  assessment_id: number;
  interpretation: Interpretation;
  source: AnxietySource;
  model: string | null;
}

export interface SeriesPoint {
  assessment_id: number;
  scheduled_at: string;
  event_id: number | null;
  cognitive: number | null;
  somatic: number | null;
  selfconfidence: number | null;
  flags: string[];
}

export interface AthleteSeries {
  athlete_id: number;
  instrument_type: AnxietyInstrumentType;
  baseline_cognitive: number | null;
  baseline_somatic: number | null;
  baseline_selfconfidence: number | null;
  points: SeriesPoint[];
  note: string | null;
}

export interface GroupMember {
  athlete_id: number;
  assessment_id: number;
  cognitive: number | null;
  somatic: number | null;
  selfconfidence: number | null;
  flags: string[];
}

export interface GroupTriage {
  event_id: number;
  buckets: Record<GroupPattern, GroupMember[]>;
  alerts: GroupMember[];
}

export interface ImportRowError {
  row: number;
  error: string;
}

export interface ImportResult {
  imported: number;
  skipped: number;
  errors: ImportRowError[];
}

export interface CreateAssessmentInput {
  athlete_id: number;
  event_id?: number | null;
  scheduled_at: string;
  instrument_type?: AnxietyInstrumentType | null;
  override?: boolean;
}

export interface CreateBatchInput {
  athlete_ids: number[];
  event_id: number;
  scheduled_at: string;
}
