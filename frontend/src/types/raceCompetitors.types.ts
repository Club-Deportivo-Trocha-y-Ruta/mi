/**
 * Tipos del módulo race-competitors (enlace retroactivo de competitors).
 *
 * Mirror de los Pydantic schemas en `backend/app/schemas/race_competitors.py`.
 * Endpoints bajo `/api/race-competitors/*` (Option A R1).
 *
 * Privacidad: `display_name` proviene de PDFs oficiales públicos de la
 * Federación; no exponer DOB ni datos médicos.
 */

// ---------------------------------------------------------------------------
// Sugerencias top-N (match fuzzy backend)
// ---------------------------------------------------------------------------

export interface AthleteSuggestion {
  athlete_id: number;
  full_name: string;
  /** Score en rango [0, 1]. Ya viene escalado: NO normalizar. */
  score: number;
  /** Texto humano explicando el match (ej. "Nombre fuzzy 0.92 + categoría INF_A"). */
  reason: string;
}

// ---------------------------------------------------------------------------
// GET /api/race-competitors/?unlinked=true
// ---------------------------------------------------------------------------

export interface UnlinkedCompetitorItem {
  id: number;
  display_name: string;
  normalized_name: string;
  club_text: string | null;
  sex: "M" | "F" | null;
  results_count: number;
  /** Temporadas en las que participó (ej. [2025, 2026]). */
  seasons: number[];
  /** Top-N sugerencias incluidas inline cuando se solicita. */
  suggestions: AthleteSuggestion[];
}

export interface UnlinkedCompetitorsListResponse {
  items: UnlinkedCompetitorItem[];
  total: number;
}

export interface UnlinkedCompetitorsParams {
  unlinked?: boolean;
  /**
   * Filtro de club por texto (case-insensitive, contiene).
   * Ejemplo: "trocha" filtra a competitors con club_text que contenga "trocha".
   */
  club_filter?: string;
  /** Temporada exacta (ej. 2026). */
  season?: number;
  include_suggestions?: boolean;
  /** Top-N de sugerencias inline (default backend: 3). */
  suggestions_limit?: number;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// GET /api/race-competitors/{id}/suggestions
// ---------------------------------------------------------------------------

export interface CompetitorSuggestionsResponse {
  competitor_id: number;
  suggestions: AthleteSuggestion[];
}

// ---------------------------------------------------------------------------
// POST /api/race-competitors/{id}/link
// ---------------------------------------------------------------------------

export interface CompetitorLinkRequest {
  athlete_id: number;
}

export interface CompetitorLinkResponse {
  competitor_id: number;
  athlete_id: number;
  /** ISO datetime. */
  linked_at: string;
  /** Cantidad de RaceResult propagados al athlete_id. */
  results_propagated: number;
  /** true si el competitor ya estaba enlazado al mismo athlete (idempotente). */
  already_linked: boolean;
}

// ---------------------------------------------------------------------------
// DELETE /api/race-competitors/{id}/link
// ---------------------------------------------------------------------------

export interface CompetitorUnlinkResponse {
  competitor_id: number;
  was_linked: boolean;
  /** Cantidad de RaceResult que quedaron sin athlete_id asociado. */
  results_propagated: number;
}
