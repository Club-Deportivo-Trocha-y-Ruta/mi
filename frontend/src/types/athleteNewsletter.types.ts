/**
 * Tipos para el módulo Boletín Mensual Individual por Atleta (Fase 1.8).
 *
 * Derivados del schema Pydantic backend: `app/schemas/athlete_newsletter.py`.
 * NUNCA incluir `sent_to` — es PII almacenada solo en DB, no expuesta por API.
 */

export type NewsletterStatus = "draft" | "approved" | "sent" | "failed";

export type NarrativeOverride = {
  strengths?: string | null;
  area_to_develop?: string | null;
  milestone?: string | null;
};

export type AiNarrative = {
  strengths: string;
  area_to_develop: string;
  milestone: string;
  model: string;
  prompt_version: string;
  confidence: "low" | "medium" | "high";
};

export type AthleteNewsletter = {
  id: number;
  athlete_id: number;
  year: number;
  month: number;
  status: NewsletterStatus;
  /** Bloques de contenido para el email (sin antropometría — esos van solo en PDF). */
  email_blocks: Record<string, unknown> | null;
  ai_narrative: AiNarrative | null;
  coach_narrative_overrides: NarrativeOverride | null;
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
};

export type AthleteNewsletterCreate = {
  year: number;
  month: number;
  force?: boolean;
};

export type AthleteNewsletterPatch = {
  coach_narrative_overrides: NarrativeOverride;
};

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
