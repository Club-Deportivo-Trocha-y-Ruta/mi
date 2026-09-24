/**
 * Tipos de composición corporal por pliegues cutáneos (feature 046).
 *
 * Mirror manual de `backend/app/schemas/body_composition.py`
 * (`contracts/skinfolds-api.md`, `data-model.md` §5–§6). Mismo patrón que
 * `types/anthropometry.types.ts`: interfaces escritas a mano, con el schema
 * Zod equivalente en `schemas/bodyComposition.schema.ts` (allowlist en
 * cliente, `.parse()` de respuestas de API).
 *
 * Privacidad (Ley 1581): estos tipos nunca incluyen nombre/apellido del
 * deportista; sólo `athlete_id`.
 */

/** Los seis sitios de pliegue del protocolo (orden fijo del wizard). */
export type SkinfoldSite =
  | "triceps"
  | "biceps"
  | "subscapular"
  | "medial_calf"
  | "iliac_crest"
  | "supraspinale";

export const SKINFOLD_SITES: readonly SkinfoldSite[] = [
  "triceps",
  "biceps",
  "subscapular",
  "medial_calf",
  "iliac_crest",
  "supraspinale",
];

/** Entrada de un sitio: o se omitió, o trae 2–3 lecturas en milímetros. */
export type SkinfoldSiteIn =
  | { declined: true }
  | { declined?: false; readings: number[] };

export interface SkinfoldSetIn {
  caliper_model: string;
  sites: Record<SkinfoldSite, SkinfoldSiteIn>;
}

export interface SkinfoldSiteOut {
  value_mm: number | null;
  readings: number[] | null;
  declined: boolean;
  /** true cuando las dos primeras lecturas superan la tolerancia y no hubo tercera. */
  unconfirmed: boolean;
}

export interface SkinfoldSetOut {
  record_id: number;
  athlete_id: number;
  evaluation_date: string;
  caliper_model: string;
  protocol_version: string;
  sites: Record<SkinfoldSite, SkinfoldSiteOut>;
  sum4_mm: number | null;
  sum6_mm: number | null;
  body_fat_pct: number | null;
  fat_mass_kg: number | null;
  fat_free_mass_kg: number | null;
  equation_version: string | null;
  /** Margen de medición mostrado junto al cambio (siempre 4). */
  margin_pct: number;
  measured_by: number;
  updated_at: string;
  /** Sitios con dos lecturas fuera de tolerancia sin tercera confirmatoria. */
  needs_third_reading_unconfirmed: SkinfoldSite[];
}

// ---------------------------------------------------------------------------
// Lectura derivada (nunca persistida) — contracts/body-composition-reading.md
// ---------------------------------------------------------------------------

export type SumChangeCode = "none" | "within_noise" | "up_real" | "down_real";
export type WeightChangeCode = "up" | "flat_or_down" | "unavailable";
export type HeightGrowthCode = "growing" | "stalled" | "unavailable";
export type VelocityCode = "within_or_above" | "below" | "unavailable";
export type BmiZChangeCode = "ok" | "drop_moderate" | "drop_large" | "unavailable";
export type ReferenceCode =
  | "low_extreme"
  | "low"
  | "normal"
  | "high"
  | "high_extreme"
  | "unavailable";
export type FfmTrendCode = "up" | "flat" | "down" | "unavailable";

/** Banda del coach (nunca visible a familias tal cual). */
export type CoachBand = "verde" | "ambar" | "rojo";
/** Proyección familiar — nunca `rojo` (contract §3c). */
export type FamilyBand = "verde" | "ambar";

export type BandReasonCode =
  | "no_real_change"
  | "expected_pubertal_gain"
  | "pre_spurt_accumulation"
  | "post_phv_lean_gain"
  | "first_set"
  | "stable"
  | "sum_up_unexplained"
  | "sum_up_velocity_low"
  | "sum_down_unexplained"
  | "reference_extreme"
  | "bmi_z_drop"
  | "velocity_low_persistent"
  | "energy_availability_pattern";

