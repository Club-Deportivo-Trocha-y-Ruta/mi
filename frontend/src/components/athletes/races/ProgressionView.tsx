/**
 * ProgressionView — vista «Progresión» de la pestaña «Carreras» (feature 045,
 * US1/US4). Es el cascarón de `HistoryProgressionCard` (feature 044) ampliado:
 *
 *   - pide el historial con `series_kind=all` — las copas van a la línea
 *     (`HistoryChart`) y los campeonatos a tarjetas de lectura
 *     (`ChampionshipReadingCard`, un campeonato es un pelotón distinto: no hay
 *     tendencia que graficar);
 *   - selector de métrica (brecha vs. mediana por defecto) y filtro de
 *     competencia (los grupos de comparación de la 039: una serie por
 *     copa/campeonato — nunca se mezclan pelotones distintos en una línea);
 *   - «texto primero»: chips de temporada, últimos resultados y cambios de
 *     categoría son DOM plano; solo la gráfica es un chunk lazy (recharts),
 *     así la primera pintura en 3G no espera al gráfico;
 *   - `HistoryTable` como alternativa textual debajo.
 *
 * `audience="family"` limita las métricas a mediana, percentil y posición y
 * oculta «Brecha vs. 1.ª posición» del campeonato (Ley 1581 + salvaguarda 045;
 * el backend tampoco envía esas claves a una familia).
 */
import { lazy, Suspense, useMemo, useState } from "react";
import { TrendingUp } from "lucide-react";

import { ChampionshipReadingCard } from "@/components/athletes/ai/ChampionshipReadingCard";
import { CaveatsNote } from "@/components/race/history/CaveatsNote";
import {
  CategoryChangesList,
  summarizeResult,
} from "@/components/race/history/HistoryProgressionCard";
import { HistoryTable } from "@/components/race/history/HistoryTable";
import {
  DEFAULT_HISTORY_METRIC,
  HISTORY_METRICS,
  historyMetricsFor,
  resolveHistoryMetric,
} from "@/components/race/history/historyMetrics";
import type {
  HistoryAudience,
  HistoryMetric,
} from "@/components/race/history/historyMetrics";
import { SeasonCompletionChips } from "@/components/race/history/SeasonCompletionChips";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteRaceHistory } from "@/hooks/race/useAthleteRaceHistory";
import { formatRaceDateShort } from "@/lib/raceHistoryFormat";
import { cn } from "@/lib/utils";
import type { EvolutionPoint } from "@/types/athleteRaceAnalysis.types";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";

const HistoryChart = lazy(() =>
  import("@/components/race/history/HistoryChart").then((m) => ({
    default: m.HistoryChart,
  })),
);

export interface ProgressionViewProps {
  athleteId: number;
  audience: HistoryAudience;
  className?: string;
}

const CAVEATS_NOTE_ID = "progression-caveats-note-anchor";
const ALL_GROUPS = "all";

const SELECT_CLASS = cn(
  "min-h-12 rounded-lg bg-surface-raised px-3 py-2 text-sm text-charcoal outline-none",
  "shadow-ring focus:ring-2 focus:ring-primary/40",
);

interface GroupOption {
  key: string;
  label: string;
}

/** Una opción por serie (copa o campeonato) presente en el historial; copas
 * primero, luego campeonatos, cada bloque por nombre. */
function buildGroupOptions(points: RaceHistoryPoint[]): GroupOption[] {
  const bySeries = new Map<number, RaceHistoryPoint>();
  for (const p of points) {
    if (!bySeries.has(p.series_id)) bySeries.set(p.series_id, p);
  }
  return [...bySeries.values()]
    .sort((a, b) => {
      if (a.series_kind !== b.series_kind) {
        return a.series_kind === "cup" ? -1 : 1;
      }
      return a.series_name.localeCompare(b.series_name, "es");
    })
    .map((p) => ({ key: String(p.series_id), label: p.series_name }));
}

/**
 * Punto de historial → punto de evolución, la forma que lee
 * `ChampionshipReadingCard`. `value` lleva la posición: la tarjeta decide
 * «No completó la prueba» cuando no hay valor NI posición (DNF/DNS/DSQ).
 * `gap_pct` (brecha vs. 1.ª posición) solo existe en el punto de coach — en
 * el de familia la clave está ausente y la tarjeta tampoco la pinta.
 */
function toChampionshipPoint(p: RaceHistoryPoint): EvolutionPoint {
  const base = {
    valida_num: 1,
    event_id: p.event_id,
    event_date: p.event_date,
    value: p.position,
    unit: "rank",
    series_kind: p.series_kind,
    label: p.label,
    series_id: p.series_id,
    series_name: p.series_name,
    field_size: p.field_size,
    percentile: p.percentile,
    position: p.position,
    gap_to_median_pct: p.gap_to_median_pct,
  };
  return "gap_to_winner_pct" in p
    ? { ...base, gap_pct: p.gap_to_winner_pct }
    : base;
}

