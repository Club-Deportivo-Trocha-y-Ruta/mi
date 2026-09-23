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
import type { RaceEventPriority } from "@/types/raceEvents.types";

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
  /** Brecha vs. mediana (2026-09-23) — métrica por defecto para coach y
   * familia: comparable entre válidas porque no depende de quién ganó. */
  GAP_TO_MEDIAN_PCT: "gap_to_median_pct",
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

import type { InsightV3 } from "@/types/insightV3.types";

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
  /**
   * Feature 036 (T030) — fecha ISO (`YYYY-MM-DD`) del evento vinculado por
   * `event_id`. `null` cuando el insight no tiene evento vinculado (resumen
   * de temporada, o filas legacy previas a la columna `event_id`).
   */
  event_date: string | null;
  /**
   * Feature 036 (T030) — tipo de serie del evento vinculado (`"cup"` |
   * `"championship"`). Fuente de verdad para distinguir un Cto.
   * Departamental de una válida regular — reemplaza la convención retirada
   * `valida_num === 99` (ver `lib/insights.ts#validaLabel`). `null` en las
   * mismas condiciones que `event_date`.
   */
  series_kind: "cup" | "championship" | null;
  /**
   * Feature 039 (T038) — nivel de la serie de campeonato vinculada
   * (`"departmental"` | `"national"`); las copas no tienen nivel. Fuente
   * para distinguir "Cto. Departamental" de "Cto. Nacional" en
   * `lib/insights.ts#validaLabel` — ausente (`undefined`)/`null` cae al
   * default "departamental" (insights previos a la feature, o sin
   * `series_kind === "championship"`). Opcional por el mismo motivo
   * aditivo que `EvolutionPoint.series_level` (no rompe fixtures/tests
   * previos a la feature).
   */
  series_level?: SeriesLevel | null;
  /**
   * Identidad de copa/campeonato (hotfix multicopa, 2026-09-16) — nombre y
   * abreviación de `race_series` vinculada por `event_id`. Fuente para
   * `lib/insights.ts#raceLabel`, que reemplaza a `validaLabel` como único
   * punto de verdad para el rótulo de una válida: antes solo distinguía
   * copa/campeonato/nacional-departamental sin nombrar NUNCA la copa
   * concreta, lo que permitía que la Válida IV de una copa se leyera y
   * agrupara junto a la Válida IV de otra (bug de identidad de válida).
   * `null` en insights legacy (previos a esta columna) o sin evento
   * vinculado (resumen de temporada) — `raceLabel` cae al rótulo sin copa
   * en ese caso, nunca inventa un nombre.
   */
  series_id?: number | null;
  /** Ver nota de `series_id`. Nombre completo, ej. "Copa Let's GO". */
  series_name?: string | null;
  /** Ver nota de `series_id`. Abreviación para chips, ej. "Let's GO". */
  series_short_name?: string | null;
  /**
   * Wave 3 (hotfix multicopa, 2026-09-16) — prioridad del evento vinculado
   * (`race_events.priority`). `null` → UNKNOWN. Fuente del banner de
   * tapering-mismatch en `ComparatorPanel` — reemplaza la comparación por
   * tipo-de-carrera hardcodeada que dependía de `lib/raceCalendar.ts`
   * (retirado).
   */
  priority?: RaceEventPriority | null;
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
  /**
   * Feature 036 (US4) — `true` únicamente cuando la fila fue persistida por
   * el camino de FALLA de `services/race/ai/fallback.py`
   * (`deterministic_fallback`): el `summary_text` es entonces el placeholder
   * fijo "Análisis IA no disponible…", no un análisis real. La variante N=1
   * (`deterministic_fallback_n1`) es un análisis legítimo y mantiene
   * `is_fallback=false`.
   */
  is_fallback: boolean;
  /** Solo presente si fue parseado en el cliente (v2 insights). */
  parsed_sections?: InsightParsedSections;
  /**
   * Feature 037 (T104) — titular del insight v3, leído server-side de
   * `structured_json.headline`. `null` para insights v1/v2 (sin
   * `structured_json`) o si el campo no está presente.
   */
  headline?: string | null;
  /**
   * Feature 037 (T104) — calificación del coach al insight: `1` = útil,
   * `-1` = no útil. `null` = sin calificar.
   */
  coach_rating?: number | null;
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
  /**
   * Feature 037 (T104) — contenido completo de `structured_json`
   * (`InsightV3.model_dump()`). `null` para insights v1/v2. En modo
   * parent el backend omite server-side `field_reading.expected_position`
   * / `delta_vs_expected`, `coach_question` y la evidencia de las
   * observaciones de dominio `training` — ver data-model.md §API deltas.
   */
  structured?: InsightV3 | null;
  /**
   * Feature 037 (T104) — respuesta del coach a
   * `structured.coach_question`, ya escrubeada de nombres prohibidos.
   * Omitida server-side en modo parent.
   */
  coach_answer_text?: string | null;
  coach_answer_at?: string | null;
}

