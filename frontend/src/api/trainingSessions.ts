import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import {
  monthlyReportKeys,
  parentSessionKeys,
  trainingSessionKeys,
} from "@/api/queryKeys";
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
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // Privacy R2: userId va al inicio del key (después del namespace) para
  // aislar cache por cuenta. `invalidateQueries({ queryKey: ["training-sessions"] })`
  // sigue funcionando porque TanStack hace match por prefijo.
  return useQuery({
    queryKey: trainingSessionKeys.list(userId, filters),
    queryFn: () => fetchTrainingSessions(filters),
    enabled: !!accessToken,
  });
}

export function useTrainingSession(id: number, enabled = true) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // Hook dual-rol (coach + parent). Añadimos userId al key para aislar
  // cache entre cuentas, pero NO lo exigimos en `enabled` porque tests
  // de coach legacy mockean auth.store sin `user.id` (queryKey de bajo
  // riesgo: el backend ya filtra por RBAC).
  return useQuery({
    queryKey: trainingSessionKeys.detail(userId, id),
    queryFn: () => fetchTrainingSession(id),
    enabled: !!accessToken && enabled && !!id,
  });
}

export function useCreateTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createTrainingSession,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: trainingSessionKeys.all });
    },
  });
}

export function useUpdateTrainingSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TrainingSessionUpdate }) =>
      updateTrainingSession(id, payload),
    onSuccess: () => {
      // Invalidación por prefijo de namespace: alcanza a todas las
      // variantes con userId en el key (R2). Más amplia que la versión
      // anterior `["training-session", id]`, pero el coach rara vez
      // tiene múltiples sesiones en cache a la vez.
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
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // R2: userId en el key. Dual-rol (coach + parent); no gateamos `enabled`
  // sobre userId para no romper tests legacy de coach que mockean auth.store
  // sin `user.id`. Aislamiento del cache se logra via key.
  return useQuery({
    queryKey: trainingSessionKeys.attendance(userId, sessionId),
    queryFn: () => fetchSessionAttendance(sessionId),
    enabled: !!accessToken && enabled && !!sessionId,
  });
}

export function useUpdateAttendance(sessionId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // El optimistic update toca el cache con el mismo key que la query de
  // lectura (incluye userId). Si en el futuro este hook lo usa un padre,
  // el optimistic update sigue tocando su slice del cache.
  const attendanceKey = trainingSessionKeys.attendance(userId, sessionId);
  return useMutation({
    mutationFn: ({ athleteId, payload }: { athleteId: number; payload: AttendanceUpdate }) =>
      updateAttendance(sessionId, athleteId, payload),
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
      // Invalidación por namespace para alcanzar todas las variantes
      // con userId en el key (R2).
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
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // R2: userId al inicio aísla cache entre cuentas (tablets familiares).
  // Hook exclusivo de padre → gateamos `enabled` también sobre userId
  // como defensa en profundidad: si user no está cargado, no disparamos
  // una request que podría intentar usar credenciales viejas.
  return useQuery({
    queryKey: parentSessionKeys.list(userId, filters, parentAthleteIds),
    queryFn: () => fetchParentSessions(filters, parentAthleteIds),
    enabled: !!accessToken && userId !== null,
  });
}

export function useParentMonthlySummary(year: number, month: number, athleteId?: number) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  // R2: ver useParentSessions. Hook exclusivo de padre.
  return useQuery({
    queryKey: parentSessionKeys.monthlySummary(userId, year, month, athleteId),
    queryFn: () => fetchParentMonthlySummary(year, month, athleteId),
    enabled: !!accessToken && !!year && !!month && userId !== null,
  });
}
