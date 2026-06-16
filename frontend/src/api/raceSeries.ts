/**
 * API client del módulo race-series.
 *
 * Auth: JWT via interceptor en apiClient.
 *
 * Endpoints cubiertos:
 *   - GET  /api/race-analysis/race-series          → listRaceSeries  (coach+admin)
 *   - POST /api/race-analysis/race-series          → createRaceSeries (coach+admin)
 *
 * Spec 014 — Cup vs Championship:
 *   Reemplaza el hardcode COPA_VALLE_SERIES con carga dinámica desde el backend.
 *   El campo `kind` discrimina entre series tipo copa (con válidas numeradas y
 *   ranking acumulado) y campeonatos (evento único anual, sin válidas).
 *
 * Privacidad: race-series son datos públicos de federación — no exponen PII de
 * menores (Ley 1581).
 */
import { apiClient } from "@/api/client";
import type {
  RaceSeriesCreate,
  RaceSeriesListFilters,
  RaceSeriesListResponse,
  RaceSeriesRead,
} from "@/types/raceSeries.types";

const BASE = "/api/race-analysis/race-series";

// ---------------------------------------------------------------------------
// GET / — Listar series con filtros opcionales
// ---------------------------------------------------------------------------

/**
 * GET /api/race-analysis/race-series
 *
 * Lista todas las series de competencias. Soporta filtros por `season` y `kind`.
 * El campo `event_count` de cada ítem lo calcula el backend (sin N+1).
 *
 * @param filters - Filtros opcionales: season (año) y/o kind (cup|championship).
 * @param options - Opciones de fetch (signal para cancelación).
 */
export async function listRaceSeries(
  filters: RaceSeriesListFilters = {},
  options?: { signal?: AbortSignal },
): Promise<RaceSeriesListResponse> {
  const params: Record<string, string | number> = {};
  if (filters.season != null) params.season = filters.season;
  if (filters.kind != null) params.kind = filters.kind;

  // Trailing slash requerido: FastAPI hace 307 sin ella, y el browser pierde
  // el header Authorization al seguir el redirect a localhost:8000 directamente
  // (bypass del proxy Vite). Ver bug detectado en E2E cup-vs-championship.spec.ts.
  const response = await apiClient.get<RaceSeriesListResponse>(BASE + "/", {
    params,
    signal: options?.signal,
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// POST / — Crear serie
// ---------------------------------------------------------------------------

/**
 * POST /api/race-analysis/race-series/
 *
 * Crea una nueva serie de competencias. El backend fija `points_scheme_code`
 * en `copa_valle_2026` — el cliente no lo envía (decisión D5, spec 014).
 *
 * @returns La serie creada (201).
 * @throws 409 si ya existe una serie con el mismo (name, season_year).
 * @throws 422 si algún campo falla validación.
 */
export async function createRaceSeries(
  body: RaceSeriesCreate,
  options?: { signal?: AbortSignal },
): Promise<RaceSeriesRead> {
  // Trailing slash requerido — mismo motivo que listRaceSeries.
  const response = await apiClient.post<RaceSeriesRead>(BASE + "/", body, {
    signal: options?.signal,
  });
  return response.data;
}
