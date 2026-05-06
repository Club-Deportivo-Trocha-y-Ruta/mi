import { z } from "zod";

import { MaturationStatus } from "@/types/enums";

/** Schema de validación de la respuesta del backend.
 *
 * Defensa en profundidad: si el backend filtrara accidentalmente PII
 * (first_name, last_name, birth_date…) Zod las descarta porque no están
 * declaradas. Equivale a una allowlist en cliente.
 */
export const phvExplanationResponseSchema = z
  .object({
    text: z.string().min(1),
    model: z.string(),
    provider: z.string(),
    generated_at: z.string(),
    age_group: z.enum(["10-12", "13-15", "16+"]),
    maturation_status: z.union([
      z.nativeEnum(MaturationStatus),
      z.literal(""),
    ]),
  })
  .strip();

export const aiHealthResponseSchema = z
  .object({
    enabled: z.boolean(),
    provider: z.string(),
    model: z.string(),
  })
  .strip();

export type PHVExplanationResponseValidated = z.infer<
  typeof phvExplanationResponseSchema
>;
