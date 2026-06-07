import { z } from "zod";

// Regla única compartida cliente↔servidor. El backend valida exactamente este
// patrón (https://www.strava.com/activities/<id>); mantenemos el cliente igual
// para evitar "válido en cliente, 422 en servidor".
export const STRAVA_ACTIVITY_RE = /^https:\/\/www\.strava\.com\/activities\/\d+$/;

export const SESSION_KIND_OPTIONS = [
  { value: "entrenamiento", label: "Entrenamiento" },
  { value: "actividad_conjunta", label: "Actividad conjunta" },
  { value: "salida", label: "Salida" },
  { value: "otro", label: "Otro" },
] as const;

export const trainingSessionCreateSchema = z.object({
  scheduled_date: z.string().min(1, "La fecha es requerida"),
  scheduled_start_time: z
    .string()
    .regex(/^\d{2}:\d{2}$/, "La hora debe estar en formato HH:MM"),
  duration_min: z
    .number()
    .int()
    .min(15, "Mínimo 15 minutos")
    .max(240, "Máximo 240 minutos"),
  location: z
    .string()
    .min(1, "El lugar es requerido")
    .max(200, "Máximo 200 caracteres"),
  technical_focus: z
    .string()
    .min(1, "El foco técnico es requerido")
    .max(200, "Máximo 200 caracteres"),
  description: z
    .string()
    .min(1, "La descripción es requerida")
    .max(2000, "Máximo 2000 caracteres"),
  session_kind: z
    .enum(["entrenamiento", "actividad_conjunta", "salida", "otro"])
    .default("entrenamiento"),
  objectives: z
    .string()
    .max(1000, "Máximo 1000 caracteres")
    .optional()
    .or(z.literal("")),
  route_text: z
    .string()
    .max(500, "Máximo 500 caracteres")
    .optional()
    .or(z.literal("")),
  strava_url: z
    .string()
    .optional()
    .refine((v) => !v || STRAVA_ACTIVITY_RE.test(v), "URL de Strava no válida"),
  coach_notes: z
    .string()
    .max(2000, "Máximo 2000 caracteres")
    .optional()
    .or(z.literal("")),
  convocados_athlete_ids: z
    .array(z.number())
    .min(1, "Debes convocar al menos un atleta"),
});

// Campos validados por paso del asistente. Se usan con RHF `trigger(fields)`
// para bloquear "Siguiente" hasta que el paso actual sea válido.
export const STEP_GENERAL_FIELDS = [
  "scheduled_date",
  "scheduled_start_time",
  "duration_min",
  "location",
  "technical_focus",
  "description",
  "session_kind",
  "objectives",
] as const;

export const STEP_ATHLETES_FIELDS = ["convocados_athlete_ids"] as const;

export const STEP_ROUTE_NOTES_FIELDS = [
  "route_text",
  "strava_url",
  "coach_notes",
] as const;

// Usamos z.input para que session_kind sea optional en el form (el schema
// tiene .default("entrenamiento") que hace el output non-optional, pero
// el form necesita poder inicializar el campo con undefined).
export type TrainingSessionFormValues = z.input<typeof trainingSessionCreateSchema>;
