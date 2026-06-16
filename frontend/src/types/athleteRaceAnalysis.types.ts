/**
 * Tipos TypeScript del módulo athlete-race-analysis (BE-2 → FE-1).
 *
 * Mirror 1:1 de los Pydantic schemas en:
 *   backend/app/schemas/athlete_race_analysis.py
 *
 * Privacidad (CLAUDE.md §Privacidad):
 *   Ninguno de estos tipos expone ``athlete_id``, ``competitor_id``,
 *   ``generated_by_user_id`` ni la PK BigInt de runs. ``run_id`` es el
 *   ``external_run_id`` (UUID hex), no la PK interna.
 *
 *   Los pseudónimos de distribución son determinísticos (``C0001`` …) y
 *   no contienen nombres reales.
 *
 * NOTA: ``MetricsSnapshotV1`` viene del módulo race-results v2 — lo
 * declaramos minimalmente acá para no acoplarnos al schema completo del
 * backend (que tiene más campos opcionales). Si el snapshot llega sin
 * ``schema_version`` el backend lo entrega como dict puro.
 */

// ---------------------------------------------------------------------------
// Enums (compatibles con literal unions; backend usa Pydantic str-Enum)
// ---------------------------------------------------------------------------

export type InsightConfidence = "low" | "medium" | "high";
export type AnalysisConfidence = "low" | "medium" | "high";

export const EvolutionMetric = {
  PODIUM_GAP_MS: "podium_gap_ms",
  RANKING: "ranking",
  TIME_MS: "time_ms",
  PERCENTILE: "percentile",
} as const;
export type EvolutionMetric = (typeof EvolutionMetric)[keyof typeof EvolutionMetric];

/** Estados expuestos al frontend del agent_runs (subset). */
export type AthleteRunStatus =
  | "running"
  | "awaiting_hitl"
  | "completed"
  | "rejected"
  | "failed"
  | "cancelled";

// ---------------------------------------------------------------------------
// MetricsSnapshotV1 (subconjunto pragmático — backend puede mandar dict
// para snapshots legacy sin schema_version, ver schema race_ai.py).
// ---------------------------------------------------------------------------

export interface MetricsSnapshotV1 {
  schema_version: 1;
  event_id: number;
  season: number;
  valida_num: number;
  event_date: string;
  status: "finished" | "dnf" | "dns" | "dsq";
  race_time_ms?: number | null;
  position?: number | null;
  podium_gap_ms?: number | null;
  ranking_in_category?: number | null;
  category_id: number;
  category_code: string;
  category_size: number;
  category_time_mean_ms?: number | null;
  category_time_stddev_ms?: number | null;
  category_time_min_ms?: number | null;
  category_time_max_ms?: number | null;
  extras?: Record<string, unknown>;
}

/** Snapshot rehidratado: si el JSON cumple MetricsSnapshotV1 el backend
 * lo envía tipado; para snapshots viejos entrega un dict arbitrario. */
export type MetricsSnapshot = MetricsSnapshotV1 | Record<string, unknown>;

export function isMetricsSnapshotV1(
  snapshot: MetricsSnapshot | undefined | null,
): snapshot is MetricsSnapshotV1 {
  return (
    !!snapshot &&
    typeof snapshot === "object" &&
    (snapshot as MetricsSnapshotV1).schema_version === 1
  );
}

// ---------------------------------------------------------------------------
// Insights — listado y detalle
// ---------------------------------------------------------------------------

export interface InsightLink {
  id: number;
  generated_at: string;
  coach_approved: boolean;
}

/**
 * Secciones parseadas del summary_text para insights v2 (prompt_version
 * === "race_analyst_v2"). Se poblan en el frontend extrayendo los bloques
 * bajo headers ## del markdown. No vienen del backend — se computan en
 * el cliente mediante ``parseV2Sections``.
 */
export interface InsightParsedSections {
  what_happened?: string;
  journey_so_far?: string;
  looking_ahead?: string;
  season_summary?: string;
  /** Presente solo en insights v2 generados con US-2 (FR-007): sección
   * "## Contexto de temporada". Ausente (undefined) en insights legacy. */
  season_context?: string;
}

export interface AthleteInsightOut {
  id: number;
  season: number;
  /** 0 = use_case agregado de temporada. 1..7 = válida regular. 99 = Cto. */
  valida_num: number | null;
  event_id: number | null;
  use_case: string;
  summary_text: string;
  confidence: InsightConfidence;
  model: string;
  prompt_version: string;
  coach_approved: boolean;
  generated_at: string;
  approved_at: string | null;
  is_active: boolean;
  deprecated_at: string | null;
  /** Solo presente si fue parseado en el cliente (v2 insights). */
  parsed_sections?: InsightParsedSections;
}

