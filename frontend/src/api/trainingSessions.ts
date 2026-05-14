import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
import type {
  Attendance,
  AttendanceUpdate,
  MonthlyReportCreatePayload,
  MonthlyReportFull,
  ParentMonthlySummary,
  SessionFilters,
  TrainingSession,
  TrainingSessionCreate,
  TrainingSessionUpdate,
} from "@/types/trainingSession.types";

const BASE = "/api/training-sessions";

export async function fetchTrainingSessions(
  filters?: SessionFilters,
): Promise<TrainingSession[]> {
  const params: Record<string, string> = {};
  if (filters?.from_date) params.from = filters.from_date;
  if (filters?.to_date) params.to = filters.to_date;
  if (filters?.status) params.status = filters.status;
  if (filters?.athlete_id) params.athlete_id = String(filters.athlete_id);
  const response = await apiClient.get<TrainingSession[]>(BASE, { params });
  return response.data;
}

export async function fetchTrainingSession(id: number): Promise<TrainingSession> {
  const response = await apiClient.get<TrainingSession>(`${BASE}/${id}`);
  return response.data;
}

export async function createTrainingSession(
  payload: TrainingSessionCreate,
): Promise<TrainingSession> {
  const response = await apiClient.post<TrainingSession>(BASE, payload);
  return response.data;
}

export async function updateTrainingSession(
  id: number,
  payload: TrainingSessionUpdate,
): Promise<TrainingSession> {
  const response = await apiClient.patch<TrainingSession>(`${BASE}/${id}`, payload);
  return response.data;
}

export async function executeTrainingSession(id: number): Promise<TrainingSession> {
  const response = await apiClient.post<TrainingSession>(`${BASE}/${id}/execute`);
  return response.data;
}

export interface CancelTrainingSessionOptions {
  notify?: boolean;
  reason?: string;
}

export async function cancelTrainingSession(
  id: number,
  opts?: CancelTrainingSessionOptions,
): Promise<TrainingSession> {
  const params: Record<string, string> = {};
  if (opts?.notify !== undefined) params.notify = String(opts.notify);
  if (opts?.reason) params.reason = opts.reason;
  const response = await apiClient.delete<TrainingSession>(`${BASE}/${id}`, { params });
  return response.data;
}

export function useTrainingSessions(filters?: SessionFilters) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["training-sessions", filters],
    queryFn: () => fetchTrainingSessions(filters),
    enabled: !!accessToken,
  });
}

export function useTrainingSession(id: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["training-session", id],
    queryFn: () => fetchTrainingSession(id),
    enabled: !!accessToken && enabled && !!id,
  });
}

export function useCreateTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTrainingSession,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["training-sessions"] });
    },
  });
}

export function useUpdateTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TrainingSessionUpdate }) =>
      updateTrainingSession(id, payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["training-sessions"] });
      void queryClient.invalidateQueries({
        queryKey: ["training-session", variables.id],
      });
    },
  });
}

export function useExecuteTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: executeTrainingSession,
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["training-sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["training-session", id] });
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
    onSuccess: (_data, vars) => {
      void queryClient.invalidateQueries({ queryKey: ["training-sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["training-session", vars.id] });
    },
  });
}

export async function fetchSessionAttendance(sessionId: number): Promise<Attendance[]> {
  const response = await apiClient.get<Attendance[]>(
    `${BASE}/${sessionId}/attendance`,
  );
  return response.data;
}

export async function updateAttendance(
  sessionId: number,
  athleteId: number,
  payload: AttendanceUpdate,
): Promise<Attendance> {
  const response = await apiClient.patch<Attendance>(
    `${BASE}/${sessionId}/attendance/${athleteId}`,
    payload,
  );
  return response.data;
}

export async function bulkSetConvocatoria(
  sessionId: number,
  athleteIds: number[],
  sendNotification = false,
): Promise<Attendance[]> {
  const response = await apiClient.put<Attendance[]>(
    `${BASE}/${sessionId}/attendance`,
    { athlete_ids: athleteIds, send_notification: sendNotification },
  );
  return response.data;
}

export async function uploadRouteFile(
  sessionId: number,
  file: File,
): Promise<TrainingSession> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<TrainingSession>(
    `${BASE}/${sessionId}/route-file`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return response.data;
}

export function useSessionAttendance(sessionId: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["training-session-attendance", sessionId],
    queryFn: () => fetchSessionAttendance(sessionId),
    enabled: !!accessToken && enabled && !!sessionId,
  });
}

