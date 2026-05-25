/**
 * Hooks de TanStack Query para session media (fotos / videos).
 *
 * Las funciones HTTP puras viven en `@/api/sessionMedia`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sessionMediaKeys, trainingSessionKeys } from "@/api/queryKeys";
import {
  deleteSessionMedia,
  fetchSessionMedia,
  updateSessionMedia,
  uploadSessionMedia,
} from "@/api/sessionMedia";
import { useAuthStore } from "@/store/auth.store";
import type {
  SessionMediaUpdatePayload,
  SessionMediaUploadPayload,
} from "@/types/trainingSession.types";

export function useSessionMedia(sessionId: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: sessionMediaKeys.list(userId, sessionId),
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
      void queryClient.invalidateQueries({ queryKey: sessionMediaKeys.all });
      void queryClient.invalidateQueries({
        queryKey: trainingSessionKeys.details,
      });
    },
  });
}

export function useDeleteSessionMedia(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mediaId: number) => deleteSessionMedia(sessionId, mediaId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sessionMediaKeys.all });
      void queryClient.invalidateQueries({
        queryKey: trainingSessionKeys.details,
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
      void queryClient.invalidateQueries({ queryKey: sessionMediaKeys.all });
      void queryClient.invalidateQueries({
        queryKey: trainingSessionKeys.details,
      });
    },
  });
}
