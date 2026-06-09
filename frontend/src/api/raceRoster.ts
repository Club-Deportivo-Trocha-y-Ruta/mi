/**
 * API client del módulo race roster (convocatoria).
 *
 * Auth: JWT via interceptor en apiClient.
 *
 * Endpoints cubiertos:
 *   - GET    /api/race-analysis/race-events/{id}/roster         → getRaceRoster
 *   - POST   /api/race-analysis/race-events/{id}/roster         → createRosterEntry
 *   - PATCH  /api/race-analysis/race-events/{id}/roster/{eid}   → updateRosterEntry
 *   - DELETE /api/race-analysis/race-events/{id}/roster/{eid}   → deleteRosterEntry
 *
 * Errores documentados:
 *   - POST 409 → atleta ya en el roster de esta válida
 *   - POST 422 → athlete_id no pertenece al club
 *   - PATCH/DELETE 404 → entrada no encontrada
 */
import { apiClient } from "@/api/client";
import type {
  RaceRosterResponse,
  RosterEntry,
  RosterEntryCreate,
  RosterEntryUpdate,
} from "@/types/raceRoster.types";

const BASE = "/api/race-analysis/race-events";

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * GET /api/race-analysis/race-events/{raceEventId}/roster
 *
 * Retorna el roster completo con los campos de reconciliación.
 * Para padres el backend filtra a solo el hijo propio.
 */
export async function getRaceRoster(
  raceEventId: number,
  options?: { signal?: AbortSignal },
): Promise<RaceRosterResponse> {
  const response = await apiClient.get<RaceRosterResponse>(
    `${BASE}/${raceEventId}/roster`,
    { signal: options?.signal },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

/**
 * POST /api/race-analysis/race-events/{raceEventId}/roster
 *
 * Agrega un atleta del club a la convocatoria.
 * RBAC: coach + admin.
 *
 * 409 si el atleta ya está en el roster.
 * 422 si el athlete_id no pertenece al club.
 */
export async function createRosterEntry(
  raceEventId: number,
  body: RosterEntryCreate,
  options?: { signal?: AbortSignal },
): Promise<RosterEntry> {
  const response = await apiClient.post<RosterEntry>(
    `${BASE}/${raceEventId}/roster`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * PATCH /api/race-analysis/race-events/{raceEventId}/roster/{entryId}
 *
 * Actualiza el estado o la nota de una entrada del roster.
 * RBAC: coach + admin.
 *
 * 404 si la entrada no existe.
 */
export async function updateRosterEntry(
  raceEventId: number,
  entryId: number,
  body: RosterEntryUpdate,
  options?: { signal?: AbortSignal },
): Promise<RosterEntry> {
  const response = await apiClient.patch<RosterEntry>(
    `${BASE}/${raceEventId}/roster/${entryId}`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * DELETE /api/race-analysis/race-events/{raceEventId}/roster/{entryId}
 *
 * Elimina una entrada del roster. Retorna 204 sin body.
 * RBAC: coach + admin.
 *
 * 404 si la entrada no existe.
 */
export async function deleteRosterEntry(
  raceEventId: number,
  entryId: number,
  options?: { signal?: AbortSignal },
): Promise<void> {
  await apiClient.delete(`${BASE}/${raceEventId}/roster/${entryId}`, {
    signal: options?.signal,
  });
}
