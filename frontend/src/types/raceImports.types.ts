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
// Condiciones de carrera (F-COND — feature condiciones)
// ---------------------------------------------------------------------------

/**
 * Estado del terreno al momento de la carrera.
 * Mirror del enum `SurfaceCondition` en el backend.
 */
export type SurfaceCondition =
  | "seca"
  | "humeda"
  | "barro"
  | "lluvia"
  | "mixta";

// ---------------------------------------------------------------------------
// Header / Warnings
// ---------------------------------------------------------------------------

export interface ImportHeader {
  series_name: string;
  season: number;
  valida_num: number;
  event_name: string;
}

/**
 * Estado de una carga. `dry_run` y `discarded` llegaron con la feature 045:
 * `pending|dry_run` son las cargas «en curso» (se pueden retomar o descartar);
 * `discarded` queda fuera del listado por defecto.
 */
export type ImportStatus =
  | "pending"
  | "dry_run"
  | "committed"
  | "failed"
  | "discarded";

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
  /**
   * Spec 014 — Cup vs Championship: tipo de la serie a la que pertenece el
   * evento. El backend lo usa para resolver/crear la serie correctamente y
   * para omitir el número de válida en campeonatos (fuerza sequence_number=1,
   * is_championship=true). Default `cup` para compatibilidad hacia atrás.
   */
  series_kind?: "cup" | "championship";
  /**
   * Feature 023 — Nivel del campeonato (departamental|nacional). Solo
   * consultado por el backend cuando crea una serie de campeonato NUEVA;
   * ignorado si la serie ya existe (resuelta por `series_id`). Default
   * `departmental` para compatibilidad hacia atrás.
   */
  series_level?: "departmental" | "national";
  // F-COND — campos opcionales de condiciones de carrera
  /** Descripción corta del clima (máx 60 chars), ej: "Soleado con viento". */
  climate?: string | null;
  /** Temperatura ambiente en °C (0-50). Acepta string o number para flexibilidad de inputs. */
  temperature_c?: string | number | null;
  /** Estado del terreno en el momento de la prueba. */
  surface_condition?: SurfaceCondition | null;
  /** Altitud de la sede en metros sobre el nivel del mar (0-5000). */
  altitude_msnm?: number | null;
  /** Notas adicionales de condiciones climáticas (máx 2000 chars). */
  weather_notes?: string | null;
}

/**
 * Condiciones de carrera tal como las devuelve el backend en el bloque
 * `conditions` del response de `/imports/parse`.
 *
 * Todos los campos son `null` cuando no se enviaron en el form-data.
 * `temperature_c` llega como string decimal desde el backend (Decimal → str).
 */
export interface ParsedConditions {
  climate: string | null;
  temperature_c: string | null;
  surface_condition: SurfaceCondition | null;
  altitude_msnm: number | null;
  weather_notes: string | null;
}

export interface ImportParseResponse {
  parse_id: string; // uuid o id numérico serializado
  sha256: string;
  header: ImportHeader;
  n_rows_resultados: number;
  n_rows_general: number;
  warnings: string[];

  // F-COND — condiciones de carrera parseadas (null si no se enviaron).
  conditions?: ParsedConditions | null;

