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
  const totalSec = Math.round(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const mm = m.toString().padStart(2, "0");
  const ss = s.toString().padStart(2, "0");
  return `${h}:${mm}:${ss}`;
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

  /**
   * Dominio del XAxis con padding lateral para que las ReferenceLine de los
   * extremos (mejor/peor tiempo) no queden pegadas al borde del SVG y sus
   * labels sean clipeadas por recharts.
   *
   * Padding = 8% del rango total de la curva, con un mínimo de 1 s (1 000 ms)
   * para evitar padding cero cuando la curva tiene un solo punto.
   */
  const xDomain = useMemo<[number, number] | undefined>(() => {
    if (!query.data || query.data.curve.length === 0) return undefined;
    const xs = query.data.curve.map((p) => p.x_ms);
    const lo = Math.min(...xs);
    const hi = Math.max(...xs);
    const pad = Math.max((hi - lo) * 0.08, 1_000);
    return [lo - pad, hi + pad];
  }, [query.data]);

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
                <ResponsiveContainer width="100%" height={320}>
                  <AreaChart
                    data={query.data.curve}
                    margin={{ top: 30, right: 16, bottom: 48, left: 12 }}
                  >
                    <CartesianGrid stroke="rgba(34,42,53,0.08)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="x_ms"
                      type="number"
                      domain={xDomain ?? ["dataMin", "dataMax"]}
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
                    <RiderReferenceLines points={query.data.points} />
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
  points: { pseudonym: string; time_ms: number; is_self: boolean; display_name?: string | null }[];
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
  const hasDisplayNames = sorted.some((p) => p.display_name != null);
  const nameHeader = hasDisplayNames ? "Nombre" : "Pseudónimo";
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
            <th className="px-3 py-2 font-medium">{nameHeader}</th>
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
              <td className="px-3 py-1.5 font-mono text-xs">
                {p.display_name ?? p.pseudonym}
              </td>
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

// ---------------------------------------------------------------------------
// RiderReferenceLines — marca a CADA corredora sobre la curva
// ---------------------------------------------------------------------------

interface RiderReferenceLinesProps {
  points: { pseudonym: string; time_ms: number; is_self: boolean; display_name?: string | null }[];
}

function shortName(name: string): string {
  const first = name.trim().split(/\s+/)[0];
  return first ?? name;
}

/** Renderiza una ReferenceLine por corredora (excluye self — ya tiene su
 *  propia línea "Tú" arriba). Color: verde=mejor, rojo=peor, gris=resto.
 *  Labels alternados arriba/abajo según índice para reducir solapamiento.
 *  Usa primer nombre para que el label no invada otros. */
function RiderReferenceLines({ points }: RiderReferenceLinesProps) {
  if (points.length === 0) return null;
  const sorted = [...points].sort((a, b) => a.time_ms - b.time_ms);
  const bestTime = sorted[0].time_ms;
  const worstTime = sorted[sorted.length - 1].time_ms;
  return (
    <>
      {sorted.map((p, idx) => {
        if (p.is_self) return null;
        const isBest = p.time_ms === bestTime;
        const isWorst = p.time_ms === worstTime && worstTime !== bestTime;
        const stroke = isBest ? "#16a34a" : isWorst ? "#dc2626" : "#94a3b8";
        const fill = isBest ? "#15803d" : isWorst ? "#b91c1c" : "#64748b";
        // Mejor + peor siempre abajo (anclas visuales); el resto alterna.
        const position: "top" | "bottom" =
          isBest || isWorst ? "bottom" : idx % 2 === 0 ? "bottom" : "top";
        const label = p.display_name
          ? shortName(p.display_name)
          : p.pseudonym;
        return (
          <ReferenceLine
            key={`${p.pseudonym}-${p.time_ms}`}
            x={p.time_ms}
            stroke={stroke}
            strokeDasharray="3 3"
            strokeWidth={1.5}
            label={{
              value: label,
              position,
              fill,
              fontSize: 10,
            }}
          />
        );
      })}
    </>
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
        value={stddevMs !== null ? formatTime(stddevMs) : "—"}
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
