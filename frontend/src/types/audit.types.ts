/**
 * Tipos del historial de auditoría (feature 041 — gobernanza multi-coach).
 *
 * Mirror de los schemas Pydantic en `backend/app/schemas/audit.py`.
 * Contrato: specs/041-multi-coach-governance/contracts/audit-log-api.md §5, §14.
 *
 * Privacidad (Ley 1581): estas filas NUNCA llevan el nombre, la fecha de
 * nacimiento ni datos del deportista — el único nombre propio es el del
 * actor adulto (coach o administrador). El atleta viaja solo como
 * `athlete_id`.
 */

export type AuditActorKind = "user" | "system" | "webhook" | "cron";

export type AuditAction =
  | "create"
  | "update"
  | "archive"
  | "delete"
  | "restore"
  | "approve"
  | "unapprove"
  | "send"
  | "export"
  | "cancel"
  | "execute"
  | "link"
  | "unlink"
  | "role_change"
  | "activate"
  | "deactivate"
  | "purge";

export type AuditEntityType =
  | "user"
  | "club"
  | "club_member"
  | "athlete"
  | "parent_athlete"
  | "parent_invite"
  | "parental_consent"
  | "anthropometric_record"
  | "training_session"
  | "training_session_coach"
  | "session_attendance"
  | "session_media"
  | "calendar_event"
  | "event_attendance"
  | "athlete_ai_explanation"
  | "monthly_report"
  | "club_project_profile"
  | "athlete_monthly_newsletter"
  | "athlete_ai_insight"
  | "agent_run"
  | "race_import"
  | "race_series"
  | "race_event"
  | "race_event_roster"
  | "race_result"
  | "race_competitor"
  | "interval_structure"
  | "interval_template"
  | "strava_connection"
  | "strava_activity"
  | "audit_log";

/** UserRole / ClubRole — mismos cuatro valores en ambos enums del backend. */
export type AuditActorRole = "admin" | "coach" | "parent" | "athlete";

export type AuditReasonGroup =
  | "athlete_archive"
  | "athlete_restore"
  | "cancel"
  | "account"
  | "parent_removal";

export type AuditDiffScalar = string | number | boolean | string[] | null;

export interface AuditDiffValue {
  before: AuditDiffScalar;
  after: AuditDiffScalar;
}

export interface AuditEntryDetail {
  changed_fields: string[];
  changed_field_labels: string[];
  diff: Record<string, AuditDiffValue> | null;
  meta: Record<string, unknown> | null;
}

export interface AuditEntryOut {
  id: number;
  occurred_at: string;
  actor_user_id: number | null;
  actor_kind: AuditActorKind;
  actor_role: AuditActorRole | null;
  actor_display_name: string;
  action: AuditAction;
  entity_type: AuditEntityType;
  entity_id: number;
  entity_label: string;
  club_id: number | null;
  athlete_id: number | null;
  reason_code: string | null;
  reason_label: string | null;
  sentence_es: string;
  request_id: string;
  detail: AuditEntryDetail;
}

export interface AuditListOut {
  items: AuditEntryOut[];
  total: number;
  limit: number;
  offset: number;
}

/** Query params compartidos por `/clubs/{id}/audit-log` y `/athletes/{id}/audit-log`. */
export interface AuditLogFilters {
  entity_type?: AuditEntityType;
  action?: AuditAction;
  actor_user_id?: number;
  athlete_id?: number;
  request_id?: string;
  from?: string; // YYYY-MM-DD
  to?: string; // YYYY-MM-DD
  limit?: number;
  offset?: number;
}

export interface AuditReasonCodeOut {
  code: string;
  label: string;
  group: AuditReasonGroup;
}

export interface AuditReasonCodeListOut {
  items: AuditReasonCodeOut[];
}
