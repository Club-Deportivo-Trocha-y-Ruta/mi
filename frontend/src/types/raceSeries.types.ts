/**
 * Tipos del módulo race-series.
 *
 * Mirror de los Pydantic schemas en `backend/app/schemas/race_series.py`
 * y el enum `RaceSeriesKind` en `backend/app/models/race_series.py`.
 *
 * Spec 014 — Cup vs Championship:
 *   Introduce `kind` como discriminador de tipo de serie.
 *   - `cup`: serie con válidas numeradas y ranking acumulado de temporada.
 *   - `championship`: serie de un único evento anual, sin válidas ni puntos.
 *
 * Privacidad: race-series son datos de logística de federación — no exponen
 * PII de menores (Ley 1581).
 */

// ---------------------------------------------------------------------------
// Enum de tipo de serie
// ---------------------------------------------------------------------------

/**
 * Tipo de serie de competencias.
 *
 * - `cup`: Copa con válidas numeradas y ranking acumulado (ej. Copa Valle).
 * - `championship`: Campeonato anual único sin válidas ni puntos acumulados
 *   (ej. Campeonato Departamental, Nacional).
 */
export type RaceSeriesKind = "cup" | "championship";

/**
 * Nivel jerárquico de la serie de competencias.
 *
 * - `departmental`: Campeonato/Copa de alcance departamental (ej. Copa Valle,
 *   Campeonato Departamental).
 * - `national`: Campeonato de alcance nacional (ej. Campeonato Nacional MTB).
 */
export type RaceSeriesLevel = "departmental" | "national";

// ---------------------------------------------------------------------------
// Filtros de lista
// ---------------------------------------------------------------------------

/**
 * Filtros opcionales para `GET /api/race-analysis/race-series`.
 */
export interface RaceSeriesListFilters {
  /** Filtrar por año de temporada (ej. 2026). */
  season?: number;
  /** Filtrar por tipo de serie. */
  kind?: RaceSeriesKind;
}

// ---------------------------------------------------------------------------
// POST — Crear serie
// ---------------------------------------------------------------------------

/**
 * Payload de creación de una serie de competencias.
 * Mirror de `RaceSeriesCreate` del backend.
 *
 * Nota: `points_scheme_code` NO se envía — el backend lo fija en
 * `copa_valle_2026` (decisión D5 del spec 014).
 */
export interface RaceSeriesCreate {
  name: string;
  season_year: number;
  kind: RaceSeriesKind;
  organizer?: string | null;
  /** Nivel de la serie. Omitido → el backend usa `departmental` por defecto. */
  level?: RaceSeriesLevel;
}

// ---------------------------------------------------------------------------
// Respuesta de GET y POST
// ---------------------------------------------------------------------------

/**
 * Representación de una serie de competencias (respuesta de lista y creación).
 * Mirror de `RaceSeriesRead` del backend.
 */
export interface RaceSeriesRead {
  id: number;
  name: string;
  season_year: number;
  organizer: string | null;
  kind: RaceSeriesKind;
  level: RaceSeriesLevel;
  /** Número de eventos (válidas o campeonatos) en la serie. */
  event_count: number;
}

// ---------------------------------------------------------------------------
// Respuesta paginada del GET /race-series
// ---------------------------------------------------------------------------

/**
 * Respuesta del `GET /api/race-analysis/race-series`.
 * Mirror de `RaceSeriesListResponse` del backend.
 */
export interface RaceSeriesListResponse {
  items: RaceSeriesRead[];
  total: number;
}
