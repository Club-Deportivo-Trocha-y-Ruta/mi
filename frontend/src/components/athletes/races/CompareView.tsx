/**
 * CompareView — vista «Comparar» de la pestaña «Carreras» (feature 045,
 * T039). SOLO coach (FR-015): distribución del campo + comparador de
 * progreso entre dos válidas. `CarrerasTab` no la monta para la familia,
 * ni siquiera por dirección directa (`view=comparar` cae en «Progresión»).
 *
 * El comparador antes vivía en un Sheet lateral dentro de «Distribución»
 * (Sprint 2 BB3); dentro de una vista propia va en línea — ya no hay un
 * botón intermedio.
 */
import { BarChart3, Scale } from "lucide-react";

import { ComparatorPanel } from "@/components/athletes/ai/ComparatorPanel";
import { DistributionChart } from "@/components/athletes/ai/DistributionChart";

export interface CompareViewProps {
  athleteId: number;
}

export function CompareView({ athleteId }: CompareViewProps) {
  return (
    <div className="space-y-6" data-testid="compare-view">
      <section
        className="space-y-3"
        aria-labelledby="compare-distribution-title"
      >
        <h3
          id="compare-distribution-title"
          className="font-display flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <BarChart3 size={16} aria-hidden="true" />
          Distribución del campo
        </h3>
        <DistributionChart athleteId={athleteId} />
      </section>

      <section
        className="space-y-3"
        aria-labelledby="compare-progress-title"
      >
        <h3
          id="compare-progress-title"
          className="font-display flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <Scale size={16} aria-hidden="true" />
          Comparador de progreso
        </h3>
        <p className="text-xs text-mid-gray">
          Compara el progreso del atleta entre dos válidas de la temporada.
        </p>
        <ComparatorPanel athleteId={athleteId} />
      </section>
    </div>
  );
}
