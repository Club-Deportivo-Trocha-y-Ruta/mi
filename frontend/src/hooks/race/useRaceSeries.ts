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
 *   - `useUpdateRaceSeries()`       → mutation PATCH /race-series/{id}
 *     (hotfix multicopa — identidad de válida: edición de `short_name`)
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
import { createRaceSeries, listRaceSeries, updateRaceSeries } from "@/api/raceSeries";
import { raceEventKeys } from "@/hooks/race/useRaceEvents";
import type {
  RaceSeriesCreate,
  RaceSeriesListFilters,
  RaceSeriesListResponse,
  RaceSeriesRead,
  RaceSeriesUpdate,
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
 * @param options - `enabled` (default true) para apagar la query cuando el
 *   consumidor no la necesita (p. ej. el wizard standalone — FR-007 feature 015,
 *   que no debe disparar GET /race-series).
 */
export function useRaceSeriesList(
  filters: RaceSeriesListFilters = {},
  options?: { enabled?: boolean },
) {
  return useQuery<RaceSeriesListResponse>({
    queryKey: raceSeriesKeys.list(filters),
    queryFn: ({ signal }) => listRaceSeries(filters, { signal }),
    // staleTime razonable: las series no cambian con mucha frecuencia.
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
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

// ---------------------------------------------------------------------------
// useUpdateRaceSeries — PATCH /race-series/{id}
// ---------------------------------------------------------------------------

export interface UseUpdateRaceSeriesVariables {
  id: number;
  body: RaceSeriesUpdate;
}

/**
 * Mutation para actualizar una serie existente (nombre y/o `short_name`).
 *
 * Hotfix multicopa — identidad de válida: permite al coach fijar el nombre
 * corto de una copa (ej. "Let's GO") usado en chips/labels compactos.
 *
 * On success invalida:
 *   - `raceSeriesKeys.all` → todos los pickers/listas de series se refrescan
 *   - `raceEventKeys.all`  → las válidas de esa serie (InfoTab, listas)
 *     vuelven a resolver el nombre/short_name actualizado.
 */
export function useUpdateRaceSeries() {
  const queryClient = useQueryClient();

  return useMutation<RaceSeriesRead, unknown, UseUpdateRaceSeriesVariables>({
    mutationKey: ["raceSeries", "update"],
    mutationFn: ({ id, body }) => updateRaceSeries(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: raceSeriesKeys.all });
      void queryClient.invalidateQueries({ queryKey: raceEventKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Error message helper
// ---------------------------------------------------------------------------

/**
 * Extrae mensaje legible del error axios de `useUpdateRaceSeries` /
 * `useCreateRaceSeries` para banners/toasts inline.
 *
 * 409 → colisión de (name, season_year) con otra serie.
 * 404 → la serie fue eliminada en paralelo (edición concurrente).
 */
export function getRaceSeriesErrorMessage(
  err: unknown,
  fallback = "No se pudo actualizar la serie. Intenta de nuevo.",
): string {
  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const status = e.response?.status;
    if (status === 409) {
      return "Ya existe una serie con ese nombre para la temporada.";
    }
    if (status === 404) {
      return "La serie ya no existe. Recarga la página.";
    }
    if (status === 403) {
      return "Sin permiso para realizar esta acción.";
    }
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (e.message && !/status code \d+/i.test(e.message)) {
      return e.message;
    }
  }
  return fallback;
}
