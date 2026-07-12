/**
 * SeasonInsightsPage — panorama agregado de una temporada (PR3).
 *
 * Ruta: /competitions/insights/season/:year
 * Acceso: coach + admin (parents → redirect por ProtectedRoute; backend 403).
 *
 * Consume `GET /api/race-analysis/insights/season/{year}` (una query agregada,
 * sin N+1). Tabla longitudinal por deportista: válidas corridas, victorias,
 * podios, mejor posición, puntos acumulados.
 *
 * Privacidad: el endpoint es coach/admin only; expone nombres reales porque
 * el caller está autorizado. NO se genera narrativa IA en esta vista.
 */
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Trophy } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  SiblingViewTabs,
  type SiblingViewTabsItem,
} from "@/components/layout/SiblingViewTabs";
import { useSeasonPanorama } from "@/hooks/athletes/useSeasonPanorama";
import { currentSeason } from "@/lib/datetime";

// Vistas hermanas del área Competencias (data-model.md §2, navigation-model.md) —
// compartidas con CompetitionsListPage y UnlinkedCompetitorsPage.
const COMPETITIONS_SIBLING_VIEWS: SiblingViewTabsItem[] = [
  { label: "Válidas", to: "/competitions" },
  { label: "Sin enlazar", to: "/competitions/unlinked" },
  {
    label: "Panorama de temporada",
    to: `/competitions/insights/season/${currentSeason()}`,
  },
];

function HeaderBar({ year }: { year: number }) {
  return (
    <header className="space-y-1">
      <Link
        to="/competitions"
        className="inline-flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
        data-testid="back-to-insights"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Análisis IA
      </Link>
      <h1
        className="font-display text-2xl text-charcoal"
      >
        Panorama de temporada {year}
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
      className="space-y-2 rounded-xl bg-white p-4 shadow-card"
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

  const { data, isLoading, isError, refetch } = useSeasonPanorama(
    validYear ? yearNum : null,
  );

  const items = useMemo(() => data?.items ?? [], [data]);

  if (!validYear) {
    return (
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
        <HeaderBar year={0} />
        <SiblingViewTabs items={COMPETITIONS_SIBLING_VIEWS} />
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

      <SiblingViewTabs items={COMPETITIONS_SIBLING_VIEWS} />

      {isLoading && <TableSkeleton />}

      {isError && !isLoading && (
        <div
          className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6 shadow-card"
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
          className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center shadow-card"
          data-testid="season-insights-empty"
        >
          <p className="text-sm text-mid-gray">
            No hay resultados registrados para la temporada {yearNum}.
          </p>
        </div>
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div
          className="overflow-hidden rounded-xl bg-white shadow-card"
        >
          <table className="w-full text-sm" data-testid="season-insights-table">
            <caption className="sr-only">
              Panorama de la temporada {yearNum} por deportista
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
              {items.map((it) => (
                <tr
                  key={it.athlete_id}
                  className="cursor-pointer border-b border-light-gray/60 transition-colors last:border-0 hover:bg-light-gray/40"
                  onClick={() =>
                    navigate(`/athletes/${it.athlete_id}?tab=ai_analysis`)
                  }
                  data-testid={`season-row-${it.athlete_id}`}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-charcoal">
                        {it.athlete_display_name}
                      </span>
                      {it.wins > 0 && (
                        <Badge variant="secondary" className="gap-1 text-xs">
                          <Trophy size={10} aria-hidden="true" />
                          {it.wins}
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-center text-mid-gray">
                    {it.races_count}
                  </td>
                  <td className="px-3 py-3 text-center text-mid-gray">
                    {it.podiums}
                  </td>
                  <td className="px-3 py-3 text-center text-mid-gray">
                    {it.best_position ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-charcoal">
                    {it.total_points}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default SeasonInsightsPage;
