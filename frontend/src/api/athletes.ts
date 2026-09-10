import { apiClient } from "@/api/client";
import type {
  AthleteCreate,
  AthleteDetailOut,
  AthleteListOut,
  AthleteOut,
  AthleteUpdate,
} from "@/types/athlete.types";
import type {
  AnthropometricRecord,
  AnthropometryCreate,
} from "@/types/anthropometry.types";

export async function getAthletes(params?: {
  club_id?: number;
  sort?: "recent_attendance";
  /** Admin-only (contracts/athlete-archive.md §4); coach → 403. */
  include_archived?: boolean;
}): Promise<AthleteListOut> {
  const response = await apiClient.get<AthleteListOut>("/api/athletes", { params });
  return response.data;
}

export async function getAthlete(id: number): Promise<AthleteDetailOut> {
  const response = await apiClient.get<AthleteDetailOut>(`/api/athletes/${id}`);
  return response.data;
}

export async function createAthlete(payload: AthleteCreate): Promise<AthleteOut> {
  const response = await apiClient.post<AthleteOut>("/api/athletes", payload);
  return response.data;
}

export async function updateAthlete(
  id: number,
  payload: AthleteUpdate,
): Promise<AthleteOut> {
  const response = await apiClient.patch<AthleteOut>(`/api/athletes/${id}`, payload);
  return response.data;
}

/**
 * Archiva (soft delete) un atleta — reemplaza `deleteAthlete`
 * (contracts/athlete-archive.md §1). `reason_code` es obligatorio; el
 * backend responde 422 si falta o no pertenece al catálogo
 * `athlete_archive`.
 *
 * Gotcha de axios: `apiClient.delete(url, body)` descarta el payload —
 * debe ir en `{ data: body }`.
 */
export async function archiveAthlete(id: number, reasonCode: string): Promise<void> {
  await apiClient.delete(`/api/athletes/${id}`, {
    data: { reason_code: reasonCode },
  });
}

/** Restaura un atleta archivado — admin only (contracts/athlete-archive.md §2). */
export async function restoreAthlete(id: number, reasonCode: string): Promise<void> {
  await apiClient.post(`/api/athletes/${id}/restore`, {
    reason_code: reasonCode,
  });
}

export async function getAnthropometry(
  athleteId: number,
): Promise<AnthropometricRecord[]> {
  const response = await apiClient.get<AnthropometricRecord[]>(
    `/api/athletes/${athleteId}/anthropometry`,
  );
  return response.data;
}

export async function createAnthropometry(
  athleteId: number,
  payload: AnthropometryCreate,
): Promise<AnthropometricRecord> {
  const response = await apiClient.post<AnthropometricRecord>(
    `/api/athletes/${athleteId}/anthropometry`,
    payload,
  );
  return response.data;
}
