/**
 * EvolutionChart — serie temporal por temporada del deportista (FE-1).
 *
 * Permite al usuario elegir temporada y métrica:
 *   - podium_gap_ms  → diferencia al P1 (ms)  · menor=mejor
 *   - ranking        → posición en categoría · menor=mejor (eje invertido)
 *   - time_ms        → tiempo total (ms)      · menor=mejor
 *
 * Si confidence==="low" (serie con n<3) mostramos un disclaimer claro:
 * el atleta tiene muy pocos datos para concluir tendencia.
 *
 * Cada punto se keya por event_id para que copa (Válida I) y campeonato
 * (mismo valida_num=1) nunca colisionen en el eje categorical.
 */
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DotItemDotProps } from "recharts";
import { Calendar, Info, LayoutGrid, Table2 } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAthleteEvolution } from "@/hooks/athletes/useAthleteEvolution";
import { cn } from "@/lib/utils";
import { confidenceForPoints } from "@/lib/insights";
import { EvolutionMetric } from "@/types/athleteRaceAnalysis.types";
import type {
  ComparisonGroupOption,
  EvolutionPoint,
} from "@/types/athleteRaceAnalysis.types";
import { ChampionshipReadingCard } from "@/components/athletes/ai/ChampionshipReadingCard";
import { formatMs, formatValue } from "@/lib/evolutionFormat";

interface EvolutionChartProps {
  athleteId: number;
  defaultSeason?: number;
}

const METRIC_LABELS: Record<EvolutionMetric, string> = {
  [EvolutionMetric.PODIUM_GAP_MS]: "Diferencia al podio",
  [EvolutionMetric.RANKING]: "Posición en categoría",
  [EvolutionMetric.TIME_MS]: "Tiempo total",
  [EvolutionMetric.PERCENTILE]: "Percentil categoría",
};

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

function buildSeasonOptions(currentSeason: number): number[] {
  const start = 2024;
  const out: number[] = [];
  for (let y = currentSeason; y >= start; y--) out.push(y);
  return out;
}

