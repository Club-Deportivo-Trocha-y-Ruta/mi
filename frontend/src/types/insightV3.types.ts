/**
 * Tipos TypeScript del InsightV3 estructurado (feature 037, T205).
 *
 * Mirror 1:1 de los Pydantic schemas en:
 *   backend/app/services/race/insight_v3.py (T201, aún no implementado —
 *   este archivo sigue ``specs/037-ai-insights-v3-causal/data-model.md
 *   §InsightV3`` como contrato de referencia).
 *
 * Privacidad (CLAUDE.md §Privacidad de menores): ningún campo de este
 * modelo contiene nombre real, peso, IMC ni estado nutricional — son
 * observaciones/acciones ya redactadas por el analista IA sobre datos
 * agregados y numéricos.
 */

export const EvidenceDomain = {
  RACE: "race",
  FIELD: "field",
  TRAINING: "training",
  MATURATION: "maturation",
  CONDITIONS: "conditions",
  HISTORY: "history",
} as const;
export type EvidenceDomain = (typeof EvidenceDomain)[keyof typeof EvidenceDomain];

export const ActionCategory = {
  TECHNIQUE: "technique",
  VOLUME: "volume",
  RECOVERY: "recovery",
  NUTRITION: "nutrition",
  PSYCHOLOGY: "psychology",
  TACTICS: "tactics",
} as const;
export type ActionCategory = (typeof ActionCategory)[keyof typeof ActionCategory];

export type Priority = "low" | "med" | "high";

export const Horizon = {
  NEXT_WEEK: "next_week",
  NEXT_RACE: "next_race",
  SEASON: "season",
} as const;
export type Horizon = (typeof Horizon)[keyof typeof Horizon];

export const CatalogKind = {
  TECHNIQUE_SKILL: "technique_skill",
  STRENGTH_BLOCK: "strength_block",
  INTERVAL_TEMPLATE: "interval_template",
} as const;
export type CatalogKind = (typeof CatalogKind)[keyof typeof CatalogKind];

export type InsightV3Confidence = "high" | "medium" | "low";

export interface Observation {
  /** ≤ 300 caracteres, una oración interpretativa. */
  claim: string;
  /** 1..3 items, ≤ 140 caracteres, cada uno con ≥1 número copiado de los datos. */
  evidence: string[];
  domain: EvidenceDomain;
  confidence: InsightV3Confidence;
}

export interface CatalogRef {
  kind: CatalogKind;
  /** Código de habilidad técnica "A".."H", o id numérico como string. */
  code: string;
  /** Rellenado por los prechecks del backend desde catalog_context. */
  label: string | null;
}

export interface ActionV3 {
  /** ≤ 280 caracteres, imperativo, concreto (qué, cuántas veces, cuánto). */
  text: string;
  category: ActionCategory;
  priority: Priority;
  horizon: Horizon;
  catalog_ref: CatalogRef | null;
  /** Índice dentro de `observations`. */
  derived_from: number | null;
}

export interface FieldReading {
  /** 0..100, 100 = ganador. */
  percentile: number | null;
  expected_position: number | null;
  actual_position: number | null;
  delta_vs_expected: number | null;
  gap_to_p3_hhmmss: string | null;
  /** "Válida V · Copa Valle" / "Cto. Departamental". */
  series_label: string;
  /** ≤ 200 caracteres, prosa. */
  summary: string;
}

export type InsightV3Trend =
  | "improving"
  | "stable"
  | "declining"
  | "mixed"
  | "first_reference";

export interface InsightV3 {
  schema_version: "v3";
  /** ≤ 200 caracteres. */
  headline: string;
  field_reading: FieldReading | null;
  trend: InsightV3Trend;
  /** 2..4 items. */
  observations: Observation[];
  /** 2..3 items. */
  actions: ActionV3[];
  /** 0..2 items, ≤ 140 caracteres. */
  watch_signals: string[];
  /** ≤ 240 caracteres, termina en "?". */
  coach_question: string;
  /** 0..3 items, ≤ 140 caracteres. */
  data_gaps: string[];
  /** Títulos de sección de docs/01-marco-teorico.md, 0..3 items. */
  principles_cited: string[];
}
