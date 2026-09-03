/**
 * ParentNewsletterPage — detalle de una bitácora enviada, portal de padres
 * (feature 038, T303). Ruta `/my-athletes/:athleteId/bitacora/:newsletterId`.
 *
 * Renderiza `StageLogView mode="parent"` (T303 depende del componente
 * compartido de la misma oleada — ver nota de import más abajo) y dispara
 * `useMarkNewsletterRead` UNA sola vez por `newsletterId` en el primer
 * render exitoso (guardado además contra doble-disparo local con un `ref`,
 * encima del guard por `sessionStorage` que ya trae el propio hook —
 * data-model.md §6).
 */
import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
// NOTA DE DEPENDENCIA (T303): StageLogView se construye en paralelo en esta
// misma oleada (Wave 2/3, mode="parent"). Si el chunk aún no existe al
// correr los tests de este archivo, vitest fallará al resolver este import
// — se resuelve solo cuando el componente hermano quede commiteado.
import { StageLogView } from "@/components/newsletter/StageLogView";
import { useParentNewsletter } from "@/hooks/parents/useParentNewsletter";
import { useMarkNewsletterRead } from "@/hooks/parents/useMarkNewsletterRead";
import { getParentNewsletterPdfUrl } from "@/api/parentNewsletters";
import { triggerBlobDownload } from "@/lib/download";
import { useMutation } from "@tanstack/react-query";

export function ParentNewsletterPage() {
  const { athleteId: athleteIdParam, newsletterId: newsletterIdParam } = useParams();
  const athleteId = Number(athleteIdParam);
  const newsletterId = Number(newsletterIdParam);
  const validIds = Number.isFinite(athleteId) && Number.isFinite(newsletterId);

  const newsletterQuery = useParentNewsletter(
    validIds ? athleteId : undefined,
    validIds ? newsletterId : undefined,
  );
  const markReadMutation = useMarkNewsletterRead(athleteId, newsletterId);
  const pdfMutation = useMutation({
    mutationFn: () => getParentNewsletterPdfUrl(athleteId, newsletterId),
    onSuccess: (blob) => {
      triggerBlobDownload(
        blob,
        `bitacora-${newsletter?.year ?? ""}-${String(newsletter?.month ?? "").padStart(2, "0")}.pdf`,
      );
    },
  });

  // Guard local además del guard por sessionStorage del propio hook: evita
  // que un re-render (p. ej. React StrictMode en dev, o refetch) dispare
  // `mutate()` más de una vez por montaje de esta página.
  const hasFiredRef = useRef(false);

  const newsletter = newsletterQuery.data;

  useEffect(() => {
    if (newsletter && !hasFiredRef.current) {
      hasFiredRef.current = true;
      markReadMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newsletter]);

  if (!validIds) return null;

  if (newsletterQuery.isLoading) {
    return (
      <section className="space-y-4">
        <div className="h-5 w-28 animate-pulse rounded bg-light-gray" />
        <div role="status" aria-busy="true" aria-label="Cargando bitácora" className="space-y-3">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      </section>
    );
  }

  if (newsletterQuery.isError || !newsletter) {
    return (
      <section className="space-y-4">
        <Link
          to={`/my-athletes/${athleteId}/bitacora`}
          className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
        >
          <span aria-hidden="true">←</span>
          <span>Bitácora</span>
        </Link>
        <div className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-sm text-mid-gray">No se pudo cargar esta bitácora.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <Link
          to={`/my-athletes/${athleteId}/bitacora`}
          className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray transition-colors hover:text-charcoal"
        >
          <span aria-hidden="true">←</span>
          <span>Bitácora</span>
        </Link>
        {newsletter.has_pdf && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => pdfMutation.mutate()}
            disabled={pdfMutation.isPending}
            data-testid="download-bitacora-pdf-btn"
          >
            <Download size={14} aria-hidden="true" />
            {pdfMutation.isPending ? "Descargando…" : "Descargar PDF"}
          </Button>
        )}
      </div>

      <StageLogView mode="parent" stageLog={newsletter.stage_log} />
    </section>
  );
}
