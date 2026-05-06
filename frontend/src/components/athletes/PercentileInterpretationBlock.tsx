/**
 * PercentileInterpretationBlock
 *
 * Muestra la interpretación de un indicador de crecimiento OMS para un atleta:
 * banda coloreada, label, valor medido, frase narrativa y toggle de detalles técnicos.
 *
 * Coherente con NutritionalClassification.tsx (tokens de color, tipografía Cal Sans).
 * Fuente: OMS 2007 / Res. MinSalud 2465/2016.
 */

import React, { useState } from "react";

import { useGrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";
import { getBandSpec } from "@/lib/growth/bands";
import type { GrowthIndicator } from "@/lib/growth/lms";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PercentileInterpretationBlockProps {
  record: AnthropometricRecord;
  sex: "M" | "F";
  birthDate: string;
  indicator: GrowthIndicator;
  /** Si true, oculta el toggle de Z-score detallado. Default false. */
  hideAdvanced?: boolean;
}

// ---------------------------------------------------------------------------
// Mapas de color Tailwind
// ---------------------------------------------------------------------------

const BG_COLOR = {
  green: "bg-green-50",
  yellow: "bg-yellow-50",
  orange: "bg-orange-50",
  red: "bg-red-50",
  blue: "bg-blue-50",
} as const;

const TEXT_COLOR = {
  green: "text-green-700",
  yellow: "text-yellow-700",
  orange: "text-orange-700",
  red: "text-red-700",
  blue: "text-blue-700",
} as const;

const DOT_COLOR = {
  green: "bg-green-500",
  yellow: "bg-yellow-400",
  orange: "bg-orange-500",
  red: "bg-red-600",
  blue: "bg-blue-500",
} as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Formatea el valor del atleta con unidad según el indicador. */
function formatValue(value: number, indicator: GrowthIndicator): string {
  switch (indicator) {
    case "height_for_age":
      return `${value.toFixed(1)} cm`;
    case "weight_for_age":
      return `${value.toFixed(1)} kg`;
    case "bmi_for_age":
      return `${value.toFixed(1)} kg/m²`;
  }
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function PercentileInterpretationBlock({
  record,
  sex,
  birthDate,
  indicator,
  hideAdvanced = false,
}: PercentileInterpretationBlockProps): React.ReactElement | null {
  const [showDetails, setShowDetails] = useState(false);

  const metrics = useGrowthMetrics({ record, sex, birthDate, indicator });

  if (metrics === null) return null;

  const spec = getBandSpec(indicator, metrics.band);
  const bg = BG_COLOR[spec.color];
  const textColor = TEXT_COLOR[spec.color];
  const dotColor = DOT_COLOR[spec.color];

  const zLabel =
    metrics.zScore >= 0
      ? `+${metrics.zScore.toFixed(2)}`
      : metrics.zScore.toFixed(2);

  return (
    <div
      className={`rounded-xl p-4 ${bg}`}
      role="region"
      aria-label={`Interpretacion ${indicator}`}
    >
      {/* Franja superior: dot + label + valor */}
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${dotColor}`}
          aria-hidden="true"
        />
        <span className={`text-sm font-medium ${textColor}`}>{spec.label}</span>
        <span className="ml-auto text-xs text-mid-gray">
          {formatValue(metrics.value, indicator)}
        </span>
      </div>

      {/* Frase narrativa */}
      <p className="mt-2 text-sm text-charcoal">{spec.narrative}</p>

      {/* Toggle detalles tecnicos */}
      {!hideAdvanced && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowDetails((prev) => !prev)}
            className="text-xs text-mid-gray underline-offset-2 hover:underline focus:outline-none"
            aria-expanded={showDetails}
          >
            {showDetails ? "Ocultar detalles" : "Detalles tecnicos"}
          </button>

          {showDetails && (
            <p
              className="mt-1 text-xs tabular-nums text-mid-gray"
              data-testid="technical-details"
            >
              Z={zLabel} | P{metrics.percentile}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
