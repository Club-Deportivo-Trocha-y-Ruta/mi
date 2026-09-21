/**
 * Schema Zod del módulo race-identity (feature 044, US4).
 *
 * Cubre el único body de escritura de texto libre en la revisión de
 * identidad — la decisión sobre un candidato
 * (`POST /candidates/{id}/decide`). Catálogo cerrado a propósito (dos
 * respuestas posibles, sin texto libre): un acta de menores no debe admitir
 * un campo donde alguien pueda escribir un nombre.
 *
 * Contrato: specs/044-race-history-backfill/contracts/identity-review-api.md
 */
import { z } from "zod";

export const IDENTITY_DECISION_ANSWERS = [
  "same_person",
  "different_people",
] as const;

export const identityDecideSchema = z.object({
  answer: z.enum(IDENTITY_DECISION_ANSWERS, {
    message: "Selecciona si es la misma persona o personas distintas.",
  }),
});

export type IdentityDecideFormValues = z.infer<typeof identityDecideSchema>;