  // Feature 044 (US1) — integridad de lectura: categorías del acta con su
  // completitud, y filas que el parser no pudo interpretar. Aditivo, default
  // vacío en el backend para no romper clientes previos.
  categories?: ParsedCategory[];
  unreadable_rows?: UnreadableRow[];

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
// Feature 044 (US1) — Integridad de lectura del acta
// (contracts/reading-integrity.md §"API deltas")
//
// Mirror de `backend/app/schemas/race_imports.py`:
// `ParsedCategoryRead`, `CompletenessRead`, `UnreadableRowRead`,
// `RowCorrectionIn`, `AcknowledgeIn`, `AcknowledgeReasonsResponse`.
//
// Privacidad: `ParsedResultsRow` trae nombre/ciudad/club de un corredor —
// mismo origen público (PDF oficial de la Federación) que `MatchPreview`
// arriba. Nunca va a un log ni a un parámetro de query/URL.
// ---------------------------------------------------------------------------

/** Estado de completitud de una categoría (`completeness.CompletenessReport`). */
export type CompletenessStatus = "ok" | "inconsistent" | "acknowledged";

/** Cómo resolvió el header de una categoría (`normalizer.mapping_kind_for`). */
export type CategoryMappingKind =
  | "exact"
  | "rename"
  | "season_specific"
  | "unknown";

export interface CategoryCompleteness {
  status: CompletenessStatus;
  missing: number[];
  duplicated: number[];
}

/** Una fila cruda del acta tal como la interpretó el parser. */
export interface ParsedResultsRow {
  position: number | null;
  bib: string;
  name: string;
  city: string;
  club: string;
  time_raw: string;
  points: number;
}

/** Una categoría del acta con su completitud (mirror `ParsedCategoryRead`). */
export interface ParsedCategory {
  header_raw: string;
  /** `null` = encabezado no reconocido; las filas se conservan igual. */
  code: string | null;
  mapping_kind: CategoryMappingKind;
  rows: ParsedResultsRow[];
  /**
   * Cantidad de filas cuando la categoría se rehidrata desde
   * `GET /imports/{id}` (feature 045): el meta persistido solo guarda el
   * conteo, no las filas (`rows` llega vacío). Si existe, gana sobre
   * `rows.length` al mostrar la columna «Filas».
   */
  row_count?: number;
  completeness: CategoryCompleteness;
}

/** Banda de fila que el parser no pudo interpretar — solo ubicación. */
export interface UnreadableRow {
  page: number;
  ordinal: number | null;
}

// ---------------------------------------------------------------------------
// POST /imports/{parse_id}/corrections
// ---------------------------------------------------------------------------

export type RowCorrectionOp = "add" | "edit" | "remove";

/** Cuerpo de una fila para `POST /{parse_id}/corrections` (mirror `ResultsRowIn`). */
export interface RowCorrectionRow {
  position: number | null;
  bib: string;
  name: string;
  city: string;
  club: string;
  time_raw: string;
  points: number;
}

/** Body de `POST /{parse_id}/corrections` (mirror `RowCorrectionIn`). */
export interface RowCorrectionInput {
  op: RowCorrectionOp;
  category_header: string;
  ordinal: number;
  /** Obligatorio para `add`/`edit`; ausente en `remove`. */
  row?: RowCorrectionRow | null;
}

/** Respuesta común de `/corrections` y `/acknowledge`. */
export interface CategoryCompletenessResponse {
  category_header: string;
  completeness: CategoryCompleteness;
}

// ---------------------------------------------------------------------------
// POST /imports/{parse_id}/acknowledge + GET /imports/acknowledge-reasons
// ---------------------------------------------------------------------------

/** Catálogo CERRADO de motivos de reconocimiento (mirror `AcknowledgeReasonCode`). */
export type AcknowledgeReasonCode =
  | "source_duplicate_ordinal"
  | "source_missing_ordinal"
  | "source_disqualification_gap"
  | "verified_against_source";

/** Body de `POST /{parse_id}/acknowledge` (mirror `AcknowledgeIn`). */
export interface AcknowledgeInput {
  category_header: string;
  reason: AcknowledgeReasonCode;
}

export interface AcknowledgeReasonOption {
  code: string;
  label: string;
}

export interface AcknowledgeReasonsResponse {
  options: AcknowledgeReasonOption[];
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
  /**
   * Feature 044 (US1/US5) — headers de categorías cuyo commit quedó fuera
   * (inconsistentes sin reconocer, o de encabezado no reconocido). Aditivo,
   * default vacío en el backend.
   */
  pending_categories?: string[];
}

// ---------------------------------------------------------------------------
// POST /imports/{parse_id}/commit-pending — feature 044 (US5)
// (`contracts/historical-load.md` §"Idempotence and resumption")
// ---------------------------------------------------------------------------

/**
 * Ingiere solo las categorías que quedaron pendientes en un commit parcial
 * anterior, una vez consistentes o reconocidas. Mismo shape de respuesta
 * que `/commit` — `pending_categories` refleja lo que siga sin resolver.
 * `409 nothing_pending` cuando no hay nada por ingerir; sujeto al mismo
 * candado `409 identity_pending` (por carga, feature 045) que `/commit`.
 */
export type ImportCommitPendingResponse = ImportCommitResponse;

/**
 * Cuerpo PLANO del `409` con que `/commit` y `/commit-pending` bloquean una
 * carga que tiene decisiones de identidad pendientes (feature 045,
 * `contracts/api.md`). Reemplaza al viejo cuerpo anidado (`detail` como objeto
 * con un `code`), que ya no existe. `pending_for_import` cuenta solo los
 * candidatos que involucran a ESTA carga; `review_path` lleva a resolverlos
 * conservando `import=<id>` para volver al mismo punto.
 */
export interface IdentityPendingBody {
  detail: "identity_pending";
  pending_for_import: number;
  review_path: string;
}

// ---------------------------------------------------------------------------
// GET /imports/{id} · POST /imports/{id}/discard — feature 045 (US3)
// ---------------------------------------------------------------------------

/**
 * Proyección pública del meta de una carga (`_PUBLIC_PARSE_META_KEYS` en el
 * backend). Sin rutas de storage ni `corrections` (filas de un menor).
 * `null` en una carga ya confirmada por completo (el meta se limpia).
 */
export interface ImportParseMeta {
  header?: Partial<ImportHeader> & {
    event_date?: string;
    location?: string;
  };
  conditions?: ParsedConditions | null;
  categories_found?: string[];
  n_rows_resultados?: number;
  n_rows_general?: number;
  /** `rows` es un CONTEO en el meta persistido, no la lista de filas. */
  categories?: Array<{
    header_raw: string;
    code: string | null;
    mapping_kind: CategoryMappingKind;
    rows: number;
    completeness: CategoryCompleteness;
  }>;
  unreadable_rows?: UnreadableRow[];
  acknowledged?: Array<{ category_header: string; reason: string }>;
  pending_categories?: string[];
}

/** Mirror de `ImportDetailRead` — lo justo para retomar el wizard. */
export interface ImportDetail {
  id: number;
  status: ImportStatus;
  source_filename: string | null;
  parse_meta: ImportParseMeta | null;
  created_at: string; // ISO datetime
  event_id: number | null;
  season: number | null;
  /**
   * Cuándo se confirmó la versión previa de la misma válida (ISO datetime):
   * el mismo dato que `ImportParseResponse.parent_committed_at`, para el aviso
   * de revisión del wizard retomado. `null` si es la primera carga de la
   * válida o la carga ya no está en curso.
   */
  parent_committed_at?: string | null;
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
  // -------------------------------------------------------------------------
  // Feature 044 (US5) — tablero de carga histórica
  // (`contracts/historical-load.md` §"Board fields", `contracts/ui-history.md` §3).
  //
  // Siempre presentes (nunca `undefined`) — mirror exacto de
  // `ImportListItem` en `backend/app/schemas/race_imports.py`. `season` /
  // `valida_num` / `series_name` se resuelven de `parse_meta_json["header"]`
  // mientras el import conserva meta, y de `RaceEvent`→`RaceSeries` una vez
  // committeado sin pendientes; solo son `null` para un import roto sin
  // meta ni evento resuelto (caso defensivo, no el flujo normal).
  // -------------------------------------------------------------------------
  /** Año de temporada del válida/evento asociado. `null` solo en un import roto. */
  season: number | null;
  /** Número de válida dentro de la serie (`null` en campeonatos, o en un import roto). */
  valida_num: number | null;
  /** Nombre de la serie (ej. "Copa Valle de Ciclomontañismo"). `null` solo en un import roto. */
  series_name: string | null;
  /**
   * Categorías cuyo commit quedó pendiente (inconsistentes sin reconocer o
   * de encabezado no reconocido) — mirror de
   * `ImportCommitResponse.pending_categories`, contado.
   */
  pending_categories_count: number;
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

// ---------------------------------------------------------------------------
// PR4 — catálogo cerrado de motivos + diff read-only de la última revisión
// ---------------------------------------------------------------------------

export interface RevisionReasonOption {
  code: string;
  label: string;
}

export interface RevisionReasonsResponse {
  options: RevisionReasonOption[];
}

export interface RevisionDiffItem {
  action: "create" | "update" | "delete";
  group:
    | "position"
    | "time"
    | "gap_gc"
    | "category_reclassified"
    | "added_removed";
  competitor_display_name: string;
  category_code: string | null;
  field_before: string | null;
  field_after: string | null;
}

export interface RevisionDiffGroupCounts {
  position: number;
  time: number;
  gap_gc: number;
  category_reclassified: number;
  added_removed: number;
}

export interface RaceEventDiffResponse {
  race_event_id: number;
  has_revision: boolean;
  last_revision_at: string | null;
  reason_code: string | null;
  counts: RevisionDiffGroupCounts;
  items: RevisionDiffItem[];
}

// ---------------------------------------------------------------------------
// Feature 015 — Prefill import from competition (view-model, frontend-only)
//
// Composed by `useImportPrefill(raceEventId)` from the existing race-event and
// race-series reads. NO new backend field, table, or endpoint (FR-012).
// Privacidad: solo lleva metadata de competencia ya visible en la tarjeta
// "Información" del detalle — cero PII de menores (FR-013).
// ---------------------------------------------------------------------------

/**
 * Estado del prefill del wizard cuando se lanza desde una competencia.
 *
 * - `loading`: se están resolviendo evento + serie.
 * - `ready`: evento cargado Y serie resuelta desde `series_id` → `values`.
 * - `blocked`: la serie/tipo no se pudo determinar (FR-009) → se ofrece
 *   `editMetadataHref` y la importación NO puede continuar.
 * - `error`: el fetch del evento falló (404 u otro) → UI de error existente.
 */
export type ImportPrefillStatus = "loading" | "ready" | "blocked" | "error";

/**
 * Valores derivados que se precargan y bloquean en el paso 1 del wizard.
 *
 * `series_kind` se deriva de `series.kind` y NO es editable en el flujo
 * (FR-005). `valida_num` es `null` para campeonatos (campo oculto, FR-008).
 * Las condiciones se precargan pero permanecen editables (comportamiento
 * actual del wizard).
 */
export interface ImportPrefillValues {
  series_kind: ImportSeriesKind;
  series_name: string;
  season: number;
  valida_num: number | null;
  event_name: string;
  event_date: string;
  location: string;
  conditions?: {
    climate?: string;
    temperature_c?: number;
    surface_condition?: SurfaceCondition | null;
    altitude_msnm?: number;
    weather_notes?: string;
  };
}

/** Tipo de serie derivado — espejo del enum de race-series (cup | championship). */
export type ImportSeriesKind = "cup" | "championship";

/**
 * View-model del prefill producido por `useImportPrefill(raceEventId)`.
 *
 * Cuando el wizard se monta sin `raceEventId` (flujo standalone) este
 * view-model NO se produce y el wizard se comporta exactamente como hoy
 * (FR-007).
 */
export interface ImportPrefill {
  status: ImportPrefillStatus;
  raceEventId: number;
  /** Presente solo cuando `status === "ready"`. */
  values?: ImportPrefillValues;
  /** Presente cuando `status === "blocked"` — destino del escape hatch (FR-009). */
  editMetadataHref?: string;
}
