/**
 * Tipos del módulo race-results y race-standings.
 *
 * Mirror de los schemas en `backend/app/schemas/race_results.py`.
 *
 * Endpoints cubiertos:
 *   - GET /api/race-analysis/race-events/{id}/results    → RaceEventResultsResponse
 *   - GET /api/race-analysis/race-events/{id}/standings  → RaceEventStandingsResponse
 *
 * Privacidad:
 *   - `display_name` es el nombre normalizado del corredor (puede ser nombre
 *     de un menor). Solo se renderiza a coach/admin (la ruta está protegida
 *     con ProtectedRoute).
 *   - Padres solo ven sus propios hijos (filtrado en el backend); el frontend
 *     renderiza lo que devuelve la API sin exponer datos de terceros.
 *   - `athlete_id` vincula al corredor con el perfil del atleta del club
 *     (puede ser null si el corredor no pertenece al club).
 */

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

/**
 * Posibles estados de un corredor en una carrera.
 * "finished" = terminó; "dnf" = no terminó; "dns" = no salió; "dsq" = descalificado.
 */
export type RaceResultStatus = "finished" | "dnf" | "dns" | "dsq";

// ---------------------------------------------------------------------------
// MetricSet — motor único de métricas de carrera (feature 045)
// ---------------------------------------------------------------------------

/**
 * Métricas de un resultado, tal como las calcula el motor del backend
 * (`field_metrics.py`, `data-model.md` §1). Ningún consumidor las recalcula.
 *
 * Esta es la vista de coach/admin (completa) y la única definición de la
 * forma: la vista de familia y las variantes por endpoint
 * (`RaceHistoryPoint`, `RaceResultRow.metrics`) se derivan de aquí.
 */
export interface CoachMetricSet {
  /** «Parrilla»: FINISHED + MINUS_LAPS de la categoría. */
  field_size: number;
  /** FINISHED con tiempo — denominador real de percentil y brecha a la mediana. */
  timed_finishers: number;
  position: number | null;
  /** «Percentil» por tiempo; `null` con menos de 5 cronometrados. */
  percentile: number | null;
  /** «Brecha vs. mediana» (%); negativo = más rápido. Mismas reglas de `null`. */
  gap_to_median_pct: number | null;
  /** «Brecha vs. 1.ª posición» (%) contra el tiempo oficial de P1. */
  gap_to_winner_pct: number | null;
  /** Brecha absoluta a la 1.ª posición (ms). */
  gap_to_winner_ms: number | null;
  /** «Brecha vs. podio» (%) contra el tiempo oficial de P3. */
  gap_to_podium_pct: number | null;
  /** Brecha absoluta al podio (ms). */
  gap_to_podium_ms: number | null;
}

/**
 * Claves que el backend NUNCA envía a una familia: brechas (% y ms) contra
 * el líder o el podio (Ley 1581 + salvaguarda 045). Se **eliminan** del
 * payload — no llegan como `null`. Única lista de lo oculto: `FamilyMetricSet`
 * y los fixtures de familia se derivan de ella.
 */
export const LEADER_GAP_METRIC_KEYS = [
  "gap_to_winner_pct",
  "gap_to_winner_ms",
  "gap_to_podium_pct",
  "gap_to_podium_ms",
] as const satisfies readonly (keyof CoachMetricSet)[];

export type LeaderGapMetricKey = (typeof LEADER_GAP_METRIC_KEYS)[number];

/**
 * Vista de familia: `CoachMetricSet` sin las brechas contra líder/podio.
 * Código de familia que lea cualquiera de esas brechas no compila.
 */
export type FamilyMetricSet = Omit<CoachMetricSet, LeaderGapMetricKey>;

/**
 * Lo que puede llegar por el cable. Las claves de líder/podio están
 * ausentes (no `null`) en la variante de familia, así que su presencia
 * discrimina: `"gap_to_winner_pct" in metrics` estrecha a `CoachMetricSet`.
 */
export type MetricSet = CoachMetricSet | FamilyMetricSet;

// ---------------------------------------------------------------------------
// Results — per-event finishing order
// ---------------------------------------------------------------------------

/**
 * Una fila de resultados de la carrera — un corredor en una categoría.
 * Mirror de `RaceResultRow` del backend.
 */
