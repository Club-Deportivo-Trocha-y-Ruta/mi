/**
 * Schema Zod + inferencia TypeScript para el diálogo de edición del nombre
 * corto de una serie de competencias (`race_series.short_name`).
 *
 * Hotfix multicopa — identidad de válida (2026-09-16): las etiquetas de copa
 * usan `short_name` cuando existe (ej. "Let's GO" en vez de "Copa Let's Go
 * Interdepartamental XCO") en chips donde el espacio es limitado. Editable
 * por el coach desde `InfoTab` de la competencia.
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Schema del diálogo "Editar nombre corto"
// ---------------------------------------------------------------------------

/**
 * Sin `.transform()` a propósito — RHF's `useForm<T>` tipa los valores del
 * form con el tipo de ENTRADA del resolver, y un `.transform()` que cambia
 * de forma (`string | undefined` → `string | null`) rompe esa inferencia
 * (mismatch `Resolver<Input, ..., Output>` vs `Resolver<Output, ..., Output>`).
 * La normalización a `null` cuando el campo queda vacío vive en el submit
 * handler del diálogo, mismo patrón que `location: values.location || null`
 * en `CompetitionFormPage`.
 */
export const editSeriesShortNameSchema = z.object({
  short_name: z.string().max(40, "Máximo 40 caracteres").optional(),
});

export type EditSeriesShortNameFormValues = z.infer<
  typeof editSeriesShortNameSchema
>;