export function EvolutionChart({
  athleteId,
  defaultSeason,
}: EvolutionChartProps) {
  const [season, setSeason] = useState<number>(
    defaultSeason ?? getDefaultSeason(),
  );
  const [metric, setMetric] = useState<EvolutionMetric>(
    EvolutionMetric.PODIUM_GAP_MS,
  );
  // Feature 039 (D6/D4) — grupo de comparación elegido explícitamente por
  // el usuario en el selector "Competencia". `undefined` = sin elección
  // explícita todavía: se pide la temporada completa (sin `series_id`) y
  // el grupo por defecto (primera copa, si no hay copas el primer
  // campeonato) se resuelve filtrando esa respuesta en el cliente — así
  // el render inicial no paga una segunda ida y vuelta al backend.
  // Cambiar de temporada resetea la elección (data-model.md §8).
  const [selectedSeriesId, setSelectedSeriesId] = useState<
    number | undefined
  >(undefined);

  const query = useAthleteEvolution(athleteId, season, metric, selectedSeriesId);

  const groups: ComparisonGroupOption[] = query.data?.groups ?? [];

  const defaultGroupId = useMemo(() => {
    if (groups.length === 0) return undefined;
    const firstCup = groups.find((g) => g.kind === "cup");
    return (firstCup ?? groups[0]).series_id;
  }, [groups]);

  const activeGroupId = selectedSeriesId ?? defaultGroupId;
  const activeGroup = groups.find((g) => g.series_id === activeGroupId);
  const isChampionshipView = activeGroup?.kind === "championship";

  // Serie a mostrar: si el backend ya filtró (pedimos con `series_id`,
  // `selected_group` viene poblado) usamos `series` tal cual. Si no
  // (respuesta sin filtrar, temporada completa) filtramos en el cliente
  // por el grupo activo — con fallback a la serie completa cuando el
  // filtro no matchea nada (fixtures anteriores a esta feature, cuyos
  // puntos no traen `series_id`: back-compat, contracts/evolution-api.md
  // "clients that ignore groups keep working").
  const displaySeries = useMemo((): EvolutionPoint[] => {
    if (!query.data) return [];
    if (query.data.selected_group || activeGroupId === undefined) {
      return query.data.series;
    }
    const filtered = query.data.series.filter(
      (p) => p.series_id === activeGroupId,
    );
    return filtered.length > 0 ? filtered : query.data.series;
  }, [query.data, activeGroupId]);

  // Datos: solo puntos finitos (con valor numérico) para el LineChart.
  // Keyed por event_id para que copa y campeonato con mismo valida_num
  // no colisionen en el eje categorical.
  const chartData = useMemo(
    () => displaySeries.filter((p) => p.value !== null).map(toChartPoint),
    [displaySeries],
  );

  // Mapa event_id → label para el tickFormatter del XAxis.
  const labelByEventId = useMemo(() => {
    return new Map(displaySeries.map((p) => [p.event_id, p.label]));
  }, [displaySeries]);

  const dnfPoints = useMemo(() => {
    return displaySeries.filter((p) => p.value === null);
  }, [displaySeries]);

  // Feature 039 (F-2 fix) — el aviso de confianza baja debe reflejar el
  // grupo mostrado, no la temporada completa. Cuando la respuesta llega
  // sin filtrar (`selected_group` null: sin elección explícita todavía)
  // `query.data.confidence` está calculado sobre TODA la temporada — lo
  // derivamos en cliente sobre `displaySeries` (el grupo por defecto ya
  // resuelto) con los mismos umbrales que el backend
  // (`confidenceForPoints`). Una vez que el usuario elige una `series_id`
  // explícita, el backend ya filtra y su `confidence` es correcto para
  // ese grupo — se usa tal cual.
  const effectiveConfidence = query.data?.selected_group
    ? query.data.confidence
    : confidenceForPoints(displaySeries);

  const isRanking = metric === EvolutionMetric.RANKING;
  const unit = query.data?.series[0]?.unit ?? (isRanking ? "rank" : "ms");

  const seasonOptions = buildSeasonOptions(getDefaultSeason());

  const subtitle = isChampionshipView
    ? "Resultado frente a su propio pelotón."
    : activeGroup
      ? `Tendencia a lo largo de las válidas de ${activeGroup.label}.`
      : "Tendencia a lo largo de las válidas de la temporada.";

  return (
    <section
      className={cn("rounded-xl bg-white p-5 space-y-4", "shadow-card")}
      aria-label="Gráfica de evolución por temporada"
      data-testid="evolution-chart"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3
            className="font-display flex items-center gap-2 text-sm text-charcoal"
            style={{ letterSpacing: "0.2px" }}
          >
            <Calendar size={16} aria-hidden="true" />
            Evolución
          </h3>
          <p className="mt-0.5 text-xs text-mid-gray">{subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="evo-season">
            Temporada
          </label>
          <select
            id="evo-season"
            value={season}
            onChange={(e) => {
              setSeason(Number(e.target.value));
              // Feature 039 (data-model.md §8) — cambiar de temporada
              // resetea la elección de grupo: el default (primera copa)
              // se vuelve a resolver contra los grupos de la temporada
              // nueva.
              setSelectedSeriesId(undefined);
            }}
            className={cn(
              "min-h-12 rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
              "shadow-ring",
            )}
            data-testid="evolution-season-select"
          >
            {seasonOptions.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="evo-metric">
            Métrica
          </label>
          <select
            id="evo-metric"
            value={metric}
            onChange={(e) => setMetric(e.target.value as EvolutionMetric)}
            className={cn(
              "min-h-12 rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
              "shadow-ring",
            )}
            data-testid="evolution-metric-select"
          >
            {Object.entries(METRIC_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
          {groups.length > 0 && (
            <>
              <label className="sr-only" htmlFor="evo-group">
                Competencia
              </label>
              <select
                id="evo-group"
                value={activeGroupId ?? ""}
                onChange={(e) => setSelectedSeriesId(Number(e.target.value))}
                className={cn(
                  "min-h-12 rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40",
                  "shadow-ring",
                )}
                data-testid="evolution-group-select"
              >
                {groups.map((g) => (
                  <option key={g.series_id} value={g.series_id}>
                    {g.label}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
      </header>

      {query.isLoading && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando evolución"
        >
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {query.isError && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          No pudimos cargar la evolución para esta temporada.
        </div>
      )}

      {!query.isLoading && !query.isError && query.data && (
        <>
          {isChampionshipView ? (
            // Feature 039 (D5) — un grupo de campeonato tiene un único
            // evento (INV-2): se lee como tarjeta de estadísticas + la
            // tabla twin, nunca como gráfica de un solo punto.
            <div className="space-y-3">
              {displaySeries[0] && activeGroup ? (
                <>
                  <ChampionshipReadingCard
                    point={displaySeries[0]}
                    group={activeGroup}
                  />
                  <EvolutionTable
                    points={displaySeries.map(toChartPoint)}
                    unit={unit}
                  />
                </>
              ) : (
                <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
                  Sin datos para esta temporada/métrica.
                </div>
              )}
            </div>
          ) : chartData.length === 0 ? (
            <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
              Sin datos para esta temporada/métrica.
            </div>
          ) : (
            <Tabs defaultValue="chart" className="w-full">
              <TabsList aria-label="Vista de evolución" data-testid="evolution-view-tabs">
                <TabsTrigger value="chart" data-testid="evolution-tab-chart" className="gap-1.5">
                  <LayoutGrid size={14} aria-hidden="true" />
                  Gráfica
                </TabsTrigger>
                <TabsTrigger value="table" data-testid="evolution-tab-table" className="gap-1.5">
                  <Table2 size={14} aria-hidden="true" />
                  Tabla
                </TabsTrigger>
              </TabsList>

              <TabsContent value="chart">
                <div className="w-full">
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart
                      data={chartData}
                      margin={{ top: 8, right: 16, bottom: 8, left: 12 }}
                    >
                      <CartesianGrid stroke="var(--color-border-gray)" />
                      <XAxis
                        dataKey="event_id"
                        tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
                        tickFormatter={(v: number) =>
                          labelByEventId.get(v) ?? String(v)
                        }
                        label={{
                          value: "Evento",
                          position: "insideBottom",
                          offset: -4,
                          style: { fontSize: 11, fill: "var(--color-mid-gray)" },
                        }}
                      />
                      <YAxis
                        tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
                        reversed={isRanking}
                        tickFormatter={(v: number) => formatMs(v, unit)}
                        width={70}
                      />
                      <Tooltip
                        content={(props: unknown) => (
                          <EvolutionTooltip
                            {...(props as TooltipLikeProps)}
                            unit={unit}
                          />
                        )}
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="var(--color-primary)"
                        strokeWidth={2}
                        dot={renderEvolutionDot}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>

                  {/* Leyenda accesible de etiquetas del eje X.
                      Expone los labels en el DOM para accesibilidad y para que
                      el campeonato ("Cto. Dep.") sea identificable sin depender
                      del SVG de recharts. */}
                  <ol
                    aria-label="Etiquetas del eje de evolución"
                    className="mt-2 flex flex-wrap gap-x-3 gap-y-1 justify-center"
                  >
                    {chartData.map((entry) => (
                      <li
                        key={entry.event_id}
                        className={cn(
                          "text-[10px] text-mid-gray",
                          entry.series_kind === "championship" &&
                            "font-medium text-amber-700",
                        )}
                      >
                        {entry.label}
                      </li>
                    ))}
                  </ol>
                </div>
              </TabsContent>

              <TabsContent value="table">
                <EvolutionTable points={chartData} unit={unit} />
              </TabsContent>
            </Tabs>
          )}

          {/* Disclaimer si confidence baja — no aplica a un campeonato: es
              una sola carrera leída como tarjeta, no una tendencia. */}
          {!isChampionshipView && effectiveConfidence === "low" && (
            <div
              role="note"
              className={cn(
                "flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900",
              )}
            >
              <Info size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              <p>
                Muestra insuficiente (n&lt;3) — la tendencia mostrada puede no
                ser representativa. Esperamos más válidas para ganar confianza.
              </p>
            </div>
          )}

          {/* El "no finalizó" de un campeonato ya lo cubre el estado propio
              de ChampionshipReadingCard ("No completó la prueba."). */}
          {!isChampionshipView && dnfPoints.length > 0 && (
            <div className="rounded-lg bg-light-gray/30 px-3 py-2 text-xs text-mid-gray">
              <span className="font-medium">No finalizó:</span>{" "}
              {dnfPoints.map((p) => p.label).join(", ")}
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Custom dot — marca el punto del campeonato con un diamante distintivo
// (T030). El resto de puntos mantiene un círculo simple en --color-primary.
// ---------------------------------------------------------------------------

interface EvolutionChartPoint {
  event_id: number;
  label: string;
  series_kind: string;
  /** Feature 039 (D7) — level-aware, alimenta el texto del ChampionshipDot
   *  y de los twins de leyenda/tabla. Ausente en fixtures previas a la
   *  feature (fallback a "Cto. Dep." en `championshipDotLabel`). */
  series_level?: string;
  event_date: string;
  value: number | null;
}

/** Mapea un `EvolutionPoint` de la API al shape mínimo que usan el chart,
 *  la leyenda `<ol>` y la tabla — reutilizado tanto en la vista de copa
 *  (con `value` filtrado a no-nulo) como en la tarjeta de campeonato (un
 *  único punto, puede ser DNF). */
function toChartPoint(p: EvolutionPoint): EvolutionChartPoint {
  return {
    event_id: p.event_id,
    label: p.label,
    series_kind: p.series_kind,
    series_level: p.series_level,
    event_date: p.event_date,
    value: p.value,
  };
}

/** "Cto. Dep." / "Cto. Nal." según `series_level` (D7) — "departmental" por
 *  defecto para fixtures que aún no traen el campo. */
function championshipDotLabel(seriesLevel?: string): string {
  return seriesLevel === "national" ? "Cto. Nal." : "Cto. Dep.";
}

/** Render function pasado a `<Line dot={...}>` — recharts invoca esto por
 *  cada punto con `payload` = la fila de `chartData` correspondiente. */
function renderEvolutionDot(props: DotItemDotProps) {
  const { cx, cy, index, payload } = props;
  if (cx === undefined || cy === undefined) return null;
  const point = payload as EvolutionChartPoint;
  const key = `evo-dot-${index}`;

  if (point?.series_kind === "championship") {
    return (
      <ChampionshipDot
        key={key}
        cx={cx}
        cy={cy}
        label={championshipDotLabel(point.series_level)}
      />
    );
  }

  return (
    <circle key={key} cx={cx} cy={cy} r={4} fill="var(--color-primary)" />
  );
}

/** Marcador diamante ("Cto. Dep." / "Cto. Nal.") — contracts/chart-style.md
 *  §"Championship on-point marking". Mismo color que la serie propia
 *  (identidad, no polaridad); anillo de 2px en el color de superficie para
 *  legibilidad sobre la línea; etiqueta directa además de (no en
 *  reemplazo de) la leyenda `<ol>` accesible. */
function ChampionshipDot({
  cx,
  cy,
  label,
}: {
  cx: number;
  cy: number;
  label: string;
}) {
  const half = 6; // radio ~6 → diamante de 12x12px, sobre el piso de 8px
  return (
    <g>
      <rect
        x={cx - half}
        y={cy - half}
        width={half * 2}
        height={half * 2}
        fill="var(--color-primary)"
        stroke="var(--color-surface)"
        strokeWidth={2}
        transform={`rotate(45 ${cx} ${cy})`}
      />
      <text
        x={cx}
        y={cy - half - 6}
        textAnchor="middle"
        fontSize={10}
        fontWeight={600}
        fill="var(--color-charcoal)"
      >
        {label}
      </text>
    </g>
  );
}

// ---------------------------------------------------------------------------
// Table-view twin (T031) — misma información que el tooltip (label / fecha
// del evento / valor), fila del campeonato marcada igual que la leyenda
// `<ol>` de arriba (ámbar). Es la salida obligatoria del WARN de contraste
// del accent sobre superficie blanca (contracts/chart-style.md).
// ---------------------------------------------------------------------------

interface EvolutionTableProps {
  points: EvolutionChartPoint[];
  unit: string;
}

function EvolutionTable({ points, unit }: EvolutionTableProps) {
  return (
    <table className="w-full text-sm" data-testid="evolution-table">
      <caption className="sr-only">
        Evolución por temporada — vista de tabla
      </caption>
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-mid-gray">
          <th className="px-3 py-2 font-medium">Evento</th>
          <th className="px-3 py-2 font-medium">Fecha</th>
          <th className="px-3 py-2 font-medium">Valor</th>
        </tr>
      </thead>
      <tbody>
        {points.map((p) => (
          <tr
            key={p.event_id}
            className={cn(
              "text-charcoal",
              p.series_kind === "championship" &&
                "font-medium text-amber-700",
            )}
          >
            <td className="px-3 py-1.5">{p.label}</td>
            <td className="px-3 py-1.5">{p.event_date}</td>
            <td className="px-3 py-1.5">{formatValue(p.value, unit)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

/** Shape laxo del props que pasa recharts al ``content`` del Tooltip.
 * Lo declaramos así para evitar tirar de los generics complejos
 * ``TooltipContentProps<TValue, TName>`` que en v3.8 no aceptan
 * estrechar los tipos sin terminar en errores irreconciliables. */
interface TooltipLikeProps {
  active?: boolean;
  payload?: Array<{ payload?: unknown }>;
}

interface EvolutionTooltipExtra {
  unit: string;
}

function EvolutionTooltip(
  props: TooltipLikeProps & EvolutionTooltipExtra,
) {
  const { active, payload, unit } = props;
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload as {
    label: string;
    event_date: string;
    value: number;
  };
  return (
    <div
      className={cn("rounded-lg bg-white px-3 py-2 text-xs", "shadow-ambient")}
    >
      <p className="font-semibold text-charcoal">{point.label}</p>
      <p className="text-mid-gray">{point.event_date}</p>
      <p className="mt-1 text-charcoal">{formatValue(point.value, unit)}</p>
    </div>
  );
}
