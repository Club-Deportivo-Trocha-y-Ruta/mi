/**
 * Hooks TanStack Query del módulo race-competitors (Option A R1).
 *
 * - `useUnlinkedCompetitors(filters)` → GET /api/race-competitors/?unlinked=true
 * - `useCompetitorSuggestions(competitorId, enabled)` → query lazy on-demand
 * - `useLinkCompetitor()` → mutation POST /{id}/link
 * - `useUnlinkCompetitor()` → mutation DELETE /{id}/link
 *
 * Invalidaciones tras mutación: `['raceCompetitors']` + `['raceAnalysis']`
 * (los analytics dependen de los enlaces).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  getCompetitorSuggestions,
  linkCompetitor,
  listUnlinkedCompetitors,
  unlinkCompetitor,
} from "@/api/raceCompetitors";
import { useAuthStore } from "@/store/auth.store";
import type {
  CompetitorLinkResponse,
  CompetitorSuggestionsResponse,
  CompetitorUnlinkResponse,
  UnlinkedCompetitorsListResponse,
  UnlinkedCompetitorsParams,
} from "@/types/raceCompetitors.types";

export const raceCompetitorsKeys = {
  all: ["raceCompetitors"] as const,
  unlinked: (filters: UnlinkedCompetitorsParams) =>
    ["raceCompetitors", "unlinked", filters] as const,
  suggestions: (competitorId: number, limit: number) =>
    ["raceCompetitors", "suggestions", competitorId, limit] as const,
};

export function useUnlinkedCompetitors(
  filters: UnlinkedCompetitorsParams = {},
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery<UnlinkedCompetitorsListResponse, unknown>({
    queryKey: raceCompetitorsKeys.unlinked(filters),
    queryFn: () => listUnlinkedCompetitors(filters),
    enabled: !!accessToken,
    staleTime: 30_000,
  });
}

/** Hook lazy — sólo dispara fetch cuando `enabled=true` (ej. al expandir row). */
export function useCompetitorSuggestions(
  competitorId: number | null,
  enabled: boolean,
  limit = 5,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery<CompetitorSuggestionsResponse, unknown>({
    queryKey: raceCompetitorsKeys.suggestions(competitorId ?? -1, limit),
    queryFn: () => getCompetitorSuggestions(competitorId as number, limit),
    enabled: enabled && competitorId != null && !!accessToken,
    staleTime: 60_000,
  });
}

export interface UseLinkCompetitorVariables {
  competitorId: number;
  athleteId: number;
}

export function useLinkCompetitor() {
  const queryClient = useQueryClient();
  return useMutation<
    CompetitorLinkResponse,
    unknown,
    UseLinkCompetitorVariables
  >({
    mutationKey: ["raceCompetitors", "link"],
    mutationFn: ({ competitorId, athleteId }) =>
      linkCompetitor(competitorId, athleteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: raceCompetitorsKeys.all,
      });
      void queryClient.invalidateQueries({ queryKey: ["raceAnalysis"] });
    },
  });
}

export interface UseUnlinkCompetitorVariables {
  competitorId: number;
}

export function useUnlinkCompetitor() {
  const queryClient = useQueryClient();
  return useMutation<
    CompetitorUnlinkResponse,
    unknown,
    UseUnlinkCompetitorVariables
  >({
    mutationKey: ["raceCompetitors", "unlink"],
    mutationFn: ({ competitorId }) => unlinkCompetitor(competitorId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: raceCompetitorsKeys.all,
      });
      void queryClient.invalidateQueries({ queryKey: ["raceAnalysis"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Error message helper — mapea status codes a copy en español
// ---------------------------------------------------------------------------

/**
 * Extrae mensaje legible del error axios para mostrar en toast.
 * Mapea status codes documentados (403, 404, 409, 422) a copy específico.
 */
export function getCompetitorErrorMessage(
  err: unknown,
  fallback = "Error inesperado. Intenta de nuevo.",
): string {
  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const status = e.response?.status;
    if (status === 409) {
      return "Este competidor ya está enlazado a otro atleta. Desvincúlalo primero.";
    }
    if (status === 403) {
      return "Sin permiso: el atleta no pertenece a tu club.";
    }
    if (status === 404) {
      return "Competidor o atleta no encontrado.";
    }
    if (status === 422) {
      return "Datos inválidos. Verifica el atleta seleccionado.";
    }
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (e.message && !/status code \d+/i.test(e.message)) {
      return e.message;
    }
  }
  return fallback;
}
