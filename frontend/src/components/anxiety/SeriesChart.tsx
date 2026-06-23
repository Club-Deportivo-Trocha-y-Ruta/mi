/**
 * SeriesChart — gráfico de líneas de evolución temporal de subescalas (US5).
 *
 * Lazy-loaded desde IndividualPanel para no penalizar el bundle inicial.
 * Usa Recharts (ya en las dependencias del proyecto). Las líneas de base se
 * dibujan como ReferenceLine horizontales.
 *
 * Privacidad: usa `assessment_id` como identificador, nunca nombres.
 */
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AthleteSeries } from "@/types/anxiety.types";

interface SeriesChartProps {
  series: AthleteSeries;
  /** ID de la evaluación actualmente seleccionada (se resalta). */
  highlightAssessmentId?: number;
}

const SUBSCALE_LABEL: Record<string, string> = {
  cognitive: "Cognitivo",
  somatic: "Somático",
  selfconfidence: "Autoconfianza",
};

export function SeriesChart({ series, highlightAssessmentId }: SeriesChartProps) {
  const data = series.points.map((p) => ({
    date: new Date(p.scheduled_at).toLocaleDateString("es-CO", {
      month: "short",
      day: "numeric",
    }),
    cognitive: p.cognitive ?? undefined,
    somatic: p.somatic ?? undefined,
    selfconfidence: p.selfconfidence ?? undefined,
    assessmentId: p.assessment_id,
  }));

  const highlightIdx =
    highlightAssessmentId != null
      ? data.findIndex((d) => d.assessmentId === highlightAssessmentId)
      : -1;

  return (
    <div
      style={{ width: "100%", overflowX: "auto" }}
      role="img"
      aria-label="Gráfico de evolución de subescalas de ansiedad"
    >
      <ResponsiveContainer width="100%" height={200} minWidth={300}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value, name) => [
              typeof value === "number" ? value.toFixed(2) : "—",
              SUBSCALE_LABEL[String(name)] ?? String(name),
            ]}
          />
          <Legend formatter={(value) => SUBSCALE_LABEL[String(value)] ?? String(value)} />

          {series.baseline_cognitive != null && (
            <ReferenceLine
              y={series.baseline_cognitive}
              stroke="#93c5fd"
              strokeDasharray="4 2"
            />
          )}
          {series.baseline_somatic != null && (
            <ReferenceLine
              y={series.baseline_somatic}
              stroke="#fca5a5"
              strokeDasharray="4 2"
            />
          )}
          {series.baseline_selfconfidence != null && (
            <ReferenceLine
              y={series.baseline_selfconfidence}
              stroke="#86efac"
              strokeDasharray="4 2"
            />
          )}

          {highlightIdx >= 0 && data[highlightIdx] && (
            <ReferenceLine x={data[highlightIdx].date} stroke="#6366f1" strokeWidth={2} />
          )}

          <Line
            type="monotone"
            dataKey="cognitive"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="somatic"
            stroke="#ef4444"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="selfconfidence"
            stroke="#22c55e"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SeriesChart;
