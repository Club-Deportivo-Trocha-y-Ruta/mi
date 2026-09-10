/**
 * Etiquetas es-CO para los filtros del historial de auditoría (feature
 * 041 — gobernanza multi-coach). El backend ya envía `sentence_es` y
 * `entity_label` listos para mostrar (ver `AuditEntryRow`); estas etiquetas
 * son solo para poblar los `<select>` de filtro por tipo de registro y
 * acción, que sí viajan como el código crudo del enum en la query string.
 */
import type { AuditAction, AuditEntityType } from "@/types/audit.types";

export const AUDIT_ENTITY_TYPE_LABELS: Record<AuditEntityType, string> = {
  user: "Usuario",
  club: "Club",
  club_member: "Miembro del club",
  athlete: "Atleta",
  parent_athlete: "Vínculo padre-atleta",
  parent_invite: "Invitación a padre",
  parental_consent: "Consentimiento parental",
  anthropometric_record: "Medición antropométrica",
  training_session: "Sesión de entrenamiento",
  training_session_coach: "Entrenador de sesión",
  session_attendance: "Asistencia a sesión",
  session_media: "Media de sesión",
  calendar_event: "Evento de calendario",
  event_attendance: "Asistencia a evento",
  athlete_ai_explanation: "Explicación IA",
  monthly_report: "Informe mensual",
  club_project_profile: "Perfil de proyecto del club",
  athlete_monthly_newsletter: "Boletín mensual",
  athlete_ai_insight: "Insight IA",
  agent_run: "Ejecución de IA",
  race_import: "Importación de carrera",
  race_series: "Serie de carreras",
  race_event: "Evento de carrera",
  race_event_roster: "Convocatoria de carrera",
  race_result: "Resultado de carrera",
  race_competitor: "Competidor",
  interval_structure: "Estructura de intervalos",
  interval_template: "Plantilla de intervalos",
  strava_connection: "Conexión Strava",
  strava_activity: "Actividad Strava",
  audit_log: "Registro de auditoría",
};

export const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
  create: "Creación",
  update: "Actualización",
  archive: "Archivado",
  delete: "Eliminación",
  restore: "Restauración",
  approve: "Aprobación",
  unapprove: "Desaprobación",
  send: "Envío",
  export: "Exportación",
  cancel: "Cancelación",
  execute: "Ejecución",
  link: "Enlace",
  unlink: "Desenlace",
  role_change: "Cambio de rol",
  activate: "Activación",
  deactivate: "Desactivación",
  purge: "Purga",
};
