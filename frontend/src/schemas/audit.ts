/**
 * Espejo Zod de `backend/app/schemas/audit.py` (feature 041 — gobernanza
 * multi-coach). Contrato: specs/041-multi-coach-governance/contracts/audit-log-api.md §5, §14.
 *
 * Un fallo de parseo es un bug, no un estado de UI (§12 del contrato):
 * no se atrapa el error, se deja que TanStack Query lo propague.
 */
import { z } from "zod";

export const auditActorKindSchema = z.enum(["user", "system", "webhook", "cron"]);

export const auditActionSchema = z.enum([
  "create",
  "update",
  "archive",
  "delete",
  "restore",
  "approve",
  "unapprove",
  "send",
  "export",
  "cancel",
  "execute",
  "link",
  "unlink",
  "role_change",
  "activate",
  "deactivate",
  "purge",
]);

export const auditEntityTypeSchema = z.enum([
  "user",
  "club",
  "club_member",
  "athlete",
  "parent_athlete",
  "parent_invite",
  "parental_consent",
  "anthropometric_record",
  "training_session",
  "training_session_coach",
  "session_attendance",
  "session_media",
  "calendar_event",
  "event_attendance",
  "athlete_ai_explanation",
  "monthly_report",
  "club_project_profile",
  "athlete_monthly_newsletter",
  "athlete_ai_insight",
  "agent_run",
  "race_import",
  "race_series",
  "race_event",
  "race_event_roster",
  "race_result",
  "race_competitor",
  "interval_structure",
  "interval_template",
  "strava_connection",
  "strava_activity",
  "audit_log",
]);

export const auditActorRoleSchema = z.enum(["admin", "coach", "parent", "athlete"]);

export const auditReasonGroupSchema = z.enum([
  "athlete_archive",
  "athlete_restore",
  "cancel",
  "account",
  "parent_removal",
]);

const auditDiffScalarSchema = z.union([
  z.string(),
  z.number(),
  z.boolean(),
  z.array(z.string()),
  z.null(),
]);

export const auditDiffValueSchema = z.object({
  before: auditDiffScalarSchema,
  after: auditDiffScalarSchema,
});

export const auditEntryDetailSchema = z.object({
  changed_fields: z.array(z.string()),
  changed_field_labels: z.array(z.string()),
  diff: z.record(z.string(), auditDiffValueSchema).nullable(),
  meta: z.record(z.string(), z.unknown()).nullable(),
});

export const auditEntryOutSchema = z.object({
  id: z.number(),
  occurred_at: z.string(),
  actor_user_id: z.number().nullable(),
  actor_kind: auditActorKindSchema,
  actor_role: auditActorRoleSchema.nullable(),
  actor_display_name: z.string(),
  action: auditActionSchema,
  entity_type: auditEntityTypeSchema,
  entity_id: z.number(),
  entity_label: z.string(),
  club_id: z.number().nullable(),
  athlete_id: z.number().nullable(),
  reason_code: z.string().nullable(),
  reason_label: z.string().nullable(),
  sentence_es: z.string(),
  request_id: z.string(),
  detail: auditEntryDetailSchema,
});

export const auditListOutSchema = z.object({
  items: z.array(auditEntryOutSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export const auditReasonCodeOutSchema = z.object({
  code: z.string(),
  label: z.string(),
  group: auditReasonGroupSchema,
});

export const auditReasonCodeListOutSchema = z.object({
  items: z.array(auditReasonCodeOutSchema),
});

export type AuditEntryOutParsed = z.infer<typeof auditEntryOutSchema>;
export type AuditListOutParsed = z.infer<typeof auditListOutSchema>;
export type AuditReasonCodeListOutParsed = z.infer<typeof auditReasonCodeListOutSchema>;
