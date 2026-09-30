/**
 * Schemas Zod de la planilla mensual de asistencia IMDERTY (feature 047).
 *
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md`.
 * Enums y etiquetas: `specs/047-imderty-attendance-sheet/data-model.md`.
 *
 * Cada enum expone su lista de valores oficiales (para los <select>) y un
 * mapa `*Labels` en español neutro con tildes completas, la misma etiqueta
 * que la planilla oficial imprime (mayúsculas donde el formato FO-GDD-057
 * las exige). No hay, y nunca debe haber, un enum de orientación sexual
 * (FR-009).
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Enums oficiales
// ---------------------------------------------------------------------------

export const imdertyDocumentTypes = ["rc", "ti", "cc", "ce", "ppt", "pep", "nes"] as const;
export const imdertyDocumentTypeSchema = z.enum(imdertyDocumentTypes);
export type ImdertyDocumentType = z.infer<typeof imdertyDocumentTypeSchema>;

export const imdertyDocumentTypeLabels: Record<ImdertyDocumentType, string> = {
  rc: "R.C",
  ti: "T.I",
  cc: "C.C",
  ce: "C.E",
  ppt: "PPT",
  pep: "PEP",
  nes: "NES",
};

export const imdertyGrades = [
  "prejardin",
  "jardin",
  "transicion",
  "g1",
  "g2",
  "g3",
  "g4",
  "g5",
  "g6",
  "g7",
  "g8",
  "g9",
  "g10",
  "g11",
  "no_escolarizado",
  "otro",
] as const;
export const imdertyGradeSchema = z.enum(imdertyGrades);
export type ImdertyGrade = z.infer<typeof imdertyGradeSchema>;

export const imdertyGradeLabels: Record<ImdertyGrade, string> = {
  prejardin: "PREJARDÍN",
  jardin: "JARDÍN",
  transicion: "TRANSICIÓN",
  g1: "1",
  g2: "2",
  g3: "3",
  g4: "4",
  g5: "5",
  g6: "6",
  g7: "7",
  g8: "8",
  g9: "9",
  g10: "10",
  g11: "11",
  no_escolarizado: "NO ESCOLARIZADO",
  otro: "OTRO",
};

export const imdertyEthnicities = [
  "AFROCOLOMBIANO",
  "INDÍGENA",
  "MESTIZO",
  "MULATO",
  "NO SABE NO RESPONDE",
  "OTRO",
  "PALENQUERO",
  "RAIZAL",
  "ROM GITANO",
] as const;
export const imdertyEthnicitySchema = z.enum(imdertyEthnicities);
export type ImdertyEthnicity = z.infer<typeof imdertyEthnicitySchema>;

/** Los valores oficiales ya son la etiqueta a mostrar (no hay un código separado). */
export const imdertyEthnicityLabels: Record<ImdertyEthnicity, string> = Object.fromEntries(
  imdertyEthnicities.map((value) => [value, value]),
) as Record<ImdertyEthnicity, string>;

export const imdertyDisabilities = [
  "OLFATIVA Y TACTO",
  "MENTAL",
  "MOVILIDAD",
  "MULTIPLE",
  "ORAL",
  "PSICOSOCIAL",
  "VISUAL",
  "VOZ Y HABLA",
  "NO SABE NOMBRARLA",
  "N/A",
] as const;
export const imdertyDisabilitySchema = z.enum(imdertyDisabilities);
export type ImdertyDisability = z.infer<typeof imdertyDisabilitySchema>;

export const imdertyDisabilityLabels: Record<ImdertyDisability, string> = Object.fromEntries(
  imdertyDisabilities.map((value) => [value, value]),
) as Record<ImdertyDisability, string>;

export const imdertyYesNoValues = ["si", "no"] as const;
export const imdertyYesNoSchema = z.enum(imdertyYesNoValues);
export type ImdertyYesNo = z.infer<typeof imdertyYesNoSchema>;

export const imdertyYesNoLabels: Record<ImdertyYesNo, string> = {
  si: "SI",
  no: "NO",
};

export const imdertyPrograms = [
  "masificacion",
  "educacion_fisica_deporte_escolar",
  "primera_infancia",
  "hevs",
  "recreacion",
  "deporte_social_comunitario",
  "lecyd_cda",
  "competencia",
  "conjunto",
  "individual",
  "adaptado",
] as const;
export const imdertyProgramSchema = z.enum(imdertyPrograms);
export type ImdertyProgram = z.infer<typeof imdertyProgramSchema>;

