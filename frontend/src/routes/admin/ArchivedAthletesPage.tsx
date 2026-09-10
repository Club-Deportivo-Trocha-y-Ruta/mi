/**
 * ArchivedAthletesPage — vista admin "Atletas archivados" (feature 041 —
 * gobernanza multi-coach). Ruta `/admin/atletas-archivados`, solo admin.
 * Contrato: specs/041-multi-coach-governance/contracts/athlete-archive.md §11.
 *
 * Tabla server-side filtrada (sin `@tanstack/react-table`, research.md R-28)
 * sobre `useArchivedAthletes`. El motivo se resuelve contra el catálogo
 * cerrado `athlete_archive` (`useAuditReasonCodes`) — nunca una segunda
 * copia hardcodeada de las etiquetas (contrato §3).
 */
import { useMemo, useState } from "react";
import { ArchiveRestore } from "lucide-react";

import { RestoreAthleteDialog } from "@/components/athletes/RestoreAthleteDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useArchivedAthletes } from "@/hooks/admin/useArchivedAthletes";
import { useRestoreAthlete } from "@/hooks/athletes/useRestoreAthlete";
import { useAuditReasonCodes } from "@/hooks/useAuditReasonCodes";
import { extractErrorDetail } from "@/lib/apiError";
import { formatDate } from "@/lib/datetime";
import type { AthleteOut } from "@/types/athlete.types";

export function ArchivedAthletesPage() {
  const archivedQuery = useArchivedAthletes();
  const reasonCodesQuery = useAuditReasonCodes("athlete_archive");
  const restoreMutation = useRestoreAthlete();

  const [restoreTarget, setRestoreTarget] = useState<AthleteOut | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const reasonLabelByCode = useMemo(() => {
    const entries = reasonCodesQuery.data?.items ?? [];
    return new Map(entries.map((entry) => [entry.code, entry.label]));
  }, [reasonCodesQuery.data]);

  const items = archivedQuery.items;

  function handleRestore(reasonCode: string) {
    if (!restoreTarget) return;
    setRestoreError(null);
    restoreMutation.mutate(
      { id: restoreTarget.id, reasonCode },
      {
        onSuccess: () => {
          setRestoreTarget(null);
        },
        onError: (err) => {
          setRestoreError(
            extractErrorDetail(err, "No se pudo restaurar el atleta. Intenta de nuevo."),
          );
        },
      },
    );
  }

  return (
    <section className="space-y-5" data-testid="archived-athletes-page">
      <PageHeader
        title="Atletas archivados"
        subtitle="Deportistas retirados del club. Su información se conserva y puede restaurarse."
      />

      {archivedQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4 shadow-card"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Cargando atletas archivados…</span>
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={idx} className="h-14 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {archivedQuery.isError && !archivedQuery.isLoading && (
        <ErrorState
          message="No se pudo cargar la lista de atletas archivados."
          onRetry={async () => {
            await archivedQuery.refetch();
          }}
          isColdStart={isColdStartError(archivedQuery.error)}
        />
      )}

      {!archivedQuery.isLoading && !archivedQuery.isError && items.length === 0 && (
        <EmptyState title="No hay atletas archivados." />
      )}

      {!archivedQuery.isLoading && !archivedQuery.isError && items.length > 0 && (
        <div className="rounded-xl bg-white shadow-card">
          <Table data-testid="archived-athletes-table">
            <TableHeader>
              <TableRow>
                <TableHead>Deportista</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead>Archivado por</TableHead>
                <TableHead>Fecha</TableHead>
                <TableHead className="text-right">Acción</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((athlete) => (
                <TableRow key={athlete.id} data-testid="archived-athlete-row">
                  <TableCell>
                    {athlete.first_name} {athlete.last_name}
                  </TableCell>
                  <TableCell>
                    {(athlete.deleted_reason_code &&
                      reasonLabelByCode.get(athlete.deleted_reason_code)) ??
                      athlete.deleted_reason_code ??
                      "—"}
                  </TableCell>
                  <TableCell>{athlete.deleted_by?.display_name ?? "—"}</TableCell>
                  <TableCell>
                    {athlete.deleted_at ? formatDate(athlete.deleted_at) : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="min-h-12"
                      data-testid="restore-athlete-button"
                      onClick={() => {
                        setRestoreError(null);
                        setRestoreTarget(athlete);
                      }}
                    >
                      <ArchiveRestore size={14} className="mr-1.5" aria-hidden="true" />
                      Restaurar
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <RestoreAthleteDialog
        open={restoreTarget !== null}
        athleteFullName={
          restoreTarget ? `${restoreTarget.first_name} ${restoreTarget.last_name}` : ""
        }
        isPending={restoreMutation.isPending}
        errorMessage={restoreError ?? undefined}
        onCancel={() => setRestoreTarget(null)}
        onConfirm={handleRestore}
      />
    </section>
  );
}
