import type { MaturationStatus } from "@/types/enums";

export interface AnthropometryCreate {
  evaluation_date: string;
  mesocycle?: number | null;
  weight_kg: number;
  standing_height_cm: number;
  arm_span_cm?: number | null;
  sitting_height_cm: number;
  notes?: string | null;
}

export interface AnthropometricRecord {
  id: number;
  athlete_id: number;
  evaluation_date: string;
  mesocycle: number | null;
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
}
