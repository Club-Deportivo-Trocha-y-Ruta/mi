/**
 * Cliente API del informe de actividad por entrenador (feature 041 —
 * gobernanza multi-coach, US7). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §1.
 *
 * Auth: bearer JWT vía interceptor de `@/api/client`. El backend enforza
 * `can_view_audit` (admin: cualquier club; coach: solo el suyo; padre y
 * atleta: `403`) — superficie interna de gestión, nunca se llama desde
 * `routes/parents/`.
 *
 * `coachActivityOutSchema.parse` valida la forma real de la respuesta; ver
 * su docstring para el margen de tolerancia en los contadores.
 */
import { apiClient } from "@/api/client";
import { coachActivityOutSchema } from "@/schemas/coachActivity.schema";
import type {
  CoachActivityOut,
  CoachActivityParams,
} from "@/types/coachActivity.types";

/** GET /api/clubs/{club_id}/coach-activity */
export async function getCoachActivity(
  clubId: number,
  params: CoachActivityParams,
  options?: { signal?: AbortSignal },
): Promise<CoachActivityOut> {
  const response = await apiClient.get<unknown>(
    `/api/clubs/${clubId}/coach-activity`,
    {
      params: {
        from: params.from,
        to: params.to,
        coach_user_id: params.coach_user_id,
      },
      signal: options?.signal,
    },
  );
  return coachActivityOutSchema.parse(response.data);
}
