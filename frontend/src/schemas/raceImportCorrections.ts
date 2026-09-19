/**
 * Schemas Zod del asistente de integridad de lectura (feature 044, US1).
 *
 * Cubren los dos diálogos del wizard de importación:
 *  - `RowCorrectionDialog`  → agregar/editar/eliminar una fila de una
 *    categoría parseada (`POST /imports/{parse_id}/corrections`).
 *  - `AcknowledgeGapDialog` → reconocer una categoría con completitud
 *    inconsistente, motivo de un catálogo CERRADO
 *    (`POST /imports/{parse_id}/acknowledge`).
 *
 * Contrato: specs/044-race-history-backfill/contracts/reading-integrity.md
 * (forma) y contracts/ui-history.md §2 (UI). Motivos y operaciones son
 * catálogos cerrados a propósito — texto libre sobre un acta de menores
 * invita a escribir nombres (mismo criterio que `staff.schema.ts` R-31).
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// RowCorrectionDialog — agregar / editar / eliminar una fila
// ---------------------------------------------------------------------------

export const ROW_CORRECTION_OPS = ["add", "edit", "remove"] as const;

export const rowCorrectionSchema = z
  .object({
    op: z.enum(ROW_CORRECTION_OPS, { message: "Selecciona una operación." }),
    ordinal: z
      .number({ message: "El puesto es obligatorio." })
      .int("El puesto debe ser un número entero.")
      .min(1, "El puesto debe ser mayor a 0."),
    bib: z.string().trim().max(20, "Máximo 20 caracteres.").optional().or(z.literal("")),
    name: z.string().trim().max(200, "Máximo 200 caracteres.").optional().or(z.literal("")),
    city: z.string().trim().max(120, "Máximo 120 caracteres.").optional().or(z.literal("")),
    club: z.string().trim().max(200, "Máximo 200 caracteres.").optional().or(z.literal("")),
    time_raw: z
      .string()
      .trim()
      .max(20, "Máximo 20 caracteres.")
      .optional()
      .or(z.literal("")),
    points: z
      .union([z.string(), z.number()])
      .optional()
      .refine(
        (v) => v === undefined || v === "" || (!isNaN(Number(v)) && Number(v) >= 0),
        { message: "Los puntos no pueden ser negativos." },
      ),
  })
  .superRefine((values, ctx) => {
    // El nombre solo es obligatorio para agregar/editar — una fila que se
    // elimina no necesita datos nuevos (research R-05, `apply_corrections`
    // ignora `row` en `remove`).
    if (values.op !== "remove" && (!values.name || values.name.trim().length === 0)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "El nombre es obligatorio.",
        path: ["name"],
      });
    }
  });

export type RowCorrectionFormValues = z.infer<typeof rowCorrectionSchema>;

// ---------------------------------------------------------------------------
// AcknowledgeGapDialog — reconocer una categoría inconsistente
// ---------------------------------------------------------------------------

export const ACKNOWLEDGE_REASON_CODES = [
  "source_duplicate_ordinal",
  "source_missing_ordinal",
  "source_disqualification_gap",
  "verified_against_source",
] as const;

export const acknowledgeGapSchema = z.object({
  reason: z.enum(ACKNOWLEDGE_REASON_CODES, {
    message: "Selecciona un motivo del catálogo.",
  }),
});

export type AcknowledgeGapFormValues = z.infer<typeof acknowledgeGapSchema>;
