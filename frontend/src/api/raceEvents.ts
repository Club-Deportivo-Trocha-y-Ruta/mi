/**
 * API client del módulo race-events — condiciones de carrera (F-COND).
 *
 * Endpoint: PATCH /api/race-analysis/race-events/{id}/conditions
 * Auth: JWT via interceptor en apiClient. Cobertura: coach + admin.
 *
 * No existe GET independiente de condiciones — el evento completo se
 * obtiene desde los endpoints de análisis existentes que retornan el
 * race_event embebido (ej. /runs/:id/result).
 */
import { apiClient } from "@/api/client";
import type {
  RaceEventConditions,
  RaceEventConditionsUpdate,
} from "@/types/raceEvents.types";

const BASE = "/api/race-analysis/race-events";

/**
 * PATCH /api/race-analysis/race-events/{raceEventId}/conditions
 *
 * Actualiza parcialmente las condiciones logísticas de un evento.
 * Solo los campos presentes en `body` se modifican (merge semántico).
 *
 * `temperature_c` se serializa a string en JSON si llega como number,
 * el backend lo recibe como Decimal y lo acepta en ambas formas.
 */
export async function updateRaceEventConditions(
  raceEventId: number,
  body: RaceEventConditionsUpdate,
  options?: { signal?: AbortSignal },
): Promise<RaceEventConditions> {
  const response = await apiClient.patch<RaceEventConditions>(
    `${BASE}/${raceEventId}/conditions`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}
