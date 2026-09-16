/**
 * InsightsTab — insights agregados del club para una válida.
 *
 * Muestra el grid de análisis IA por atleta (scopeado a la válida).
 * Es la misma vista que ClubInsightsByRacePage pero incrustada dentro
 * de un tab (sin header propio, sin botón "Volver").
 *
 * Props: `raceEventId: number`, `hasResults?: boolean`, `isCoachOrAdmin?: boolean`
 *
 * T011 (feature 010): GroupAnalysisPanel se monta sobre el grid,
 * visible únicamente para coach/admin (isCoachOrAdmin prop).
 */
import { Users } from "lucide-react";

import { GroupAnalysisPanel } from "@/components/competitions/insights/GroupAnalysisPanel";
import { CompetitionChatPanel } from "@/components/competitions/chat/CompetitionChatPanel";
import { AthleteLink } from "@/components/shared/AthleteLink";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AnalyzeAthleteButton } from "@/components/competitions/insights/AnalyzeAthleteButton";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { useClubInsightsByRace } from "@/hooks/athletes/useClubInsightsByRace";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  raceLabelForInsight,
} from "@/lib/insights";
import { toPlainExcerpt } from "@/lib/markdownExcerpt";
import { cn } from "@/lib/utils";
import type { ClubInsightByRaceItem } from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Card de insight (idéntica a ClubInsightsByRacePage pero con props limpias)
// ---------------------------------------------------------------------------

interface InsightCardProps {
  item: ClubInsightByRaceItem;
  /** coach/admin → muestra el botón "Analizar con IA" por tarjeta. */
  canAnalyze?: boolean;
  /** Año de temporada (necesario para lanzar el análisis). */
  season?: number;
  /** Número de válida (sequence_number del evento; necesario para lanzar). */
  validaNum?: number;
  /** event_id de la competición — desambigua copa vs campeonato al lanzar. */
  raceEventId?: number;
}

