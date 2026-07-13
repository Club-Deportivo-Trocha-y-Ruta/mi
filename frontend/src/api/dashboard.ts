/**
 * API client puro para el agregado de mission-control del coach (feature 031).
 *
 * Endpoint: GET /api/dashboard/coach-summary
 * Ver `specs/031-coach-home-mission-control/contracts/coach-summary-endpoint.md`.
 *
 * Privacy (FR-010): el payload es solo conteos y minutos por banda — jamás
 * ids/nombres de atletas ni contenido de sesiones.
 */
import { apiClient } from "@/api/client";
import type { CoachSummary } from "@/types/dashboard.types";

const BASE = "/api/dashboard/coach-summary";

export async function fetchCoachSummary(): Promise<CoachSummary> {
  const response = await apiClient.get<CoachSummary>(BASE);
  return response.data;
}
