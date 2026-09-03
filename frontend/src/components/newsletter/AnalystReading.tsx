/**
 * AnalystReading — "Lectura del analista": traducción a lenguaje familiar
 * del InsightV3 adjunto (feature 038, T301, US3). Solo se renderiza cuando
 * `analystReading` no es null — la ausencia (mes sin válida, insight no
 * elegible) la decide `StageLogView`, este componente nunca imprime un
 * placeholder de "sin análisis".
 *
 * `sourceInsightId` es SOLO para `mode="coach"` — el DTO de padres
 * (`to_parent_dto`) nunca lo incluye (data-model.md §1); se muestra como
 * nota de procedencia discreta, nunca visible para la familia.
 */
import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export interface AnalystReadingProps {
  analystReading: {
    headline_family: string;
    action_family: string;
    valida_label: string;
  };
  mode: "coach" | "parent";
  sourceInsightId?: number;
}

export function AnalystReading({
  analystReading,
  mode,
  sourceInsightId,
}: AnalystReadingProps) {
  return (
    <section
      className="rounded-xl border border-primary/20 bg-white p-4 shadow-card"
      aria-label="Lectura del analista"
      data-testid="analyst-reading"
    >
      <div className="flex items-center gap-2">
        <Badge variant="default" className="gap-1">
          <Sparkles size={11} aria-hidden="true" />
          Lectura del analista
        </Badge>
        <span className="text-xs text-mid-gray">{analystReading.valida_label}</span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-charcoal">
        {analystReading.headline_family}
      </p>
      <p className="mt-1 text-sm leading-relaxed text-charcoal">
        {analystReading.action_family}
      </p>
      {mode === "coach" && sourceInsightId !== undefined && (
        <p className="mt-2 text-[11px] text-mid-gray" data-testid="analyst-reading-provenance">
          Fuente: análisis #{sourceInsightId} (visible solo para el estudio)
        </p>
      )}
    </section>
  );
}
