import { ChevronDown } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { phvPlainLabel } from "@/lib/anthropometry/phvPlain";
import type { PHVResult } from "@/lib/phv";

export interface PhvPlainSummaryProps {
  phv: PHVResult;
}

function signed(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

/**
 * Resumen de maduración en lenguaje llano (feature 048): etiqueta, qué
 * implica para el entrenamiento y, plegado, el detalle técnico.
 */
export function PhvPlainSummary({ phv }: PhvPlainSummaryProps) {
  return (
    <section
      aria-label="Resumen de maduración"
      className="rounded-card bg-light-gray p-4"
      data-testid="phv-plain-summary"
    >
      <p className="text-base font-semibold text-charcoal">
        {phvPlainLabel(phv.maturationStatus)}
      </p>
      <p className="mt-1 text-sm text-charcoal">{phv.trainingImplications}</p>

      <Collapsible className="mt-3">
        <CollapsibleTrigger className="group flex min-h-12 items-center gap-2 rounded-control text-sm font-medium text-link-blue focus-visible:outline-2 focus-visible:outline-primary">
          Detalle técnico
          <ChevronDown
            className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180"
            aria-hidden="true"
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <dl className="grid grid-cols-1 gap-2 pt-2 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-mid-gray">Maturity offset</dt>
              <dd className="font-medium text-charcoal">{signed(phv.maturityOffset)}</dd>
            </div>
            <div>
              <dt className="text-mid-gray">Edad al PHV</dt>
              <dd className="font-medium text-charcoal">{phv.ageAtPhv} años</dd>
            </div>
            <div>
              <dt className="text-mid-gray">Longitud de pierna</dt>
              <dd className="font-medium text-charcoal">{phv.legLengthCm} cm</dd>
            </div>
          </dl>
        </CollapsibleContent>
      </Collapsible>
    </section>
  );
}
