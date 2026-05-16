import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
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

export function useSessionMedia(sessionId: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["training-session-media", sessionId],
    queryFn: () => fetchSessionMedia(sessionId),
    enabled: !!accessToken && enabled && !!sessionId,
  });
}

export function useUploadSessionMedia(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SessionMediaUploadPayload) =>
      uploadSessionMedia(sessionId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["training-session-media", sessionId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["training-session", sessionId],
      });
    },
  });
}

export function useDeleteSessionMedia(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mediaId: number) => deleteSessionMedia(sessionId, mediaId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["training-session-media", sessionId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["training-session", sessionId],
      });
    },
  });
}

export function useUpdateSessionMedia(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      mediaId,
      payload,
    }: {
      mediaId: number;
      payload: SessionMediaUpdatePayload;
    }) => updateSessionMedia(sessionId, mediaId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["training-session-media", sessionId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["training-session", sessionId],
      });
    },
  });
}
