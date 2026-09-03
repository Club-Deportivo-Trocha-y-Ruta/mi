/**
 * Tipos para el módulo Boletín Mensual Individual por Atleta (Fase 1.8).
 *
 * Derivados del schema Pydantic backend: `app/schemas/athlete_newsletter.py`.
 * NUNCA incluir `sent_to` — es PII almacenada solo en DB, no expuesta por API.
 */

import type {
  HideableBlock,
  RegenerableBlock,
  StageLog,
  StageOverrides,
} from "@/types/stageLog.types";

export type NewsletterStatus = "draft" | "approved" | "sent" | "failed";

/** `DeliveryRow` del DTO coach — data-model.md §4. Nunca incluye email en claro. */
export type DeliveryRow = {
  parent_user_id: number | null;
  email_masked: string;
  has_account: boolean;
  sent_at: string;
  delivered_at?: string | null;
  opened_at?: string | null;
  web_read_at?: string | null;
  bounced: boolean;
};

export type AthleteNewsletter = {
  id: number;
  athlete_id: number;
  year: number;
  month: number;
  status: NewsletterStatus;
  /** Bloques de contenido para el email (sin antropometría — esos van solo en PDF). */
  email_blocks: Record<string, unknown> | null;
  badges_earned: Array<Record<string, unknown>> | null;
  /**
   * Indicador booleano de existencia de PDF generado.
   * El backend NO expone la ruta de storage (predecible y potencialmente
   * accesible sin auth). Descargar siempre vía endpoint /pdf autenticado.
   */
  has_pdf: boolean;
  pdf_generated_at: string | null;
  pdf_sha256: string | null;
  generated_by_user_id: number | null;
  approved_by_user_id: number | null;
  approved_at: string | null;
  sent_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  // NUNCA incluir sent_to — PII solo en DB

  // -- Feature 038 (bitácora) --
  stage_log: StageLog | null;
  stage_overrides: StageOverrides | null;
  hidden_blocks: HideableBlock[];
  coach_note: string | null;
  read_at: string | null;
  delivery: DeliveryRow[];
  /** Insights adjuntados, en el orden elegido por el coach (AnalystPicker). */
  selected_race_insight_ids: number[];
};

export type AthleteNewsletterCreate = {
  year: number;
  month: number;
  force?: boolean;
};

export type AthleteNewsletterPatch = {
  // -- Feature 038 (bitácora) --
  stage_overrides?: StageOverrides;
  hidden_blocks?: HideableBlock[];
  coach_note?: string | null;
  /** Reorden únicamente — debe ser una permutación de la lista ya guardada. */
  selected_race_insight_ids?: number[];
};

// ---------------------------------------------------------------------------
// Regenerate block (feature 038)
// ---------------------------------------------------------------------------

export interface RegenerateBlockRequest {
  block: RegenerableBlock;
  instruction?: string;
}

export type BatchResult = {
  period_year: number;
  period_month: number;
  total_athletes: number;
  created: number;
  skipped: number;
  failed: number;
  newsletter_ids: number[];
  errors: string[];
};

// ---------------------------------------------------------------------------
// attach-insights (Sprint 4 hotfix)
// ---------------------------------------------------------------------------

export interface AttachInsightsRequest {
  insight_ids: number[];
  year?: number | null;
  month?: number | null;
}

export interface AttachInsightsResponse {
  newsletter_id: number;
  athlete_id: number;
  year: number;
  month: number;
  status: string;
  selected_race_insight_ids: number[];
  created: boolean;
}
