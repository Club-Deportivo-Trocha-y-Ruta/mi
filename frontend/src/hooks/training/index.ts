/**
 * Hooks de TanStack Query para training sessions, attendance,
 * monthly reports y parent sessions / summary.
 *
 * Las funciones HTTP puras viven en `@/api/trainingSessions` y se
 * mantienen estables (consumidas por estos hooks + tests).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bulkSetConvocatoria,
  cancelTrainingSession,
  createMonthlyReport,
  createTrainingSession,
  executeTrainingSession,
  fetchMonthlyReport,
  fetchMonthlyReports,
  fetchParentMonthlySummary,
  fetchParentSessions,
  fetchSessionAttendance,
  fetchTrainingSession,
  fetchTrainingSessions,
  sendMonthlyReport,
  updateAttendance,
  updateTrainingSession,
  uploadRouteFile,
} from "@/api/trainingSessions";
import {
  monthlyReportKeys,
  parentSessionKeys,
  trainingSessionKeys,
} from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";
import { useAuthStore } from "@/store/auth.store";
import type {
  Attendance,
  AttendanceUpdate,
  MonthlyReportCreatePayload,
  SessionFilters,
  TrainingSessionUpdate,
} from "@/types/trainingSession.types";
import type { UseFormSetError } from "react-hook-form";

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export function useTrainingSessions(filters?: SessionFilters) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: trainingSessionKeys.list(userId, filters),
    queryFn: () => fetchTrainingSessions(filters),
    enabled: !!accessToken,
  });
}

export function useTrainingSession(id: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: trainingSessionKeys.detail(userId, id),
    queryFn: () => fetchTrainingSession(id),
    enabled: !!accessToken && enabled && !!id,
  });
}

export interface UseCreateTrainingSessionOptions<T extends Record<string, unknown>> {
  setError?: UseFormSetError<T>;
}

export function useCreateTrainingSession<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: UseCreateTrainingSessionOptions<T>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTrainingSession,
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.all });
    },
  });
}

export function useUpdateTrainingSession<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TrainingSessionUpdate }) =>
      updateTrainingSession(id, payload),
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.lists });
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.details });
    },
  });
}

export function useExecuteTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: executeTrainingSession,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.lists });
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.details });
    },
  });
}

export interface CancelTrainingSessionVars {
  id: number;
  notify?: boolean;
  reason?: string;
}

export function useCancelTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, notify, reason }: CancelTrainingSessionVars) =>
      cancelTrainingSession(id, { notify, reason }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.lists });
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.details });
    },
  });
}

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------

export function useSessionAttendance(sessionId: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: trainingSessionKeys.attendance(userId, sessionId),
    queryFn: () => fetchSessionAttendance(sessionId),
    enabled: !!accessToken && enabled && !!sessionId,
  });
}

export function useUpdateAttendance(sessionId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const attendanceKey = trainingSessionKeys.attendance(userId, sessionId);
  return useMutation({
    mutationFn: ({
      athleteId,
      payload,
    }: {
      athleteId: number;
      payload: AttendanceUpdate;
    }) => updateAttendance(sessionId, athleteId, payload),
    onMutate: async ({ athleteId, payload }) => {
      await queryClient.cancelQueries({ queryKey: attendanceKey });
      const previous = queryClient.getQueryData<Attendance[]>(attendanceKey);
      queryClient.setQueryData<Attendance[]>(
        attendanceKey,
        (old) =>
          old?.map((a) =>
            a.athlete_id === athleteId ? { ...a, ...payload } : a,
          ) ?? [],
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(attendanceKey, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: attendanceKey });
    },
  });
}

export interface BulkSetConvocatoriaVars {
  athleteIds: number[];
  sendNotification?: boolean;
}

export function useBulkSetConvocatoria(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ athleteIds, sendNotification }: BulkSetConvocatoriaVars) =>
      bulkSetConvocatoria(sessionId, athleteIds, sendNotification ?? false),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: trainingSessionKeys.attendances,
      });
    },
  });
}

export function useUploadRouteFile(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadRouteFile(sessionId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: trainingSessionKeys.details,
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Monthly reports
// ---------------------------------------------------------------------------

export function useMonthlyReports(clubId: number | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: monthlyReportKeys.list(clubId),
    queryFn: () => fetchMonthlyReports(clubId!),
    enabled: !!accessToken && !!clubId,
  });
}

export function useMonthlyReport(
  clubId: number | undefined,
  year: number,
  month: number,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: monthlyReportKeys.detail(clubId, year, month),
    queryFn: () => fetchMonthlyReport(clubId!, year, month),
    enabled: !!accessToken && !!clubId && !!year && !!month,
  });
}

export function useGenerateMonthlyReport(clubId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MonthlyReportCreatePayload) =>
      createMonthlyReport(clubId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: monthlyReportKeys.list(clubId),
      });
    },
  });
}

export function useSendMonthlyReport(clubId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) =>
      sendMonthlyReport(clubId, year, month),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: monthlyReportKeys.lists,
      });
      void queryClient.invalidateQueries({
        queryKey: monthlyReportKeys.details,
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Parent portal
// ---------------------------------------------------------------------------

export function useParentSessions(
  filters?: SessionFilters,
  parentAthleteIds?: number[],
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: parentSessionKeys.list(userId, filters, parentAthleteIds),
    queryFn: () => fetchParentSessions(filters, parentAthleteIds),
    enabled: !!accessToken && userId !== null,
  });
}

export function useParentMonthlySummary(
  year: number,
  month: number,
  athleteId?: number,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: parentSessionKeys.monthlySummary(userId, year, month, athleteId),
    queryFn: () => fetchParentMonthlySummary(year, month, athleteId),
    enabled: !!accessToken && !!year && !!month && userId !== null,
  });
}
