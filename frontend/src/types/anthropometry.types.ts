import type { SkinfoldSetOut } from "@/types/bodyComposition.types";
import type { MaturationStatus } from "@/types/enums";

export interface AnthropometryCreate {
  evaluation_date: string;
  weight_kg: number;
  standing_height_cm: number;
  arm_span_cm?: number | null;
  sitting_height_cm: number;
  notes?: string | null;
}

export type BikeFitCategory = "short_reach" | "standard" | "long_reach";

export interface MorphologyMetrics {
  ape_index: number;
  arm_span_height_delta_cm: number;
  posture_screening_flag: boolean;
  posture_screening_message: string | null;
  bike_fit_category: BikeFitCategory;
  bike_fit_guidance: string;
  ape_index_advisory: string | null;
}

/**
 * Referencia poblacional usada para calcular los Z-score/percentil/banda
 * almacenados en el registro. `null` = registro legado aún no recomputado
 * (feature 040 — la UI debe mostrar "Referencia anterior — pendiente de
 * actualizar" en ese caso; ver `contracts/band-vocabulary.md`).
 */
export type GrowthSource = "WHO" | "CDC" | null;

export interface AnthropometricRecord {
  id: number;
  athlete_id: number;
  evaluation_date: string;
  weight_kg: number;
  standing_height_cm: number;
  arm_span_cm: number | null;
  sitting_height_cm: number;
  leg_length_cm: number;
  leg_sitting_ratio: number;
  maturity_offset: number;
  age_at_phv: number;
  maturation_status: MaturationStatus;
  training_implications: string | null;
  evaluated_by: number;
  created_at: string;
  notes: string | null;
  // Campos de percentiles de crecimiento (calculados por el backend, opcionales en records historicos)
  height_z_score?: number | null;
  height_percentile?: number | null;
  bmi?: number | null;
  bmi_z_score?: number | null;
  bmi_percentile?: number | null;
  weight_z_score?: number | null;
  weight_percentile?: number | null;
  nutritional_status?: string | null;
  morphology?: MorphologyMetrics | null;
  /** Referencia usada para los campos anteriores (feature 040). */
  growth_source?: GrowthSource;
  /** Solo coach/admin (feature 048): el usuario es el evaluador o admin. Omitido para padres. */
  can_modify?: boolean;
  /** Solo coach/admin (feature 048): códigos de plausibilidad para el marcador «Revisar». */
  plausibility_flags?: PlausibilityCode[];
  /**
   * Set de pliegues cutáneos de esta evaluación (feature 046,
   * `contracts/skinfolds-api.md` §3). Siempre `null` para padres.
   */
  skinfolds?: SkinfoldSetOut | null;
}

/** Códigos estables de la API (research R5); el texto en español vive en el frontend. */
export type PlausibilityCode =
  | "height_decreased"
  | "height_velocity_implausible"
  | "weight_change_large"
  | "sitting_ratio_atypical"
  | "arm_span_ratio_atypical";

export type PlausibilityMeasure =
  | "weight"
  | "standing_height"
  | "sitting_height"
  | "arm_span";

/** Cuerpo de `POST /api/athletes/{id}/anthropometry/plausibility` (dry-run). */
export interface PlausibilityCheckRequest {
  evaluation_date: string;
  weight_kg: number;
  standing_height_cm: number;
  sitting_height_cm: number;
  arm_span_cm?: number | null;
  /** Al editar: excluye ese registro de «anterior». */
  record_id?: number | null;
}

export interface PlausibilityWarning {
  code: PlausibilityCode;
  measure: PlausibilityMeasure;
}

export interface PlausibilityCheckResponse {
  warnings: PlausibilityWarning[];
  previous_evaluation_date: string | null;
}

/** Cuerpo de `PUT /api/athletes/{id}/anthropometry/{record_id}` (reemplazo completo). */
export interface AnthropometryUpdate {
  evaluation_date: string;
  weight_kg: number;
  standing_height_cm: number;
  sitting_height_cm: number;
  arm_span_cm?: number | null;
  notes?: string | null;
}

/** Fila de `GET /api/anthropometry/roster` (sesión grupal). */
export interface RosterRow {
  athlete_id: number;
  full_name: string;
  category: string;
  sex: "M" | "F";
  birth_date: string;
  last_evaluation_date: string | null;
  has_record_on_date: boolean;
  skinfolds_eligible: boolean;
}

/** Cuerpo 409 `anthropometry_same_date_exists` (research R4). */
export interface SameDateConflictDetail {
  detail: "anthropometry_same_date_exists";
  existing_record_id: number;
  same_values: boolean;
}
