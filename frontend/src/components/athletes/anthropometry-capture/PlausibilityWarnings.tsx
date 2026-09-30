import { useState } from "react";
import { TriangleAlert } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  PLAUSIBILITY_COPY,
  PLAUSIBILITY_MEASURE_LABELS,
} from "@/lib/anthropometry/plausibilityCopy";
import type {
  PlausibilityMeasure,
  PlausibilityWarning,
} from "@/types/anthropometry.types";

export interface PlausibilityWarningsProps {
  warnings: PlausibilityWarning[];
  /** «Volver a medir»: el asistente salta al paso de esa medida. */
  onRemeasure: (measure: PlausibilityMeasure) => void;
  /** «Está bien así»: la advertencia queda reconocida (no bloquea el guardado). */
  onAcknowledge?: (warning: PlausibilityWarning) => void;
}

/** Una advertencia ámbar por cada aviso de plausibilidad, sin bloquear el guardado. */
export function PlausibilityWarnings({
  warnings,
  onRemeasure,
  onAcknowledge,
}: PlausibilityWarningsProps) {
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const visible = warnings.filter((w) => !dismissed.has(w.code));
  if (visible.length === 0) return null;

  return (
    <ul className="flex flex-col gap-3" aria-label="Advertencias de la medición">
      {visible.map((warning) => (
        <li key={warning.code}>
          <Alert
            role="note"
            variant="warning"
            className="border-amber-300 bg-amber-50 text-amber-950"
          >
            <TriangleAlert aria-hidden="true" />
            <p className="font-semibold">
              {PLAUSIBILITY_MEASURE_LABELS[warning.measure]}
            </p>
            <p className="mt-1">{PLAUSIBILITY_COPY[warning.code]}</p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <Button
                type="button"
                variant="outline"
                size="lg"
                onClick={() => onRemeasure(warning.measure)}
              >
                Volver a medir
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="lg"
                onClick={() => {
                  setDismissed((prev) => new Set(prev).add(warning.code));
                  onAcknowledge?.(warning);
                }}
              >
                Está bien así
              </Button>
            </div>
          </Alert>
        </li>
      ))}
    </ul>
  );
}
