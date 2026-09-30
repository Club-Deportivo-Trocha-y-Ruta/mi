/**
 * Schema Zod del formulario de captura antropométrica (feature 048).
 *
 * Mismos rangos que el backend (`AnthropometryCreate`, data-model.md):
 * peso 20–150, talla de pie 100–220, talla sentado (neta) 50–120,
 * envergadura 100–220 o null, fecha no futura, razón sentado/de pie en
 * [0.40, 0.65].
 *
 * `sitting_height_cm` es la lectura BRUTA sobre el banco; la talla neta
 * (bruta − `bench_height_cm`) es lo que se envía. `bench_height_cm` es solo
 * de formulario: nunca se envía.
 */

import { z } from "zod";

export const CAPTURE_RANGES = {
  weight_kg: { min: 20, max: 150 },
  standing_height_cm: { min: 100, max: 220 },
  sitting_height_cm: { min: 50, max: 120 },
  arm_span_cm: { min: 100, max: 220 },
} as const;

export const SITTING_RATIO_MIN = 0.4;
export const SITTING_RATIO_MAX = 0.65;

const REQUIRED = "Obligatorio";
const INVALID = "Ingresa un número válido";

function ranged(min: number, max: number, unit: string) {
  return z
    .number({ error: (i) => (i.input === undefined ? REQUIRED : INVALID) })
    .refine((v) => Number.isFinite(v), INVALID)
    .min(min, `Mín. ${min} ${unit}`)
    .max(max, `Máx. ${max} ${unit}`);
}

/** Fecha local de hoy en YYYY-MM-DD. */
export function todayISO(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Talla sentado neta = lectura bruta − altura del banco (redondeada a 0.1). */
export function netSittingHeight(gross: number, bench: number | null | undefined): number {
  return Math.round((gross - (bench ?? 0)) * 10) / 10;
}

export const anthropometryCaptureSchema = z
  .object({
    evaluation_date: z
      .string({ error: REQUIRED })
      .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha inválida")
      .refine((d) => d <= todayISO(), "No puede ser futura"),
    weight_kg: ranged(CAPTURE_RANGES.weight_kg.min, CAPTURE_RANGES.weight_kg.max, "kg"),
    standing_height_cm: ranged(
      CAPTURE_RANGES.standing_height_cm.min,
      CAPTURE_RANGES.standing_height_cm.max,
      "cm",
    ),
    /** Lectura bruta; el rango 50–120 aplica a la talla neta (ver superRefine). */
    sitting_height_cm: z
      .number({ error: (i) => (i.input === undefined ? REQUIRED : INVALID) })
      .refine((v) => Number.isFinite(v), INVALID),
    arm_span_cm: ranged(
      CAPTURE_RANGES.arm_span_cm.min,
      CAPTURE_RANGES.arm_span_cm.max,
      "cm",
    )
      .nullable()
      .optional(),
    bench_height_cm: z
      .number({ error: INVALID })
      .refine((v) => Number.isFinite(v), INVALID)
      .min(0, "No puede ser negativa")
      .nullable()
      .optional(),
    notes: z.string().max(2000, "Máx. 2000 caracteres").nullable().optional(),
  })
  .superRefine((v, ctx) => {
    const net = netSittingHeight(v.sitting_height_cm, v.bench_height_cm);
    if (net <= 0) {
      ctx.addIssue({
        code: "custom",
        path: ["sitting_height_cm"],
        message: "La talla sentado debe ser mayor que la altura del banco",
      });
      return;
    }
    const { min, max } = CAPTURE_RANGES.sitting_height_cm;
    if (net < min) {
      ctx.addIssue({ code: "custom", path: ["sitting_height_cm"], message: `Mín. ${min} cm` });
      return;
    }
    if (net > max) {
      ctx.addIssue({ code: "custom", path: ["sitting_height_cm"], message: `Máx. ${max} cm` });
      return;
    }
    if (v.standing_height_cm > 0) {
      const ratio = net / v.standing_height_cm;
      if (ratio < SITTING_RATIO_MIN || ratio > SITTING_RATIO_MAX) {
        ctx.addIssue({
          code: "custom",
          path: ["sitting_height_cm"],
          message: "La talla sentado no es coherente con la talla de pie",
        });
      }
    }
  });

export type AnthropometryCaptureValues = z.infer<typeof anthropometryCaptureSchema>;

/** Convierte los valores del formulario al cuerpo de la API (talla neta, sin banco). */
export function toAnthropometryPayload(v: AnthropometryCaptureValues) {
  return {
    evaluation_date: v.evaluation_date,
    weight_kg: v.weight_kg,
    standing_height_cm: v.standing_height_cm,
    sitting_height_cm: netSittingHeight(v.sitting_height_cm, v.bench_height_cm),
    arm_span_cm: v.arm_span_cm ?? null,
    notes: v.notes ?? null,
  };
}