export const imdertyProgramLabels: Record<ImdertyProgram, string> = {
  masificacion: "Masificación",
  educacion_fisica_deporte_escolar: "Educación física y deporte escolar",
  primera_infancia: "Primera infancia",
  hevs: "HEVS",
  recreacion: "Recreación",
  deporte_social_comunitario: "Deporte social comunitario",
  lecyd_cda: "LECYD - CDA",
  competencia: "Competencia",
  conjunto: "Conjunto",
  individual: "Individual",
  adaptado: "Adaptado",
};

export const imdertyBarrioZones = [
  "1",
  "2",
  "3",
  "4",
  "ZONA NORTE",
  "ZONA CENTRO",
  "ZONA SUR",
] as const;
export const imdertyBarrioZoneSchema = z.enum(imdertyBarrioZones);
export type ImdertyBarrioZone = z.infer<typeof imdertyBarrioZoneSchema>;

// ---------------------------------------------------------------------------
// Barrio catalog
// ---------------------------------------------------------------------------

export const barrioSchema = z.object({
  id: z.number().int().positive(),
  name: z.string(),
  zone: imdertyBarrioZoneSchema,
  is_active: z.boolean(),
});
export type Barrio = z.infer<typeof barrioSchema>;

export const barrioListSchema = z.array(barrioSchema);

export const barrioCreateSchema = z.object({
  name: z.string().trim().min(1, "Ingresa el nombre del barrio"),
  zone: imdertyBarrioZoneSchema,
  is_active: z.boolean().default(true),
});
export type BarrioCreateValues = z.infer<typeof barrioCreateSchema>;

export const barrioUpdateSchema = barrioCreateSchema.partial();
export type BarrioUpdateValues = z.infer<typeof barrioUpdateSchema>;

// ---------------------------------------------------------------------------
// Athlete IMDERTY profile
// ---------------------------------------------------------------------------

export const surnameSplitSchema = z.object({
  confirmed: z.boolean(),
  proposed_first: z.string().nullable(),
  proposed_second: z.string().nullable(),
});
export type SurnameSplit = z.infer<typeof surnameSplitSchema>;

export const barrioRefSchema = z.object({
  id: z.number().int().positive(),
  name: z.string(),
  zone: z.string(),
});
export type BarrioRef = z.infer<typeof barrioRefSchema>;

export const imdertyGuardianSchema = z.object({
  user_id: z.number().int().positive(),
  display_name: z.string(),
  has_phone: z.boolean(),
  is_primary_contact: z.boolean(),
});
export type ImdertyGuardian = z.infer<typeof imdertyGuardianSchema>;

export const sensitiveAuthorizationSchema = z.object({
  id: z.number().int().positive(),
  guardian_user_id: z.number().int().positive(),
  authorized_on: z.string(),
  active: z.boolean(),
});
export type SensitiveAuthorization = z.infer<typeof sensitiveAuthorizationSchema>;

export const imdertyProfileSchema = z.object({
  athlete_id: z.number().int().positive(),
  first_surname: z.string().nullable(),
  second_surname: z.string().nullable(),
  surname_split: surnameSplitSchema,
  document_type: imdertyDocumentTypeSchema.nullable(),
  document_number: z.string().nullable(),
  address: z.string().nullable(),
  barrio: barrioRefSchema.nullable(),
  other_municipality: z.boolean(),
  school: z.string().nullable(),
  grade: imdertyGradeSchema.nullable(),
  eps: z.string().nullable(),
  phone: z.string().nullable(),
  guardians: z.array(imdertyGuardianSchema),
  effective_phone_source: z
    .enum(["athlete", "primary_guardian", "first_guardian", "none"])
    .nullable(),
  sensitive: z.object({ authorization: sensitiveAuthorizationSchema.nullable() }),
});
export type ImdertyProfile = z.infer<typeof imdertyProfileSchema>;

export const imdertyProfileUpdateSchema = z.object({
  first_surname: z.string().trim().min(1).nullable().optional(),
  second_surname: z.string().trim().nullable().optional(),
  confirm_surname_split: z.boolean().default(false),
  document_type: imdertyDocumentTypeSchema.nullable().optional(),
  document_number: z.string().trim().nullable().optional(),
  address: z.string().trim().nullable().optional(),
  barrio_id: z.number().int().positive().nullable().optional(),
  other_municipality: z.boolean().optional(),
  school: z.string().trim().nullable().optional(),
  grade: imdertyGradeSchema.nullable().optional(),
  eps: z.string().trim().nullable().optional(),
  phone: z.string().trim().nullable().optional(),
});
export type ImdertyProfileUpdateValues = z.infer<typeof imdertyProfileUpdateSchema>;

