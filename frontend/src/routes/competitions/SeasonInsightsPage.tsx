/**
 * SeasonInsightsPage — panorama agregado de una temporada (PR3).
 *
 * Ruta: /competitions/season/:year (feature 045; `/competitions/insights/season/:year`
 * redirige aquí). En el menú es «Temporada».
 * Acceso: coach + admin (parents → redirect por ProtectedRoute; backend 403).
 *
 * Consume `GET /api/race-analysis/insights/season/{year}` (una query agregada,
 * sin N+1). Tabla longitudinal por deportista: válidas corridas, victorias,
 * podios, mejor posición, puntos acumulados.
 *
 * Privacidad: el endpoint es coach/admin only; expone nombres reales porque
 * el caller está autorizado. NO se genera narrativa IA en esta vista.
 *
 * Wave 3 (hotfix multicopa, 2026-09-16): cada `item` trae `by_series` — un
 * desglose por copa (nunca campeonatos, excluidos por el backend de este
 * endpoint). Los campos planos legacy (`races_count`/`wins`/`podiums`/
 * `best_position`/`total_points`) son sumas cross-copa deprecadas — esta
 * página NUNCA los lee. Con una sola copa en toda la temporada, la tabla se
 * ve igual que antes (mismas 4 columnas, ahora leídas de `by_series[0]`, sin
 * selector). Con 2+ copas, un selector de copa sobre la tabla decide qué
 * columnas se muestran — un coach compara una copa a la vez, nunca una suma
 * mezclada (mismo criterio que `ComparatorPanel`/`raceLabel`).
 *
 * Feature 045 (US5, T057): sobre la tabla vive el panel «Análisis pendientes»
 * (`PendingAnalysesPanel`), controlado por `?analisis=por-aprobar|desactualizados`
 * — el destino de las filas «Análisis por aprobar» / «Insights IA
 * desactualizados» del Home.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ClipboardCheck, Trophy } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  SiblingViewTabs,
  type SiblingViewTabsItem,
} from "@/components/layout/SiblingViewTabs";
import {
  parsePendingAnalysesMode,
  PendingAnalysesPanel,
} from "@/components/competitions/season/PendingAnalysesPanel";
import { useSeasonPanorama } from "@/hooks/athletes/useSeasonPanorama";
import { currentSeason } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type {
  SeasonPanoramaAthleteItem,
  SeasonPanoramaSeriesItem,
} from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Copas de la temporada — deriva la lista de selección a partir de
// `by_series` de todos los atletas (Wave 3, hotfix multicopa).
// ---------------------------------------------------------------------------

interface SeriesOption {
  seriesId: number;
  label: string;
}

/**
 * Lista deduplicada de copas presentes en la temporada, en el orden en que
 * aparecen recorriendo los atletas (cada `by_series` individual ya viene
 * ordenado por fecha de primera carrera — no hay una fecha "global" a nivel
 * de respuesta para ordenar entre atletas, así que el primer atleta que
 * trae una copa fija su posición en la lista).
 */
function resolveSeriesOptions(items: SeasonPanoramaAthleteItem[]): SeriesOption[] {
  const seen = new Map<number, SeriesOption>();
  for (const item of items) {
    for (const s of item.by_series) {
      if (!seen.has(s.series_id)) {
        seen.set(s.series_id, {
          seriesId: s.series_id,
          label: s.series_short_name ?? s.series_name,
        });
      }
    }
  }
  return Array.from(seen.values());
}

/** Cifras de un atleta para una copa — ceros/— cuando no la disputó. */
function statsForSeries(
  item: SeasonPanoramaAthleteItem,
  seriesId: number | null,
): Pick<SeasonPanoramaSeriesItem, "races" | "podiums" | "wins" | "best_position" | "points"> {
  const EMPTY = { races: 0, podiums: 0, wins: 0, best_position: null, points: 0 } as const;
  if (seriesId === null) {
    // Camino de una sola copa (o ninguna) en toda la temporada.
    return item.by_series[0] ?? EMPTY;
  }
  return item.by_series.find((s) => s.series_id === seriesId) ?? EMPTY;
}

// Secciones del área Competencias (feature 045, `contracts/ui-copy.md`):
// «Competencias» · «Temporada» · «Cargas e identidades». «Temporada» apunta al
// año de ESTA página (no al vigente) para que la pastilla activa se resuelva
// también al ver otras temporadas.
function competitionsSiblingViews(year: number): SiblingViewTabsItem[] {
  return [
    { label: "Competencias", to: "/competitions" },
    { label: "Temporada", to: `/competitions/season/${year}` },
    { label: "Cargas e identidades", to: "/competitions/imports" },
  ];
}

function HeaderBar({ year }: { year: number }) {
  return (
    <header className="space-y-1">
      <Link
        to="/competitions"
        className="inline-flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
        data-testid="back-to-insights"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Competencias
      </Link>
      <h1
        className="font-display text-2xl text-charcoal"
      >
        Temporada {year}
      </h1>
      <p className="text-sm text-mid-gray">
        Resumen agregado de los deportistas del club a lo largo de la temporada.
      </p>
    </header>
  );
}

