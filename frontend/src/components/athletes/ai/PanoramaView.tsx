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
 */
import { useMemo } from "react";
import { Sparkles } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAthleteEvolution } from "@/hooks/athletes/useAthleteEvolution";
import { EvolutionMetric } from "@/types/athleteRaceAnalysis.types";
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

        {/* KPI 3: "Podios" está pendiente de un campo adicional del backend
            (ver docstring del archivo) — mientras tanto esta KPI muestra
            "Válidas completadas" de la serie, que sí es un dato real. */}
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
      className="bg-white shadow-card"
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