export function useUpdateAttendance(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ athleteId, payload }: { athleteId: number; payload: AttendanceUpdate }) =>
      updateAttendance(sessionId, athleteId, payload),
    onMutate: async ({ athleteId, payload }) => {
      await queryClient.cancelQueries({
        queryKey: ["training-session-attendance", sessionId],
      });
      const previous = queryClient.getQueryData<Attendance[]>([
        "training-session-attendance",
        sessionId,
      ]);
      queryClient.setQueryData<Attendance[]>(
        ["training-session-attendance", sessionId],
        (old) =>
          old?.map((a) =>
            a.athlete_id === athleteId ? { ...a, ...payload } : a,
          ) ?? [],
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          ["training-session-attendance", sessionId],
          context.previous,
        );
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: ["training-session-attendance", sessionId],
      });
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
        queryKey: ["training-session-attendance", sessionId],
      });
    },
  });
}

export function useUploadRouteFile(sessionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadRouteFile(sessionId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["training-session", sessionId] });
    },
  });
}

// ---------------------------------------------------------------------------
// Reportes mensuales — PASO 12
// ---------------------------------------------------------------------------

const CLUBS_BASE = "/api/clubs";

export async function fetchMonthlyReports(clubId: number): Promise<MonthlyReportFull[]> {
  const response = await apiClient.get<MonthlyReportFull[]>(
    `${CLUBS_BASE}/${clubId}/monthly-reports`,
  );
  return response.data;
}

export async function fetchMonthlyReport(
  clubId: number,
  year: number,
  month: number,
): Promise<MonthlyReportFull> {
  const response = await apiClient.get<MonthlyReportFull>(
    `${CLUBS_BASE}/${clubId}/monthly-reports/${year}/${month}`,
  );
  return response.data;
}

export async function createMonthlyReport(
  clubId: number,
  payload: MonthlyReportCreatePayload,
): Promise<MonthlyReportFull> {
  const response = await apiClient.post<MonthlyReportFull>(
    `${CLUBS_BASE}/${clubId}/monthly-reports`,
    payload,
  );
  return response.data;
}

export async function sendMonthlyReport(
  clubId: number,
  year: number,
  month: number,
): Promise<{ enviados: number; total_admins: number; sent_at: string | null }> {
  const response = await apiClient.post(
    `${CLUBS_BASE}/${clubId}/monthly-reports/${year}/${month}/send`,
  );
  return response.data;
}

export function useMonthlyReports(clubId: number | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["monthly-reports", clubId],
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
    queryKey: ["monthly-report", clubId, year, month],
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
      void queryClient.invalidateQueries({ queryKey: ["monthly-reports", clubId] });
    },
  });
}

export function useSendMonthlyReport(clubId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) =>
      sendMonthlyReport(clubId, year, month),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["monthly-reports", clubId] });
      void queryClient.invalidateQueries({ queryKey: ["monthly-report", clubId] });
    },
  });
}

// ---------------------------------------------------------------------------
// Parent portal — PASO 13
// ---------------------------------------------------------------------------

export async function fetchParentSessions(
  filters?: SessionFilters,
  parentAthleteIds?: number[],
): Promise<TrainingSession[]> {
  const params: Record<string, string> = {};
  if (filters?.from_date) params.from = filters.from_date;
  if (filters?.to_date) params.to = filters.to_date;
  if (filters?.status) params.status = filters.status;
  if (filters?.athlete_id) params.athlete_id = String(filters.athlete_id);
  const response = await apiClient.get<TrainingSession[]>(BASE, { params });
  if (parentAthleteIds && parentAthleteIds.length > 0) {
    return response.data.filter(
      (s) =>
        s.kid_attendances?.some((a) => parentAthleteIds.includes(a.athlete_id)) ?? false,
    );
  }
  return response.data;
}

export async function fetchParentMonthlySummary(
  year: number,
  month: number,
  athleteId?: number,
): Promise<ParentMonthlySummary[]> {
  const params: Record<string, string> = {};
  if (athleteId) params.athlete_id = String(athleteId);
  const response = await apiClient.get<ParentMonthlySummary[]>(
    `/api/parents/training/monthly-summary/${year}/${month}`,
    { params },
  );
  return response.data;
}

export function useParentSessions(filters?: SessionFilters, parentAthleteIds?: number[]) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["parent-sessions", filters, parentAthleteIds],
    queryFn: () => fetchParentSessions(filters, parentAthleteIds),
    enabled: !!accessToken,
  });
}

export function useParentMonthlySummary(year: number, month: number, athleteId?: number) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["parent-monthly-summary", year, month, athleteId],
    queryFn: () => fetchParentMonthlySummary(year, month, athleteId),
    enabled: !!accessToken && !!year && !!month,
  });
}
