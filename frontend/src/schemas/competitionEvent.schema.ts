/**
 * Schema Zod + inferencia TypeScript para el formulario de
 * creación/edición de una competencia (race_event).
 *
 * Spec 014 — Cup vs Championship:
 *   - Eliminado COPA_VALLE_SERIES hardcode (el picker es ahora dinámico).
 *   - Eliminada la opción 99=CD de VALIDA_OPTIONS (campeonatos son una serie
 *     distinta, no un número especial de válida).
 *   - El schema es ahora "type-aware":
 *       · Para series tipo copa (`kind=cup`), `sequence_number` es requerido (1–98).
 *       · Para series tipo campeonato (`kind=championship`), `sequence_number`
 *         es ignorado — el backend lo fuerza a 1 y no lo muestra en UI.
 *   - `is_championship` eliminado del schema de formulario; se deriva del
 *     `kind` de la serie seleccionada (decisión D2, spec 014).
 *
 * Cubre los campos admitidos por `RaceEventCreate` y `RaceEventUpdate`.
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Schema base (campos comunes a copa y campeonato)
// ---------------------------------------------------------------------------

const baseEventSchema = z.object({
  series_id: z.number().int().positive("Selecciona una serie"),
  name: z.string().min(1, "El nombre es obligatorio").max(200, "Máximo 200 caracteres"),
  event_date: z
    .string()
    .min(1, "La fecha es obligatoria")
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Formato de fecha inválido"),
  location: z.string().max(150, "Máximo 150 caracteres").nullable().optional(),
  status: z.enum(["scheduled", "completed", "cancelled"]),
});

// ---------------------------------------------------------------------------
// Schema copa: sequence_number requerido (1–98)
// ---------------------------------------------------------------------------

export const cupEventSchema = baseEventSchema.extend({
  series_kind: z.literal("cup"),
  sequence_number: z
    .number({ error: "El número de válida es obligatorio" })
    .int()
    .min(1, "Mínimo 1")
    .max(98, "Máximo 98"),
});

// ---------------------------------------------------------------------------
// Schema campeonato: sequence_number omitido (backend fuerza 1)
// ---------------------------------------------------------------------------

export const championshipEventSchema = baseEventSchema.extend({
  series_kind: z.literal("championship"),
  // sequence_number es ignorado para campeonatos; incluido como opcional
  // solo para que el tipo discriminado sea manejable en el formulario.
  sequence_number: z.number().int().optional(),
});

// ---------------------------------------------------------------------------
// Schema discriminado completo
// ---------------------------------------------------------------------------

export const competitionEventSchema = z.discriminatedUnion("series_kind", [
  cupEventSchema,
  championshipEventSchema,
]);

export type CompetitionEventFormValues = z.infer<typeof competitionEventSchema>;

// ---------------------------------------------------------------------------
// Opciones de número de válida para el select del formulario (solo copa)
// ---------------------------------------------------------------------------

/** Opciones de válida para series tipo copa. No incluye 99=CD (legacy). */
export const VALIDA_OPTIONS = [
  { value: 1, label: "Válida 1" },
  { value: 2, label: "Válida 2" },
  { value: 3, label: "Válida 3" },
  { value: 4, label: "Válida 4" },
  { value: 5, label: "Válida 5" },
  { value: 6, label: "Válida 6" },
  { value: 7, label: "Válida 7" },
  { value: 8, label: "Válida 8" },
  { value: 9, label: "Válida 9" },
] as const;

// ---------------------------------------------------------------------------
// Opciones de estado (sin cambios)
// ---------------------------------------------------------------------------

export const STATUS_OPTIONS = [
  { value: "scheduled", label: "Planificada" },
  { value: "completed", label: "Completada" },
  { value: "cancelled", label: "Cancelada" },
] as const;
