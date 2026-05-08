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
      // mismo año: el mes debe ser menor al actual, o si es el actual, solo si ya pasó el día 28
      if (data.month < currentMonth) return true;
      if (data.month === currentMonth) {
        return new Date().getDate() > 28;
      }
      return false;
    },
    {
      message:
        "Solo se puede generar el reporte de meses ya cerrados (mes anterior o antes)",
      path: ["month"],
    },
  );

export type MonthlyReportFormValues = z.infer<typeof monthlyReportCreateSchema>;
