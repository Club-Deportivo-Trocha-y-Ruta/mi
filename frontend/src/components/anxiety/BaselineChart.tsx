import type { SeriesPoint } from "@/types/anxiety.types";

interface BaselineChartProps {
  points: SeriesPoint[];
  baselineCognitive: number | null;
  baselineSomatic: number | null;
}

const WIDTH = 320;
const HEIGHT = 120;
const PAD = 8;

function path(values: (number | null)[], min: number, max: number): string {
  const span = max - min || 1;
  const step = values.length > 1 ? (WIDTH - PAD * 2) / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      if (v === null) return "";
      const x = PAD + i * step;
      const y = HEIGHT - PAD - ((v - min) / span) * (HEIGHT - PAD * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
}

/**
 * Sparkline accesible de la evolución vs. línea base (lazy-loaded por
 * IndividualPanel). SVG puro, sin dependencias externas — barato y testeable.
 */
export function BaselineChart({ points }: BaselineChartProps) {
  const cog = points.map((p) => p.cognitive);
  const som = points.map((p) => p.somatic);
  const all = [...cog, ...som].filter((v): v is number => v !== null);
  if (all.length === 0) {
    return (
      <p className="text-sm text-slate-500">Aún no hay datos para graficar.</p>
    );
  }
  const min = Math.min(...all);
  const max = Math.max(...all);

  return (
    <figure>
      <figcaption className="mb-2 text-xs text-slate-500">
        Evolución (cognitiva en azul, somática en naranja)
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="Gráfica de evolución de las subescalas frente a la línea base"
      >
        <path d={path(cog, min, max)} fill="none" stroke="#2563eb" strokeWidth={2} />
        <path d={path(som, min, max)} fill="none" stroke="#ea580c" strokeWidth={2} />
      </svg>
    </figure>
  );
}

export default BaselineChart;
