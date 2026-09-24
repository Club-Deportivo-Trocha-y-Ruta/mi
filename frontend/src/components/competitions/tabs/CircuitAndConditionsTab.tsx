/**
 * CircuitAndConditionsTab — pestaña «Circuito y condiciones» del detalle de
 * una competencia (feature 045, US6, research R-12).
 *
 * Reúne en un solo lugar lo que antes eran dos pestañas hermanas:
 *   - «Circuito»: perfil del circuito (`race/course/CourseTab`, feature 043).
 *   - «Condiciones»: clima, temperatura, superficie y altitud
 *     (`ConditionsTab` → `RaceConditionsCard`).
 *
 * Orden: circuito primero (es lo que nombra la pestaña y lo que más se
 * consulta antes de una salida), condiciones después. Cada bloque lleva su
 * propio `<h2>` para que el orden de encabezados de la página sea válido
 * (h1 de la página → h2 de cada bloque → h3 de las tarjetas internas).
 *
 * `CourseTab` arrastra mapa + perfil de elevación (recharts/leaflet), así que
 * se carga con `React.lazy` y su propio `Suspense`: abrir esta pestaña muestra
 * las condiciones al instante mientras el circuito termina de cargar.
 *
 * Props:
 *   - `raceEventId: number` — id del evento (ambos bloques).
 *   - `event: RaceEventRead` — condiciones embebidas para `ConditionsTab`.
 */
import { lazy, Suspense } from "react";

import { ConditionsTab } from "@/components/competitions/tabs/ConditionsTab";
import { Skeleton } from "@/components/ui/skeleton";
import type { RaceEventRead } from "@/types/raceEvents.types";

const CourseTab = lazy(() =>
  import("@/components/race/course/CourseTab").then((m) => ({
    default: m.CourseTab,
  })),
);

export interface CircuitAndConditionsTabProps {
  raceEventId: number;
  event: RaceEventRead;
}

function CourseFallback() {
  return (
    <div
      className="space-y-2 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline"
      role="status"
      aria-busy="true"
      aria-label="Cargando circuito…"
      data-testid="circuit-tab-fallback"
    >
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export function CircuitAndConditionsTab({
  raceEventId,
  event,
}: CircuitAndConditionsTabProps) {
  return (
    <div className="space-y-6" data-testid="circuit-conditions-tab">
      <section aria-labelledby="circuit-conditions-circuit-heading" className="space-y-3">
        <h2
          id="circuit-conditions-circuit-heading"
          className="text-sm font-semibold text-charcoal"
        >
          Circuito
        </h2>
        <Suspense fallback={<CourseFallback />}>
          <CourseTab raceEventId={raceEventId} />
        </Suspense>
      </section>

      <section aria-labelledby="circuit-conditions-conditions-heading" className="space-y-3">
        <h2
          id="circuit-conditions-conditions-heading"
          className="text-sm font-semibold text-charcoal"
        >
          Condiciones
        </h2>
        <ConditionsTab raceEventId={raceEventId} event={event} />
      </section>
    </div>
  );
}
