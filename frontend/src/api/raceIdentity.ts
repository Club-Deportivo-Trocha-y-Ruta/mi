/**
 * API client del módulo race-identity (revisión de identidad, feature 044
 * US4).
 *
 * Endpoints bajo `/api/race-identity/*` — coach + admin
 * (ver contracts/identity-review-api.md).
 */
import { apiClient } from "@/api/client";
import type {
  IdentityCandidatesParams,
  IdentityCandidatesResponse,
  IdentityDecideRequest,
  IdentityDecideResponse,
  IdentityRebuildResponse,
  IdentityReverseResponse,
  IdentitySummaryResponse,
} from "@/types/raceIdentity.types";

const BASE = "/api/race-identity";

/** POST /api/race-identity/rebuild — recalcula candidatos (worker thread, budget ≤ 10 s). */
export async function rebuildIdentityCandidates(options?: {
  signal?: AbortSignal;
}): Promise<IdentityRebuildResponse> {
  const response = await apiClient.post<IdentityRebuildResponse>(
    `${BASE}/rebuild`,
    {},
    { signal: options?.signal },
  );
  return response.data;
}

/** GET /api/race-identity/candidates?state=&kind=&page= */
export async function listIdentityCandidates(
  params: IdentityCandidatesParams = {},
  options?: { signal?: AbortSignal },
): Promise<IdentityCandidatesResponse> {
  const response = await apiClient.get<IdentityCandidatesResponse>(
    `${BASE}/candidates`,
    {
      params: {
        state: params.state,
        kind: params.kind,
        page: params.page ?? 1,
      },
      signal: options?.signal,
    },
  );
  return response.data;
}

/** GET /api/race-identity/summary */
export async function getIdentitySummary(options?: {
  signal?: AbortSignal;
}): Promise<IdentitySummaryResponse> {
  const response = await apiClient.get<IdentitySummaryResponse>(
    `${BASE}/summary`,
    { signal: options?.signal },
  );
  return response.data;
}

/** POST /api/race-identity/candidates/{id}/decide — 409 si el candidato ya no está `pending`. */
export async function decideIdentityCandidate(
  candidateId: number,
  body: IdentityDecideRequest,
  options?: { signal?: AbortSignal },
): Promise<IdentityDecideResponse> {
  const response = await apiClient.post<IdentityDecideResponse>(
    `${BASE}/candidates/${candidateId}/decide`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/** POST /api/race-identity/candidates/{id}/reverse — vuelve el candidato a `pending`. */
export async function reverseIdentityCandidate(
  candidateId: number,
  options?: { signal?: AbortSignal },
): Promise<IdentityReverseResponse> {
  const response = await apiClient.post<IdentityReverseResponse>(
    `${BASE}/candidates/${candidateId}/reverse`,
    {},
    { signal: options?.signal },
  );
  return response.data;
}
