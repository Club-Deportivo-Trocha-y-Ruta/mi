/**
 * HistoryChart — línea de progresión entre válidas/temporadas de un atleta
 * (feature 044, US6, `contracts/ui-history.md` §1).
 *
 * Una sola métrica a la vez — nunca dos ejes Y. Por defecto la brecha a la
 * mediana (`gap_to_median_pct`); el eje se invierte cuando menor es mejor
 * (arriba = mejor, cero = "Mediana de su categoría"). Velocidad media se
 * retiró de esta vista el 2026-09-22 (decisión del propietario: "no es un
 * dato relevante" en una comparación cruza-temporada; sigue disponible por
 * válida en el tab Circuito, feature 043).
 *
 * Feature 045 (T036): la prop `metric` elige qué graficar —
 * `gap_to_median_pct` | `percentile` | `position` | `gap_to_winner_pct` |
 * `gap_to_podium_pct` (ver `historyMetrics.ts`). `audience="family"` limita
 * a mediana, percentil y posición: una métrica de líder/podio pedida por la
 * familia cae en la mediana (defensa en profundidad — el backend tampoco
 * envía esas claves a una familia). El selector de métrica vive en la vista
 * («Progresión»), no aquí.
 *
 * Feature 045 (T075, FR-017): cada punto —incluidos los marcadores huecos de
 * no-finalista— es un enlace a su competencia (coach → detalle interno,
 * familia → vista de resultados de solo lectura), con área de toque de 48 px
 * y accesible por teclado. Requiere un `Router` en el árbol.
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
import { useMemo } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
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

import { cn } from "@/lib/utils";
import { raceEventHref } from "@/lib/raceEventHref";
import { formatFieldSize, formatRaceDateShort } from "@/lib/raceHistoryFormat";
import {
  DEFAULT_HISTORY_METRIC,
  HISTORY_METRICS,
  resolveHistoryMetric,
} from "@/components/race/history/historyMetrics";
import type {
  HistoryAudience,
  HistoryMetric,
  HistoryMetricConfig,
} from "@/components/race/history/historyMetrics";
import {
  NON_FINISHER_STATUSES,
  RACE_HISTORY_STATUS_LABELS,
} from "@/types/raceHistory.types";
import type {
  RaceHistoryPoint,
  RaceHistoryResultStatus,
} from "@/types/raceHistory.types";

export interface HistoryChartProps {
  points: RaceHistoryPoint[];
  /** Métrica graficada — default: brecha vs. mediana. */
  metric?: HistoryMetric;
  /** Limita las métricas: la familia no ve líder/podio. Default "coach". */
  audience?: HistoryAudience;
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
  /** Valor graficado — el de la métrica activa (`null` = sin dato). */
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

function toRow(p: RaceHistoryPoint, config: HistoryMetricConfig): ChartRow {
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
    value: config.select(p),
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
  config: HistoryMetricConfig,
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
    const row = toRow(p, config);

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
      // `value` ya es `null` para un no-finalista (sin tiempo) — se deja
      // así aquí; el componente decide DÓNDE plotearlo (fuera del rango
      // real de datos, ver `buildYDomain`) una vez conoce el dominio.
      nonFinisherRows.push(row);
    }
    prev = row;
  }

  return { rows, dashedPairs, categoryChangeMarkers, nonFinisherRows };
}

/**
 * Dominio del eje Y — MAJOR 1 de la revisión UX (T077): un no-finalista NO
 * puede plotearse en 0, porque eso choca visualmente con la línea de
 * "Mediana de su categoría", que también vive en 0.
 *
 * Se calcula un dominio a partir SOLO de los valores reales (finalistas con
 * dato), con un margen del 15 %; los no-finalistas se plotean en el borde
 * inferior de ESE dominio — una franja separada, nunca en 0. Para las
 * brechas firmadas (con línea de referencia en 0) el dominio siempre incluye
 * 0 (si no, la línea de referencia quedaría fuera de vista para un atleta
 * siempre por encima/debajo de ella). Percentil usa un dominio fijo 0–100 y
 * posición un eje de enteros ≥ 1.
 */
function buildYDomain(
  realValues: number[],
  config: HistoryMetricConfig,
): [number, number] {
  if (config.fixedDomain) return config.fixedDomain;

  const values =
    config.referenceLabel !== null ? [...realValues, 0] : [...realValues];
  if (values.length === 0) return config.integerAxis ? [1, 5] : [-1, 1];

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const pad = span > 0 ? span * 0.15 : Math.max(Math.abs(min) * 0.15, 1);
  if (config.integerAxis) {
    // Posición: enteros, nunca por debajo de la 1.ª.
    return [Math.max(1, Math.floor(min - pad)), Math.ceil(max + pad)];
  }
  // Redondeo a 2 decimales: sin él, `min - pad` arrastra el ruido binario del
  // punto flotante (una brecha de +2.1 % daba marcas como "99999995 %" en el
  // eje, reportado por el coach en producción).
  const round2 = (v: number) => Math.round(v * 100) / 100;
  return [round2(min - pad), round2(max + pad)];
}

