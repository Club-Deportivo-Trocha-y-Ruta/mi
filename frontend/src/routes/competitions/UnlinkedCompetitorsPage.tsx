/**
 * UnlinkedCompetitorsPage — wrapper de página para UnlinkedCompetitorsTab.
 *
 * Ruta: /competitions/unlinked
 * Acceso: coach + admin.
 *
 * Monta la herramienta de enlace retroactivo de competidores sin modificar
 * el componente `UnlinkedCompetitorsTab` (se conserva intacto como componente
 * compartido). Este wrapper añade el header de página más la fila de
 * pastillas de vistas hermanas (Válidas | Sin enlazar | Panorama de
 * temporada) del área Competencias (`data-model.md` §2, FR-007).
 */
import { Suspense } from "react";
import { UnlinkedCompetitorsTab } from "@/components/race/UnlinkedCompetitorsTab";
import {
  SiblingViewTabs,
  type SiblingViewTabsItem,
} from "@/components/layout/SiblingViewTabs";
import { currentSeason } from "@/lib/datetime";

// Vistas hermanas del área Competencias — compartidas con CompetitionsListPage
// y SeasonInsightsPage.
const COMPETITIONS_SIBLING_VIEWS: SiblingViewTabsItem[] = [
  { label: "Válidas", to: "/competitions" },
  { label: "Sin enlazar", to: "/competitions/unlinked" },
  {
    label: "Panorama de temporada",
    to: `/competitions/insights/season/${currentSeason()}`,
  },
];

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

      <SiblingViewTabs items={COMPETITIONS_SIBLING_VIEWS} />

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
