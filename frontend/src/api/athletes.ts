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
