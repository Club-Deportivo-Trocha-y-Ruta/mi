import { z } from "zod";

const STRAVA_URL_RE = /^https?:\/\/(www\.)?strava\.com\/activities\/\d+/;

export const trainingSessionCreateSchema = z.object({
  age_group: z.enum(["u12", "u15"]),
  scheduled_date: z
    .string()
    .min(1, "La fecha es requerida")
    .refine((val) => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return new Date(val) >= today;
    }, "La fecha no puede ser en el pasado"),
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
  route_text: z
    .string()
    .max(500, "Máximo 500 caracteres")
    .optional()
    .or(z.literal("")),
  strava_url: z
    .string()
    .regex(STRAVA_URL_RE, "URL de Strava no válida")
    .optional()
    .or(z.literal("")),
  convocados_athlete_ids: z
    .array(z.number())
    .min(1, "Debes convocar al menos un atleta"),
});

export type TrainingSessionFormValues = z.infer<typeof trainingSessionCreateSchema>;
