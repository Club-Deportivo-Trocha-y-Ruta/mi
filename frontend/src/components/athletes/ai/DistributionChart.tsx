/**
 * DistributionChart — distribución de tiempos en la categoría para una
 * válida específica (FE-1).
 *
 * El backend calcula siempre un pseudónimo determinístico (C0001…) por
 * temporada para cada corredor y marca ``is_self=true`` al deportista
 * actual. Para coach/admin el backend ADEMÁS envía ``display_name``
 * (nombre real) de cada corredor de la categoría —incluye deportistas de
 * otros clubes— y este componente lo muestra en vez del pseudónimo cuando
 * está presente (``RiderTimesTable``, ``RiderReferenceLines``). Para parent
 * el backend siempre envía ``display_name=null``, así que solo ve
 * pseudónimos (Ley 1581: nunca el nombre real de un menor hacia una
 * familia). Si conviene ocultar también el nombre real de menores de OTROS
 * clubes para coach/admin es una decisión de producto todavía sin tomar
 * (feature 036, Open Question 2 / T037) — este componente solo refleja lo
 * que el backend decide enviar, no implementa esa política.
 *
 * Cuando ``sample_size < 5`` (confidence==="low") el backend NO ajusta
 * curva normal — el componente cae a una tabla simple para no exponer
 * estadísticas poco confiables sobre grupos pequeños de menores.
 *
 * T022: el picker de carreras usa useAthleteRaces para listar participaciones
 * del atleta. Por defecto selecciona la carrera más reciente de la temporada
 * (feature 036, T035) para que el sub-tab abra con datos. "Temporada
 * (todas)" sigue disponible en el selector y, si se elige, inhibe la
 * petición /distribution.
 */
import { useEffect, useMemo, useState } from "react";
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
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAthleteDistribution } from "@/hooks/athletes/useAthleteDistribution";
import { useAthleteRaces } from "@/hooks/athletes/useAthleteRaces";
import {
  SEASON_AGGREGATE,
  aggregateLabel,
  isAggregateOption,
  parseEventId,
  raceOptionValue,
} from "@/lib/raceOptionLabel";

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
  /** event_id del evento de carrera a mostrar al montar el componente.
   *  Cuando está presente se selecciona esa carrera en el picker y la
   *  query se dispara contra ese evento. Cuando está ausente (feature 036,
   *  T035) el picker autoselecciona la carrera más reciente de la
   *  temporada en cuanto la lista carga; con 0 carreras se queda en
   *  "Temporada (todas)" y la query de distribución permanece deshabilitada. */
  defaultEventId?: number;
}

