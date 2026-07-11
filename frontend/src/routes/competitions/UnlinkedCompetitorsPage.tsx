/**
 * UnlinkedCompetitorsPage — wrapper de página para UnlinkedCompetitorsTab.
 *
 * Ruta: /competitions/unlinked
 * Acceso: coach + admin.
 *
 * Monta la herramienta de enlace retroactivo de competidores sin modificar
 * el componente `UnlinkedCompetitorsTab` (se conserva intacto como componente
 * compartido). Este wrapper añade únicamente el header de página.
 */
import { Suspense } from "react";
import { UnlinkedCompetitorsTab } from "@/components/race/UnlinkedCompetitorsTab";

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function UnlinkedCompetitorsPage() {
  return (
    <section className="space-y-5">
      {/* Header */}
      <div>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Competidores sin enlazar
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Vincula competidores de Copa Valle con los deportistas del club.
        </p>
      </div>

      {/* Contenido */}
      <Suspense
        fallback={
          <div
            className="flex min-h-[20vh] items-center justify-center text-sm text-mid-gray"
            role="status"
            aria-live="polite"
          >
            Cargando competidores sin enlazar...
          </div>
        }
      >
        <UnlinkedCompetitorsTab />
      </Suspense>
    </section>
  );
}
