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
// Results — per-event finishing order
// ---------------------------------------------------------------------------

/**
 * Una fila de resultados de la carrera — un corredor en una categoría.
 * Mirror de `RaceResultRow` del backend.
 */
export interface RaceResultRow {
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