export interface AthleteInsightDetailOut extends AthleteInsightOut {
  recommendations: Array<Record<string, unknown>>;
  metrics_snapshot: MetricsSnapshot;
  principles_cited: Array<Record<string, unknown>>;
  supersedes: InsightLink[];
  superseded_by: InsightLink | null;
  /** True si la atleta tiene 1 válida en toda la temporada — gatilla banner N=1. */
  is_first_in_season?: boolean | null;
  /** Informativo: total de válidas de la temporada con resultados. */
  season_validas_count?: number | null;
}

export interface AthleteInsightListResponse {
  items: AthleteInsightOut[];
  total: number;
  limit: number;
  offset: number;
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export interface AthleteRunOut {
  /** external_run_id (UUID hex) — NUNCA la PK BigInt interna. */
  run_id: string;
  status: AthleteRunStatus;
  season: number | null;
  valida_nums: number[] | null;
  started_at: string;
  finished_at: string | null;
  explain_mode: boolean;
  has_output: boolean;
}

export interface AthleteRunListResponse {
  items: AthleteRunOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface AthleteStartRunBody {
  season: number;
  valida_nums?: number[] | null;
  /**
   * Ancla explícita por evento (desambigua copa vs campeonato con el mismo
   * sequence_number en la temporada). Se envía al lanzar desde una competición.
   */
  event_id?: number | null;
  explain_mode?: boolean;
}

// ---------------------------------------------------------------------------
// Analytics — evolution + distribution
// ---------------------------------------------------------------------------

export interface EvolutionPoint {
  valida_num: number;
  event_id: number;
  event_date: string;
  value: number | null;
  unit: string;
  series_kind: "cup" | "championship";
  label: string;
}

export interface EvolutionResponse {
  season: number;
  metric: EvolutionMetric;
  series: EvolutionPoint[];
  confidence: AnalysisConfidence;
}

export interface DistributionPoint {
  pseudonym: string;
  time_ms: number;
  is_self: boolean;
  /** Coach/admin: nombre real del competidor. Parent: null (solo pseudónimo). */
  display_name?: string | null;
}

export interface DistributionCurvePoint {
  x_ms: number;
  density: number;
}

export interface DistributionResponse {
  season: number;
  event_id: number;
  category_id: number;
  category_code: string;
  sample_size: number;
  mean_ms: number | null;
  stddev_ms: number | null;
  athlete_time_ms: number | null;
  athlete_z_score: number | null;
  athlete_percentile: number | null;
  points: DistributionPoint[];
  curve: DistributionCurvePoint[];
  confidence: AnalysisConfidence;
}

export interface RaceParticipationOption {
  event_id: number;
  sequence_number: number;
  series_kind: "cup" | "championship";
  event_date: string;
  event_name: string;
  location: string | null;
  label: string;
}

export interface RaceParticipationResponse {
  season: number;
  items: RaceParticipationOption[];
}

// ---------------------------------------------------------------------------
// Calendar helper
// ---------------------------------------------------------------------------

export interface AvailableRaceEvent {
  id: number;
  name: string;
  event_date: string;
  sequence_number: number;
  location: string | null;
  series_id: number;
}

// ---------------------------------------------------------------------------
// Club insights by race — cross-atleta por válida (Sprint 3)
// ---------------------------------------------------------------------------

export interface ClubInsightByRaceItem {
  athlete_id: number;
  athlete_display_name: string;
  valida_num: number | null;
  insight_id: number | null;
  summary_excerpt: string | null;
  generated_at: string | null;
  confidence: InsightConfidence | null;
  /**
   * PR5 / FR-018 — external_run_id del run cuyo `stale_since` no es null.
   * Presente solo cuando el run del que proviene el insight fue marcado como
   * desactualizado (la revisión de resultados lo invalidó automáticamente).
   * El frontend renderiza el `StaleAnalysisBadge` cuando este campo no es null.
   * Backend: campo opcional — null/ausente cuando el run está vigente.
   */
  stale_run_id?: string | null;
}

export interface ClubInsightsByRaceResponse {
  race_event_id: number;
  race_event_label: string;
  total_athletes: number;
  items: ClubInsightByRaceItem[];
}

// ---------------------------------------------------------------------------
// Query params type-aliases (para uso en hooks)
// ---------------------------------------------------------------------------

export interface AthleteInsightsParams {
  season?: number;
  use_case?: string;
  valida_num?: number;
  include_deprecated?: boolean;
  latest_only?: boolean;
  limit?: number;
  offset?: number;
}

export interface AthleteRunsParams {
  status?: AthleteRunStatus;
  season?: number;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Season panorama (PR3 unificación /competitions)
// GET /api/race-analysis/insights/season/{year} — coach/admin only.
// Mirror de backend/app/schemas/season_panorama.py.
// ---------------------------------------------------------------------------

export interface SeasonPanoramaAthleteItem {
  athlete_id: number;
  athlete_display_name: string;
  races_count: number;
  wins: number;
  podiums: number;
  best_position: number | null;
  total_points: number;
}

export interface SeasonPanoramaResponse {
  season: number;
  total_athletes: number;
  items: SeasonPanoramaAthleteItem[];
}
