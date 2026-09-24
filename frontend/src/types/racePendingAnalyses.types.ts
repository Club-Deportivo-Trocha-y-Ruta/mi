/**
 * Tipos de los análisis IA pendientes del coach (feature 045, US5).
 *
 * Mirror de `backend/app/schemas/race_pending_analyses.py`.
 *
 * Endpoints cubiertos:
 *   - GET  /api/race-analysis/pending-analyses?state=&season=
 *   - POST /api/race-analysis/runs/{run_id}/dismiss-stale
 *
 * Solo coach/admin (padre → 403). Para cada `state`, los ítems son
 * exactamente los que cuenta el resumen del Home (`analyses_awaiting_approval`
 * / `insights_stale`, SC-005).
 *
 * Privacidad: `athlete_ref` es el nombre que la UI del coach ya muestra. Se
 * renderiza tal cual y jamás se escribe en un log, toast ni query key.
 */

/** Estado de un análisis que espera acción del coach. */
export type PendingAnalysisState = "awaiting_approval" | "stale";

/**
 * Qué respalda el ítem: una válida (se re-ejecuta con `event_id`) o el resumen
 * de temporada (`valida_num=0`; se re-ejecuta con `POST …/season-summary`).
 */
export type PendingAnalysisKind = "valida" | "season_summary";

/** Un análisis pendiente en la lista de «Temporada». */
export interface PendingAnalysis {
  /** `external_run_id` del run (no la PK interna). */
  run_id: string;
  /** Insight activo del run; `null` mientras espera aprobación. */
  insight_id: number | null;
  athlete_id: number;
  /** Nombre que la UI del coach ya muestra. Nunca se registra en logs. */
  athlete_ref: string;
  /** Competencia del análisis; `null` si es de temporada. */
  event_id: number | null;
  event_label: string;
  /**
   * Temporada del análisis (la usa «Re-ejecutar»); `null` si el backend no
   * pudo resolverla. Opcional: un backend previo a este campo no lo envía.
   */
  season?: number | null;
  /**
   * Tipo de análisis; `null` si el backend no pudo determinarlo. Opcional: un
   * backend previo a este campo no lo envía (se trata como desconocido).
   */
  kind?: PendingAnalysisKind | null;
  state: PendingAnalysisState;
  /** ISO 8601. */
  updated_at: string;
}

/** Respuesta de `GET /pending-analyses`: más recientes primero. */
export type PendingAnalyses = PendingAnalysis[];

/** Respuesta de `POST /runs/{run_id}/dismiss-stale` (siempre `stale=false`). */
export interface RunDismissStaleResponse {
  run_id: string;
  stale: boolean;
}

export interface PendingAnalysesParams {
  state: PendingAnalysisState;
  /** Acota la lista a una temporada (YYYY); sin él coincide con el conteo del Home. */
  season?: number;
}
