/**
 * Funciones HTTP puras para session media.
 *
 * Los hooks de TanStack Query viven en `@/hooks/sessionMedia/index.ts`.
 */
import { apiClient } from "@/api/client";
import type {
  SessionMedia,
  SessionMediaParent,
  SessionMediaUpdatePayload,
  SessionMediaUploadPayload,
} from "@/types/trainingSession.types";

const BASE = "/api/training-sessions";

export async function fetchSessionMedia(
  sessionId: number,
): Promise<Array<SessionMedia | SessionMediaParent>> {
  const response = await apiClient.get<Array<SessionMedia | SessionMediaParent>>(
    `${BASE}/${sessionId}/media`,
  );
  return response.data;
}

export async function uploadSessionMedia(
  sessionId: number,
  payload: SessionMediaUploadPayload,
): Promise<SessionMedia> {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("media_type", payload.media_type);
  formData.append("athlete_ids", payload.athlete_ids.join(","));
  formData.append("consent_ack", String(payload.consent_ack));
  if (payload.caption) {
    formData.append("caption", payload.caption);
  }
  const response = await apiClient.post<SessionMedia>(
    `${BASE}/${sessionId}/media`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return response.data;
}

export async function deleteSessionMedia(
  sessionId: number,
  mediaId: number,
): Promise<void> {
  await apiClient.delete(`${BASE}/${sessionId}/media/${mediaId}`);
}

export async function updateSessionMedia(
  sessionId: number,
  mediaId: number,
  payload: SessionMediaUpdatePayload,
): Promise<SessionMedia> {
  const response = await apiClient.patch<SessionMedia>(
    `${BASE}/${sessionId}/media/${mediaId}`,
    payload,
  );
  return response.data;
}

// ─── Re-export de hooks (migración incremental: ver @/hooks/sessionMedia) ────

export {
  useDeleteSessionMedia,
  useSessionMedia,
  useUpdateSessionMedia,
  useUploadSessionMedia,
} from "@/hooks/sessionMedia";