// ---------------------------------------------------------------------------
// Answer insight — feature 037 (T104/T205)
// POST /api/athletes/{id}/race-analysis/insights/{insight_id}/answer
// ---------------------------------------------------------------------------

/**
 * Body de `answerInsight`. Al menos uno de los dos campos debe venir — el
 * backend responde 422 si ambos son `undefined`/`null`.
 */
export interface AnswerInsightBody {
  answer_text?: string | null;
  rating?: number | null;
}

// ---------------------------------------------------------------------------
// Season summary — feature 037 (T203/T205)
// Contrato nuevo: POST /season-summary lanza un run agéntico (202) en vez
// de generar de forma síncrona (200 con summary_text, contrato legacy de
// feature 036 — ver `SeasonSummaryResponse` en `api/athleteRaceAnalysis.ts`).
// ---------------------------------------------------------------------------

export interface AthleteSeasonSummaryRunResponse {
  /** external_run_id (UUID hex) — pollable vía GET /race-analysis/runs/:id/status. */
  run_id: string;
  status: string;
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

/** Nivel de una serie de campeonato (`race_series.level`); ignorado para copas. */
export type SeriesLevel = "departmental" | "national";

/**
 * Grupo de comparación (feature 039) — mirror de
 * `contracts/evolution-api.md` / `data-model.md` §1. Cada copa y cada
 * campeonato de la temporada es su propio grupo; nunca se mezclan en la
 * misma serie del gráfico (research.md D1/D5).
 */
export interface ComparisonGroupOption {
  comparison_group: string;
  series_id: number;
  kind: "cup" | "championship";
  level: SeriesLevel;
  label: string;
  n_points: number;
}

/**
 * Punto de evolución para coach/admin. Es la única definición de la forma;
 * `FamilyEvolutionPoint` se deriva de ella.
 *
 * Feature 045: `percentile`, `field_size`, `position` y `gap_to_median_pct`
 * vienen del motor único de métricas (`MetricSet`, ver
 * `raceResults.types.ts`).
 */
export interface CoachEvolutionPoint {
  valida_num: number;
  event_id: number;
  event_date: string;
  value: number | null;
  unit: string;
  series_kind: "cup" | "championship";
  label: string;
  /**
   * Feature 039 — campos aditivos de `data-model.md` §5. Opcionales para no
   * romper fixtures/tests previos a la feature (que construyen
   * `EvolutionPoint` sin grupo de comparación, p. ej.
   * `cupAndChampionshipConflictHandler`) — el backend real siempre los
   * envía una vez desplegada la feature.
   */
  series_id?: number;
  series_name?: string;
  series_level?: SeriesLevel;
  comparison_group?: string;
  field_size?: number | null;
  percentile?: number | null;
  /**
   * Feature 039 (fix B-2/F-1) — posición cruda de llegada (`null` en
   * DNF/DNS/DSQ) y gap % frente al ganador de la categoría
   * (`100 * (tiempo - tiempo_ganador) / tiempo_ganador`, `null` cuando no
   * aplica). Expuestos para cualquier `metric` — no dependen del selector
   * activo (`contracts/evolution-api.md`). Opcionales por el mismo motivo
   * aditivo que el resto de campos de esta sección.
   *
   * Feature 045: `gap_pct` es la brecha vs. 1.ª posición (nombre heredado
   * de `MetricSet.gap_to_winner_pct`) — **coach only**: el backend la
   * omite en los puntos de un padre, y por eso no existe en
   * `FamilyEvolutionPoint`.
   */
  position?: number | null;
  gap_pct?: number | null;
  /**
   * Brecha vs. mediana (2026-09-23) — porcentaje respecto a la mediana de
   * tiempos FINISHED de la categoría del evento (backend:
   * `field_metrics.compute_field_metrics`, misma fuente que
   * `RaceHistoryPoint.gap_to_median_pct`). Negativo = más rápido que la
   * mediana. Expuesto para cualquier `metric`, igual que `gap_pct`. `null`
   * si el atleta no finalizó o si la categoría del evento tiene menos de 5
   * finalistas CON tiempo registrado.
   */
  gap_to_median_pct?: number | null;
  /**
   * Feature 043 (US2) — velocidad promedio derivada de esa válida (mismo
   * cálculo que `RaceResultRow.avg_speed_kmh`, ver
   * `results-derived-figures.md` §3), redondeada a 1 decimal. `null` sin
   * circuito configurado o sin vueltas completadas calculables. No se usa
   * para ningún agregado (media/mejor/tendencia) — es un valor por fila,
   * mostrado solo en la vista de tabla de `EvolutionChart`. Opcional por el
   * mismo motivo aditivo que el resto de campos de esta sección.
   */
  avg_speed_kmh?: number | null;
}

/** Punto de evolución para familia: sin `gap_pct` (ausente, no `null`).
 * Código de familia que lo lea no compila. */
export type FamilyEvolutionPoint = Omit<CoachEvolutionPoint, "gap_pct">;

/** Lo que puede llegar por el cable; `"gap_pct" in point` estrecha a
 * `CoachEvolutionPoint`. */
export type EvolutionPoint = CoachEvolutionPoint | FamilyEvolutionPoint;

export interface EvolutionResponse {
  season: number;
  metric: EvolutionMetric;
  series: EvolutionPoint[];
  confidence: AnalysisConfidence;
  /** Feature 039 — aditivo, ver nota de opcionalidad en `EvolutionPoint`. */
  groups?: ComparisonGroupOption[];
  /** Feature 039 — eco del `series_id` aplicado (`null` sin filtro). */
  selected_group?: string | null;
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
  /** Feature 039 — aditivo, ver nota de opcionalidad en `EvolutionPoint`. */
  series_id?: number;
  series_name?: string;
  series_level?: SeriesLevel;
  /**
   * Hotfix multicopa (2026-09-16) — abreviación para chips (`raceLabel`,
   * `lib/insights.ts`). Aditivo por el mismo motivo que el resto de campos
   * de esta sección.
   */
  series_short_name?: string | null;
  /** Wave 3 — ver nota de `priority` en `AthleteInsightOut`. */
  priority?: RaceEventPriority | null;
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
  /** Hotfix multicopa (2026-09-16) — ver nota en `AthleteInsightOut`. */
  event_id?: number | null;
  series_id?: number | null;
  series_name?: string | null;
  series_short_name?: string | null;
  insight_id: number | null;
  summary_excerpt: string | null;
  generated_at: string | null;
  confidence: InsightConfidence | null;
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
  /**
   * Hotfix multicopa (2026-09-16) — desambigua copa vs. campeonato con el
   * mismo `valida_num` en la temporada, igual que `AthleteStartRunBody`.
   */
  event_id?: number;
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

/**
 * Wave 3 (hotfix multicopa, 2026-09-16) — desglose por copa de un atleta.
 * Ordenado por fecha de la primera carrera disputada de esa copa. Los
 * campeonatos NO aparecen acá (excluidos por el backend de este endpoint) —
 * `series_kind` siempre es `"cup"` en la práctica, se mantiene tipado por
 * completitud futura.
 */
export interface SeasonPanoramaSeriesItem {
  series_id: number;
  series_name: string;
  series_short_name: string | null;
  series_kind: "cup" | "championship";
  races: number;
  points: number;
  podiums: number;
  wins: number;
  best_position: number | null;
}

export interface SeasonPanoramaAthleteItem {
  athlete_id: number;
  athlete_display_name: string;
  /**
   * @deprecated Suma cross-copa (hotfix multicopa, 2026-09-16) — mezcla
   * copas distintas en un solo número, el mismo colapso de identidad que
   * originó el bug. Usar `by_series`; se mantiene solo por compatibilidad
   * de respuestas legacy en el período de transición del backend.
   */
  races_count: number;
  /** @deprecated Ver nota de `races_count` — usar `by_series`. */
  wins: number;
  /** @deprecated Ver nota de `races_count` — usar `by_series`. */
  podiums: number;
  /** @deprecated Ver nota de `races_count` — usar `by_series`. */
  best_position: number | null;
  /** @deprecated Ver nota de `races_count` — usar `by_series`. */
  total_points: number;
  /**
   * Wave 3 — fuente única de verdad de este endpoint. Cada copa que el
   * atleta disputó en la temporada, con sus propias cifras (nunca sumadas
   * entre copas). Vacío si el atleta no disputó ninguna copa (solo
   * campeonatos, o ningún resultado).
   */
  by_series: SeasonPanoramaSeriesItem[];
}

export interface SeasonPanoramaResponse {
  season: number;
  total_athletes: number;
  items: SeasonPanoramaAthleteItem[];
}
