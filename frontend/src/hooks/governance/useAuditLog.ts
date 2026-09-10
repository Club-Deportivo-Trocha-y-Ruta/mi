/**
 * Historial de auditoría — club y atleta (feature 041 — gobernanza
 * multi-coach). Consumido por la página de historial del club y el panel
 * "historial" de la ficha del atleta.
 *
 * `filters` entra completo en la queryKey (research R-28: convención de
 * listas filtradas) para que cada combinación de filtros cachee por
 * separado y `keepPreviousData` evite el parpadeo al paginar/filtrar.
 * Contrato: specs/041-multi-coach-governance/contracts/audit-log-api.md §12.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getAthleteAuditLog, getClubAuditLog } from "@/api/audit";
import type { AuditLogFilters } from "@/types/audit.types";

export const clubAuditLogQueryKey = (clubId: number, filters: AuditLogFilters = {}) =>
  ["audit", "club", clubId, filters] as const;

export const athleteAuditLogQueryKey = (
  athleteId: number,
  filters: Omit<AuditLogFilters, "athlete_id"> = {},
) => ["audit", "athlete", athleteId, filters] as const;

export function useClubAuditLog(clubId: number | null, filters: AuditLogFilters = {}) {
  return useQuery({
    queryKey: clubAuditLogQueryKey(clubId ?? -1, filters),
    queryFn: ({ signal }) => getClubAuditLog(clubId as number, filters, { signal }),
    enabled: clubId !== null && Number.isFinite(clubId),
    placeholderData: keepPreviousData,
  });
}

export function useAthleteAuditLog(
  athleteId: number | null,
  filters: Omit<AuditLogFilters, "athlete_id"> = {},
) {
  return useQuery({
    queryKey: athleteAuditLogQueryKey(athleteId ?? -1, filters),
    queryFn: ({ signal }) => getAthleteAuditLog(athleteId as number, filters, { signal }),
    enabled: athleteId !== null && Number.isFinite(athleteId),
    placeholderData: keepPreviousData,
  });
}
