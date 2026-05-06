export type AgeGroup = "u12" | "u15";

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
  age_group: AgeGroup;
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
  attendance_summary?: { athlete_id: number; status: AttendanceStatus }[] | null;
}

export interface TrainingSessionCreate {
  age_group: AgeGroup;
  scheduled_date: string;
  scheduled_start_time: string;
  duration_min: number;
  location: string;
  technical_focus: string;
  description: string;
  route_text?: string | null;
  strava_url?: string | null;
  convocados_athlete_ids: number[];
}

export interface TrainingSessionUpdate {
  age_group?: AgeGroup;
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

export interface MonthlyMetrics {
  total_sessions: number;
  executed_sessions: number;
  cancelled_sessions: number;
  planned_sessions: number;
  sessions_u12: number;
  sessions_u15: number;
  technical_focuses: string[];
  avg_attendance_rate?: number | null;
}

export interface MonthlyReport {
  id: number;
  club_id: number;
  year: number;
  month: number;
  ai_summary?: string | null;
  metrics_snapshot: MonthlyMetrics;
  generated_by_user_id: number;
  generated_at: string;
  sent_at?: string | null;
}

// ---------------------------------------------------------------------------
// Reporte mensual — PASO 12
// ---------------------------------------------------------------------------

export interface AthleteAttendanceStats {
  pseudonym: string;
  count_present: number;
  count_total: number;
  percentage: number;
}

export interface MonthlyMetricsSnapshot {
  total_sessions_planned: number;
  total_sessions_executed: number;
  total_sessions_cancelled: number;
  attendance_stats: AthleteAttendanceStats[];
  focos_técnicos: string[];
  avg_rpe: number | null;
  avg_rubric_effort: number | null;
  avg_rubric_attitude: number | null;
  avg_rubric_technique: number | null;
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
  sent_at: string | null;
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
  age_group?: AgeGroup | "";
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
}