export const imdertyProfileUpdateResponseSchema = z.object({
  profile: imdertyProfileSchema,
  warnings: z.array(z.string()).default([]),
});
export type ImdertyProfileUpdateResponse = z.infer<typeof imdertyProfileUpdateResponseSchema>;

export const primaryContactUpdateSchema = z.object({
  guardian_user_id: z.number().int().positive().nullable(),
});
export type PrimaryContactUpdateValues = z.infer<typeof primaryContactUpdateSchema>;

export const primaryContactResponseSchema = z.object({
  guardians: z.array(imdertyGuardianSchema),
});
export type PrimaryContactResponse = z.infer<typeof primaryContactResponseSchema>;

// ---------------------------------------------------------------------------
// Sensitive data
// ---------------------------------------------------------------------------

export const sensitiveAuthorizationCreateSchema = z.object({
  guardian_user_id: z.number().int().positive(),
  authorized_on: z.string().min(1, "Selecciona la fecha de autorización"),
});
export type SensitiveAuthorizationCreateValues = z.infer<typeof sensitiveAuthorizationCreateSchema>;

export const sensitiveDataSchema = z.object({
  ethnicity: imdertyEthnicitySchema,
  disability: imdertyDisabilitySchema,
  conflict_victim: imdertyYesNoSchema.nullable(),
});
export type SensitiveData = z.infer<typeof sensitiveDataSchema>;

export const sensitiveDataUpdateSchema = sensitiveDataSchema;
export type SensitiveDataUpdateValues = z.infer<typeof sensitiveDataUpdateSchema>;

// ---------------------------------------------------------------------------
// Club settings
// ---------------------------------------------------------------------------

export const clubImdertySettingsSchema = z.object({
  contractor_name: z.string().nullable(),
  venue: z.string().nullable(),
  training_days: z.string().nullable(),
  schedule: z.string().nullable(),
  programs: z.array(imdertyProgramSchema),
});
export type ClubImdertySettings = z.infer<typeof clubImdertySettingsSchema>;

export const clubImdertySettingsUpdateSchema = z.object({
  contractor_name: z.string().trim().nullable().optional(),
  venue: z.string().trim().nullable().optional(),
  training_days: z.string().trim().nullable().optional(),
  schedule: z.string().trim().nullable().optional(),
  programs: z.array(imdertyProgramSchema).default([]),
});
export type ClubImdertySettingsUpdateValues = z.infer<typeof clubImdertySettingsUpdateSchema>;

// ---------------------------------------------------------------------------
// Sheet: readiness + generation
// ---------------------------------------------------------------------------

/** "YYYY-MM" — el mismo formato usado por los parámetros `from`/`to` del contrato. */
export const imdertyMonthSchema = z
  .string()
  .regex(/^\d{4}-(0[1-9]|1[0-2])$/, "Formato de mes inválido (AAAA-MM)");

export const readinessGapSchema = z.object({
  athlete_id: z.number().int().positive(),
  display_name: z.string(),
  codes: z.array(z.string()),
  activity_dates: z.array(z.string()),
});
export type ReadinessGap = z.infer<typeof readinessGapSchema>;

export const imdertyReadinessSchema = z.object({
  months: z.array(z.string()),
  month_in_progress: z.boolean(),
  months_without_activity: z.array(z.string()),
  athlete_count: z.number().int().nonnegative(),
  gaps: z.array(readinessGapSchema),
});
export type ImdertyReadiness = z.infer<typeof imdertyReadinessSchema>;

export const imdertySheetHeaderSchema = z.object({
  contractor_name: z.string().nullable().optional(),
  venue: z.string().nullable().optional(),
  training_days: z.string().nullable().optional(),
  schedule: z.string().nullable().optional(),
  programs: z.array(imdertyProgramSchema).optional(),
});
export type ImdertySheetHeaderValues = z.infer<typeof imdertySheetHeaderSchema>;

export const imdertySheetRequestSchema = z.object({
  from: imdertyMonthSchema,
  to: imdertyMonthSchema,
  header: imdertySheetHeaderSchema.nullable().optional(),
  save_header_as_default: z.boolean().default(false),
});
export type ImdertySheetRequestValues = z.infer<typeof imdertySheetRequestSchema>;
