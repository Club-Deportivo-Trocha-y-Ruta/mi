/**
 * PanoramaView — contenido del sub-tab "Panorama" en AthleteAIAnalysisTab.
 *
 * Sprint 2 (BB2):
 *   - HeroLastInsightCard (arriba).
 *   - MiniSparkline de evolución posición (debajo del Hero).
 *   - 3 KPI cards: total aprobados, mejor posición temporada, válidas
 *     completadas.
 *
 * KPI "Podios temporada" (pendiente): el snapshot de insight no tiene un
 * campo ``podios`` directo ni sumable sin leer cada detalle, así que no
 * está implementada — no inventar el dato ni el conteo. En su lugar, la
 * tercera KPI muestra "Válidas completadas" (dato real, derivado de la
 * serie de evolución) hasta que exista un endpoint de métricas agregadas.
 *
 * Privacidad: este componente no filtra por modo — la responsabilidad
 * recae en HeroLastInsightCard (confianza, boletín) y en el tab-gating
 * del padre (Comparador, Distribución).
 *
 * Wave 3 (hotfix multicopa, 2026-09-16): "Mejor posición" y "Válidas
 * completadas" mezclaban el ranking de TODAS las copas/campeonatos de la
 * temporada en un solo mínimo/conteo — el mismo colapso de identidad que
 * originó el bug (dos copas no compiten en el mismo pelotón, un P3 de una
 * copa chica no es comparable a un P3 de una copa grande). Este componente
 * es visible para coach Y parent, así que no puede consumir el endpoint
 * coach/admin-only de panorama de temporada (`by_series`,
 * `SeasonInsightsPage.tsx`) — en su lugar reutiliza `useAthleteEvolution`
 * (ya autorizado para los 3 roles, feature 039) y su propio `groups`, con
 * el mismo criterio de "copa por defecto" que `EvolutionChart.tsx`
 * (primera copa, o el primer grupo si no hay copas). Con una sola copa (o
 * ninguna) en la temporada el label no cambia — se ve igual que antes.
 */
import { useMemo } from "react";
import { Sparkles } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAthleteEvolution } from "@/hooks/athletes/useAthleteEvolution";
import {
  EvolutionMetric,
  type ComparisonGroupOption,
} from "@/types/athleteRaceAnalysis.types";
import type { AthleteOut } from "@/types/athlete.types";
import { HeroLastInsightCard } from "./HeroLastInsightCard";
import { MiniSparkline } from "./MiniSparkline";

function getCurrentSeason(): number {
  return new Date().getFullYear();
}

interface PanoramaViewProps {
  athlete: AthleteOut;
  mode: "coach" | "parent";
  onOpenDetail: (id: number) => void;
  onAddToNewsletter: (id: number) => void;
  /** IDs seleccionados para boletín (BB4). Solo coach. */
  newsletterSelection?: Set<number>;
  /** Toggle del checkbox de boletín (BB4). Solo coach. */
  onToggleSelection?: (id: number) => void;
}