export type LegMissing =
  | "weight"
  | "height"
  | "velocity"
  | "bmi_z"
  | "reference"
  | "previous_set";

export interface ReferencePoint {
  percentile: number | null;
  code: ReferenceCode;
}

export interface BodyCompositionReading {
  sets_count: number;
  sum4_change_mm: number | null;
  sum6_change_mm: number | null;
  sum_change_code: SumChangeCode;
  weight_change_code: WeightChangeCode;
  height_growth_code: HeightGrowthCode;
  velocity_code: VelocityCode;
  bmi_z_change_code: BmiZChangeCode;
  reference_triceps: ReferencePoint;
  reference_subscapular: ReferencePoint;
  ffm_trend_code: FfmTrendCode;
  sites_declined_count: number;
  band: CoachBand;
  family_band: FamilyBand;
  latest_attempt_declined: string | null;
  band_reason_code: BandReasonCode;
  legs_missing: LegMissing[];
  next_due_date: string | null;
  days_until_due: number | null;
}

// ---------------------------------------------------------------------------
// Read models compuestos
// ---------------------------------------------------------------------------

export interface BodyCompositionSeriesPoint {
  date: string;
  value: number;
}

export interface BodyCompositionSeries {
  sum4: BodyCompositionSeriesPoint[];
  sum6: BodyCompositionSeriesPoint[];
  per_site: Record<SkinfoldSite, BodyCompositionSeriesPoint[]>;
}

export interface BodyCompositionEstimatesLatest {
  body_fat_pct: number | null;
  fat_mass_kg: number | null;
  fat_free_mass_kg: number | null;
  equation_version: string | null;
  margin_pct: number;
}

export interface BodyCompositionReferenceInfo {
  source: string;
  population: string;
  side: string;
  age_range: string;
}

/** `GET /api/athletes/{id}/body-composition` (coach/admin). */
export interface BodyCompositionOut {
  athlete_id: number;
  sets: SkinfoldSetOut[];
  series: BodyCompositionSeries | null;
  reading: BodyCompositionReading | null;
  estimates_latest: BodyCompositionEstimatesLatest | null;
  reference: BodyCompositionReferenceInfo | null;
  next_due_date: string | null;
}

/** Bloque `body_composition` de `GrowthSummaryOut` para coach/admin. */
export interface BodyCompositionSummary {
  has_data: boolean;
  latest_set_date: string | null;
  /** `null` (como las demás claves de lectura) cuando `has_data=false`. */
  band: CoachBand | null;
  family_band: FamilyBand | null;
  family_label: string | null;
  family_sentence: string | null;
  next_due_date: string | null;
  days_until_due: number | null;
  latest_attempt_declined: string | null;
  coach_reason: string | null;
  sum4_mm: number | null;
  sum4_change_mm: number | null;
  sum_change_code: SumChangeCode | null;
  sum6_mm: number | null;
  body_fat_pct: number | null;
  fat_free_mass_kg: number | null;
  legs_missing: LegMissing[];
}

/**
 * Bloque `body_composition` de `GrowthSummaryOut` para padres — exactamente
 * estas cinco claves, sin `band` ni cifras (`contracts/skinfolds-api.md` §5).
 */
export interface BodyCompositionFamilySummary {
  has_data: boolean;
  latest_set_date: string | null;
  family_band: FamilyBand | null;
  family_label: string | null;
  family_sentence: string | null;
}

/** Discriminado por rol: sólo el coach recibe `band`. */
export type BodyCompositionSummaryOut =
  | BodyCompositionSummary
  | BodyCompositionFamilySummary;

/** `body_composition` fijo del boletín mensual (spec FR-036, nunca vía IA). */
export interface BodyCompositionNewsletterBlock {
  family_label: string;
  family_sentence: string;
  notice_text: string;
}
