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
import { Calendar, Info } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteEvolution } from "@/hooks/athletes/useAthleteEvolution";
import { cn } from "@/lib/utils";
import { EvolutionMetric } from "@/types/athleteRaceAnalysis.types";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

function formatMs(ms: number, unit: string): string {
  if (unit === "ms") {
    if (ms >= 60_000) {
      const totalSec = ms / 1000;
      const min = Math.floor(totalSec / 60);
      const sec = (totalSec - min * 60).toFixed(1);
      return `${min}:${sec.padStart(4, "0")}`;
    }
    return `${(ms / 1000).toFixed(2)} s`;
  }
  if (unit === "rank") return `P${Math.round(ms)}`;
  if (unit === "pct") return `${Math.round(ms)}`;
  return `${ms} ${unit}`;
}

function formatValue(value: number | null, unit: string): string {
  if (value === null) return "—";
  return formatMs(value, unit);
}

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

  const query = useAthleteEvolution(athleteId, season, metric);

  // Datos: solo puntos finitos (con valor numérico) para el LineChart.
  // Keyed por event_id para que copa y campeonato con mismo valida_num
  // no colisionen en el eje categorical.
  const chartData = useMemo(() => {
    if (!query.data) return [];
    return query.data.series
      .filter((p) => p.value !== null)
      .map((p) => ({
        event_id: p.event_id,
        label: p.label,
        series_kind: p.series_kind,
        event_date: p.event_date,
        value: p.value as number,
      }));
  }, [query.data]);

  // Mapa event_id → label para el tickFormatter del XAxis.
  const labelByEventId = useMemo(() => {
    if (!query.data) return new Map<number, string>();
    return new Map(query.data.series.map((p) => [p.event_id, p.label]));
  }, [query.data]);

  const dnfPoints = useMemo(() => {
    if (!query.data) return [];
    return query.data.series.filter((p) => p.value === null);
  }, [query.data]);

  const isRanking = metric === EvolutionMetric.RANKING;
  const unit = query.data?.series[0]?.unit ?? (isRanking ? "rank" : "ms");

  const seasonOptions = buildSeasonOptions(getDefaultSeason());

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4"
      style={{ boxShadow: cardShadow }}
      aria-label="Gráfica de evolución por temporada"
      data-testid="evolution-chart"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3
            className="flex items-center gap-2 text-sm text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
          >
            <Calendar size={16} aria-hidden="true" />
            Evolución
          </h3>
          <p className="mt-0.5 text-xs text-mid-gray">
            Tendencia a lo largo de las válidas de la temporada.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="evo-season">
            Temporada
          </label>
          <select
            id="evo-season"
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
            className="rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            data-testid="evolution-metric-select"
          >
            {Object.entries(METRIC_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
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
          {chartData.length === 0 ? (
            <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
              Sin datos para esta temporada/métrica.
            </div>
          ) : (
            <div className="w-full">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart
                  data={chartData}
                  margin={{ top: 8, right: 16, bottom: 8, left: 12 }}
                >
                  <CartesianGrid stroke="rgba(34,42,53,0.08)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="event_id"
                    tick={{ fontSize: 12, fill: "#5a6172" }}
                    tickFormatter={(v: number) =>
                      labelByEventId.get(v) ?? String(v)
                    }
                    label={{
                      value: "Evento",
                      position: "insideBottom",
                      offset: -4,
                      style: { fontSize: 11, fill: "#5a6172" },
                    }}
                  />
                  <YAxis
                    tick={{ fontSize: 12, fill: "#5a6172" }}
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
                    stroke="#131316"
                    strokeWidth={2}
                    dot={{ r: 4, fill: "#131316" }}
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
          )}

          {/* Disclaimer si confidence baja */}
          {query.data.confidence === "low" && (
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

          {dnfPoints.length > 0 && (
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
      className="rounded-lg bg-white px-3 py-2 text-xs"
      style={{ boxShadow: "rgba(34, 42, 53, 0.15) 0px 2px 8px" }}
    >
      <p className="font-semibold text-charcoal">{point.label}</p>
      <p className="text-mid-gray">{point.event_date}</p>
      <p className="mt-1 text-charcoal">{formatValue(point.value, unit)}</p>
    </div>
  );
}