export function PanoramaView({
  athlete,
  mode,
  onOpenDetail,
  onAddToNewsletter,
  newsletterSelection,
  onToggleSelection,
}: PanoramaViewProps) {
  const season = getCurrentSeason();

  // KPI: total de aprobados
  const headerQuery = useAthleteInsights(athlete.id, {
    latest_only: true,
    limit: 1,
  });
  const totalApproved = headerQuery.data?.total ?? null;

  // KPI: mejor posición de la temporada (posición mínima numérica = mejor).
  // Pedimos la temporada completa (sin `seriesId`) y resolvemos el grupo
  // por defecto en cliente — mismo patrón que `EvolutionChart.tsx` (evita
  // una segunda ida y vuelta al backend para el caso más común).
  const evolutionQuery = useAthleteEvolution(
    athlete.id,
    season,
    EvolutionMetric.RANKING,
  );

  const groups: ComparisonGroupOption[] = evolutionQuery.data?.groups ?? [];

  // Wave 3: primera copa de la temporada (o el primer grupo si el atleta
  // solo tiene campeonatos) — nunca se mezclan copas distintas en el
  // mínimo. `undefined` cuando no hay grupos (temporada sin datos, o
  // fixtures/insights previos a la feature 039 sin `series_id`).
  const primaryGroupId = useMemo(() => {
    if (groups.length === 0) return undefined;
    const firstCup = groups.find((g) => g.kind === "cup");
    return (firstCup ?? groups[0]).series_id;
  }, [groups]);
  const primaryGroup = groups.find((g) => g.series_id === primaryGroupId);
  // Un solo grupo en toda la temporada → el label no cambia, se ve igual
  // que antes del hotfix.
  const bestPositionLabel =
    groups.length > 1 && primaryGroup
      ? `Mejor posición ${season} · ${primaryGroup.label}`
      : `Mejor posición ${season}`;
  const racesCompletedLabel =
    groups.length > 1 && primaryGroup
      ? `Válidas completadas · ${primaryGroup.label}`
      : "Válidas completadas";

  // Serie a promediar: filtrada al grupo por defecto cuando hay más de una
  // copa/campeonato; si el filtro no matchea nada (puntos legacy sin
  // `series_id`) cae a la serie completa — back-compat, mismo criterio que
  // `EvolutionChart.tsx`.
  const rankingSeries = useMemo(() => {
    const series = evolutionQuery.data?.series ?? [];
    if (primaryGroupId === undefined) return series;
    const filtered = series.filter((p) => p.series_id === primaryGroupId);
    return filtered.length > 0 ? filtered : series;
  }, [evolutionQuery.data, primaryGroupId]);

  const bestPosition = useMemo(() => {
    const positions = rankingSeries
      .map((p) => p.value)
      .filter((v): v is number => v !== null && Number.isFinite(v));
    if (positions.length === 0) return null;
    return Math.min(...positions);
  }, [rankingSeries]);

  return (
    <div className="space-y-4" data-testid="panorama-view">
      {/* T095 (feature 036, US6): antes este sub-tab no tenía ningún
          heading — a diferencia de EvolutionChart/DistributionChart/
          LaunchAnalysisForm, que exponen un <h3> real bajo el <h2> "Insights
          IA" de AthleteAIAnalysisTab.tsx. Sin heading, la navegación por
          encabezados (tecla "H") saltaba directo de "Insights IA" al resto
          de sub-vistas. Mismo nivel/tipografía que esas 3 para no romper el
          orden h2 → h3. */}
      <h3
        className="font-display flex items-center gap-2 text-sm text-charcoal"
        style={{ letterSpacing: "0.2px" }}
      >
        <Sparkles size={16} aria-hidden="true" />
        Panorama
      </h3>

      {/* Hero — último análisis aprobado */}
      <HeroLastInsightCard
        athlete={athlete}
        mode={mode}
        onOpenDetail={onOpenDetail}
        onAddToNewsletter={
          newsletterSelection !== undefined && onToggleSelection !== undefined
            ? (id) => {
                // BB4: si ya seleccionado, usa el toggle; si no, también.
                onToggleSelection(id);
              }
            : onAddToNewsletter
        }
        newsletterSelection={newsletterSelection}
        onToggleSelection={onToggleSelection}
      />

      {/* Sparkline de evolución (BB2) */}
      <MiniSparkline athleteId={athlete.id} />

      {/* KPI cards (BB2) */}
      <div
        className="grid grid-cols-1 gap-3 sm:grid-cols-3"
        aria-label="Indicadores clave de rendimiento"
      >
        {/* KPI 1: Total análisis aprobados */}
        <KpiCard
          label="Análisis aprobados"
          value={
            headerQuery.isLoading
              ? null
              : totalApproved !== null
                ? String(totalApproved)
                : "—"
          }
          isLoading={headerQuery.isLoading}
          testId="panorama-kpi-total"
        />

        {/* KPI 2: Mejor posición temporada — Wave 3: acotada a la copa
            principal del atleta (ver nota del docstring del archivo). */}
        <KpiCard
          label={bestPositionLabel}
          value={
            evolutionQuery.isLoading
              ? null
              : bestPosition !== null
                ? `P${bestPosition}`
                : "—"
          }
          isLoading={evolutionQuery.isLoading}
          testId="panorama-kpi-best-position"
        />

        {/* KPI 3: "Podios" está pendiente de un campo adicional del backend
            (ver docstring del archivo) — mientras tanto esta KPI muestra
            "Válidas completadas" de la serie, que sí es un dato real. Wave
            3: misma copa que KPI 2 (`rankingSeries`) — una fila con "P1 de
            Copa Valle" junto a un conteo de válidas de TODAS las copas
            confundiría al coach sobre a qué carreras se refiere cada cifra. */}
        <KpiCard
          label={racesCompletedLabel}
          value={
            evolutionQuery.isLoading
              ? null
              : (() => {
                  const count = rankingSeries.filter(
                    (p) => p.value !== null,
                  ).length;
                  return count > 0 ? String(count) : "—";
                })()
          }
          isLoading={evolutionQuery.isLoading}
          testId="panorama-kpi-races"
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KpiCard — card shadcn con cifra grande + label pequeño
// ---------------------------------------------------------------------------

interface KpiCardProps {
  label: string;
  value: string | null;
  isLoading: boolean;
  testId: string;
  note?: string;
}

function KpiCard({ label, value, isLoading, testId, note }: KpiCardProps) {
  return (
    <Card
      data-testid={testId}
      className="bg-surface-raised shadow-card"
    >
      <CardContent className="p-4">
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-16 mb-2" />
            <Skeleton className="h-3 w-24" />
          </>
        ) : (
          <>
            <p
              className="font-display text-2xl font-bold text-charcoal"
            >
              {value ?? "—"}
            </p>
            <p className="mt-1 text-xs text-mid-gray">{label}</p>
            {note && (
              <p className="mt-1 text-[10px] italic text-mid-gray/70">{note}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
