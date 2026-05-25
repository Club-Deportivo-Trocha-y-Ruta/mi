/**
 * DistributionChart — distribución de tiempos en la categoría para una
 * válida específica (FE-1).
 *
 * El backend pseudonimiza cada corredor con un código determinístico
 * (C0001…) por temporada — nunca expone nombres reales. Marca como
 * ``is_self=true`` al deportista actual.
 *
 * Cuando ``sample_size < 5`` (confidence==="low") el backend NO ajusta
 * curva normal — el componente cae a una tabla simple para no exponer
 * estadísticas poco confiables sobre grupos pequeños de menores.
 */
import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BarChart3, Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteDistribution } from "@/hooks/athletes/useAthleteDistribution";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const VALIDA_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "I" },
  { value: 2, label: "II" },
  { value: 3, label: "III" },
  { value: 4, label: "IV" },
  { value: 5, label: "V" },
  { value: 6, label: "VI" },
  { value: 7, label: "VII" },
  { value: 99, label: "Cto. Dep." },
];

function getDefaultSeason(): number {
  return new Date().getFullYear();
}

function formatTime(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  const totalSec = ms / 1000;
  const min = Math.floor(totalSec / 60);
  const sec = (totalSec - min * 60).toFixed(1);
  return `${min}:${sec.padStart(4, "0")}`;
}

interface DistributionChartProps {
  athleteId: number;
  defaultSeason?: number;
  defaultValidaNum?: number;
}

