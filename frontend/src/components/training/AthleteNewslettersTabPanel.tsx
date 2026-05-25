/**
 * AthleteNewslettersTabPanel — lista de boletines mensuales en el perfil del atleta.
 *
 * Se monta en AthleteDetailPage tab="newsletters" (solo coach/admin).
 * Mobile (<640px): cards apiladas. Desktop: tabla compacta.
 * Sort: año desc, mes desc. Paginación "Ver más" si >12.
 *
 * Path de destino: /training/athlete-newsletters/{athleteId}/{newsletterId}
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mail } from "lucide-react";

import { useAthleteNewsletters } from "@/api/athleteNewsletters";
import { cn } from "@/lib/utils";
import type { AthleteNewsletter, NewsletterStatus } from "@/types/athleteNewsletter.types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const PAGE_SIZE = 12;

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

interface StatusConfig {
  label: string;
  className: string;
}

function statusConfig(status: NewsletterStatus): StatusConfig {
  switch (status) {
    case "sent":
      return {
        label: "Enviado",
        className:
          "bg-blue-100 text-blue-700 border border-blue-300",
      };
    case "approved":
      return {
        label: "Aprobado",
        className:
          "bg-green-100 text-green-700 border border-green-300",
      };
    case "draft":
      return {
        label: "Borrador",
        className:
          "bg-gray-100 text-gray-600 border border-gray-300",
      };
    case "failed":
      return {
        label: "Falló",
        className:
          "bg-red-100 text-red-700 border border-red-300",
      };
  }
}

function StatusChip({ status }: { status: NewsletterStatus }) {
  const { label, className } = statusConfig(status);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        className,
      )}
    >
      {label}
    </span>
  );
}

function monthLabel(month: number): string {
  return MONTH_NAMES[(month ?? 1) - 1] ?? String(month);
}

function sortNewsletters(list: AthleteNewsletter[]): AthleteNewsletter[] {
  return [...list].sort((a, b) => {
    if (b.year !== a.year) return b.year - a.year;
    return b.month - a.month;
  });
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

interface EmptyStateProps {
  athleteId: number;
}

function EmptyState({ athleteId }: EmptyStateProps) {
  const navigate = useNavigate();

  return (
    <div
      className="flex flex-col items-center gap-4 rounded-xl bg-white px-6 py-12 text-center"
      style={{ boxShadow: cardShadow }}
      data-testid="newsletters-empty-state"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-light-gray">
        <Mail className="h-6 w-6 text-mid-gray" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-charcoal">
          Aun no hay boletines para este atleta.
        </p>
        <p className="text-xs text-mid-gray">
          Genera el primer boletin mensual desde el dashboard.
        </p>
      </div>
      <div className="flex flex-col items-center gap-2 sm:flex-row">
        <button
          type="button"
          onClick={() =>
            navigate(`/training/athlete-newsletters?generate=${athleteId}`)
          }
          className="min-h-[44px] rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          data-testid="generate-newsletter-cta"
        >
          Generar boletin de este mes
        </button>
        <Link
          to="/training/athlete-newsletters"
          className="min-h-[44px] flex items-center rounded-lg px-4 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          data-testid="dashboard-newsletters-link"
        >
          Ir al dashboard de boletines
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Desktop table row
// ---------------------------------------------------------------------------

function TableRow({ newsletter, athleteId }: { newsletter: AthleteNewsletter; athleteId: number }) {
  return (
    <tr
      className="border-t border-gray-100 transition-colors hover:bg-gray-50"
      data-testid={`newsletter-row-${newsletter.id}`}
    >
      <td className="py-3 pl-5 pr-4 text-sm font-medium text-charcoal">
        {monthLabel(newsletter.month)} {newsletter.year}
      </td>
      <td className="px-4 py-3">
        <StatusChip status={newsletter.status} />
      </td>
      <td className="py-3 pl-4 pr-5 text-right">
        <Link
          to={`/training/athlete-newsletters/${athleteId}/${newsletter.id}`}
          className="min-h-[44px] inline-flex items-center text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          aria-label={`Ver detalle del boletin de ${monthLabel(newsletter.month)} ${newsletter.year}`}
          data-testid={`newsletter-detail-link-${newsletter.id}`}
        >
          Ver detalle →
        </Link>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Mobile card
// ---------------------------------------------------------------------------

function MobileCard({ newsletter, athleteId }: { newsletter: AthleteNewsletter; athleteId: number }) {
  return (
    <div
      className="rounded-xl bg-white p-4"
      style={{ boxShadow: cardShadow }}
      data-testid={`newsletter-card-${newsletter.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-charcoal">
            {monthLabel(newsletter.month)} {newsletter.year}
          </p>
          <StatusChip status={newsletter.status} />
        </div>
        <Link
          to={`/training/athlete-newsletters/${athleteId}/${newsletter.id}`}
          className="min-h-[44px] inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          aria-label={`Ver detalle del boletin de ${monthLabel(newsletter.month)} ${newsletter.year}`}
          data-testid={`newsletter-mobile-link-${newsletter.id}`}
        >
          Ver detalle →
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export interface AthleteNewslettersTabPanelProps {
  athleteId: number;
}

export function AthleteNewslettersTabPanel({ athleteId }: AthleteNewslettersTabPanelProps) {
  const [page, setPage] = useState(1);
  const query = useAthleteNewsletters(athleteId);

  if (query.isLoading) {
    return (
      <div className="space-y-3" data-testid="newsletters-skeleton">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-14 animate-pulse rounded-xl bg-light-gray" />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <div
        className="rounded-xl bg-white p-6 text-center"
        style={{ boxShadow: cardShadow }}
        data-testid="newsletters-error"
      >
        <p className="text-sm text-red-600">Error al cargar los boletines. Intenta de nuevo.</p>
      </div>
    );
  }

  const sorted = sortNewsletters(query.data ?? []);
  const visible = sorted.slice(0, page * PAGE_SIZE);
  const hasMore = sorted.length > visible.length;

  if (sorted.length === 0) {
    return <EmptyState athleteId={athleteId} />;
  }

  return (
    <div className="space-y-3" data-testid="newsletters-tab-panel">
      {/* Desktop table */}
      <div
        className="hidden sm:block overflow-hidden rounded-xl bg-white"
        style={{ boxShadow: cardShadow }}
      >
        <table className="w-full" aria-label="Boletines mensuales del atleta">
          <thead>
            <tr className="bg-gray-50">
              <th
                scope="col"
                className="py-3 pl-5 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-mid-gray"
              >
                Mes / Año
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-mid-gray"
              >
                Estado
              </th>
              <th
                scope="col"
                className="py-3 pl-4 pr-5 text-right text-xs font-semibold uppercase tracking-wide text-mid-gray"
              >
                Accion
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((n) => (
              <TableRow key={n.id} newsletter={n} athleteId={athleteId} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="flex flex-col gap-3 sm:hidden">
        {visible.map((n) => (
          <MobileCard key={n.id} newsletter={n} athleteId={athleteId} />
        ))}
      </div>

      {/* Ver más */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            className="min-h-[44px] rounded-lg px-5 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            data-testid="ver-mas-btn"
          >
            Ver más
          </button>
        </div>
      )}
    </div>
  );
}
