import type { MaturationStatus } from "@/types/enums";

/** Grupo de edad usado por el backend para ajustar guardrails. */
export type AgeGroup = "10-12" | "13-15" | "16+";

/** Respuesta de POST /api/ai/athletes/{id}/phv-explanation */
export interface PHVExplanationResponse {
  /** Texto generado y saneado por guardrails. Listo para mostrar a padres. */
  text: string;
  /** ID del modelo (ej: "claude-sonnet-4-5"). */
  model: string;
  /** Nombre del proveedor (ej: "anthropic", "fake"). */
  provider: string;
  /** ISO 8601 UTC. */
  generated_at: string;
  age_group: AgeGroup;
  maturation_status: MaturationStatus | "";
}

/** Respuesta de GET /api/ai/health (solo admin). */
export interface AIHealthResponse {
  enabled: boolean;
  provider: string;
  model: string;
}

/** Estado de presupuesto de IA para la señal pre-lanzamiento. */
export type AIBudgetStatus = "ok" | "warning" | "exhausted";

/** Respuesta de GET /api/ai/status (coach + admin).
 *
 * Señal pre-lanzamiento reutilizada por todo botón "Analizar con IA"
 * para mostrar presupuesto/concurrencia antes del clic. Sin montos en
 * dólares (eso sigue siendo solo-admin vía /admin/ai-usage) ni
 * identificadores de deportistas.
 */
export interface AIStatusResponse {
  budget_status: AIBudgetStatus;
  budget_remaining_pct: number;
  concurrency_available: boolean;
  est_wait_seconds: number;
}

/** Respuesta de POST/GET
 *  /api/ai/athletes/{id}/measurements/{record_id}/explanation
 *
 *  Análisis particular de una medición vs el historial. A diferencia del
 *  PHV global, incluye los deltas calculados respecto a la medición
 *  inmediata anterior para que el frontend pueda renderizar un resumen
 *  visual antes del texto IA.
 */
export interface AnthropometricRecordExplanationResponse {
  text: string;
  model: string;
  provider: string;
  generated_at: string;
  age_group: AgeGroup;
  maturation_status: MaturationStatus | "";
  record_id: number;
  num_previous_measurements: number;
  delta_height_cm: number | null;
  delta_weight_kg: number | null;
}
