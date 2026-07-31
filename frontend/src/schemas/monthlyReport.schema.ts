import { z } from "zod";

const currentYear = new Date().getFullYear();
const currentMonth = new Date().getMonth() + 1;

export const monthlyReportCreateSchema = z
  .object({
    year: z
      .number()
      .int()
      .min(2024, "El año mínimo es 2024")
      .max(currentYear, `El año máximo es ${currentYear}`),
    month: z
      .number()
      .int()
      .min(1, "Mes inválido")
      .max(12, "Mes inválido"),
    coach_observations: z
      .string()
      .max(2000, "Máximo 2000 caracteres")
      .optional(),
    force_regenerate: z.boolean(),
  })
  .refine(
    (data) => {
      if (data.year < currentYear) return true;
      // TEMPORAL (revertir tras generar el informe de julio 2026 on-demand):
      // relaja a "<=" en paridad con el relax temporal del backend.
      return data.month <= currentMonth;
    },
    {
      message:
        "Solo se puede generar el reporte de meses ya cerrados (mes anterior o antes)",
      path: ["month"],
    },
  );

export type MonthlyReportFormValues = z.infer<typeof monthlyReportCreateSchema>;

// ---------------------------------------------------------------------------
// Campos aditivos del Informe Técnico Mensual (feature 022) — todos opcionales
// para mantener compatibilidad con snapshots antiguos que no los incluyen.
// Espejo de los campos añadidos en `backend/app/schemas/training_session.py`
// (`SessionDetailItem`, `AthleteAttendanceStats`, `CompetitionResultItem`).
// ---------------------------------------------------------------------------

export const sessionDetailItemSchema = z.object({
  session_date: z.string(),
  start_time: z.string(),
  technical_focus: z.string(),
  location: z.string(),
  status: z.enum(["executed", "cancelled", "planned"]),
  present_count: z.number().int(),
  attendee_total: z.number().int(),
});

export type SessionDetailItemValues = z.infer<typeof sessionDetailItemSchema>;

// Campos aditivos de `AthleteAttendanceStats`: promedios de rúbrica por
// atleta. `undefined`/`null` → el consumidor debe renderizar
// "Pendiente — regenerar informe".
export const athleteAttendanceStatsAdditiveSchema = z.object({
  avg_rubric_effort: z.number().nullable().optional(),
  avg_rubric_attitude: z.number().nullable().optional(),
  avg_rubric_technique: z.number().nullable().optional(),
});

// Campos aditivos de `CompetitionResultItem`: identidad estable del evento
// y clasificación de la carrera (copa vs. campeonato) para saber si el
// resultado suma puntos al ranking.
export const competitionResultAdditiveSchema = z.object({
  event_id: z.number().int().optional().default(0),
  series_kind: z.string().nullable().optional(),
  awards_points: z.boolean().optional().default(true),
});
