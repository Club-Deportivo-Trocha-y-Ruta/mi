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
  parse_id: string; // uuid o id numérico serializado
  sha256: string;
  header: ImportHeader;
  n_rows_resultados: number;
  n_rows_general: number;
  warnings: string[];

  // F-UP-REV2 — metadatos de revisión detectada en /parse.
  // Cuando `(series, valida_num)` ya tiene un commit previo, el backend
  // marca el import como revisión y devuelve datos del padre para que
  // el wizard pueda renderizar el modo `diff` en step 2 sin esperar al
  // dry-run.
  will_be_revision?: boolean;
  parent_import_id?: number;
  parent_event_id?: number;
  parent_committed_at?: string; // ISO datetime
  parent_n_results?: number;
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
  /**
   * Nombre original del corredor tal como aparece en el PDF (sin normalizar).
   * El backend lo emite como `competitor_name` (ver
   * `backend/app/schemas/race_imports.py::MatchPreview`). Mantener este
   * nombre alineado con el schema Pydantic para evitar columnas vacías en
   * el wizard de validación (paso 2).
   */
  competitor_name: string;
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

/** Dry-run F-UP normal — el coach valida matches TyR antes del commit. */
export interface ImportDryRunMatchesResponse {
  parse_id: string;
  matches: ImportMatchPreview[];
  counts: ImportMatchCounts;
  warnings: string[];
  /** `false | undefined` cuando NO es revisión (preserva backward compat). */
  is_revision?: false;
}

// ---------------------------------------------------------------------------
// F-UP-REV3/4 — Diff de revisión
// ---------------------------------------------------------------------------

/** Estado de una fila persistida o nueva (subset de RaceResult). */
export interface ResultSnapshot {
  position?: number | null;
  race_time_ms?: number | null;
  points_awarded?: number | null;
  status?: string | null;
}

/** Una acción del diff por competidor. */
export interface DiffRow {
  action: "create" | "update" | "delete" | "unchanged";
  competitor_normalized_name: string;
  competitor_display_name: string;
  category_code: string;
  /** Snapshot anterior (presente para update/delete/unchanged). */
  before?: ResultSnapshot | null;
  /** Snapshot nuevo (presente para create/update/unchanged). */
  after?: ResultSnapshot | null;
  /** ID del RaceResult persistido — null en `create`. */
  result_id?: number | null;
}

export interface DiffSummary {
  n_create: number;
  n_update: number;
  n_delete: number;
  n_unchanged: number;
  n_total: number;
}

/** Dry-run modo revisión — backend devuelve diff completo. */
export interface ImportDryRunRevisionResponse {
  parse_id: string;
  is_revision: true;
  parent_event_id: number;
  diff_summary: DiffSummary;
  diff_rows: DiffRow[];
  warnings: string[];
}

/** Union — el wizard discrimina en `is_revision`. */
export type ImportDryRunResponse =
  | ImportDryRunMatchesResponse
  | ImportDryRunRevisionResponse;

// ---------------------------------------------------------------------------
// POST /imports/{parse_id}/commit
// ---------------------------------------------------------------------------

export interface ImportResolvedMatch {
  competitor_normalized_name: string;
  athlete_id: number | null;
}

export interface ImportCommitRequest {
  resolved_matches: ImportResolvedMatch[];
  /**
   * F-UP-REV4 — motivo opcional de la revisión.
   *
   * Obligatorio cuando el dry-run reporta `n_delete > 0`. El backend
   * valida (422 si missing) — el wizard también valida client-side para
   * UX (botón disabled).
   */
  revision_reason?: string;
}

export interface ImportCommitResponse {
  parse_id: string;
  race_event_id: number;
  n_results_inserted: number;
  n_competitors_created: number;
  n_competitors_linked: number;
  /**
   * F-UP-REV4 — banner de advertencia opcional cuando el diff es
   * inusualmente grande (n_total > 500 o deletes > 20% unchanged).
   */
  warning_banner?: string | null;
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
