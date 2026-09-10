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

/**
 * Referencia a un miembro adulto del staff (041 §1.2, `NewsletterActorRef`
 * en `backend/app/schemas/athlete_newsletter.py`). SIEMPRE un coach/admin,
 * nunca un menor — `display_name` resuelve incluso para cuentas
 * desactivadas (FR-013); el objeto entero es `null` solo cuando la FK es
 * `NULL` en el backend.
 */
export type ActorRef = {
  user_id: number;
  display_name: string;
};

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

  // -- Feature 041 (gobernanza multi-entrenador / concurrencia optimista) --
  /**
   * Token de concurrencia optimista (041 §2). Viaja también como header
   * `ETag: W/"<edit_version>"` en el GET; se reenvía en el PATCH vía
   * `If-Match` (ver `patchAthleteNewsletter`).
   */
  edit_version: number;
  /**
   * Quién escribió (o borró) la nota del entrenador. Superficie SOLO
   * coach/admin — nunca se expone a la familia (FR-012, Ley 1581: siempre
   * staff adulto, nunca un menor).
   */
  coach_note_author: ActorRef | null;
  coach_note_updated_at: string | null;
  /** Último entrenador que guardó cambios de contenido (PATCH). */
  last_edited_by: ActorRef | null;
  /** Versión legible de `generated_by_user_id`. */
  generated_by: ActorRef | null;
  /** Versión legible de `approved_by_user_id`. */
  approved_by: ActorRef | null;

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
  /**
   * Precondición de concurrencia optimista (041 §2.2) — alternativa en
   * body a `If-Match`. `patchAthleteNewsletter` la extrae del payload y la
   * envía siempre como header `If-Match`, nunca como campo real del body
   * (el backend tampoco la escribe a ninguna columna).
   */
  expected_version?: number;
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
