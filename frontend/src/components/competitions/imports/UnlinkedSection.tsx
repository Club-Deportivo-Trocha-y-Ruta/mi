/**
 * UnlinkedSection — «Sin enlazar»: herramienta de enlace retroactivo de
 * competidores de Copa Valle con los deportistas del club, dentro de «Cargas e
 * identidades» (feature 045, US3; nace del cuerpo de `UnlinkedCompetitorsPage`).
 *
 * Monta `UnlinkedCompetitorsTab` sin modificarlo (componente compartido).
 */
import { Suspense } from "react";

import { UnlinkedCompetitorsTab } from "@/components/race/UnlinkedCompetitorsTab";

export function UnlinkedSection() {
  return (
    <div className="space-y-5" data-testid="unlinked-section">
      <p className="text-sm text-mid-gray">
        Vincula competidores de Copa Valle con los deportistas del club.
      </p>
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
    </div>
  );
}
