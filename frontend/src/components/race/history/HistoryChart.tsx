/**
 * HistoryChart — línea de progresión entre válidas/temporadas de un atleta
 * (feature 044, US6, `contracts/ui-history.md` §1).
 *
 * Un solo eje (nunca dos): el toggle de métrica cambia qué campo se grafica,
 * no agrega un segundo eje Y. "Brecha a la mediana" invierte el eje (arriba
 * = más rápido, cero = "Mediana de su categoría"); "Velocidad media" no se
 * invierte (arriba ya es mejor).
 *
 * La línea nunca implica continuidad donde no la hay:
 *   - Un cambio de categoría (`category_changed`) corta la línea por
 *     completo — no hay conector, ni sólido ni punteado: son pelotones
 *     distintos, unirlos sería leer una tendencia que no existe. Se marca
 *     con una `ReferenceLine` vertical con la etiqueta "A → B".
 *   - Un salto de válida o de temporada dentro de la MISMA categoría sí se
 *     conecta, pero punteado — hubo tiempo/carreras de por medio.
 *   - DNF/DNS/DSQ se dibujan como marcador hueco en la línea base (0), sin
 *     valor y sin conectarse a nada — su estado va en el tooltip.
 *
 * Mecánica de render: en vez de N líneas por tramo (frágil para el
 * tooltip, que terminaría reportando el punto más cercano de cada tramo a
 * la vez), se usa UNA sola `<Line>` "sólida" cuyo array de datos intercala
 * filas fantasma (`value: null`) exactamente en los cortes — con
 * `connectNulls={false}` eso basta para que recharts no dibuje el
 * segmento ahí. Los saltos punteados son líneas de 2 puntos aparte (pocas
 * por temporada), y los no-finalistas son una tercera línea sin trazo,
 * solo con marcador. El tooltip deduplica por `event_id` e ignora las
 * filas fantasma.
 */
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DotItemDotProps } from "recharts";

import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import {
  formatFieldSize,
  formatGapPct,
  formatRaceDateShort,
  formatSpeedKmh,
} from "@/lib/raceHistoryFormat";
import {
  NON_FINISHER_STATUSES,
  RACE_HISTORY_STATUS_LABELS,
} from "@/types/raceHistory.types";
import type {
  RaceHistoryPoint,
  RaceHistoryResultStatus,
} from "@/types/raceHistory.types";

type HistoryMetric = "gap" | "speed";

const METRIC_LABELS: Record<HistoryMetric, string> = {
  gap: "Brecha a la mediana",
  speed: "Velocidad media",
};

export interface HistoryChartProps {
  points: RaceHistoryPoint[];
  className?: string;
}

// ---------------------------------------------------------------------------
// Filas de la gráfica
// ---------------------------------------------------------------------------

interface ChartRow {
  isPhantom?: boolean;
  eventId: number | null;
  x: number;
  eventDate: string;
  label: string;
  season: number;
  categoryLabel: string;
  categoryChanged: boolean;
  previousCategoryLabel: string | null;
  status: RaceHistoryResultStatus | null;
  fieldSize: number | null;
  gapMedianPct: number | null;
  avgSpeedKmh: number | null;
  /** Valor de la métrica activa — lo que efectivamente se grafica. */
  value: number | null;
}

function parseDateMs(isoDate: string): number {
  return new Date(`${isoDate}T00:00:00Z`).getTime();
}

/** "Válida 1 — Ginebra" → 1. `null` si el label no sigue esa convención
 * (fixtures de campeonato u otras series sin numeración de válida). */
function parseValidaNum(label: string): number | null {
  const match = /Válida\s+(\d+)/i.exec(label);
  return match ? Number(match[1]) : null;
}

/** `true` si hubo temporada u otras válidas de por medio entre dos puntos
 * consecutivos de la MISMA categoría. Cambiar de temporada siempre cuenta
 * como salto (dato estructurado, siempre disponible); un salto de válida
 * dentro de la misma temporada solo se detecta cuando ambos labels siguen
 * la convención "Válida N" — si no, se asume contiguo antes que inventar
 * un corte que no se puede sustentar. */