function InsightCard({
  item,
  canAnalyze = false,
  season,
  validaNum,
  raceEventId,
}: InsightCardProps) {
  const isMasked = item.athlete_id === 0;
  const hasInsight = item.insight_id !== null;
  const isClickable = !isMasked && hasInsight;
  const initials = item.athlete_display_name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();

  // Botón de análisis por tarjeta: solo coach/admin, atleta no enmascarado,
  // con season + validaNum disponibles. Mismo contrato que ResultsTable.
  const showAnalyze =
    canAnalyze && !isMasked && item.athlete_id > 0 && season != null && validaNum != null;
  // Frescura para el botón: undefined=sin insight → launch directo; null=insight
  // fresco → confirmar. T041 (feature 036): el backend nunca marcó un insight
  // de esta vista como "stale" (ClubInsightByRaceItem no expone ese dato), así
  // que ese tercer estado no es alcanzable aquí — se retiró junto al badge.
  const insightFreshness = item.insight_id === null ? undefined : null;

  // El backend recorta summary_text (markdown) a 200 chars para el excerpt —
  // toPlainExcerpt limpia headers/énfasis/links, incluso truncados a mitad.
  const plainExcerpt =
    item.summary_excerpt !== null ? toPlainExcerpt(item.summary_excerpt) : "";

  return (
    // `relative` habilita el patrón "stretched link" en el nombre (más abajo):
    // el <a> visualmente solo envuelve el nombre pero su `after:inset-0` cubre
    // toda la card, así el área completa es clickable sin anidar controles
    // interactivos (axe nested-interactive) — el botón de análisis es hermano
    // del link, nunca su hijo, y se eleva con z-10 para quedar por encima.
    <article
      className={cn(
        "relative flex h-full flex-col rounded-xl bg-white p-4 shadow-card transition-shadow",
        hasInsight
          ? "ring-1 ring-[rgba(34,42,53,0.08)]"
          : "border border-dashed border-mid-gray/50",
        isClickable && "hover:shadow-md",
      )}
      data-testid={`insights-tab-card-${item.athlete_id}`}
      aria-label={item.athlete_display_name}
    >
      {/* Header: avatar + nombre + estado (una sola línea, sin duplicar). */}
      <div className="mb-3 flex items-start gap-3">
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold",
            hasInsight ? "bg-charcoal text-white" : "bg-light-gray text-mid-gray",
          )}
          aria-hidden="true"
        >
          {initials || <Users size={14} />}
        </div>
        <div className="min-w-0 flex-1">
          {isClickable ? (
            <AthleteLink
              athleteId={item.athlete_id}
              tab="ai_analysis"
              className="line-clamp-2 text-sm font-semibold leading-tight text-charcoal after:absolute after:inset-0"
            >
              {item.athlete_display_name}
            </AthleteLink>
          ) : (
            <p className="line-clamp-2 text-sm font-semibold leading-tight text-charcoal">
              {item.athlete_display_name}
            </p>
          )}
          {hasInsight ? (
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Badge variant="secondary" className="text-xs">
                {raceLabelForInsight(item, "chip")}
              </Badge>
              {item.confidence !== null && (
                <Badge
                  variant={confidenceVariant(item.confidence)}
                  className="text-xs"
                >
                  {confidenceLabel(item.confidence)}
                </Badge>
              )}
            </div>
          ) : (
            <p className="mt-1 text-xs text-mid-gray">Sin análisis todavía</p>
          )}
        </div>
      </div>

      {/* Body: excerpt en texto plano, flexible para empujar el footer abajo. */}
      <div className="flex-1">
        {plainExcerpt && (
          <p className="line-clamp-3 text-sm leading-relaxed text-charcoal">
            {plainExcerpt}
          </p>
        )}
      </div>

      {/* Footer: fecha a la izquierda, acción a la derecha — misma posición
          en todas las cards para que las filas queden alineadas. */}
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-[rgba(34,42,53,0.08)] pt-3">
        <span className="text-xs text-mid-gray">
          {item.generated_at !== null ? formatDateTimeCompact(item.generated_at) : null}
        </span>
        {showAnalyze && (
          <div
            className="relative z-10 ml-auto"
            data-testid={`insights-tab-analyze-${item.athlete_id}`}
          >
            <AnalyzeAthleteButton
              athleteId={item.athlete_id}
              season={season!}
              validaNum={validaNum!}
              eventId={raceEventId}
              insightFreshness={insightFreshness}
              displayName={item.athlete_display_name}
              label={item.insight_id === null ? "Analizar con IA" : "Re-analizar"}
              alwaysShowLabel
              showInsightsLink={false}
              showBudgetHint={false}
            />
          </div>
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl bg-white p-4 shadow-card"
        >
          <div className="mb-3 flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-full" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="mb-2 h-3 w-16" />
          <Skeleton className="h-12 w-full" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface InsightsTabProps {
  raceEventId: number;
  /** true cuando la competencia tiene resultados importados (para GroupAnalysisPanel). */
  hasResults?: boolean;
  /** true cuando el usuario es coach o admin (controla visibilidad del panel IA). */
  isCoachOrAdmin?: boolean;
  /** Año de temporada (del event_date). Habilita "Analizar con IA" por tarjeta. */
  season?: number;
  /** Número de válida (sequence_number del evento). Necesario para lanzar. */
  validaNum?: number;
}

/**
 * InsightsTab — grid de análisis IA por atleta scopeado a la válida.
 * Cuando el usuario es coach/admin muestra el GroupAnalysisPanel encima del grid.
 */
export function InsightsTab({
  raceEventId,
  hasResults = false,
  isCoachOrAdmin = false,
  season,
  validaNum,
}: InsightsTabProps) {
  return (
    <div className="space-y-4" data-testid="insights-tab-root">
      {isCoachOrAdmin && (
        <GroupAnalysisPanel
          raceEventId={raceEventId}
          hasResults={hasResults}
        />
      )}
      <ClubInsightsGrid
        raceEventId={raceEventId}
        isCoachOrAdmin={isCoachOrAdmin}
        season={season}
        validaNum={validaNum}
      />
      {isCoachOrAdmin && (
        <CompetitionChatPanel raceEventId={raceEventId} />
      )}
    </div>
  );
}

/**
 * ClubInsightsGrid — grid de análisis IA por atleta para una válida concreta.
 *
 * season/validaNum: recibidos por props desde CompetitionDetailPage (que ya
 * tiene el evento cargado para el header). Necesarios para el botón
 * "Analizar con IA" por tarjeta. Se mantienen como props (no query interna)
 * para que el grid sea presentacional y testeable sin QueryClient.
 */
function ClubInsightsGrid({
  raceEventId,
  isCoachOrAdmin = false,
  season,
  validaNum,
}: InsightsTabProps) {
  const { data, isLoading, isError, error, refetch } = useClubInsightsByRace(
    raceEventId,
    { latestOnly: true, limit: 50 },
  );

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="insights-tab">
        <SkeletonGrid />
      </div>
    );
  }

  if (isError || !data) {
    const isColdStart = isColdStartError(error);
    return (
      <div data-testid="insights-tab">
        <ErrorState
          isColdStart={isColdStart}
          onRetry={() => void refetch()}
          message={
            isColdStart ? undefined : "No se pudieron cargar los insights. Intenta de nuevo."
          }
        />
      </div>
    );
  }

  if (data.items.length === 0) {
    return (
      <div
        className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center shadow-card"
        data-testid="insights-tab"
      >
        <p className="text-sm text-mid-gray">
          No hay insights generados para esta válida aún. Ejecuta un análisis en
          la sección de análisis de carreras.
        </p>
      </div>
    );
  }

  // Conteo real (no `data.total_athletes`, que cuenta a todos los listados
  // aunque no tengan análisis) + orden analizados primero, pendientes
  // después — estable dentro de cada grupo (`filter` preserva el orden del
  // backend).
  const analyzedItems = data.items.filter((item) => item.insight_id !== null);
  const pendingItems = data.items.filter((item) => item.insight_id === null);
  const orderedItems = [...analyzedItems, ...pendingItems];
  const totalCount = data.items.length;

  return (
    <div className="space-y-4" data-testid="insights-tab">
      <p className="text-sm text-mid-gray">
        {analyzedItems.length} de {totalCount}{" "}
        {totalCount === 1 ? "atleta" : "atletas"} con análisis IA
      </p>
      <div className="grid grid-cols-1 gap-4 items-stretch md:grid-cols-2 lg:grid-cols-3">
        {orderedItems.map((item, index) => (
          <InsightCard
            // Se incluye `index` porque varias tarjetas enmascaradas de padre
            // comparten `athlete_id=0` + `insight_id=null` (mismo par clave),
            // lo que provoca el warning de React "two children with the same
            // key".
            key={`${item.athlete_id}-${item.insight_id ?? "none"}-${index}`}
            item={item}
            canAnalyze={isCoachOrAdmin}
            season={season}
            validaNum={validaNum}
            raceEventId={raceEventId}
          />
        ))}
      </div>
    </div>
  );
}
