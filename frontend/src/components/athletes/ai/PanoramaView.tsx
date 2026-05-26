/**
 * PanoramaView — contenido del sub-tab "Panorama" en AthleteAIAnalysisTab.
 *
 * Sprint 2 (BB2):
 *   - HeroLastInsightCard (arriba).
 *   - MiniSparkline de evolución posición (debajo del Hero).
 *   - 3 KPI cards: total aprobados, mejor posición temporada, TODO podios.
 *
 * KPI "Podios temporada": el snapshot de insight no tiene un campo
 * ``podios`` directo ni sumable sin leer cada detalle. Se deja como TODO
 * para Sprint 3 cuando se implemente el endpoint de métricas agregadas.
 * En su lugar se muestra "Mejor posición" como segunda KPI.
 *
 * Privacidad: este componente no filtra por modo — la responsabilidad
 * recae en HeroLastInsightCard (confianza, boletín) y en el tab-gating
 * del padre (Comparador, Distribución).
 */
import { useMemo } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAthleteEvolution } from "@/hooks/athletes/useAthleteEvolution";
import { EvolutionMetric } from "@/types/athleteRaceAnalysis.types";
import type { AthleteOut } from "@/types/athlete.types";
import { HeroLastInsightCard } from "./HeroLastInsightCard";
import { MiniSparkline } from "./MiniSparkline";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

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

  // KPI: mejor posición de la temporada (posición mínima numérica = mejor)
  // Usamos la serie de evolución de "ranking" para calcular el mínimo.
  const evolutionQuery = useAthleteEvolution(
    athlete.id,
    season,
    EvolutionMetric.RANKING,
  );

  const bestPosition = useMemo(() => {
    const series = evolutionQuery.data?.series ?? [];
    const positions = series
      .map((p) => p.value)
      .filter((v): v is number => v !== null && Number.isFinite(v));
    if (positions.length === 0) return null;
    return Math.min(...positions);
  }, [evolutionQuery.data]);

  return (
    <div className="space-y-4" data-testid="panorama-view">
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

        {/* KPI 2: Mejor posición temporada */}
        <KpiCard
          label={`Mejor posición ${season}`}
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

        {/* KPI 3: Podios — TODO Sprint 3 (requiere campo adicional del backend).
            Por ahora mostramos "Válidas completadas" de la serie. */}
        <KpiCard
          label="Válidas completadas"
          value={
            evolutionQuery.isLoading
              ? null
              : (() => {
                  const count = (evolutionQuery.data?.series ?? []).filter(
                    (p) => p.value !== null,
                  ).length;
                  return count > 0 ? String(count) : "—";
                })()
          }
          isLoading={evolutionQuery.isLoading}
          testId="panorama-kpi-races"
          note="Podios: TODO Sprint 3"
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
      style={{ boxShadow: cardShadow }}
      data-testid={testId}
      className="bg-white"
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
              className="text-2xl font-bold text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif" }}
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
