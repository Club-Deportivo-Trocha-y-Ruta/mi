import { z } from "zod";

// Zod schemas del módulo race-course (feature 043). Mirror de las
// validaciones del backend en `backend/app/schemas/race_course.py` — ver
// `specs/043-race-course-profile/contracts/course-api.md`.

// ---------------------------------------------------------------------------
// Subida/reemplazo de variante (GPX)
// ---------------------------------------------------------------------------

export const variantUploadSchema = z.object({
  label: z
    .string()
    .trim()
    .min(1, "El nombre de la variante es requerido")
    .max(60, "Máximo 60 caracteres"),
  recorded_laps: z.coerce
    .number()
    .int()
    .min(1, "Mínimo 1 vuelta")
    .max(20, "Máximo 20 vueltas")
    .optional(),
  file: z
    .instanceof(File)
    .refine(
      (f) => f.name.toLowerCase().endsWith(".gpx"),
      "El archivo debe ser un GPX (.gpx).",
    ),
});

export type VariantUploadFormValues = z.infer<typeof variantUploadSchema>;

// ---------------------------------------------------------------------------
// Tabla de vueltas por categoría (setups)
// ---------------------------------------------------------------------------

export const setupRowSchema = z.object({
  category_id: z.number().int().positive(),
  laps: z.coerce
    .number()
    .int()
    .min(1, "Mínimo 1 vuelta")
    .max(20, "Máximo 20 vueltas"),
  variant_id: z.number().int().positive(),
});

export const setupsSchema = z.array(setupRowSchema);

export type SetupRowFormValues = z.infer<typeof setupRowSchema>;
export type SetupsFormValues = z.infer<typeof setupsSchema>;

// ---------------------------------------------------------------------------
// Descripción del circuito
// ---------------------------------------------------------------------------

export const descriptionSchema = z.object({
  terrain_type: z
    .enum(["sendero", "trocha", "mixto", "pista", "pavimento"])
    .nullable()
    .optional(),
  technical_difficulty: z.coerce
    .number()
    .int()
    .min(1)
    .max(5)
    .nullable()
    .optional(),
  key_sectors: z
    .array(
      z.enum([
        "subida_larga",
        "bajada_tecnica",
        "rock_garden",
        "singletrack",
        "plano_rapido",
        "paso_quebrada",
        "raices",
        "escalones",
      ]),
    )
    .max(8, "Máximo 8 sectores.")
    .optional(),
  course_notes: z
    .string()
    .max(1000, "Máximo 1000 caracteres.")
    .nullable()
    .optional(),
});

export type DescriptionFormValues = z.infer<typeof descriptionSchema>;
