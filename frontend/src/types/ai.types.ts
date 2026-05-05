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