function hasTimeGap(prev: ChartRow, curr: ChartRow): boolean {
  if (prev.season !== curr.season) return true;
  const prevNum = parseValidaNum(prev.label);
  const currNum = parseValidaNum(curr.label);
  if (prevNum !== null && currNum !== null) return currNum - prevNum !== 1;
  return false;
}

function toRow(p: RaceHistoryPoint, metric: HistoryMetric): ChartRow {
  return {
    eventId: p.event_id,
    x: parseDateMs(p.event_date),
    eventDate: p.event_date,
    label: p.label,
    season: p.season,
    categoryLabel: p.category_label,
    categoryChanged: p.category_changed,
    previousCategoryLabel: p.previous_category_label,
    status: p.status,
    fieldSize: p.field_size,
    gapMedianPct: p.gap_to_median_pct,
    avgSpeedKmh: p.avg_speed_kmh,
    value: metric === "gap" ? p.gap_to_median_pct : p.avg_speed_kmh,
  };
}

function phantomBetween(a: ChartRow, b: ChartRow): ChartRow {
  return {
    isPhantom: true,
    eventId: null,
    x: (a.x + b.x) / 2,
    eventDate: "",
    label: "",
    season: a.season,
    categoryLabel: "",
    categoryChanged: false,
    previousCategoryLabel: null,
    status: null,
    fieldSize: null,
    gapMedianPct: null,
    avgSpeedKmh: null,
    value: null,
  };
}

interface BuiltChartData {
  rows: ChartRow[];
  dashedPairs: Array<[ChartRow, ChartRow]>;
  categoryChangeMarkers: ChartRow[];
  nonFinisherRows: ChartRow[];
}

function buildChartData(
  points: RaceHistoryPoint[],
  metric: HistoryMetric,
): BuiltChartData {
  const sorted = [...points].sort((a, b) =>
    a.event_date.localeCompare(b.event_date),
  );

  const rows: ChartRow[] = [];
  const dashedPairs: Array<[ChartRow, ChartRow]> = [];
  const categoryChangeMarkers: ChartRow[] = [];
  const nonFinisherRows: ChartRow[] = [];

  let prev: ChartRow | null = null;
  for (const p of sorted) {
    const row = toRow(p, metric);

    if (prev) {
      if (row.categoryChanged) {
        // Corte duro — ni sólido ni punteado, son pelotones distintos.
        rows.push(phantomBetween(prev, row));
        categoryChangeMarkers.push(row);
      } else if (hasTimeGap(prev, row)) {
        // Misma categoría, pero con tiempo/válidas de por medio — se
        // corta la línea sólida y se agrega un conector punteado aparte.
        rows.push(phantomBetween(prev, row));
        dashedPairs.push([prev, row]);
      }
    }

    rows.push(row);
    if (NON_FINISHER_STATUSES.has(p.status)) {
      // `value` ya es `null` para un no-finalista (sin tiempo/velocidad) —
      // se deja así aquí; el componente decide DÓNDE plotearlo (fuera del
      // rango real de datos, ver `buildYDomain`) una vez conoce el dominio.
      nonFinisherRows.push(row);
    }
    prev = row;
  }

  return { rows, dashedPairs, categoryChangeMarkers, nonFinisherRows };
}

/**
 * Dominio del eje Y — MAJOR 1+2 de la revisión UX (T077): un no-finalista
 * NO puede plotearse en 0, porque eso (a) choca visualmente con la línea
 * de "Mediana de su categoría" (que también vive en 0) y (b) en la métrica
 * de velocidad arrastra el eje a incluir 0 aunque el atleta ronde siempre
 * 35-45 km/h, aplastando la variación real contra el techo del rango.
 *
 * Se calcula un dominio a partir SOLO de los valores reales (finalistas
 * con dato), con un margen del 15 %; los no-finalistas se plotean en el
 * borde inferior de ESE dominio — una franja separada, nunca en 0. Para
 * la métrica "gap" se fuerza a que el dominio siempre incluya 0 (si no,
 * la línea de mediana quedaría fuera de vista para un atleta siempre por
 * encima/debajo de ella).
 */