/** Cantidad de marcas objetivo del eje X — recharts sigue pudiendo recortar
 * por espacio (``interval="preserveEnd"`` por defecto), pero SIEMPRE
 * preserva la última, así que basta con garantizar que esté en la lista. */
const X_TICK_COUNT = 6;

/**
 * Marcas del eje X, evenly-spaced entre la fecha más antigua y la más
 * reciente de la serie completa (bug reportado por el coach: el eje dejaba
 * de mostrar marcas a mitad de 2025 aunque la serie seguía hasta 2026).
 *
 * Causa raíz: con ``layout="horizontal"``, recharts trata CUALQUIER
 * ``<XAxis>`` como eje "categórico" para generar marcas — sin importar
 * ``type="number"`` — en cuanto el eje trae un ``dataKey`` (nuestro caso,
 * ``dataKey="x"``). En ese modo usa como candidatas TODAS las ``x`` de
 * ``displayedData`` en el orden de inserción (nunca ordenadas), que es la
 * UNIÓN de los ``data`` de cada ``<Line>`` — la sólida (cronológica)
 * seguida de los conectores punteados y de los no-finalistas, cuyos puntos
 * (duplicados de fechas ya vistas) quedan al FINAL del arreglo aunque sean
 * cronológicamente anteriores. El ``scale.ticks()`` "nice" de un eje
 * numérico/temporal de verdad nunca se alcanza — ver
 * ``combineCategoricalDomain``/``combineAxisTicks`` en
 * ``recharts/es6/state/selectors/axisSelectors.js``. Pasar un ``ticks``
 * explícito evita esa rama por completo: ``ticksOrNiceTicks = ticks ||
 * niceTicks`` usa directamente el arreglo que le demos, ya ordenado y con
 * el máximo real como última marca.
 */
function buildXTicks(rows: ChartRow[], count: number = X_TICK_COUNT): number[] {
  if (rows.length === 0) return [];
  const xs = rows.map((r) => r.x);
  const min = Math.min(...xs);
  const max = Math.max(...xs);
  if (min === max) return [min];
  const steps = Math.max(count - 1, 1);
  const ticks = Array.from(
    { length: count },
    (_, i) => min + ((max - min) * i) / steps,
  );
  // Único y ordenado — con pocos puntos reales, `count` marcas evenly-spaced
  // pueden coincidir (p. ej. min === max de un sub-tramo); evita duplicados.
  return Array.from(new Set(ticks)).sort((a, b) => a - b);
}

// ---------------------------------------------------------------------------
// Dots
// ---------------------------------------------------------------------------

/** Radio del área de toque de cada punto: 24 px → 48 × 48 px efectivos
 * (FR-063), aunque la marca visible sea de 4–5 px. */
const DOT_HIT_RADIUS = 24;

/**
 * Punto enlazado a su competencia (feature 045, FR-017 / US1-AC4). Es un
 * `<a>` SVG de react-router (foco y clic nativos) con un círculo transparente
 * de 48 px como área de toque y un aro visible al recibir foco de teclado.
 *
 * Enter se maneja de forma explícita (con `preventDefault`, para no navegar
 * dos veces): la activación por teclado de un `<a>` dentro de un `<svg>` no
 * es uniforme entre navegadores y no se puede confiar en ella.
 */
function DotLink({
  href,
  label,
  cx,
  cy,
  children,
}: {
  href: string;
  label: string;
  cx: number;
  cy: number;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <Link
      to={href}
      aria-label={label}
      className="group cursor-pointer outline-none"
      data-testid="history-chart-dot-link"
      onKeyDown={(event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        navigate(href);
      }}
    >
      <circle
        cx={cx}
        cy={cy}
        r={DOT_HIT_RADIUS}
        fill="transparent"
        strokeWidth={2}
        className="stroke-transparent group-focus-visible:stroke-primary"
      />
      {children}
    </Link>
  );
}

function dotLabel(row: ChartRow): string {
  return `Ver competencia: ${row.label}`;
}

function makeRenderDot(audience: HistoryAudience) {
  return function renderDot(props: DotItemDotProps) {
    const { cx, cy, index, payload } = props;
    const row = payload as ChartRow;
    if (cx === undefined || cy === undefined || row?.value == null) return null;
    const mark = <circle cx={cx} cy={cy} r={4} fill="var(--color-primary)" />;
    if (row.eventId == null) {
      return <g key={`history-dot-${index}`}>{mark}</g>;
    }
    return (
      <DotLink
        key={`history-dot-${index}`}
        href={raceEventHref(audience, row.eventId)}
        label={dotLabel(row)}
        cx={cx}
        cy={cy}
      >
        {mark}
      </DotLink>
    );
  };
}

