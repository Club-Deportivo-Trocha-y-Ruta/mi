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
}