function buildYDomain(realValues: number[], forceZero: boolean): [number, number] {
  const values = forceZero ? [...realValues, 0] : realValues;
  if (values.length === 0) return forceZero ? [-1, 1] : [0, 1];

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const pad = span > 0 ? span * 0.15 : Math.max(Math.abs(min) * 0.15, 1);
  return [min - pad, max + pad];
}

// ---------------------------------------------------------------------------
// Dots
// ---------------------------------------------------------------------------

function renderDot(props: DotItemDotProps) {
  const { cx, cy, index, payload } = props;
  const row = payload as ChartRow;
  if (cx === undefined || cy === undefined || row?.value == null) return null;
  return (
    <circle
      key={`history-dot-${index}`}
      cx={cx}
      cy={cy}
      r={4}
      fill="var(--color-primary)"
    />
  );
}

function renderHollowDot(props: DotItemDotProps) {
  const { cx, cy, index } = props;
  if (cx === undefined || cy === undefined) return null;
  return (
    <circle
      key={`history-hollow-dot-${index}`}
      cx={cx}
      cy={cy}
      r={5}
      fill="var(--color-surface)"
      stroke="var(--color-primary)"
      strokeWidth={2}
      data-testid="history-chart-non-finisher-marker"
    />
  );
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipLikeProps {
  active?: boolean;
  payload?: Array<{ payload?: unknown }>;
}

function HistoryTooltip(props: TooltipLikeProps & { metric: HistoryMetric }) {
  const { active, payload, metric } = props;
  if (!active || !payload || payload.length === 0) return null;

  // Dedupe por event_id — un mismo punto puede aparecer en más de una
  // `<Line>` (el tramo sólido que termina ahí y el punteado que arranca
  // ahí comparten el punto límite). Las filas fantasma nunca se muestran.
  const seen = new Set<number>();
  const found = payload.find((entry) => {
    const row = entry.payload as ChartRow | undefined;
    if (!row || row.isPhantom || row.eventId == null) return false;
    if (seen.has(row.eventId)) return false;
    seen.add(row.eventId);
    return true;
  });
  if (!found) return null;
  const row = found.payload as ChartRow;

  const isNonFinisher = row.status !== null && NON_FINISHER_STATUSES.has(row.status);

  return (
    <div
      className="rounded-lg bg-white px-3 py-2 text-xs shadow-ambient"
      data-testid="history-chart-tooltip"
    >
      <p className="font-semibold text-charcoal">{row.label}</p>
      <p className="text-mid-gray">
        {formatRaceDateShort(row.eventDate)} · {row.categoryLabel}
      </p>
      {isNonFinisher && row.status && (
        <p className="mt-1 text-charcoal">
          {RACE_HISTORY_STATUS_LABELS[row.status]}
        </p>
      )}
      {!isNonFinisher && (
        <p className="mt-1 text-charcoal">
          {metric === "gap"
            ? formatGapPct(row.gapMedianPct)
            : formatSpeedKmh(row.avgSpeedKmh)}
        </p>
      )}
      <p className="text-mid-gray">Parrilla: {formatFieldSize(row.fieldSize)}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function HistoryChart({ points, className }: HistoryChartProps) {
  const [metric, setMetric] = useState<HistoryMetric>("gap");

  const { rows, dashedPairs, categoryChangeMarkers, nonFinisherRows } =
    useMemo(() => buildChartData(points, metric), [points, metric]);

  // MAJOR 1+2 (T077 ux-review.md) — el dominio se calcula SOLO con los
  // valores reales (finalistas con dato); los no-finalistas se plotean en
  // su borde inferior, nunca en 0 — ver `buildYDomain`.
  const yDomain = useMemo(() => {
    const realValues = rows
      .filter((r) => !r.isPhantom && r.value != null)
      .map((r) => r.value as number);
    return buildYDomain(realValues, metric === "gap");
  }, [rows, metric]);

  const nonFinisherPlotRows = useMemo(
    () => nonFinisherRows.map((r) => ({ ...r, value: yDomain[0] })),
    [nonFinisherRows, yDomain],
  );

  const yTickFormatter = (v: number) =>
    metric === "gap" ? `${v}%` : `${v} km/h`;

  return (
    <div className={cn("space-y-3", className)} data-testid="history-chart">
      <ToggleGroup
        type="single"
        variant="outline"
        value={metric}
        onValueChange={(v) => v && setMetric(v as HistoryMetric)}
        aria-label="Métrica de la gráfica de progresión"
        data-testid="history-chart-metric-toggle"
      >
        {(Object.keys(METRIC_LABELS) as HistoryMetric[]).map((m) => (
          <ToggleGroupItem
            key={m}
            value={m}
            // MAJOR 4 (T077 ux-review.md) — objetivo táctil >= 44px (48
            // preferido); el tamaño por defecto de ToggleGroupItem es de
            // solo 36px (h-9). `min-h-12` gana sobre el `h-9` de la base
            // porque min-height siempre prevalece sobre height en CSS.
            className="min-h-12 px-4 text-xs"
            data-testid={`history-chart-metric-${m}`}
          >
            {METRIC_LABELS[m]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      {/* Pista barata de lectura del eje invertido — solo aplica a la
          brecha (la velocidad ya sube "hacia arriba" de forma natural). */}
      {metric === "gap" && (
        <p className="text-[11px] text-mid-gray" data-testid="history-chart-axis-hint">
          Más rápido que la mediana ↑ · Más lento ↓
        </p>
      )}

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 16, right: 16, bottom: 8, left: 12 }}>
          <CartesianGrid stroke="var(--color-border-gray)" />
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
            tickFormatter={(v: number) => formatRaceDateShort(
              new Date(v).toISOString().slice(0, 10),
            )}
          />
          <YAxis
            reversed={metric === "gap"}
            domain={yDomain}
            tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
            tickFormatter={yTickFormatter}
            width={70}
          />
          <Tooltip
            content={(tooltipProps: unknown) => (
              <HistoryTooltip
                {...(tooltipProps as TooltipLikeProps)}
                metric={metric}
              />
            )}
          />

          {metric === "gap" && (
            <ReferenceLine
              y={0}
              stroke="var(--color-mid-gray)"
              strokeDasharray="4 4"
              label={{
                value: "Mediana de su categoría",
                position: "insideTopLeft",
                fontSize: 11,
                fill: "var(--color-mid-gray)",
              }}
            />
          )}

          {categoryChangeMarkers.map((m) => (
            <ReferenceLine
              key={`cat-change-${m.eventId}`}
              x={m.x}
              stroke="var(--color-charcoal)"
              strokeDasharray="2 2"
              label={{
                value: `${m.previousCategoryLabel ?? "?"} → ${m.categoryLabel}`,
                position: "top",
                fontSize: 10,
                fill: "var(--color-charcoal)",
              }}
            />
          ))}

          <Line
            type="linear"
            data={rows}
            dataKey="value"
            stroke="var(--color-primary)"
            strokeWidth={2}
            dot={renderDot}
            activeDot={{ r: 6 }}
            connectNulls={false}
            isAnimationActive={false}
            legendType="none"
          />

          {dashedPairs.map(([a, b], i) => (
            <Line
              key={`dashed-${a.eventId}-${b.eventId}-${i}`}
              type="linear"
              data={[a, b]}
              dataKey="value"
              stroke="var(--color-primary)"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              isAnimationActive={false}
              legendType="none"
            />
          ))}

          {nonFinisherPlotRows.length > 0 && (
            <Line
              type="linear"
              data={nonFinisherPlotRows}
              dataKey="value"
              stroke="none"
              dot={renderHollowDot}
              isAnimationActive={false}
              legendType="none"
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
