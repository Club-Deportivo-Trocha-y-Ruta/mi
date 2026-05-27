/**
 * Schema Zod + inferencia TypeScript para el formulario de
 * creación/edición de una competencia (race_event).
 *
 * Cubre los campos admitidos por `RaceEventCreate` y `RaceEventUpdate`.
 *
 * NOTA: `sequence_number=99` con `is_championship=true` representa el
 * Campeonato Departamental (CD) en el formulario.
 */
import { z } from "zod";

export const competitionEventSchema = z.object({
  series_id: z.number().int().positive(),
  sequence_number: z.number().int().min(1).max(99),
  name: z.string().min(1, "El nombre es obligatorio").max(200, "Máximo 200 caracteres"),
  event_date: z
    .string()
    .min(1, "La fecha es obligatoria")
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Formato de fecha inválido"),
  location: z.string().max(150, "Máximo 150 caracteres").nullable().optional(),
  is_championship: z.boolean(),
  status: z.enum(["scheduled", "completed", "cancelled"]),
});

export type CompetitionEventFormValues = z.infer<typeof competitionEventSchema>;

// Opciones de número de válida para el select del formulario
export const VALIDA_OPTIONS = [
  { value: 1, label: "Válida 1" },
  { value: 2, label: "Válida 2" },
  { value: 3, label: "Válida 3" },
  { value: 4, label: "Válida 4" },
  { value: 5, label: "Válida 5" },
  { value: 6, label: "Válida 6" },
  { value: 7, label: "Válida 7" },
  { value: 99, label: "CD — Campeonato Departamental" },
] as const;

export const STATUS_OPTIONS = [
  { value: "scheduled", label: "Planificada" },
  { value: "completed", label: "Completada" },
  { value: "cancelled", label: "Cancelada" },
] as const;

/**
 * Serie hardcoded de Copa Valle.
 *
 * NOTA: El `id` de esta serie se asigna al crear la primera importación
 * (el backend crea la serie dinámicamente). En un entorno limpio el
 * primer registro suele ser id=1. Si hay desajuste, el backend retornará
 * 422 al crear la válida y el coach puede ajustar el ID manualmente.
 *
 * CF5+ debería añadir un endpoint GET /race-series/ para cargar el
 * id real dinámicamente.
 */
export const COPA_VALLE_SERIES = { id: 1, name: "Copa Valle de Ciclomontañismo" };
