/**
 * ImportsHistoryList — histórico de importaciones recientes.
 *
 * Tabla simple, paginación opcional (limit/offset), filtrado por status.
 * Diseño compacto que vive debajo del wizard.
 */
import { useState } from "react";
import { History } from "lucide-react";

import { useImportsHistory } from "@/hooks/ai/useRaceImports";
import { formatDateTimeCompact } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type {
  ImportListItem,
  ImportStatus,
} from "@/types/raceImports.types";

const STATUS_LABELS: Record<ImportStatus, string> = {
  pending: "Pendiente",
  committed: "Confirmado",
  failed: "Fallido",
};

const STATUS_CLASSES: Record<ImportStatus, string> = {
  pending: "bg-amber-100 text-amber-800",
  committed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

function StatusBadge({ status }: { status: ImportStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold",
        STATUS_CLASSES[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}


export function ImportsHistoryList() {
  const [statusFilter, setStatusFilter] = useState<ImportStatus | undefined>(
    undefined,
  );
  const query = useImportsHistory({ limit: 20, status: statusFilter });

  return (
    <section
      className="rounded-xl bg-white p-4 ring-1 ring-light-gray"
      data-testid="imports-history-list"
      aria-label="Histórico de importaciones"
    >
      <header className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-charcoal">
          <History size={16} aria-hidden="true" />
          Histórico de importaciones
        </h2>
        <select
          value={statusFilter ?? ""}
          onChange={(e) =>
            setStatusFilter(
              (e.target.value as ImportStatus) || undefined,
            )
          }
          className="rounded-lg bg-white px-2 py-1 text-xs text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          data-testid="history-status-filter"
          aria-label="Filtrar por estado"
        >
          <option value="">Todos los estados</option>
          <option value="committed">Confirmados</option>
          <option value="pending">Pendientes</option>
          <option value="failed">Fallidos</option>
        </select>
      </header>

      {query.isLoading && (
        <div className="space-y-2" data-testid="history-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-10 animate-pulse rounded-lg bg-light-gray"
            />
          ))}
        </div>
      )}

      {query.isError && (
        <p role="alert" className="text-sm text-red-600">
          No se pudo cargar el histórico.
        </p>
      )}

      {query.data && query.data.items.length === 0 && (
        <p
          className="text-center text-xs text-mid-gray"
          data-testid="history-empty"
        >
          Aún no hay importaciones.
        </p>
      )}

      {query.data && query.data.items.length > 0 && (
        <div
          className="overflow-x-auto"
          data-testid="history-table-wrapper"
        >
          <table className="w-full text-sm">
            <thead className="text-xs text-mid-gray">
              <tr>
                <th className="px-2 py-2 text-left">Fecha</th>
                <th className="px-2 py-2 text-left">Archivo</th>
                <th className="px-2 py-2 text-left">Estado</th>
                <th className="px-2 py-2 text-right">Resultados</th>
                <th className="px-2 py-2 text-left">Por</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((item: ImportListItem) => (
                <tr
                  key={item.id}
                  className="border-t border-light-gray"
                  data-testid={`history-row-${item.id}`}
                >
                  <td className="px-2 py-2 text-xs text-mid-gray">
                    {formatDateTimeCompact(item.created_at)}
                  </td>
                  <td className="px-2 py-2 text-charcoal">
                    <span className="block truncate" title={item.original_filename}>
                      {item.original_filename}
                    </span>
                    <span className="text-[10px] uppercase text-mid-gray">
                      {item.kind}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-2 py-2 text-right font-mono text-xs text-charcoal">
                    {item.n_results}
                  </td>
                  <td className="px-2 py-2 text-xs text-mid-gray">
                    {item.uploaded_by.full_name}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data.total > query.data.items.length && (
            <p className="mt-2 text-center text-[10px] text-mid-gray">
              Mostrando {query.data.items.length} de {query.data.total}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
