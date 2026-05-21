/**
 * Tipos del módulo race-imports (Wizard de carga PDFs Copa Valle).
 *
 * Mirror de los Pydantic schemas en `backend/app/schemas/race_imports.py`.
 * Endpoints documentados en `docs/10-race-results/upload-design.md` §4.
 *
 * Privacidad: ningún schema lleva nombres reales de menores fuera del
 * contexto de matches (display_name es el nombre tal como aparece en el
 * PDF oficial publicado por la Federación, ya es información pública).
 */

// ---------------------------------------------------------------------------
// Header / Warnings
// ---------------------------------------------------------------------------

export interface ImportHeader {
  series_name: string;
  season: number;
  valida_num: number;
  event_name: string;
}

export type ImportStatus = "pending" | "committed" | "failed";

// ---------------------------------------------------------------------------
// POST /imports/parse
// ---------------------------------------------------------------------------

export interface ImportParseRequestFields {
  series_name: string;
  season: number;
  valida_num: number;
  event_name: string;
  event_date: string; // YYYY-MM-DD
  location: string;
  kind?: "resultados" | "general" | "both";
}

export interface ImportParseResponse {
  parse_id: string; // uuid
  sha256: string;
  header: ImportHeader;
  n_rows_resultados: number;
  n_rows_general: number;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// POST /imports/{parse_id}/dry-run
// ---------------------------------------------------------------------------

export interface MatchedAthlete {
  id: number;
  full_name: string;
}

export interface ImportMatchPreview {
  competitor_normalized_name: string;
  competitor_display_name: string;
  tyr_athlete: MatchedAthlete | null;
  confidence: number; // 0-1
  is_ambiguous: boolean;
}

export interface ImportMatchCounts {
  confirmed: number;
  ambiguous: number;
  no_match: number;
  total: number;
}

export interface ImportDryRunResponse {
  parse_id: string;
  matches: ImportMatchPreview[];
  counts: ImportMatchCounts;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// POST /imports/{parse_id}/commit
// ---------------------------------------------------------------------------

export interface ImportResolvedMatch {
  competitor_normalized_name: string;
  athlete_id: number | null;
}

export interface ImportCommitRequest {
  resolved_matches: ImportResolvedMatch[];
}

export interface ImportCommitResponse {
  parse_id: string;
  race_event_id: number;
  n_results_inserted: number;
  n_competitors_created: number;
  n_competitors_linked: number;
}

// ---------------------------------------------------------------------------
// GET /imports/
// ---------------------------------------------------------------------------

export interface ImportUploader {
  id: number;
  full_name: string;
}

export interface ImportListItem {
  id: string;
  kind: "resultados" | "general" | "both";
  status: ImportStatus;
  created_at: string; // ISO datetime
  event_id: number | null;
  original_filename: string;
  uploaded_by: ImportUploader;
  n_results: number;
}

export interface ImportListResponse {
  items: ImportListItem[];
  total: number;
}

export interface ImportsHistoryParams {
  limit?: number;
  offset?: number;
  status?: ImportStatus;
}
