/**
 * Cliente API del resumen de crecimiento (feature 040, US2).
 *
 * Auth: bearer JWT vía interceptor de `@/api/client`; el backend enforza
 * `verify_athlete_access` (admin: cualquiera; coach: atletas de sus clubes;
 * padre: solo atletas vinculados) — ver `contracts/growth-summary-api.md`.
 *
 * Privacidad: la respuesta no trae nombre/fecha de nacimiento/notas del
 * atleta; `growthSummarySchema.parse` descarta cualquier clave adicional no
 * declarada como defensa en profundidad.
 */
import { apiClient } from "@/api/client";
import { growthSummarySchema } from "@/schemas/growth.schemas";
import type { GrowthSummary } from "@/types/growth.types";

/** GET /api/athletes/{athleteId}/growth-summary */
export async function getGrowthSummary(athleteId: number): Promise<GrowthSummary> {
  const response = await apiClient.get<unknown>(
    `/api/athletes/${athleteId}/growth-summary`,
  );
  return growthSummarySchema.parse(response.data);
}