export interface RaceResultRow {
  /** Primary key of the race_results row — required to address coach-note endpoints. */
  result_id: number;
  position: number | null;
  competitor_id: number;
  /** Nombre normalizado del corredor (puede ser menor — solo coach/admin). */
  display_name: string;
  /** Nombre del club del corredor según el PDF oficial. */
  club_text: string;
  /** ID del atleta del club si fue vinculado; null si es rival u otro club. */
  athlete_id: number | null;
  /** true si el corredor pertenece al club Trocha y Ruta. */
  is_our_club: boolean;
  status: RaceResultStatus;
  /** Tiempo de carrera en milisegundos. null si no terminó. */
  race_time_ms: number | null;
  /** Vueltas de diferencia respecto al ganador. null si ganó o no terminó. */
  laps_behind: number | null;
  /** Puntos otorgados por la posición (según el esquema de puntuación de la serie). */
  points_awarded: number | null;
  /** Número de dorsal. */
  bib_number: number | null;
  /**
   * Nota cualitativa del entrenador sobre el desempeño del corredor en la
   * válida. Solo visible para coach/admin (RBAC en el backend).
   * null cuando no hay nota registrada.
   */
  coach_note: string | null;
  /**
   * ISO 8601 timestamp de la última actualización de la nota del entrenador.
   * null cuando coach_note es null.
   */
  coach_note_updated_at: string | null;
  /**
   * Feature 043 (US2) — distancia recorrida derivada (vueltas completadas ×
   * distancia de la variante del circuito), redondeada a 1 decimal. `null`
   * cuando no hay circuito/setup para la categoría o el corredor no tiene
   * vueltas completadas calculables (DNF/DNS/DSQ, `minus_laps` sin dato).
   * Opcional — ausente en respuestas/fixtures previas a esta feature
   * (mirror de `results-derived-figures.md` §1, aditivo).
   */
  distance_km?: number | null;
  /**
   * Feature 043 (US2) — velocidad promedio derivada (distance_km / horas de
   * carrera), redondeada a 1 decimal. Mismas condiciones de `null` que
   * `distance_km`. Opcional por el mismo motivo aditivo.
   */
  avg_speed_kmh?: number | null;
  /**
   * Feature 043 (US2) — distancia de una vuelta de la variante de circuito
   * asignada a la categoría de este corredor, redondeada a 1 decimal. Se
   * repite en cada fila de la categoría (viene del setup compartido) para
   * que la tabla pueda armar el encabezado de categoría sin una consulta
   * adicional. `null` sin circuito. Opcional por el mismo motivo aditivo.
   */
  lap_distance_km?: number | null;
  /**
   * Feature 043 (US2) — desnivel positivo (m) de la variante de circuito
   * asignada. `null` sin circuito o sin altimetría en la grabación GPX.
   * Opcional por el mismo motivo aditivo.
   */
  elevation_gain_m?: number | null;
  /**
   * Feature 045 — métricas de la fila calculadas por el motor único
   * (`compute_category_metrics`). Coach/admin reciben `CoachMetricSet`; una
   * familia recibe solo `FamilyMetricSet` (claves de líder/podio ausentes).
   * `null` cuando el backend no pudo calcularlas para la fila. Opcional
   * (aditivo, `data-model.md` §4): ausente en respuestas/fixtures previas a
   * la 045. Ver `MetricSet` para cómo discriminar la variante.
   */
  metrics?: MetricSet | null;
}

/**
 * Resultados de una categoría dentro de la carrera.
 */
export interface RaceResultCategory {
  category_id: number;
  /** Código corto de la categoría (ej. "INF_M", "JUV_F"). */
  code: string;
  /** Etiqueta legible (ej. "Infantil Masculino"). */
  label: string;
  rows: RaceResultRow[];
  /**
   * Feature 043 (US2) — vueltas configuradas para esta categoría en el
   * circuito de la válida (`RaceCourseCategorySetup.laps`). `null`/ausente
   * cuando no hay setup para la categoría. Opcional — aditivo, mirror de
   * `results-derived-figures.md` §1.
   */
  laps?: number | null;
  /**
   * Feature 043 (US2) — etiqueta de la variante de circuito asignada a esta
   * categoría (ej. "Recorrido reducido"). Mismas condiciones de `null` que
   * `laps`. Opcional por el mismo motivo aditivo.
   */
  variant_label?: string | null;
}

