/**
 * Hooks TanStack Query del módulo race-series.
 *
 * Spec 014 — Cup vs Championship:
 *   Reemplaza el hardcode `COPA_VALLE_SERIES` con carga dinámica desde
 *   `GET /api/race-analysis/race-series`.
 *
 * Hooks exportados:
 *   - `useRaceSeriesList(filters?)` → lista de series con filtros opcionales
 *   - `useCreateRaceSeries()`       → mutation POST /race-series
 *
 * Query keys:
 *   - `raceSeriesKeys.all` → raíz del árbol
 *   - `raceSeriesKeys.lists()` → todas las variantes de lista
 *   - `raceSeriesKeys.list(filters)` → lista con filtros específicos
 *
 * Privacidad: race-series son datos de logística de federación — no exponen
 * PII de menores (Ley 1581).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRaceSeries, listRaceSeries } from "@/api/raceSeries";
import type {
  RaceSeriesCreate,
  RaceSeriesListFilters,
  RaceSeriesListResponse,
  RaceSeriesRead,
} from "@/types/raceSeries.types";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const raceSeriesKeys = {
  /** Raíz del árbol — invalida todo el módulo race-series. */
  all: ["raceSeries"] as const,

  /** Todas las variantes de lista (sin importar filtros). */
  lists: () => [...raceSeriesKeys.all, "list"] as const,

  /** Lista con filtros específicos. */
  list: (filters: RaceSeriesListFilters) =>
    [...raceSeriesKeys.lists(), filters] as const,
};

// ---------------------------------------------------------------------------
// useRaceSeriesList — GET /race-series
// ---------------------------------------------------------------------------

/**
 * Hook de lista de series de competencias.
 *
 * Consume `GET /api/race-analysis/race-series` con filtros opcionales
 * (`season` y/o `kind`). Útil para poblar el picker de series en los
 * formularios de creación/edición de competencias y el wizard de importación.
 *
 * Estado de carga/error expuesto directamente desde TanStack Query.
 * El componente consumidor es responsable de mostrar skeleton/empty/error
 * (Principio III — sin spinner infinito, sin texto crudo de excepción).
 *
 * @param filters - Filtros opcionales. Defaults a {} (sin filtros).
 */
export function useRaceSeriesList(filters: RaceSeriesListFilters = {}) {
  return useQuery<RaceSeriesListResponse>({
    queryKey: raceSeriesKeys.list(filters),
    queryFn: ({ signal }) => listRaceSeries(filters, { signal }),
    // staleTime razonable: las series no cambian con mucha frecuencia.
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// useCreateRaceSeries — POST /race-series
// ---------------------------------------------------------------------------

/**
 * Mutation para crear una nueva serie de competencias.
 *
 * Al crear exitosamente invalida `raceSeriesKeys.lists()` para que todos los
 * pickers de series se actualicen automáticamente.
 *
 * @returns Mutation de TanStack Query. El componente maneja los callbacks
 *   `onSuccess` y `onError` según su flujo (toast, redirect, etc.).
 */
export function useCreateRaceSeries() {
  const queryClient = useQueryClient();

  return useMutation<RaceSeriesRead, unknown, RaceSeriesCreate>({
    mutationFn: (body) => createRaceSeries(body),
    onSuccess: () => {
      // Invalida todas las listas de series para reflejar la nueva entrada.
      void queryClient.invalidateQueries({ queryKey: raceSeriesKeys.lists() });
    },
  });
}
