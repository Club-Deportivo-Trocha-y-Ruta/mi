export type SessionStatus = "planned" | "executed" | "cancelled";

/**
 * Entrenador a cargo de una sesión (feature 041 — gobernanza multi-coach,
 * contracts/session-coaches.md §3.1). `display_name` viene resuelto por el
 * backend (actor-name resolver) — nunca se arma en el cliente.
 */
export interface SessionCoach {
  user_id: number;
  display_name: string;
}

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
  session_kind?: SessionKind | null;
  objectives?: string | null;
  /**
   * Feature 041 — entrenadores a cargo, orden `added_at` asc (creador
   * primero). Opcional/aditivo: siempre no-vacío tras la migración del
   * backend (backfill B1), pero se marca opcional aquí para no romper
   * fixtures de tests existentes que aún no lo incluyen.
   */
  coaches?: SessionCoach[];
  /** Feature 041 — `false` cuando ningún entrenador de la sesión está activo. */
  has_active_coach?: boolean;
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

export type SessionKind = "entrenamiento" | "actividad_conjunta" | "salida" | "otro";

export interface TrainingSessionCreate {
  scheduled_date: string;
  scheduled_start_time: string;
  duration_min: number;
  location: string;
  technical_focus: string;
  description: string;
  route_text?: string | null;
  strava_url?: string | null;
  coach_notes?: string | null;
  convocados_athlete_ids: number[];
  send_notification?: boolean;
  session_kind?: SessionKind;
  objectives?: string | null;
  /**
   * Feature 041 — conjunto COMPLETO de entrenadores a cargo (reemplazo, no
   * parche). Ausente/`null` → el backend deja solo al creador
   * (contracts/session-coaches.md §3.2).
   */
  coach_user_ids?: number[] | null;
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
  session_kind?: SessionKind;
  objectives?: string | null;
  /**
   * Feature 041 — conjunto COMPLETO de entrenadores a cargo (reemplazo, no
   * parche). Ausente/`null` → los entrenadores no cambian
   * (contracts/session-coaches.md §3.2).
   */
  coach_user_ids?: number[] | null;
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
  // SPEC 2 — promedios de rúbrica por atleta (opcional: reportes antiguos
  // cuyo snapshot no los incluye → render "Pendiente — regenerar informe").
  avg_rubric_effort?: number | null;
  avg_rubric_attitude?: number | null;
  avg_rubric_technique?: number | null;
}

export interface SessionDetailItem {
  session_date: string;
  start_time: string;
  technical_focus: string;
  location: string;
  status: "executed" | "cancelled" | "planned";
  present_count: number;
  attendee_total: number;
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
  // SPEC 2 — detalle de sesiones del mes (opcional: reportes antiguos cuyo
  // snapshot no lo incluye → render "Pendiente — regenerar informe").
  session_detail?: SessionDetailItem[];
}

// ---------------------------------------------------------------------------
// Reporte mensual — extensión Informe Técnico (refactor)
// ---------------------------------------------------------------------------

export type MonthlyReportStatus = "draft" | "approved";

export interface NarrativeBlock {
  ai_draft: string | null;
  final_text: string | null;
  ai_model: string | null;
  ai_generated_at: string | null;
}

export interface CompetitionResult {
  athlete_name: string;
  category: string | null;
  position: number | null;
  points: number | null;
  event_name: string | null;
  event_date: string | null;
  // SPEC 2 — identidad estable del evento y clasificación (opcional:
  // reportes antiguos cuyo snapshot no los incluye).
  event_id?: number;
  series_kind?: string | null;
  awards_points?: boolean;
}

export type NarrativeBlockKey =
  | "objetivo"
  | "plan_entrenamiento"
  | "desarrollo"
  | "resultados"
  | "conclusiones"
  | "apoyos_materiales"
  | "analisis_grupo"
  | "competencia";

/**
 * Referencia a un actor adulto (coach/admin) del staff — nunca un atleta.
 * Espejo de `ActorRef` (`backend/app/schemas/audit.py`), reutilizado en
 * `MonthlyReportRead` (feature 041 — gobernanza multi-coach, T071/T074).
 * `display_name` es siempre de personal adulto: no aplica la restricción
 * de privacidad de menores (Ley 1581).
 */
export interface MonthlyReportActorRef {
  user_id: number;
  display_name: string;
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
  // Nuevos campos — Informe Técnico Mensual
  status?: MonthlyReportStatus;
  narrative_blocks?: Record<NarrativeBlockKey, NarrativeBlock> | null;
  competition_results?: CompetitionResult[] | null;
  // Evidencia de aprobación (feature 041 — gobernanza multi-coach, T071/T074).
  // Cada campo es `null`/ausente cuando se desconoce (informes previos a esta
  // feature, o campo aún no alcanzado en el ciclo de vida del informe).
  // `generated_by_user_id` (arriba) se conserva por compatibilidad; estos
  // objetos `ActorRef` son aditivos — contrato §5.5.
  generated_by?: MonthlyReportActorRef | null;
  approved_by?: MonthlyReportActorRef | null;
  approved_at?: string | null;
  // Evidencia de una aprobación anterior que una regeneración limpió — no se
  // destruye, sobrevive para trazabilidad (T071). Contrato §7: solo se
  // renderiza mientras el informe está en "draft".
  previous_approved_by?: MonthlyReportActorRef | null;
  previous_approved_at?: string | null;
  updated_by?: MonthlyReportActorRef | null;
  updated_at?: string | null;
}

// ---------------------------------------------------------------------------
// Perfil de proyecto del club — Informe Técnico
// ---------------------------------------------------------------------------

export interface ProjectProfile {
  project_name: string | null;
  executing_entity: string | null;
  report_responsible: string | null;
  purpose: string | null;
  general_objective: string | null;
  specific_objectives: string[] | null;
  territory_location: string | null;
  territory_description: string | null;
}

export interface MonthlyReportBlocksUpdate {
  blocks?: Record<string, string>;
  status?: MonthlyReportStatus;
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