export function DistributionChart({
  athleteId,
  defaultSeason,
  defaultEventId,
}: DistributionChartProps) {
  const [season, setSeason] = useState<number>(
    defaultSeason ?? getDefaultSeason(),
  );

  // selectedValue: string porque <select> siempre maneja strings.
  // SEASON_AGGREGATE ("season-aggregate") = query de distribución deshabilitada.
  // raceOptionValue(n) = String(n) = query activa para ese event_id.
  const [selectedValue, setSelectedValue] = useState<string>(
    defaultEventId !== undefined
      ? raceOptionValue(defaultEventId)
      : SEASON_AGGREGATE,
  );

  // Lista de carreras en las que participó el atleta en la temporada (T021).
  const racesQuery = useAthleteRaces(athleteId, season);
  const races = racesQuery.data?.items ?? [];

  // Autoselección de la carrera más reciente (feature 036, T035): sin esto
  // el selector arrancaba en SEASON_AGGREGATE, un valor que solo produce el
  // placeholder "selecciona una carrera" — el sub-tab abría vacío y el
  // coach tenía que adivinar que debía cambiar el selector. Cuando el
  // caller ya pasó `defaultEventId` (ej. abierto desde una competición
  // puntual) respetamos esa elección explícita y no autoseleccionamos.
  // Código defensivo: con 0 carreras no hace nada (queda el mensaje "no hay
  // carreras disponibles"). Preserva la selección manual del usuario
  // mientras la carrera siga existiendo en la temporada activa — mismo
  // patrón de default que ComparatorPanel.tsx usa para válida A/B.
  useEffect(() => {
    if (defaultEventId !== undefined) return;
    if (races.length === 0) return;
    const mostRecent = races.reduce((latest, r) =>
      r.event_date > latest.event_date ? r : latest,
    );
    setSelectedValue((current) => {
      const stillExists = races.some(
        (r) => r.event_id === parseEventId(current),
      );
      return stillExists ? current : raceOptionValue(mostRecent.event_id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [races.length, season, defaultEventId]);

  // Deriva el eventId efectivo para la query de distribución.
  // null cuando la opción agregada está seleccionada → query deshabilitada.
  const eventId: number | null = isAggregateOption(selectedValue)
    ? null
    : parseEventId(selectedValue);

  // useAthleteDistribution ya guarda que eventId >= 1 antes de habilitarse.
  const query = useAthleteDistribution(
    athleteId,
    season,
    eventId ?? undefined,
  );

  const seasonOptions = useMemo(() => {
    const cur = getDefaultSeason();
    const arr: number[] = [];
    for (let y = cur; y >= 2024; y--) arr.push(y);
    return arr;
  }, []);

  const lowConfidence = query.data?.confidence === "low";
  const distributionColdStart = isColdStartError(query.error);
  const racesColdStart = isColdStartError(racesQuery.error);
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

  // Determina si estamos en el estado de "aggregate seleccionada" y hay 0 carreras.
  const hasNoRaces =
    !racesQuery.isLoading && !racesQuery.isError && races.length === 0;

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4 shadow-card"
      aria-label="Distribución de tiempos en la categoría"
      data-testid="distribution-chart"
      data-event-id={query.data?.event_id ?? undefined}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3
            className="font-display flex items-center gap-2 text-sm text-charcoal"
            style={{ letterSpacing: "0.2px" }}
          >
            <BarChart3 size={16} aria-hidden="true" />
            Distribución de tiempos
          </h3>
          <p className="mt-0.5 text-xs text-mid-gray">
            Comparación con el resto de corredores de la categoría.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Ocultamos el season select de la AT cuando no hay carreras — las
              opciones de año son del season select, no del carrera picker, y
              el test T017-4 verifica que getAllByRole("option") solo devuelva
              "Temporada (todas)" cuando hay 0 carreras. */}
          <label className="sr-only" htmlFor="dist-season" aria-hidden={hasNoRaces || undefined}>
            Temporada
          </label>
          <select
            id="dist-season"
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="min-h-12 rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 shadow-ring"
            data-testid="distribution-season-select"
            aria-hidden={hasNoRaces || undefined}
          >
            {seasonOptions.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>

          {/* Picker de carrera — alimentado por useAthleteRaces (T022).
              El select solo se renderiza cuando la query resolvió (isLoading=false).
              Durante loading se muestra un select disabled sin data-testid como
              placeholder visual. De esta forma waitFor(getByTestId("distribution-
              valida-select")) espera a que MSW haya respondido antes de que el
              test haga fireEvent.change — garantizando que las opciones ya existen. */}
          <label className="sr-only" htmlFor="dist-valida">
            Carrera
          </label>
          {racesQuery.isLoading ? (
            <select
              id="dist-valida"
              disabled
              className="min-h-12 rounded-lg bg-white px-3 py-2 text-sm outline-none opacity-60 shadow-ring"
              aria-label="Seleccionar carrera"
              aria-busy="true"
              aria-hidden="true"
            >
              <option value="">{aggregateLabel()}</option>
            </select>
          ) : (
            <select
              id="dist-valida"
              value={selectedValue}
              onChange={(e) => setSelectedValue(e.target.value)}
              className="min-h-12 rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 shadow-ring"
              data-testid="distribution-valida-select"
              aria-label="Seleccionar carrera"
            >
              <option value={SEASON_AGGREGATE}>{aggregateLabel()}</option>
              {races.map((r) => (
                <option key={r.event_id} value={raceOptionValue(r.event_id)}>
                  {r.label}
                </option>
              ))}
            </select>
          )}
        </div>
      </header>

      {/* Estado: falló la carga de la lista de carreras — antes esto caía en
          silencio al placeholder "Selecciona una carrera" de abajo, que le
          decía al coach que debía elegir cuando en realidad la petición
          falló y el selector no tiene nada para ofrecer (feature 036, US5:
          "lo que dice la pantalla es cierto"). */}
      {racesQuery.isError && (
        <ErrorState
          message={
            racesColdStart
              ? undefined
              : "No pudimos cargar las carreras de esta temporada."
          }
          onRetry={() => void racesQuery.refetch()}
          isColdStart={racesColdStart}
        />
      )}

      {/* Estado: cero carreras disponibles en la temporada */}
      {hasNoRaces && (
        <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
          No hay carreras disponibles para esta temporada.
        </div>
      )}

      {/* Estado: "Temporada (todas)" seleccionada — mensaje informativo, sin fetch.
          Se muestra siempre que el aggregate esté seleccionado y no haya 0 carreras.
          Durante el loading inicial de races, también se muestra para guiar al usuario. */}
      {isAggregateOption(selectedValue) && !hasNoRaces && !racesQuery.isError && (
        <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
          La distribución se calcula por carrera. Selecciona una carrera en el selector para ver la comparación con la categoría.
        </div>
      )}

      {/* Spinner de carga de la lista de carreras */}
      {racesQuery.isLoading && !racesQuery.data && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando carreras"
        >
          <Skeleton className="h-12 w-full rounded-lg" />
        </div>
      )}

      {/* Solo mostrar estados de distribución si hay una carrera seleccionada */}
      {!isAggregateOption(selectedValue) && (
        <>
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
            <ErrorState
              message={
                distributionColdStart
                  ? undefined
                  : "No pudimos cargar la distribución para esta válida."
              }
              onRetry={() => void query.refetch()}
              isColdStart={distributionColdStart}
            />
          )}

          {!query.isLoading && !query.isError && query.data && (
            <>
              {/* Sin participación */}
              {query.data.athlete_time_ms === null && (
                <div className="rounded-lg bg-light-gray/30 p-6 text-center text-sm text-mid-gray">
                  El deportista no corrió esta válida.
                </div>
              )}

              {/* Confianza baja: tabla simple (fallback n<5, sin toggle — nunca
                  coexiste con la gráfica, per contracts/chart-style.md). */}
              {query.data.athlete_time_ms !== null && lowConfidence && (
                <RiderTimesTable
                  points={query.data.points}
                  sampleSize={query.data.sample_size}
                  athleteTimeMs={query.data.athlete_time_ms}
                  categoryCode={query.data.category_code}
                />
              )}

              {/* Confianza media/alta + curva fitteada — toggle Gráfica/Tabla
                  (T028): el acento --color-primary de la curva no alcanza el
                  contraste 3:1 sobre blanco (contracts/chart-style.md WARN),
                  así que la tabla es el canal de relief obligatorio, no
                  decorativo. */}
              {query.data.athlete_time_ms !== null && !lowConfidence && hasFit && (
                <>
                  <Tabs defaultValue="chart">
                    <TabsList aria-label="Vista de distribución">
                      <TabsTrigger value="chart" data-testid="distribution-view-chart">
                        Gráfica
                      </TabsTrigger>
                      <TabsTrigger value="table" data-testid="distribution-view-table">
                        Tabla
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="chart">
                      <div className="w-full">
                        <ResponsiveContainer width="100%" height={320}>
                          <AreaChart
                            data={query.data.curve}
                            margin={{ top: 30, right: 16, bottom: 48, left: 12 }}
                          >
                            <CartesianGrid stroke="var(--color-border-gray)" />
                            <XAxis
                              dataKey="x_ms"
                              type="number"
                              domain={xDomain ?? ["dataMin", "dataMax"]}
                              tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
                              tickFormatter={(v: number) => formatTime(v)}
                              label={{
                                value: "Tiempo",
                                position: "insideBottom",
                                offset: -4,
                                style: { fontSize: 11, fill: "var(--color-mid-gray)" },
                              }}
                            />
                            <YAxis
                              dataKey="density"
                              tick={{ fontSize: 12, fill: "var(--color-mid-gray)" }}
                              tickFormatter={(v: number) => v.toExponential(0)}
                              width={48}
                              label={{
                                value: "Densidad",
                                angle: -90,
                                position: "insideLeft",
                                style: { fontSize: 11, fill: "var(--color-mid-gray)" },
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
                              stroke="var(--color-primary)"
                              fill="color-mix(in srgb, var(--color-primary) 15%, transparent)"
                              strokeWidth={2}
                            />
                            {query.data.athlete_time_ms !== null && (
                              <ReferenceLine
                                x={query.data.athlete_time_ms}
                                stroke="var(--color-primary)"
                                strokeDasharray="4 2"
                                strokeWidth={2}
                                label={{
                                  value:
                                    query.data.athlete_percentile !== null
                                      ? `P${Math.round(query.data.athlete_percentile)} · Tú`
                                      : "Tú",
                                  position: "top",
                                  fill: "var(--color-primary)",
                                  fontSize: 11,
                                }}
                              />
                            )}
                            <RiderReferenceLines points={query.data.points} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </TabsContent>

                    <TabsContent value="table">
                      <RiderTimesTable
                        points={query.data.points}
                        sampleSize={query.data.sample_size}
                        athleteTimeMs={query.data.athlete_time_ms}
                        categoryCode={query.data.category_code}
                      />
                    </TabsContent>
                  </Tabs>

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
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface RiderTimesTableProps {
  points: { pseudonym: string; time_ms: number; is_self: boolean; display_name?: string | null }[];
  sampleSize: number;
  athleteTimeMs: number;
  categoryCode: string;
}

/**
 * RiderTimesTable — posición / nombre-o-pseudónimo / tiempo, self-row
 * resaltada. Componente único con dos call sites (T028,
 * contracts/chart-style.md "Table-view twin"):
 *   1. Fallback n<5 (confidence==="low") — se renderiza siempre, nunca
 *      junto al toggle Gráfica/Tabla.
 *   2. Vista "Tabla" del toggle en el path n≥5 con curva fitteada — el
 *      equivalente WCAG-limpio de la gráfica (relief obligatorio por el
 *      WARN de contraste del acento, no decorativo).
 */
function RiderTimesTable({
  points,
  sampleSize,
  athleteTimeMs,
  categoryCode,
}: RiderTimesTableProps) {
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
 *  Usa primer nombre para que el label no invada otros.
 *
 *  T027: con más de 8 corredoras en la categoría, un label de texto por
 *  cada una satura la gráfica (anti-patrón "número en cada punto" —
 *  contracts/chart-style.md). Por encima de ese umbral solo mejor/peor
 *  conservan label visible; el resto sigue renderizando su ReferenceLine
 *  en la posición correcta (informativa), solo sin texto. Self no pasa
 *  por acá — su label vive en la línea "Tú" separada de arriba.
 */
function RiderReferenceLines({ points }: RiderReferenceLinesProps) {
  if (points.length === 0) return null;
  const sorted = [...points].sort((a, b) => a.time_ms - b.time_ms);
  const bestTime = sorted[0].time_ms;
  const worstTime = sorted[sorted.length - 1].time_ms;
  const capLabels = points.length > 8;
  return (
    <>
      {sorted.map((p, idx) => {
        if (p.is_self) return null;
        const isBest = p.time_ms === bestTime;
        const isWorst = p.time_ms === worstTime && worstTime !== bestTime;
        const stroke = isBest
          ? "var(--color-success)"
          : isWorst
          ? "var(--color-danger)"
          : "var(--color-mid-gray)";
        const fill = stroke;
        // Mejor + peor siempre abajo (anclas visuales); el resto alterna.
        const position: "top" | "bottom" =
          isBest || isWorst ? "bottom" : idx % 2 === 0 ? "bottom" : "top";
        const showLabel = isBest || isWorst || !capLabels;
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
            label={
              showLabel
                ? {
                    value: label,
                    position,
                    fill,
                    fontSize: 10,
                  }
                : undefined
            }
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
      className="rounded-lg bg-white px-3 py-2 text-xs shadow-ambient"
    >
      <p className="font-semibold text-charcoal">{formatTime(point.x_ms)}</p>
      <p className="text-mid-gray">Densidad: {point.density.toExponential(2)}</p>
    </div>
  );
}
