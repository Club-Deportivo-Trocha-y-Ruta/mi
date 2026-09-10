/**
 * Catálogo cerrado de motivos de auditoría (feature 041 — gobernanza
 * multi-coach). Fuente única para todo picker "motivo" del feature: archivo
 * y restauración de atleta, cancelación de sesión/evento, desactivación y
 * reactivación de personal.
 *
 * Mismo patrón que `useRevisionReasons` (frontend/src/hooks/race/useRevisionReasons.ts):
 * catálogo cerrado, cambia solo con un deploy, así que una hora de
 * "stale" no cuesta nada y ahorra una petición por apertura de diálogo.
 * Contrato: specs/041-multi-coach-governance/contracts/audit-log-api.md §14.5.
 */
import { useQuery } from "@tanstack/react-query";

import { getAuditReasonCodes } from "@/api/audit";
import type { AuditReasonGroup } from "@/types/audit.types";

export const auditReasonCodesQueryKey = (group?: AuditReasonGroup) =>
  ["audit-reason-codes", group ?? null] as const;

export function useAuditReasonCodes(group?: AuditReasonGroup, enabled = true) {
  return useQuery({
    queryKey: auditReasonCodesQueryKey(group),
    queryFn: ({ signal }) => getAuditReasonCodes(group, { signal }),
    staleTime: 60 * 60_000,
    enabled,
  });
}