export function DistributionChart({
  athleteId,
  defaultSeason,
  defaultValidaNum,
}: DistributionChartProps) {
  const [season, setSeason] = useState<number>(
    defaultSeason ?? getDefaultSeason(),
  );
  const [validaNum, setValidaNum] = useState<number>(
    defaultValidaNum ?? 1,
  );

  const query = useAthleteDistribution(athleteId, season, validaNum);

  const seasonOptions = useMemo(() => {
    const cur = getDefaultSeason();
    const arr: number[] = [];
    for (let y = cur; y >= 2024; y--) arr.push(y);
    return arr;
  }, []);

  const lowConfidence = query.data?.confidence === "low";
  const hasFit =
    !!query.data &&
    query.data.curve.length > 0 &&
    query.data.mean_ms !== null &&
    query.data.stddev_ms !== null;

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4"
      style={{ boxShadow: cardShadow }}
      aria-label="Distribución de tiempos en la categoría"
      data-testid="distribution-chart"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3
            className="flex items-center gap-2 text-sm text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
          >
            <BarChart3 size={16} aria-hidden="true" />
            Distribución de tiempos
          </h3>
          <p className="mt-0.5 text-xs text-mid-gray">
            Comparación pseudonimizada vs. la categoría.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="dist-season">
            Temporada
          </label>
          <select
            id="dist-season"
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            data-testid="distribution-season-select"
          >
            {seasonOptions.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="dist-valida">
            Válida
          </label>
          <select
            id="dist-valida"
            value={validaNum}
            onChange={(e) => setValidaNum(Number(e.target.value))}
            className="rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            data-testid="distribution-valida-select"
          >
            {VALIDA_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {query.isLoading && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando distribución"
        >
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {query.isError && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          No pudimos cargar la distribución para esta válida.
        </div>
      )}

      {!query.isLoading && !query.isError && query.data && (
        <>
          {/* Sin participación */}
          {query.data.athlete_time_ms === null && (
            <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
              El deportista no corrió esta válida.
            </div>
          )}

          {/* Confianza baja: tabla simple */}
          {query.data.athlete_time_ms !== null && lowConfidence && (
            <LowConfidenceTable
              points={query.data.points}
              sampleSize={query.data.sample_size}
              athleteTimeMs={query.data.athlete_time_ms}
              categoryCode={query.data.category_code}
            />
          )}

          {/* Confianza media/alta + curva fitteada */}
          {query.data.athlete_time_ms !== null && !lowConfidence && hasFit && (
            <>
              <div className="w-full">
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart
                    data={query.data.curve}
                    margin={{ top: 30, right: 16, bottom: 8, left: 12 }}
                  >
                    <CartesianGrid stroke="rgba(34,42,53,0.08)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="x_ms"
                      type="number"
                      domain={["dataMin", "dataMax"]}
                      tick={{ fontSize: 12, fill: "#5a6172" }}
                      tickFormatter={(v: number) => formatTime(v)}
                      label={{
                        value: "Tiempo",
                        position: "insideBottom",
                        offset: -4,
                        style: { fontSize: 11, fill: "#5a6172" },
                      }}
                    />
                    <YAxis
                      dataKey="density"
                      tick={{ fontSize: 12, fill: "#5a6172" }}
                      tickFormatter={(v: number) => v.toExponential(0)}
                      width={48}
                      label={{
                        value: "Densidad",
                        angle: -90,
                        position: "insideLeft",
                        style: { fontSize: 11, fill: "#5a6172" },
                      }}
                    />
                    <Tooltip
                      content={(props: unknown) => (
                        <DistributionTooltip {...(props as TooltipLikeProps)} />
                      )}
                    />
                    <Area
                      type="monotone"
                      dataKey="density"
                      stroke="#131316"
                      fill="rgba(19,19,22,0.15)"
                      strokeWidth={2}
                    />
                    {query.data.athlete_time_ms !== null && (
                      <ReferenceLine
                        x={query.data.athlete_time_ms}
                        stroke="#0ea5e9"
                        strokeDasharray="4 2"
                        strokeWidth={2}
                        label={{
                          value:
                            query.data.athlete_percentile !== null
                              ? `P${Math.round(query.data.athlete_percentile)} · Tú`
                              : "Tú",
                          position: "top",
                          fill: "#0369a1",
                          fontSize: 11,
                        }}
                      />
                    )}
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <StatsSummary
                meanMs={query.data.mean_ms}
                stddevMs={query.data.stddev_ms}
                zScore={query.data.athlete_z_score}
                percentile={query.data.athlete_percentile}
                sampleSize={query.data.sample_size}
                categoryCode={query.data.category_code}
              />
            </>
          )}

          {lowConfidence && (
            <div
              role="note"
              className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900"
            >
              <Info size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              <p>
                Muestra insuficiente (n&lt;5) — no ajustamos curva normal para no
                exponer estadísticas poco confiables sobre grupos pequeños.
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface LowConfidenceTableProps {
  points: { pseudonym: string; time_ms: number; is_self: boolean }[];
  sampleSize: number;
  athleteTimeMs: number;
  categoryCode: string;
}

function LowConfidenceTable({
  points,
  sampleSize,
  athleteTimeMs,
  categoryCode,
}: LowConfidenceTableProps) {
  const sorted = [...points].sort((a, b) => a.time_ms - b.time_ms);
  return (
    <div className="space-y-3">
      <p className="text-xs text-mid-gray">
        Categoría {categoryCode} · {sampleSize}{" "}
        {sampleSize === 1 ? "corredor" : "corredores"}
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-mid-gray">
            <th className="px-3 py-2 font-medium">Posición</th>
            <th className="px-3 py-2 font-medium">Pseudónimo</th>
            <th className="px-3 py-2 font-medium">Tiempo</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr
              key={`${p.pseudonym}-${i}`}
              className={
                p.is_self
                  ? "bg-blue-50 font-medium text-blue-900"
                  : "text-charcoal"
              }
            >
              <td className="px-3 py-1.5">{i + 1}</td>
              <td className="px-3 py-1.5 font-mono text-xs">{p.pseudonym}</td>
              <td className="px-3 py-1.5">
                {formatTime(p.time_ms)}{" "}
                {p.is_self && <span className="ml-1 text-xs">· Tú</span>}
              </td>
            </tr>
          ))}
          {sorted.length === 0 && athleteTimeMs !== null && (
            <tr className="bg-blue-50 font-medium text-blue-900">
              <td className="px-3 py-1.5">1</td>
              <td className="px-3 py-1.5 font-mono text-xs">—</td>
              <td className="px-3 py-1.5">
                {formatTime(athleteTimeMs)}{" "}
                <span className="ml-1 text-xs">· Tú</span>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

interface StatsSummaryProps {
  meanMs: number | null;
  stddevMs: number | null;
  zScore: number | null;
  percentile: number | null;
  sampleSize: number;
  categoryCode: string;
}

function StatsSummary({
  meanMs,
  stddevMs,
  zScore,
  percentile,
  sampleSize,
  categoryCode,
}: StatsSummaryProps) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label="Categoría" value={categoryCode} />
      <Stat label="N corredores" value={String(sampleSize)} />
      <Stat
        label="Media (μ)"
        value={meanMs !== null ? formatTime(meanMs) : "—"}
      />
      <Stat
        label="Desv. (σ)"
        value={
          stddevMs !== null ? `${(stddevMs / 1000).toFixed(1)} s` : "—"
        }
      />
      {zScore !== null && (
        <Stat label="z-score" value={zScore.toFixed(2)} />
      )}
      {percentile !== null && (
        <Stat
          label="Percentil"
          value={`P${Math.round(percentile)}`}
          badge={
            percentile >= 75
              ? "success"
              : percentile >= 50
              ? "info"
              : percentile >= 25
              ? "warning"
              : "destructive"
          }
        />
      )}
    </dl>
  );
}

function Stat({
  label,
  value,
  badge,
}: {
  label: string;
  value: string;
  badge?: "success" | "info" | "warning" | "destructive";
}) {
  return (
    <div className="rounded-lg bg-light-gray/30 px-3 py-2">
      <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm font-semibold text-charcoal">
        {badge ? <Badge variant={badge}>{value}</Badge> : value}
      </dd>
    </div>
  );
}

/** Shape laxo del props del Tooltip de recharts (ver EvolutionChart.tsx
 * para la nota completa sobre por qué no usamos el generic upstream). */
interface TooltipLikeProps {
  active?: boolean;
  payload?: Array<{ payload?: unknown }>;
}

function DistributionTooltip(props: TooltipLikeProps) {
  const { active, payload } = props;
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload as { x_ms: number; density: number };
  return (
    <div
      className="rounded-lg bg-white px-3 py-2 text-xs"
      style={{ boxShadow: "rgba(34, 42, 53, 0.15) 0px 2px 8px" }}
    >
      <p className="font-semibold text-charcoal">{formatTime(point.x_ms)}</p>
      <p className="text-mid-gray">Densidad: {point.density.toExponential(2)}</p>
    </div>
  );
}
