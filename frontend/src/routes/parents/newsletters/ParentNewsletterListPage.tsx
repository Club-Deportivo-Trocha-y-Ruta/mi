/**
 * ParentNewsletterListPage — listado de bitácoras enviadas de un atleta,
 * portal de padres (feature 038, T303). Ruta `/my-athletes/:athleteId/bitacora`.
 *
 * Una tarjeta por bitácora `sent`, orden `(year, month)` desc (ya viene así
 * del backend, ver `useParentNewsletters`). Chip "Nueva" mientras
 * `read_at === null` — desaparece tras abrir el detalle (T204's
 * `useMarkNewsletterRead` invalida esta query en `onSuccess`).
 */
import { Link, useParams } from "react-router-dom";
import { BookOpen, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useParentNewsletters } from "@/hooks/parents/useParentNewsletters";

export function ParentNewsletterListPage() {
  const { athleteId: athleteIdParam } = useParams();
  const athleteId = Number(athleteIdParam);
  const validAthleteId = Number.isFinite(athleteId) ? athleteId : undefined;

  const newslettersQuery = useParentNewsletters(validAthleteId);

  if (newslettersQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-5 w-28 animate-pulse rounded bg-light-gray" />
        <div role="status" aria-busy="true" aria-label="Cargando bitácoras" className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      </section>
    );
  }

  if (newslettersQuery.isError) {
    return (
      <section className="space-y-4">
        <Link
          to={`/my-athletes/${validAthleteId ?? ""}`}
          className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
        >
          <span aria-hidden="true">←</span>
          <span>Volver</span>
        </Link>
        <div className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-sm text-mid-gray">No se pudieron cargar las bitácoras.</p>
        </div>
      </section>
    );
  }

  const newsletters = newslettersQuery.data ?? [];

  return (
    <section className="space-y-4">
      <Link
        to={`/my-athletes/${validAthleteId ?? ""}`}
        className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
      >
        <span aria-hidden="true">←</span>
        <span>Volver</span>
      </Link>

      <h1 className="font-display flex items-center gap-2 text-lg text-charcoal">
        <BookOpen size={18} aria-hidden="true" />
        Bitácora
      </h1>

      {newsletters.length === 0 ? (
        <div className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-sm text-mid-gray">
            Todavía no hay bitácoras enviadas para tu atleta.
          </p>
        </div>
      ) : (
        <ul className="space-y-3" data-testid="parent-newsletter-list">
          {newsletters.map((newsletter) => {
            const isUnread = newsletter.read_at === null;
            return (
              <li key={newsletter.id}>
                <Link
                  to={`/my-athletes/${validAthleteId}/bitacora/${newsletter.id}`}
                  className="flex items-center justify-between gap-3 rounded-xl bg-white p-4 shadow-card transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link-blue/50"
                  data-testid={`parent-newsletter-card-${newsletter.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                        {newsletter.period_label}
                      </p>
                      {isUnread && (
                        <Badge variant="default" data-testid={`parent-newsletter-new-${newsletter.id}`}>
                          Nueva
                        </Badge>
                      )}
                    </div>
                    <p className="mt-1 truncate text-sm font-semibold text-charcoal">
                      {newsletter.stage_title}
                    </p>
                  </div>
                  <ChevronRight size={16} className="shrink-0 text-mid-gray" aria-hidden="true" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
