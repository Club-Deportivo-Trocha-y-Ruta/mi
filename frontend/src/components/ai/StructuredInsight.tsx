import { useId, useState } from "react";
import { ChevronDown, Info } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AnthropometryInsightOut, ConfidenceLevel } from "@/types/ai.types";

export interface StructuredInsightProps {
  /** Subconjunto `structured` de una fila v2 (contracts/insight-schema.md §2). */
  insight: AnthropometryInsightOut;
  className?: string;
}

const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
};

/**
 * Renderiza el análisis estructurado (`AnthropometryInsightOut`) en su forma
 * colapsada por defecto (FR-026):
 *
 *   - Siempre visibles: la línea de resumen y las señales de aviso (si las
 *     hay), además de "qué cambió", el nivel de confianza con su motivo y
 *     los vacíos de información — son contexto factual/de alcance, no
 *     interpretación ni recomendación.
 *   - Detrás del expansor "Ver análisis completo" (`aria-expanded`/
 *     `aria-controls`, control real `<button>`): "qué significa" y
 *     "próximas 2–4 semanas".
 *
 * Puramente presentacional: no hace fetching, no conoce `critic_verdict` ni
 * el `schema_version` de FORMATO DE FILA — el consumidor (`AnthropometricRecordExplanationCard`,
 * `PHVExplanationCard`) decide cuándo mostrar esto en vez del texto libre v1.
 *
 * Tono (FR-008): las señales de aviso se presentan como "algo para que el
 * entrenador revise", nunca como una alerta — por eso usan el token
 * informativo neutro (azul), nunca ámbar ni rojo. El ámbar queda reservado
 * para el bloque condicional de implicaciones de entrenamiento (FR-030).
 */
export function StructuredInsight({ insight, className }: StructuredInsightProps) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const hasWarningSigns = insight.warning_signs.length > 0;
  const hasDataGaps = insight.data_gaps.length > 0;

  return (
    <div className={cn("space-y-3", className)} data-testid="structured-insight">
      <p
        className="text-sm font-medium text-charcoal"
        data-testid="structured-insight-summary"
      >
        {insight.summary_line}
      </p>

      {hasWarningSigns && (
        <div
          className="rounded-lg bg-blue-50 px-3 py-2"
          data-testid="structured-insight-warning-signs"
        >
          <p className="flex items-center gap-1.5 text-xs font-semibold text-blue-900">
            <Info size={13} className="shrink-0" aria-hidden="true" />
            Señales de aviso
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-blue-900">
            {insight.warning_signs.map((sign, index) => (
              <li key={index}>{sign}</li>
            ))}
          </ul>
        </div>
      )}

      <section data-testid="structured-insight-changes">
        <h5 className="text-xs font-semibold text-charcoal">Qué cambió</h5>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-charcoal">
          {insight.changes.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </section>

      <p className="text-xs text-mid-gray" data-testid="structured-insight-confidence">
        <span className="font-medium text-charcoal">
          Confianza: {CONFIDENCE_LABEL[insight.confidence.level]}
        </span>{" "}
        — {insight.confidence.reason}
      </p>

      {hasDataGaps && (
        <section data-testid="structured-insight-data-gaps">
          <h5 className="text-xs font-semibold text-charcoal">
            Vacíos de información
          </h5>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-mid-gray">
            {insight.data_gaps.map((gap, index) => (
              <li key={index}>{gap}</li>
            ))}
          </ul>
        </section>
      )}

      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls={detailsId}
        data-testid="structured-insight-toggle"
        className={cn(
          "flex min-h-8 items-center gap-1 rounded-lg text-xs font-medium text-blue-600",
          "hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
        )}
      >
        {expanded ? "Ocultar análisis completo" : "Ver análisis completo"}
        <ChevronDown
          size={13}
          aria-hidden="true"
          className={cn("transition-transform", expanded && "rotate-180")}
        />
      </button>

      {expanded && (
        <div
          id={detailsId}
          className="space-y-3"
          data-testid="structured-insight-details"
        >
          <section data-testid="structured-insight-meaning">
            <h5 className="text-xs font-semibold text-charcoal">Qué significa</h5>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-charcoal">
              {insight.meaning.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>

          <section data-testid="structured-insight-next-weeks">
            <h5 className="text-xs font-semibold text-charcoal">
              Próximas 2–4 semanas
            </h5>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-charcoal">
              {insight.next_weeks.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
