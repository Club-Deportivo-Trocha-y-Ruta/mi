/**
 * Funciones HTTP puras para training sessions, attendance, monthly
 * reports y parent portal.
 *
 * Los hooks de TanStack Query viven en `@/hooks/training/index.ts`.
 * Para preservar imports históricos durante la migración incremental,
 * este módulo re-exporta los hooks desde el nuevo home.
 */
import { apiClient } from "@/api/client";
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

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Monthly reports
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

// ---------------------------------------------------------------------------
// Parent portal
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

// ---------------------------------------------------------------------------
// Re-export de hooks (migración incremental: ver @/hooks/training)
// ---------------------------------------------------------------------------

export {
  useBulkSetConvocatoria,
  useCancelTrainingSession,
  useCreateTrainingSession,
  useExecuteTrainingSession,
  useGenerateMonthlyReport,
  useMonthlyReport,
  useMonthlyReports,
  useParentMonthlySummary,
  useParentSessions,
  useSendMonthlyReport,
  useSessionAttendance,
  useTrainingSession,
  useTrainingSessions,
  useUpdateAttendance,
  useUpdateTrainingSession,
  useUploadRouteFile,
} from "@/hooks/training";

export type {
  BulkSetConvocatoriaVars,
  CancelTrainingSessionVars,
} from "@/hooks/training";
