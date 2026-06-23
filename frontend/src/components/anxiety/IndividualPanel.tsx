import { lazy, Suspense } from "react";

import type { AthleteSeries } from "@/types/anxiety.types";

const BaselineChart = lazy(() => import("./BaselineChart"));

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

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-5"
      aria-label="Panel individual de ansiedad"
    >
      <h3 className="mb-3 text-base font-semibold text-slate-900">
        Evolución individual ({series.instrument_type.toUpperCase()})
      </h3>

      {series.note && (
        <p className="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
          {series.note}
        </p>
      )}

      <table className="mb-4 w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500">
            <th className="py-1">Dimensión</th>
            <th className="py-1">Último</th>
            <th className="py-1">Línea base</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-slate-100">
            <td className="py-1">Cognitiva</td>
            <td className="py-1">{fmt(latest?.cognitive ?? null)}</td>
            <td className="py-1">{fmt(series.baseline_cognitive)}</td>
          </tr>
          <tr className="border-t border-slate-100">
            <td className="py-1">Somática</td>
            <td className="py-1">{fmt(latest?.somatic ?? null)}</td>
            <td className="py-1">{fmt(series.baseline_somatic)}</td>
          </tr>
          <tr className="border-t border-slate-100">
            <td className="py-1">Autoconfianza</td>
            <td className="py-1">{fmt(latest?.selfconfidence ?? null)}</td>
            <td className="py-1">{fmt(series.baseline_selfconfidence)}</td>
          </tr>
        </tbody>
      </table>

      {series.points.length > 0 && (
        <Suspense
          fallback={
            <p className="text-sm text-slate-400">Cargando gráfica…</p>
          }
        >
          <BaselineChart
            points={series.points}
            baselineCognitive={series.baseline_cognitive}
            baselineSomatic={series.baseline_somatic}
          />
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
    </section>
  );
}

export default IndividualPanel;