function makeRenderHollowDot(audience: HistoryAudience) {
  return function renderHollowDot(props: DotItemDotProps) {
    const { cx, cy, index, payload } = props;
    const row = payload as ChartRow;
    if (cx === undefined || cy === undefined) return null;
    const mark = (
      <circle
        cx={cx}
        cy={cy}
        r={5}
        fill="var(--color-surface)"
        stroke="var(--color-primary)"
        strokeWidth={2}
        data-testid="history-chart-non-finisher-marker"
      />
    );
    if (row?.eventId == null) {
      return <g key={`history-hollow-dot-${index}`}>{mark}</g>;
    }
    return (
      <DotLink
        key={`history-hollow-dot-${index}`}
        href={raceEventHref(audience, row.eventId)}
        label={dotLabel(row)}
        cx={cx}
        cy={cy}
      >
        {mark}
      </DotLink>
    );
  };
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipLikeProps {
  active?: boolean;
  payload?: Array<{ payload?: unknown }>;
}

function HistoryTooltip(
  props: TooltipLikeProps & { config: HistoryMetricConfig },
) {
  const { active, payload, config } = props;
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
      className="rounded-lg bg-surface-raised px-3 py-2 text-xs shadow-ambient"
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
        <p className="mt-1 text-charcoal">{config.format(row.value)}</p>
      )}
      <p className="text-mid-gray">Parrilla: {formatFieldSize(row.fieldSize)}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function HistoryChart({
  points,
  metric = DEFAULT_HISTORY_METRIC,
  audience = "coach",
  className,
}: HistoryChartProps) {
  // La familia nunca grafica líder/podio, aunque se le pida (ver docstring).
  const effectiveMetric = resolveHistoryMetric(metric, audience);
  const config = HISTORY_METRICS[effectiveMetric];

  const { rows, dashedPairs, categoryChangeMarkers, nonFinisherRows } =
    useMemo(() => buildChartData(points, config), [points, config]);

  // MAJOR 1 (T077 ux-review.md) — el dominio se calcula SOLO con los
  // valores reales (finalistas con dato); los no-finalistas se plotean en
  // su borde inferior, nunca en 0 — ver `buildYDomain`.
  const yDomain = useMemo(() => {
    const realValues = rows
      .filter((r) => !r.isPhantom && r.value != null)
      .map((r) => r.value as number);
    return buildYDomain(realValues, config);
  }, [rows, config]);

  const nonFinisherPlotRows = useMemo(
    () => nonFinisherRows.map((r) => ({ ...r, value: yDomain[0] })),
    [nonFinisherRows, yDomain],
  );

  // Marcas explícitas del eje X — ver `buildXTicks` (bug: el eje dejaba de
  // marcar mitad de la serie con datos multi-temporada).
  const xTicks = useMemo(() => buildXTicks(rows), [rows]);

  // Los puntos enlazan a la competencia según el rol (FR-017).
  const renderDot = useMemo(() => makeRenderDot(audience), [audience]);
  const renderHollowDot = useMemo(
    () => makeRenderHollowDot(audience),
    [audience],
  );

  return (
    <div
      className={cn("space-y-3", className)}
      data-testid="history-chart"
      data-metric={effectiveMetric}
    >
      <p className="text-[11px] text-mid-gray" data-testid="history-chart-axis-hint">
        {config.axisHint}
      </p>

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 16, right: 16, bottom: 8, left: 12 }}>
          <CartesianGrid stroke="var(--color-border-gray)" />
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={xTicks}
            tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
            tickFormatter={(v: number) => formatRaceDateShort(
              new Date(v).toISOString().slice(0, 10),
            )}
          />
          <YAxis
            reversed={config.lowerIsBetter}
            domain={yDomain}
            allowDecimals={!config.integerAxis}
            tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
            tickFormatter={config.formatTick}
            width={70}
          />
          <Tooltip
            content={(tooltipProps: unknown) => (
              <HistoryTooltip
                {...(tooltipProps as TooltipLikeProps)}
                config={config}
              />
            )}
          />

          {config.referenceLabel !== null && (
            <ReferenceLine
              y={0}
              stroke="var(--color-mid-gray)"
              strokeDasharray="4 4"
              label={{
                value: config.referenceLabel,
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
            // `pointerEvents: "none"`: el aro del punto activo se dibuja ENCIMA del
            // enlace mientras hay hover; sin esto se comería el clic.
            activeDot={{ r: 6, pointerEvents: "none" }}
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
