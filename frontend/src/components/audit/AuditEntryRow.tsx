/**
 * AuditEntryRow — una fila del historial de auditoría (feature 041 —
 * gobernanza multi-coach). Contrato:
 * specs/041-multi-coach-governance/contracts/audit-log-api.md §7, §8, §12.
 *
 * Muestra `sentence_es` (frase en español ya compuesta por el backend, la
 * única fuente de la oración — nunca se recompone en el cliente) más la hora
 * relativa/formateada con `formatDateTime` (frontend/src/lib/datetime.ts).
 * "Ver detalle" despliega un `Collapsible` con los campos cambiados y el
 * diff antes/después ya filtrado por la allow-list del backend — el cliente
 * solo renderiza lo que llega, nunca decide qué mostrar.
 *
 * Privacidad (Ley 1581): el único nombre propio en la fila es el del actor
 * adulto (`actor_display_name`); el atleta viaja como `athlete_id`, nunca
 * como nombre.
 */
import { ChevronDown } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { formatDateTime } from "@/lib/datetime";
import type { AuditDiffScalar, AuditEntryOut } from "@/types/audit.types";

function formatDiffScalar(value: AuditDiffScalar): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  return String(value);
}

export interface AuditEntryRowProps {
  entry: AuditEntryOut;
}

export function AuditEntryRow({ entry }: AuditEntryRowProps) {
  const { detail } = entry;
  const hasDetail =
    detail.changed_fields.length > 0 ||
    (detail.diff !== null && Object.keys(detail.diff).length > 0);

  return (
    <div
      className="rounded-lg border border-border-gray bg-white p-3"
      data-testid="audit-entry-row"
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <p className="text-sm text-charcoal">{entry.sentence_es}</p>
        <time
          dateTime={entry.occurred_at}
          className="shrink-0 text-xs text-mid-gray"
        >
          {formatDateTime(entry.occurred_at)}
        </time>
      </div>

      {entry.reason_label && (
        <p className="mt-1 text-xs text-mid-gray">Motivo: {entry.reason_label}</p>
      )}

      {hasDetail && (
        <Collapsible className="mt-2">
          <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium text-link-blue transition-colors hover:opacity-80 [&[data-state=open]_svg]:rotate-180">
            Ver detalle
            <ChevronDown
              size={14}
              aria-hidden="true"
              className="shrink-0 transition-transform"
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2 space-y-1 rounded-md bg-light-gray p-2 text-xs text-charcoal">
              {detail.changed_field_labels.length > 0 && (
                <p>
                  <span className="font-medium">Campos cambiados: </span>
                  {detail.changed_field_labels.join(", ")}
                </p>
              )}
              {detail.diff && Object.keys(detail.diff).length > 0 && (
                <ul className="space-y-0.5">
                  {Object.entries(detail.diff).map(([field, change]) => (
                    <li key={field}>
                      <span className="font-medium">{field}: </span>
                      {formatDiffScalar(change.before)} → {formatDiffScalar(change.after)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
