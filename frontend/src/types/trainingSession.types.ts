export type SessionStatus = "planned" | "executed" | "cancelled";

export type AttendanceStatus =
  | "presente"
  | "ausente"
  | "justificado"
  | "tarde"
  | "lesionado";

export interface TrainingSession {
  id: number;
  club_id: number;
  created_by_user_id: number;
  status: SessionStatus;
  scheduled_date: string;
  scheduled_start_time: string;
  duration_min: number;
  location: string;
  technical_focus: string;
  description: string;
  route_text?: string | null;
  strava_url?: string | null;
  route_file_path?: string | null;
  coach_notes?: string | null;
  created_at: string;
  updated_at: string;
  executed_at?: string | null;
  attendance_count?: number | null;
  attendance_summary?: AttendanceSummaryCounts | null;
  kid_attendances?: KidAttendance[] | null;
  media?: SessionMedia[] | SessionMediaParent[];
}

export type MediaType = "photo" | "video";

export interface SessionMedia {
  id: number;
  session_id: number;
  media_type: MediaType;
  storage_url: string;
  thumbnail_url?: string | null;
  filename_original: string;
  mime_type: string;
  size_bytes: number;
  width?: number | null;
  height?: number | null;
  duration_sec?: number | null;
  caption?: string | null;
  consent_ack: boolean;
  uploaded_by_user_id: number;
  uploaded_at: string;
  athlete_ids: number[];
}

export interface SessionMediaParent {
  id: number;
  session_id: number;
  media_type: MediaType;
  storage_url: string;
  thumbnail_url?: string | null;
  mime_type: string;
  width?: number | null;
  height?: number | null;
  duration_sec?: number | null;
  caption?: string | null;
  uploaded_at: string;
}

export interface SessionMediaUploadPayload {
  file: File;
  media_type: MediaType;
  athlete_ids: number[];
  consent_ack: boolean;
  caption?: string;
}

export interface SessionMediaUpdatePayload {
  caption?: string | null;
  athlete_ids?: number[];
}

export interface KidAttendance {
  athlete_id: number;
  status: AttendanceStatus;
  excuse_reason?: string | null;
  rpe_omni?: number | null;
  rubric_effort?: number | null;
  rubric_attitude?: number | null;
  rubric_technique?: number | null;
  individual_feedback?: string | null;
}

export interface AttendanceSummaryCounts {
  total: number;
  presentes: number;
  ausentes: number;
  justificados: number;
  tardes: number;
  lesionados: number;
}

export interface TrainingSessionCreate {
  scheduled_date: string;
  scheduled_start_time: string;
  duration_min: number;
  location: string;
  technical_focus: string;
  description: string;
  route_text?: string | null;
  strava_url?: string | null;
  convocados_athlete_ids: number[];
  send_notification?: boolean;
}

export interface TrainingSessionUpdate {
  scheduled_date?: string;
  scheduled_start_time?: string;
  duration_min?: number;
  location?: string;
  technical_focus?: string;
  description?: string;
  route_text?: string | null;
  strava_url?: string | null;
  coach_notes?: string | null;
  convocados_athlete_ids?: number[];
  send_notification?: boolean;
}

export interface Attendance {
  id: number;
  session_id: number;
  athlete_id: number;
  athlete_name?: string | null;
  status: AttendanceStatus;
  excuse_reason?: string | null;
  rpe_omni?: number | null;
  rubric_effort?: number | null;
  rubric_attitude?: number | null;
  rubric_technique?: number | null;
  individual_feedback?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AttendanceUpdate {
  status: AttendanceStatus;
  excuse_reason?: string | null;
  rpe_omni?: number | null;
  rubric_effort?: number | null;
  rubric_attitude?: number | null;
  rubric_technique?: number | null;
  individual_feedback?: string | null;
}

// ---------------------------------------------------------------------------
// Reporte mensual — PASO 12
// ---------------------------------------------------------------------------

// Forma REAL del backend (MonthlyMetrics.model_dump): dict keyed por athlete_id.
export interface AthleteAttendanceStats {
  athlete_id: number;
  count_present: number;
  count_absent: number;
  count_justified: number;
  count_late: number;
  count_injured: number;
  total_sessions: number;
  attendance_pct: number;
}

export interface MonthlyMetricsSnapshot {
  total_sessions_planned: number;
  total_sessions_executed: number;
  total_sessions_cancelled: number;
  // Claves string (athlete_id) porque el snapshot se serializa a JSON.
  attendance_by_athlete?: Record<string, AthleteAttendanceStats>;
  technical_focus_list?: string[];
  technical_focus_counts?: Record<string, number>;
  avg_rpe: number | null;
  avg_rubric_effort: number | null;
  avg_rubric_attitude: number | null;
  avg_rubric_technique: number | null;
  // SPEC 1 — campos nuevos (opcionales: reportes antiguos no los traen).
  total_minutes_planned?: number;
  total_minutes_executed?: number;
  avg_hours_per_week?: number | null;
  attendance_status_totals?: Record<string, number>;
}

export interface MonthlyReportFull {
  id: number;
  club_id: number;
  year: number;
  month: number;
  ai_summary: string | null;
  metrics_snapshot: MonthlyMetricsSnapshot | null;
  coach_observations: string | null;
  generated_by_user_id: number;
  generated_at: string;
  // id_atleta (str) -> "Nombre Apellido". Solo presente para coach/admin.
  athlete_names?: Record<string, string>;
}

export interface MonthlyReportCreatePayload {
  year: number;
  month: number;
  coach_observations?: string;
  force_regenerate?: boolean;
}

export interface SessionFilters {
  from_date?: string;
  to_date?: string;
  status?: SessionStatus | "";
  athlete_id?: number;
}

export interface ParentMonthlySummary {
  athlete_id: number;
  athlete_name: string;
  year: number;
  month: number;
  count_present: number;
  count_total: number;
  percentage: number;
  focos_técnicos: string[];
  avg_rpe?: number | null;
  avg_rubric_effort?: number | null;
  avg_rubric_attitude?: number | null;
  avg_rubric_technique?: number | null;
}