function TableSkeleton() {
  return (
    <div
      className="space-y-2 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline"
      data-testid="season-insights-loading"
    >
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function SeasonInsightsPage() {
  const { year } = useParams<{ year: string }>();
  const navigate = useNavigate();
  const yearNum = Number(year);
  const validYear = !Number.isNaN(yearNum) && yearNum > 2000;
  const siblingViews = useMemo(
    () => competitionsSiblingViews(validYear ? yearNum : currentSeason()),
    [validYear, yearNum],
  );

  // Feature 045 (US5): `?analisis=` abre el panel de análisis pendientes; un
  // valor desconocido se ignora (panel cerrado), nunca un error.
  const [searchParams, setSearchParams] = useSearchParams();
  const pendingMode = parsePendingAnalysesMode(searchParams.get("analisis"));
  function setPendingMode(next: "por-aprobar" | "desactualizados" | null) {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === null) params.delete("analisis");
        else params.set("analisis", next);
        return params;
      },
      { replace: true },
    );
  }

  const { data, isLoading, isError, refetch } = useSeasonPanorama(
    validYear ? yearNum : null,
  );

  const items = useMemo(() => data?.items ?? [], [data]);

  // Copas presentes en la temporada (Wave 3) — con 0 ó 1 copa no se muestra
  // selector, la tabla se ve igual que antes de este hotfix.
  const seriesOptions = useMemo(() => resolveSeriesOptions(items), [items]);
  const [seriesId, setSeriesId] = useState<number | null>(null);

  useEffect(() => {
    if (seriesOptions.length === 0) {
      setSeriesId(null);
      return;
    }
    setSeriesId((current) => {
      if (current !== null && seriesOptions.some((s) => s.seriesId === current)) {
        return current;
      }
      return seriesOptions[0].seriesId;
    });
  }, [seriesOptions]);

  const showSelector = seriesOptions.length > 1;
  // Con 0 ó 1 copa, `statsForSeries(item, null)` lee `by_series[0]`
  // directamente — comportamiento idéntico al de antes del hotfix.
  const effectiveSeriesId = showSelector ? seriesId : null;
  const selectedLabel = showSelector
    ? (seriesOptions.find((s) => s.seriesId === seriesId)?.label ?? null)
    : null;

  if (!validYear) {
    return (
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
        <HeaderBar year={0} />
        <SiblingViewTabs items={siblingViews} />
        <div
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700"
          role="alert"
        >
          Año de temporada inválido.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <HeaderBar year={yearNum} />

      <SiblingViewTabs items={siblingViews} />

      {pendingMode !== null ? (
        <PendingAnalysesPanel
          mode={pendingMode}
          onModeChange={setPendingMode}
          onClose={() => setPendingMode(null)}
        />
      ) : (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            className="min-h-12"
            onClick={() => setPendingMode("por-aprobar")}
            data-testid="open-pending-analyses"
          >
            <ClipboardCheck size={16} aria-hidden="true" />
            Análisis pendientes
          </Button>
        </div>
      )}

      {isLoading && <TableSkeleton />}

      {isError && !isLoading && (
        <div
          className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-card bg-surface-raised p-6 shadow-card ring-1 ring-hairline"
          data-testid="season-insights-error"
        >
          <p className="text-sm text-mid-gray">
            No se pudo cargar el panorama. Intenta de nuevo.
          </p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div
          className="flex min-h-[20vh] items-center justify-center rounded-card bg-surface-raised p-6 text-center shadow-card ring-1 ring-hairline"
          data-testid="season-insights-empty"
        >
          <p className="text-sm text-mid-gray">
            No hay resultados registrados para la temporada {yearNum}.
          </p>
        </div>
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="space-y-3">
          {showSelector && (
            <div className="flex items-center justify-end gap-2">
              <label
                className="text-xs font-medium text-mid-gray"
                htmlFor="season-insights-series-select"
              >
                Copa
              </label>
              <select
                id="season-insights-series-select"
                data-testid="season-insights-series-select"
                value={seriesId ?? ""}
                onChange={(e) => setSeriesId(Number(e.target.value))}
                className={cn(
                  "min-h-12 rounded-lg bg-surface-raised px-3 py-2 text-sm outline-none",
                  "shadow-ring focus:ring-2 focus:ring-primary/40",
                )}
              >
                {seriesOptions.map((s) => (
                  <option key={s.seriesId} value={s.seriesId}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="overflow-hidden rounded-card bg-surface-raised shadow-card ring-1 ring-hairline">
          <table className="w-full text-sm" data-testid="season-insights-table">
            <caption className="sr-only">
              Panorama de la temporada {yearNum} por deportista
              {selectedLabel ? ` — ${selectedLabel}` : ""}
            </caption>
            <thead>
              <tr className="border-b border-light-gray text-left text-xs text-mid-gray">
                <th scope="col" className="px-4 py-3 font-medium">
                  Deportista
                </th>
                <th scope="col" className="px-3 py-3 text-center font-medium">
                  Válidas
                </th>
                <th scope="col" className="px-3 py-3 text-center font-medium">
                  Podios
                </th>
                <th scope="col" className="px-3 py-3 text-center font-medium">
                  Mejor pos.
                </th>
                <th scope="col" className="px-4 py-3 text-right font-medium">
                  Puntos
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const stats = statsForSeries(it, effectiveSeriesId);
                return (
                  <tr
                    key={it.athlete_id}
                    className="cursor-pointer border-b border-light-gray/60 transition-colors last:border-0 hover:bg-light-gray/40"
                    onClick={() =>
                      navigate(
                        `/athletes/${it.athlete_id}?tab=races&view=analisis`,
                      )
                    }
                    data-testid={`season-row-${it.athlete_id}`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-charcoal">
                          {it.athlete_display_name}
                        </span>
                        {stats.wins > 0 && (
                          <Badge variant="secondary" className="gap-1 text-xs">
                            <Trophy size={10} aria-hidden="true" />
                            {stats.wins}
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-center text-mid-gray">
                      {stats.races}
                    </td>
                    <td className="px-3 py-3 text-center text-mid-gray">
                      {stats.podiums}
                    </td>
                    <td className="px-3 py-3 text-center text-mid-gray">
                      {stats.best_position ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-charcoal">
                      {stats.points}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default SeasonInsightsPage;