/**
 * Respuesta del endpoint GET /race-events/{id}/results.
 *
 * Los campos opcionales `event_name`, `event_date`, `location`, `status`
 * son incluidos por el backend para que el frontend pueda mostrar el header
 * del evento sin una segunda llamada (Wave A + FR-030 parent view).
 */
export interface RaceEventResultsResponse {
  race_event_id: number;
  categories: RaceResultCategory[];
  /** Nombre del evento (ej. "Copa Valle IV — Cali"). */
  event_name?: string;
  /** Fecha del evento en formato ISO date (YYYY-MM-DD). */
  event_date?: string;
  /** Municipio/sede del evento. */
  location?: string;
  /** Estado del evento (ej. "completed", "scheduled"). */
  status?: string;
  /**
   * Feature 043 (US2) — `true` cuando la válida tiene al menos un circuito
   * (variante de recorrido) configurado, en cuyo caso las columnas
   * derivadas "Distancia"/"Vel. prom." se muestran en `ResultsTable`.
   * Opcional/`undefined` en respuestas y fixtures previas a esta feature
   * (mirror de `results-derived-figures.md` §1 y `ui-course.md` §5) — se
   * trata igual que `false` (columnas ocultas, SC-007).
   */
  has_course_data?: boolean;
}

/**
 * Parámetros de consulta opcionales para el endpoint de resultados.
 */
export interface RaceResultsFilters {
  /** Filtra por categoría específica. Si es undefined, retorna todas. */
  category_id?: number;
  /** Si es true, retorna solo los corredores del club Trocha y Ruta. */
  club_only?: boolean;
}

// ---------------------------------------------------------------------------
// Standings — season cumulative points
// ---------------------------------------------------------------------------

/**
 * Una fila de clasificación general — acumulado de temporada.
 * Mirror de `StandingRow` del backend.
 */
export interface StandingRow {
  rank: number;
  competitor_id: number;
  /** Nombre normalizado del corredor. */
  display_name: string;
  /** Nombre del club según el PDF oficial. */
  club_text: string;
  /** ID del atleta del club si fue vinculado; null si es rival u otro club. */
  athlete_id: number | null;
  /** true si el corredor pertenece al club Trocha y Ruta. */
  is_our_club: boolean;
  /** Puntos totales acumulados en la temporada. */
  total_points: number;
  /** Número de válidas en las que participó. */
  races_run: number;
  /** Número de podiums (posiciones 1-3). */
  podiums: number;
  /** Mejor posición obtenida en la temporada. */
  best_position: number | null;
}

/**
 * Clasificación de una categoría en la temporada.
 */
export interface StandingCategory {
  category_id: number;
  /** Código corto (ej. "INF_M"). */
  code: string;
  /** Etiqueta legible (ej. "Infantil Masculino"). */
  label: string;
  rows: StandingRow[];
}

/**
 * Respuesta del endpoint GET /race-events/{id}/standings.
 *
 * Los campos opcionales `event_name`, `event_date`, `location`, `status`
 * son incluidos por el backend para que el frontend pueda mostrar el header
 * del evento sin una segunda llamada (Wave A + FR-030 parent view).
 */
export interface RaceEventStandingsResponse {
  race_event_id: number;
  categories: StandingCategory[];
  /** Nombre del evento (ej. "Copa Valle IV — Cali"). */
  event_name?: string;
  /** Fecha del evento en formato ISO date (YYYY-MM-DD). */
  event_date?: string;
  /** Municipio/sede del evento. */
  location?: string;
  /** Estado del evento (ej. "completed", "scheduled"). */
  status?: string;
  /**
   * Feature 044 (US5, `contracts/historical-load.md` §"Points and standings")
   * — `true` cuando los puntos vienen de sumar `points_awarded` impreso en
   * el acta sin recálculo contra ninguna tabla de puntos (temporadas
   * históricas 2024/2025, esquemas `copa_valle_2024`/`copa_valle_2025` con
   * `is_official = false`). `undefined`/`false` para temporadas oficiales
   * vigentes — comportamiento sin cambios.
   */
  is_calculated?: boolean;
}

/**
 * Parámetros de consulta opcionales para el endpoint de standings.
 */
export interface RaceStandingsFilters {
  /** Filtra por categoría específica. */
  category_id?: number;
  /** Si es true, retorna solo los corredores del club. */
  club_only?: boolean;
}
