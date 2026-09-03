/**
 * DeliveryPanel — estado de entrega/lectura por familia del boletín
 * (feature 038, T302, AC-6.2). Emails siempre enmascarados
 * (`j***@gmail.com`) — el backend ya los entrega así en `DeliveryRow`.
 *
 * El backend reenvía a nivel de boletín (todas las familias registradas a
 * la vez, `force_resend`) — no existe un endpoint para reenviar a una sola
 * familia. El botón "Reenviar" aparece en cada fila por paridad con el
 * mockup del plan, pero dispara siempre la misma acción; el texto de apoyo
 * lo aclara para no prometer un reenvío selectivo que el backend no ofrece.
 */
import { AlertTriangle, CheckCircle2, Eye, Mail, MailCheck, Send } from "lucide-react";

import type { DeliveryRow } from "@/types/athleteNewsletter.types";
import { formatDate, formatDateTime } from "@/lib/datetime";

export interface DeliveryPanelProps {
  delivery: DeliveryRow[];
  onResend: () => void;
  isResending?: boolean;
}

function DeliveryStatusLine({ row }: { row: DeliveryRow }) {
  if (row.bounced) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-danger">
        <AlertTriangle size={12} aria-hidden="true" /> Rebotado
      </p>
    );
  }
  return (
    <>
      <p className="flex items-center gap-1.5 text-xs text-mid-gray">
        <Send size={12} aria-hidden="true" /> Enviado {formatDate(row.sent_at)}
      </p>
      {row.delivered_at ? (
        <p className="flex items-center gap-1.5 text-xs text-mid-gray">
          <MailCheck size={12} aria-hidden="true" /> Correo entregado{" "}
          {formatDateTime(row.delivered_at)}
        </p>
      ) : null}
      {row.opened_at ? (
        <p className="flex items-center gap-1.5 text-xs text-mid-gray">
          <Eye size={12} aria-hidden="true" /> Abierto {formatDateTime(row.opened_at)}
        </p>
      ) : null}
      {row.web_read_at ? (
        <p className="flex items-center gap-1.5 text-xs text-success">
          <Eye size={12} aria-hidden="true" /> Leído en la web {formatDateTime(row.web_read_at)}
        </p>
      ) : row.has_account ? (
        <p className="flex items-center gap-1.5 text-xs text-mid-gray">
          <Eye size={12} aria-hidden="true" /> Sin leer
        </p>
      ) : (
        <p className="flex items-center gap-1.5 text-xs text-mid-gray">
          <Mail size={12} aria-hidden="true" /> Sin cuenta web
        </p>
      )}
    </>
  );
}

export function DeliveryPanel({ delivery, onResend, isResending = false }: DeliveryPanelProps) {
  if (delivery.length === 0) {
    return (
      <div className="rounded-xl bg-white px-4 py-3 shadow-card" data-testid="delivery-panel-empty">
        <h3 className="text-sm font-semibold text-charcoal">Entrega</h3>
        <p className="mt-1 text-xs text-mid-gray">
          Este boletín todavía no se ha enviado a ninguna familia.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white px-4 py-3 shadow-card" data-testid="delivery-panel">
      <h3 className="text-sm font-semibold text-charcoal">Entrega</h3>
      <ul className="mt-2 space-y-3">
        {delivery.map((row, index) => (
          <li
            key={row.parent_user_id ?? `${row.email_masked}-${index}`}
            className="flex items-start justify-between gap-3 rounded-lg px-3 py-2 shadow-ring"
            data-testid={`delivery-row-${row.parent_user_id ?? index}`}
          >
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1.5 truncate text-sm text-charcoal">
                <CheckCircle2 size={12} aria-hidden="true" className="shrink-0 text-mid-gray" />
                {row.email_masked}
              </p>
              <DeliveryStatusLine row={row} />
            </div>
            <button
              type="button"
              onClick={onResend}
              disabled={isResending}
              className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-charcoal shadow-ring transition-opacity hover:opacity-70 disabled:opacity-50"
              data-testid={`delivery-resend-${row.parent_user_id ?? index}`}
              aria-label={`Reenviar boletín a ${row.email_masked}`}
            >
              Reenviar
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-mid-gray">
        Reenviar repite el envío a todas las familias registradas de este boletín.
      </p>
    </div>
  );
}
