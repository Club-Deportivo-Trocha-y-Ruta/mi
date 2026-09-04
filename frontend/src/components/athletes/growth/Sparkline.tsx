/**
 * Sparkline — mini tendencia inline (feature 040, US2, T038).
 *
 * SVG puro (sin Recharts): a diferencia de `athletes/ai/MiniSparkline.tsx`
 * (gráfica de evolución de ranking, con tooltip y eje), esta es una lectura
 * de un vistazo dentro de un `StatCard` — no necesita interacción ni el
 * costo del chunk de Recharts. Se usa en `GrowthStatusRow` para mostrar la
 * tendencia de talla de las últimas mediciones junto a la velocidad de
 * crecimiento (`contracts/growth-tab-ui.md` mockup de fila A).
 *
 * Accesibilidad: `role="img"` + `aria-label` describen la tendencia en
 * palabras (nunca sólo el trazo) — mismo criterio que la curva completa
 * (`PercentileChart`, `growth-tab-ui.md` §Accessibility).
 */
export interface SparklineProps {
  /** Valores en orden cronológico (más antiguo primero); el último se acentúa. */
  values: number[];
  ariaLabel: string;
  width?: number;
  height?: number;
}

const DEFAULT_WIDTH = 64;
const DEFAULT_HEIGHT = 24;
const PADDING = 3;
const LAST_POINT_RADIUS = 2.5;

interface Point {
  x: number;
  y: number;
}

function toPoints(values: number[], width: number, height: number): Point[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  // Rango 1 cuando todos los valores son iguales (línea plana) — evita
  // dividir por cero sin distorsionar valores reales.
  const range = max - min || 1;
  const innerWidth = width - PADDING * 2;
  const innerHeight = height - PADDING * 2;

  return values.map((value, index) => {
    const x =
      values.length === 1
        ? width / 2
        : PADDING + (index / (values.length - 1)) * innerWidth;
    const y = PADDING + innerHeight - ((value - min) / range) * innerHeight;
    return { x, y };
  });
}

export function Sparkline({
  values,
  ariaLabel,
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
}: SparklineProps) {
  if (values.length === 0) return null;

  const points = toPoints(values, width, height);
  const lastPoint = points[points.length - 1];
  const polylinePoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
    >
      {points.length > 1 && (
        <polyline
          points={polylinePoints}
          fill="none"
          stroke="var(--color-mid-gray)"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
      {/* Acento del último punto — el dato vigente, siempre el más reciente. */}
      <circle cx={lastPoint.x} cy={lastPoint.y} r={LAST_POINT_RADIUS} fill="var(--color-primary)" />
    </svg>
  );
}
