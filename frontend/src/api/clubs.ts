/**
 * API client de clubes. Hoy solo cubre el listado (feature 041 —
 * gobernanza multi-coach, US3), usado para poblar el selector de club de
 * "Nuevo entrenador" (contracts/staff-admin.md §7). Router:
 * `backend/app/routers/clubs.py:71-78` (`GET /api/clubs/`, autenticado,
 * sin filtros — cualquier rol lo consume; el club-scoping lo hace cada
 * router de escritura).
 */
import { apiClient } from "@/api/client";
import type { ClubOut } from "@/types/user.types";

/** GET /api/clubs/ */
export async function listClubs(
  options?: { signal?: AbortSignal },
): Promise<ClubOut[]> {
  const response = await apiClient.get<ClubOut[]>("/api/clubs/", {
    signal: options?.signal,
  });
  return response.data;
}
