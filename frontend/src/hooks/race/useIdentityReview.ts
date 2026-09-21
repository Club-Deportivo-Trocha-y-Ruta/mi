/**
 * Hooks TanStack Query del módulo race-identity — revisión de identidad
 * (feature 044, US4).
 *
 * - `useIdentityCandidates(params)` → query GET /candidates?state=&kind=&page=.
 * - `useIdentitySummary()` → query GET /summary (banner del gate de commit).
 * - `useDecideIdentityCandidate()` → mutation POST /candidates/{id}/decide.
 * - `useReverseIdentityCandidate()` → mutation POST /candidates/{id}/reverse.
 * - `useRebuildIdentityCandidates()` → mutation POST /rebuild.
 *
 * Todas las mutations invalidan la lista de candidatos y el resumen — el
 * gate de commit (`GET /summary`) y el tablero de cargas históricas leen de
 * ahí.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  decideIdentityCandidate,
  getIdentitySummary,
  listIdentityCandidates,
  rebuildIdentityCandidates,
  reverseIdentityCandidate,
} from "@/api/raceIdentity";
import type {
  IdentityCandidatesParams,
  IdentityCandidatesResponse,
  IdentityDecideRequest,
  IdentityDecideResponse,
  IdentityRebuildResponse,
  IdentityReverseResponse,
  IdentitySummaryResponse,
} from "@/types/raceIdentity.types";

export const identityReviewKeys = {
  all: ["race-identity"] as const,
  candidates: (params: IdentityCandidatesParams) =>
    ["race-identity", "candidates", params] as const,
  summary: () => ["race-identity", "summary"] as const,
};

function invalidateIdentityReview(
  queryClient: ReturnType<typeof useQueryClient>,
): void {
  void queryClient.invalidateQueries({ queryKey: identityReviewKeys.all });
}

/** GET /api/race-identity/candidates — cola paginada ordenada por score DESC. */
export function useIdentityCandidates(
  params: IdentityCandidatesParams = {},
) {
  return useQuery<IdentityCandidatesResponse, unknown>({
    queryKey: identityReviewKeys.candidates(params),
    queryFn: ({ signal }) => listIdentityCandidates(params, { signal }),
    staleTime: 10_000,
  });
}

/** GET /api/race-identity/summary — cuenta pending/same_person/different_people. */
export function useIdentitySummary() {
  return useQuery<IdentitySummaryResponse, unknown>({
    queryKey: identityReviewKeys.summary(),
    queryFn: ({ signal }) => getIdentitySummary({ signal }),
    staleTime: 10_000,
  });
}

export interface UseDecideIdentityCandidateVariables {
  candidateId: number;
  body: IdentityDecideRequest;
}

/** POST /candidates/{id}/decide — 409 si el candidato ya no está `pending`. */
export function useDecideIdentityCandidate() {
  const queryClient = useQueryClient();
  return useMutation<
    IdentityDecideResponse,
    unknown,
    UseDecideIdentityCandidateVariables
  >({
    mutationKey: ["race-identity", "decide"],
    mutationFn: ({ candidateId, body }) =>
      decideIdentityCandidate(candidateId, body),
    onSuccess: () => {
      invalidateIdentityReview(queryClient);
    },
  });
}

export interface UseReverseIdentityCandidateVariables {
  candidateId: number;
}

/** POST /candidates/{id}/reverse — vuelve el candidato a `pending`. */
export function useReverseIdentityCandidate() {
  const queryClient = useQueryClient();
  return useMutation<
    IdentityReverseResponse,
    unknown,
    UseReverseIdentityCandidateVariables
  >({
    mutationKey: ["race-identity", "reverse"],
    mutationFn: ({ candidateId }) => reverseIdentityCandidate(candidateId),
    onSuccess: () => {
      invalidateIdentityReview(queryClient);
    },
  });
}

/** POST /api/race-identity/rebuild — worker thread, budget ≤ 10 s. */
export function useRebuildIdentityCandidates() {
  const queryClient = useQueryClient();
  return useMutation<IdentityRebuildResponse, unknown, void>({
    mutationKey: ["race-identity", "rebuild"],
    mutationFn: () => rebuildIdentityCandidates(),
    onSuccess: () => {
      invalidateIdentityReview(queryClient);
    },
  });
}

// ---------------------------------------------------------------------------
// Error message helper — mapea status codes a copy en español
// ---------------------------------------------------------------------------

/**
 * Extrae mensaje legible del error axios para mostrar en toast.
 *
 * `race_identity.py` responde 409 con `detail: {code, message}` para todos
 * los conflictos documentados (`candidate_not_pending`,
 * `candidate_not_decided`, `linked_to_different_athletes`, `shared_valida`,
 * `already_same_competitor`, `linked_competitor_ambiguous` — este último
 * copy en `_CONFLICT_MESSAGES`) — ese `message` ya viene en español y es
 * más específico que un texto genérico por status code, así que se
 * prioriza. El 404 llega como `detail` string plano ("candidato {id} no
 * existe.").
 */
export function getIdentityReviewErrorMessage(
  err: unknown,
  fallback = "Error inesperado. Intenta de nuevo.",
): string {
  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const detail = e.response?.data?.detail;
    if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof (detail as { message?: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message;
    }
    if (typeof detail === "string") return detail;

    const status = e.response?.status;
    if (status === 409) {
      return "Este candidato ya fue decidido. Actualiza la lista.";
    }
    if (status === 403) {
      return "Sin permiso para revisar identidad.";
    }
    if (status === 404) {
      return "Candidato no encontrado.";
    }
    if (e.message && !/status code \d+/i.test(e.message)) {
      return e.message;
    }
  }
  return fallback;
}
