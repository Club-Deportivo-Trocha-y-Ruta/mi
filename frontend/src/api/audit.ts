/**
 * API client del historial de auditoría (feature 041 — gobernanza
 * multi-coach). Contrato:
 * specs/041-multi-coach-governance/contracts/audit-log-api.md §2, §3, §14.
 *
 * Auth: JWT vía interceptor de `apiClient`. Cobertura: admin + coach del
 * club/atleta correspondiente.
 */
import { apiClient } from "@/api/client";
import type {
  AuditListOut,
  AuditLogFilters,
  AuditReasonCodeListOut,
  AuditReasonGroup,
} from "@/types/audit.types";

/** GET /api/clubs/{club_id}/audit-log */
export async function getClubAuditLog(
  clubId: number,
  filters: AuditLogFilters = {},
  options?: { signal?: AbortSignal },
): Promise<AuditListOut> {
  const response = await apiClient.get<AuditListOut>(
    `/api/clubs/${clubId}/audit-log`,
    {
      params: {
        entity_type: filters.entity_type,
        action: filters.action,
        actor_user_id: filters.actor_user_id,
        athlete_id: filters.athlete_id,
        request_id: filters.request_id,
        from: filters.from,
        to: filters.to,
        limit: filters.limit,
        offset: filters.offset,
      },
      signal: options?.signal,
    },
  );
  return response.data;
}

/** GET /api/athletes/{athlete_id}/audit-log */
export async function getAthleteAuditLog(
  athleteId: number,
  filters: Omit<AuditLogFilters, "athlete_id"> = {},
  options?: { signal?: AbortSignal },
): Promise<AuditListOut> {
  const response = await apiClient.get<AuditListOut>(
    `/api/athletes/${athleteId}/audit-log`,
    {
      params: {
        entity_type: filters.entity_type,
        action: filters.action,
        actor_user_id: filters.actor_user_id,
        request_id: filters.request_id,
        from: filters.from,
        to: filters.to,
        limit: filters.limit,
        offset: filters.offset,
      },
      signal: options?.signal,
    },
  );
  return response.data;
}

/** GET /api/audit/reason-codes — catálogo cerrado compartido (§14). */
export async function getAuditReasonCodes(
  group?: AuditReasonGroup,
  options?: { signal?: AbortSignal },
): Promise<AuditReasonCodeListOut> {
  const response = await apiClient.get<AuditReasonCodeListOut>(
    "/api/audit/reason-codes",
    {
      params: group ? { group } : undefined,
      signal: options?.signal,
    },
  );
  return response.data;
}
