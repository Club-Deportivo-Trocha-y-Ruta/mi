import { lazy, Suspense, useState } from "react";

import type { AthleteSeries, InterpretationResponse } from "@/types/anxiety.types";

import { AnalyzeButton } from "./AnalyzeButton";
import { InterpretationPanel } from "./InterpretationPanel";

// Recharts es pesado → lazy-load para no penalizar el bundle inicial.
const SeriesChart = lazy(() =>
  import("./SeriesChart").then((m) => ({ default: m.SeriesChart })),
);

interface IndividualPanelProps {
  series: AthleteSeries;
}

function fmt(v: number | null): string {
  return v === null ? "—" : String(v);
}

/** Panel individual: puntajes, evolución vs. línea base (chart lazy), flags (US5). */
export function IndividualPanel({ series }: IndividualPanelProps) {
  const latest = series.points[series.points.length - 1] ?? null;
  const flags = latest?.flags ?? [];
  const [result, setResult] = useState<InterpretationResponse | null>(null);

  return (
    <section
      className="rounded-xl border border-border-gray bg-white p-5"
      aria-label="Panel individual de ansiedad"
    >
      <h3 className="mb-3 text-base font-semibold text-charcoal">
        Evolución individual ({series.instrument_type.toUpperCase()})
      </h3>

      {series.note && (
        <p className="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
          {series.note}
        </p>
      )}

      <table className="mb-4 w-full text-sm">
        <thead>
          <tr className="text-left text-mid-gray">
            <th className="py-1">Dimensión</th>
            <th className="py-1">Último</th>
            <th className="py-1">Línea base</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-border-gray">
            <td className="py-1">Cognitiva</td>
            <td className="py-1">{fmt(latest?.cognitive ?? null)}</td>
            <td className="py-1">{fmt(series.baseline_cognitive)}</td>
          </tr>
          <tr className="border-t border-border-gray">
            <td className="py-1">Somática</td>
            <td className="py-1">{fmt(latest?.somatic ?? null)}</td>
            <td className="py-1">{fmt(series.baseline_somatic)}</td>
          </tr>
          <tr className="border-t border-border-gray">
            <td className="py-1">Autoconfianza</td>
            <td className="py-1">{fmt(latest?.selfconfidence ?? null)}</td>
            <td className="py-1">{fmt(series.baseline_selfconfidence)}</td>
          </tr>
        </tbody>
      </table>

      {series.points.length > 0 && (
        <Suspense
          fallback={
            <p className="text-sm text-mid-gray">Cargando gráfica…</p>
          }
        >
          <SeriesChart series={series} />
        </Suspense>
      )}

      {flags.length > 0 && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3" role="alert">
          <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">
            {flags.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {latest && latest.cognitive !== null && (
        <div className="mt-4">
          <AnalyzeButton assessmentId={latest.assessment_id} onAnalyzed={setResult} />
        </div>
      )}
      {result && (
        <div className="mt-4">
          <InterpretationPanel interpretation={result.interpretation} source={result.source} />
        </div>
      )}
    </section>
  );
}

export default IndividualPanel;
