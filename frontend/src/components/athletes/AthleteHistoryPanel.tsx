/**
 * AthleteHistoryPanel — sección "Historial" de la ficha de un atleta
 * (feature 041 — gobernanza multi-coach, FR-007, US7 AS6). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §8.1.
 *
 * Muestra 15 filas (`GET /athletes/{id}/audit-log` con `limit=15`) y un
 * botón "Ver más" que aumenta el límite en pasos de 15 — sin paginación de
 * servidor con offset, a diferencia de `ClubHistoryPage` (lista corta por
 * atleta, crece sola con cada "Ver más").
 *
 * Visibilidad: solo coach/admin, gateada por el host
 * (`AthleteDetailPage.tsx`, mismo patrón que el tab "Boletines"). Este
 * componente no vuelve a verificar el rol — devuelve `null` cuando
 * `role="parent"` como defensa adicional (defence in depth, igual que el
 * backend rechaza el endpoint a un padre).
 */
import { useState } from "react";
import { History } from "lucide-react";

import { AuditEntryRow } from "@/components/audit/AuditEntryRow";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { useAthleteAuditLog } from "@/hooks/governance/useAuditLog";

const PAGE_STEP = 15;

export interface AthleteHistoryPanelProps {
  athleteId: number;
  /** "parent" nunca debe renderizar el panel (defensa en profundidad). */
  role: "coach" | "admin" | "parent" | "athlete";
}

export function AthleteHistoryPanel({ athleteId, role }: AthleteHistoryPanelProps) {
  const [limit, setLimit] = useState(PAGE_STEP);

  const auditQuery = useAthleteAuditLog(athleteId, { limit, offset: 0 });

  if (role === "parent") return null;

  const items = auditQuery.data?.items ?? [];
  const total = auditQuery.data?.total ?? 0;
  const hasMore = items.length < total;

  return (
    <div className="space-y-3" data-testid="athlete-history-panel">
      {auditQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4 shadow-card"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Cargando historial…</span>
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={idx} className="h-14 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {auditQuery.isError && !auditQuery.isLoading && (
        <ErrorState
          message="No se pudo cargar el historial de este deportista."
          onRetry={async () => {
            await auditQuery.refetch();
          }}
          isColdStart={isColdStartError(auditQuery.error)}
        />
      )}

      {!auditQuery.isLoading && !auditQuery.isError && items.length === 0 && (
        <EmptyState
          icon={History}
          title="Todavía no hay cambios registrados para este deportista."
        />
      )}

      {!auditQuery.isLoading && !auditQuery.isError && items.length > 0 && (
        <>
          <div className="space-y-2">
            {items.map((entry) => (
              <AuditEntryRow key={entry.id} entry={entry} />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-h-[48px]"
                onClick={() => setLimit((prev) => prev + PAGE_STEP)}
              >
                Ver más
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