export function ProgressionView({
  athleteId,
  audience,
  className,
}: ProgressionViewProps) {
  const query = useAthleteRaceHistory(athleteId, "all");
  const [metric, setMetric] = useState<HistoryMetric>(DEFAULT_HISTORY_METRIC);
  const [groupKey, setGroupKey] = useState<string>(ALL_GROUPS);

  const points = useMemo(() => query.data?.points ?? [], [query.data]);
  const groupOptions = useMemo(() => buildGroupOptions(points), [points]);

  // Si el grupo elegido ya no existe (cambió el historial), vuelve a «todas».
  const activeGroupKey = groupOptions.some((g) => g.key === groupKey)
    ? groupKey
    : ALL_GROUPS;
  const visiblePoints = useMemo(
    () =>
      activeGroupKey === ALL_GROUPS
        ? points
        : points.filter((p) => String(p.series_id) === activeGroupKey),
    [points, activeGroupKey],
  );
  const cupPoints = useMemo(
    () => visiblePoints.filter((p) => p.series_kind === "cup"),
    [visiblePoints],
  );
  const championshipPoints = useMemo(
    () =>
      visiblePoints
        .filter((p) => p.series_kind === "championship")
        .sort((a, b) => b.event_date.localeCompare(a.event_date)),
    [visiblePoints],
  );

  const effectiveMetric = resolveHistoryMetric(metric, audience);
  const metricOptions = historyMetricsFor(audience);

  return (
    <section
      className={cn(
        "space-y-4 rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline",
        className,
      )}
      aria-label="Progresión histórica entre temporadas"
      data-testid="progression-view"
    >
      <header>
        <h3
          className="font-display flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <TrendingUp size={16} aria-hidden="true" />
          Progresión histórica
        </h3>
        <p className="mt-0.5 text-xs text-mid-gray">
          {audience === "family"
            ? "Cómo ha cambiado tu hijo o hija entre temporadas de Copa Valle."
            : "Cómo ha cambiado el atleta entre temporadas y competencias."}
        </p>
      </header>

      {query.isLoading && (
        <div role="status" aria-busy="true" aria-label="Cargando progresión histórica">
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
      )}

      {query.isError && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          No pudimos cargar la progresión histórica de este atleta.
        </div>
      )}

      {!query.isLoading && !query.isError && query.data && (
        points.length === 0 ? (
          <p
            className="rounded-lg bg-light-gray/30 p-4 text-center text-sm text-mid-gray"
            data-testid="history-empty"
          >
            Todavía no hay carreras históricas para comparar entre temporadas.
          </p>
        ) : (
          <>
            <SeasonCompletionChips seasons={query.data.seasons} />

            <div>
              <h4 className="text-xs font-semibold text-charcoal">
                Últimos resultados
              </h4>
              <ul
                className="mt-1 space-y-0.5 text-sm text-charcoal"
                aria-label="Últimos resultados"
                data-testid="history-latest-three"
              >
                {[...visiblePoints]
                  .sort((a, b) => b.event_date.localeCompare(a.event_date))
                  .slice(0, 3)
                  .map((p) => (
                    <li key={p.event_id}>
                      {p.label} ({formatRaceDateShort(p.event_date)}) —{" "}
                      {summarizeResult(p)}
                    </li>
                  ))}
              </ul>
            </div>

            <CategoryChangesList points={visiblePoints} audience={audience} />

            <div className="flex flex-wrap items-center gap-2">
              {groupOptions.length > 1 && (
                <>
                  <label className="sr-only" htmlFor="progression-group">
                    Competencia
                  </label>
                  <select
                    id="progression-group"
                    value={activeGroupKey}
                    onChange={(e) => setGroupKey(e.target.value)}
                    className={SELECT_CLASS}
                    data-testid="progression-group-select"
                  >
                    <option value={ALL_GROUPS}>Todas las competencias</option>
                    {groupOptions.map((g) => (
                      <option key={g.key} value={g.key}>
                        {g.label}
                      </option>
                    ))}
                  </select>
                </>
              )}
              {cupPoints.length > 0 && (
                <>
                  <label className="sr-only" htmlFor="progression-metric">
                    Métrica
                  </label>
                  <select
                    id="progression-metric"
                    value={effectiveMetric}
                    onChange={(e) => setMetric(e.target.value as HistoryMetric)}
                    className={SELECT_CLASS}
                    data-testid="progression-metric-select"
                  >
                    {metricOptions.map((m) => (
                      <option key={m} value={m}>
                        {HISTORY_METRICS[m].label}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </div>

            {cupPoints.length > 0 && (
              <div aria-describedby={CAVEATS_NOTE_ID}>
                <Suspense fallback={<Skeleton className="h-72 w-full rounded-lg" />}>
                  <HistoryChart
                    points={cupPoints}
                    metric={effectiveMetric}
                    audience={audience}
                  />
                </Suspense>
              </div>
            )}

            {championshipPoints.length > 0 && (
              <div className="space-y-3" data-testid="progression-championships">
                <h4 className="text-xs font-semibold text-charcoal">
                  Campeonatos
                </h4>
                {championshipPoints.map((p) => (
                  <ChampionshipReadingCard
                    key={p.event_id}
                    point={toChampionshipPoint(p)}
                    group={{ label: p.series_name }}
                    audience={audience}
                  />
                ))}
              </div>
            )}

            <HistoryTable points={visiblePoints} audience={audience} />

            <CaveatsNote id={CAVEATS_NOTE_ID} caveats={query.data.caveats} />
          </>
        )
      )}
    </section>
  );
}
