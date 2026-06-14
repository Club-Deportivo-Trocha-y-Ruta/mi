/**
 * useRaceResults — TanStack Query hook para los resultados de una válida.
 *
 * Endpoint: GET /api/race-analysis/race-events/{id}/results
 *
 * Parámetros:
 *   - `raceEventId` — ID del evento. Si es null/undefined o <= 0, la query
 *     queda deshabilitada (útil durante el initial render).
 *   - `filters.category_id` — filtra por categoría específica.
 *   - `filters.club_only` — si es true, solo retorna corredores del club.
 *
 * staleTime: 5 min — mitiga el cold start de Render Free (~50 s primer request).
 * Los filtros forman parte de la query key para que cada combinación tenga
 * su propia entrada de caché.
 *
 * useSetResultCoachNote / useClearResultCoachNote — mutaciones con actualizaciones
 * optimistas para agregar/editar/eliminar la nota del entrenador por corredor.
 * onMutate cancela las queries, hace snapshot y parchea la caché; onError revierte;
 * onSettled invalida para mantener la mutación pendiente hasta que el refetch completa
 * (honesto sobre conectividad intermitente — FR-011/SC-006).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearResultCoachNote,
  getRaceResults,
  setResultCoachNote,
} from "@/api/raceResults";
import { useAuthStore } from "@/store/auth.store";
import { raceResultsKeys } from "@/hooks/race/invalidation";
import type {
  RaceEventResultsResponse,
  RaceResultRow,
  RaceResultsFilters,
} from "@/types/raceResults.types";

/**
 * Hook para obtener los resultados de una válida (tabla de llegada).
 *
 * @param raceEventId - ID del race event. La query se deshabilita si es
 *   null, undefined, 0, o negativo.
 * @param filters - Filtros opcionales (category_id, club_only).
 */
export function useRaceResults(
  raceEventId: number | null | undefined,
  filters: RaceResultsFilters = {},
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const enabled =
    !!accessToken && raceEventId != null && raceEventId > 0;

  return useQuery<RaceEventResultsResponse, unknown>({
    queryKey: raceResultsKeys.byEventFiltered(raceEventId ?? -1, filters),
    queryFn: ({ signal }) =>
      getRaceResults(raceEventId as number, filters, { signal }),
    enabled,
    staleTime: 5 * 60_000,
    // Feature 012, US3: mantiene la tabla anterior visible al cambiar de
    // filtro/categoría (sin estado vacío intermedio).
    placeholderData: keepPreviousData,
  });
}

// ---------------------------------------------------------------------------
// Optimistic-update helpers
// ---------------------------------------------------------------------------

/**
 * Patches the `coach_note` and `coach_note_updated_at` fields for a single row
 * inside a `RaceEventResultsResponse` cache entry.
 */
function patchNoteInResponse(
  prev: RaceEventResultsResponse | undefined,
  resultId: number,
  patch: Pick<RaceResultRow, "coach_note" | "coach_note_updated_at">,
): RaceEventResultsResponse | undefined {
  if (!prev) return prev;
  return {
    ...prev,
    categories: prev.categories.map((cat) => ({
      ...cat,
      rows: cat.rows.map((row) =>
        row.result_id === resultId ? { ...row, ...patch } : row,
      ),
    })),
  };
}

// ---------------------------------------------------------------------------
// useSetResultCoachNote
// ---------------------------------------------------------------------------

export interface SetResultCoachNoteVariables {
  /** PK of the race_results row to update. */
  resultId: number;
  /** The note text (stripped by the backend; validated by Zod on the frontend). */
  coach_note: string;
  /**
   * The race event and filters that key the query cache entry to patch
   * optimistically. Must match the key used by `useRaceResults` at the
   * call-site.
   */
  raceEventId: number;
  filters?: RaceResultsFilters;
}

/**
 * Mutation hook for creating or replacing the coach note on a race result row.
 *
 * Optimistic flow:
 *  1. `onMutate`   — cancel in-flight queries, snapshot, setQueryData with patch.
 *  2. `onError`    — restore from snapshot (rollback).
 *  3. `onSettled`  — invalidate so the mutation stays pending until refetch
 *                    (honest feedback over intermittent connectivity, FR-011).
 */
export function useSetResultCoachNote() {
  const queryClient = useQueryClient();

  return useMutation<
    RaceResultRow,
    unknown,
    SetResultCoachNoteVariables,
    { previousData: RaceEventResultsResponse | undefined }
  >({
    mutationFn: ({ resultId, coach_note }) =>
      setResultCoachNote(resultId, { coach_note }),

    onMutate: async ({ resultId, raceEventId, filters = {}, coach_note }) => {
      const queryKey = raceResultsKeys.byEventFiltered(raceEventId, filters);

      // Cancel any outgoing refetches for this query so they don't overwrite
      // the optimistic patch.
      await queryClient.cancelQueries({ queryKey });

      const previousData =
        queryClient.getQueryData<RaceEventResultsResponse>(queryKey);

      queryClient.setQueryData<RaceEventResultsResponse>(
        queryKey,
        (prev) =>
          patchNoteInResponse(prev, resultId, {
            coach_note,
            coach_note_updated_at: new Date().toISOString(),
          }),
      );

      return { previousData };
    },

    onError: (_err, { raceEventId, filters = {} }, context) => {
      if (context?.previousData !== undefined) {
        queryClient.setQueryData(
          raceResultsKeys.byEventFiltered(raceEventId, filters),
          context.previousData,
        );
      }
    },

    onSettled: (_data, _err, { raceEventId, filters = {} }) =>
      queryClient.invalidateQueries({
        queryKey: raceResultsKeys.byEventFiltered(raceEventId, filters),
      }),
  });
}

// ---------------------------------------------------------------------------
// useClearResultCoachNote
// ---------------------------------------------------------------------------

export interface ClearResultCoachNoteVariables {
  /** PK of the race_results row whose note should be cleared. */
  resultId: number;
  /** Must match the key used by `useRaceResults` at the call-site. */
  raceEventId: number;
  filters?: RaceResultsFilters;
}

/**
 * Mutation hook for clearing (deleting) the coach note on a race result row.
 *
 * Same optimistic pattern as `useSetResultCoachNote` — patches the row to
 * `coach_note: null` immediately, rolls back on error, invalidates on settled.
 */
export function useClearResultCoachNote() {
  const queryClient = useQueryClient();

  return useMutation<
    RaceResultRow,
    unknown,
    ClearResultCoachNoteVariables,
    { previousData: RaceEventResultsResponse | undefined }
  >({
    mutationFn: ({ resultId }) => clearResultCoachNote(resultId),

    onMutate: async ({ resultId, raceEventId, filters = {} }) => {
      const queryKey = raceResultsKeys.byEventFiltered(raceEventId, filters);

      await queryClient.cancelQueries({ queryKey });

      const previousData =
        queryClient.getQueryData<RaceEventResultsResponse>(queryKey);

      queryClient.setQueryData<RaceEventResultsResponse>(
        queryKey,
        (prev) =>
          patchNoteInResponse(prev, resultId, {
            coach_note: null,
            coach_note_updated_at: null,
          }),
      );

      return { previousData };
    },

    onError: (_err, { raceEventId, filters = {} }, context) => {
      if (context?.previousData !== undefined) {
        queryClient.setQueryData(
          raceResultsKeys.byEventFiltered(raceEventId, filters),
          context.previousData,
        );
      }
    },

    onSettled: (_data, _err, { raceEventId, filters = {} }) =>
      queryClient.invalidateQueries({
        queryKey: raceResultsKeys.byEventFiltered(raceEventId, filters),
      }),
  });
}
