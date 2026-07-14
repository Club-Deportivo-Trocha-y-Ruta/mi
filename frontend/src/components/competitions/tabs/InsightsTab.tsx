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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StaleAnalysisBadge } from "@/components/competitions/insights/StaleAnalysisBadge";
import { AnalyzeAthleteButton } from "@/components/competitions/insights/AnalyzeAthleteButton";
import { useClubInsightsByRace } from "@/hooks/athletes/useClubInsightsByRace";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  validaLabel,
} from "@/lib/insights";
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
  const isClickable = !isMasked && item.insight_id !== null;
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
  // fresco → confirmar; string=stale run_id → launch directo.
  const insightFreshness =
    item.insight_id === null ? undefined : (item.stale_run_id ?? null);

  // Contenido visual de la card — idéntico para todos los roles. La
  // navegación real (o su ausencia para roles sin acceso a /athletes/:id,
  // como admin) la resuelve únicamente AthleteLink más abajo, nunca este div.
  const cardBody = (
    <div
      className={[
        "rounded-xl bg-white p-4 transition-colors shadow-card",
        isClickable
          ? "cursor-pointer hover:ring-2 hover:ring-charcoal/20"
          : "opacity-60 cursor-default",
      ].join(" ")}
      data-testid={`insights-tab-card-${item.athlete_id}`}
    >
      {/* Header: avatar + nombre */}
      <div className="mb-3 flex items-center gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-charcoal text-sm font-bold text-white"
          aria-hidden="true"
        >
          {initials || <Users size={14} />}
        </div>
        <p className="line-clamp-2 text-sm font-semibold leading-tight text-charcoal">
          {item.athlete_display_name}
        </p>
      </div>

      {item.insight_id === null ? (
        <div className="space-y-1">
          <Badge variant="secondary" className="text-xs">
            Sin análisis
          </Badge>
          <p className="text-xs text-mid-gray">El análisis está pendiente.</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="secondary" className="text-xs">
              {validaLabel(item.valida_num)}
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
          {item.summary_excerpt !== null && (
            <p className="line-clamp-3 text-sm leading-relaxed text-charcoal">
              {item.summary_excerpt}
            </p>
          )}
          {item.generated_at !== null && (
            <p className="text-xs text-mid-gray">
              {formatDateTimeCompact(item.generated_at)}
            </p>
          )}
        </div>
      )}
    </div>
  );

  return (
    // Contenedor article: evita nesting de controles interactivos (axe
    // nested-interactive). El card clickable y el badge stale son hermanos
    // dentro del article, no padre-hijo.
    <article
      className="flex flex-col gap-2"
      aria-label={item.athlete_display_name}
    >
      {/* AthleteLink decide Link (coach) vs. <span> (resto de roles) —
          `/athletes/:id` es coach-only (ver AthleteLink.tsx); antes de este
          cambio, un div con role="button" navegaba ahí sin mirar el rol, y
          ProtectedRoute rebotaba a admin en silencio de vuelta al dashboard.
          Solo se monta cuando hay algo que ver (isClickable); si no, la card
          queda como contenido plano, igual que antes. */}
      {isClickable ? (
        <AthleteLink
          athleteId={item.athlete_id}
          tab="ai_analysis"
          className="block rounded-xl"
        >
          {cardBody}
        </AthleteLink>
      ) : (
        cardBody
      )}

      {/* FR-018 / PR5: badge hermano del card (no anidado) para evitar
          nested-interactive (axe). La re-ejecución es manual (D5/FR-029). */}
      {item.stale_run_id != null && (
        <div
          data-testid={`insights-tab-stale-badge-${item.athlete_id}`}
        >
          <StaleAnalysisBadge runId={item.stale_run_id} />
        </div>
      )}

      {/* US4 (per-atleta): botón "Analizar con IA" por tarjeta. Hermano del
          card clickable (no anidado) para no romper nested-interactive (axe).
          Solo coach/admin con season + validaNum resueltos. */}
      {showAnalyze && (
        <div
          className="flex justify-end"
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
          />
        </div>
      )}
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
  const { data, isLoading, isError, refetch } = useClubInsightsByRace(
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
    return (
      <div
        className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6 shadow-card"
        data-testid="insights-tab"
      >
        <p className="text-sm text-mid-gray">
          No se pudo cargar los insights. Intenta de nuevo.
        </p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Reintentar
        </Button>
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

  return (
    <div className="space-y-4" data-testid="insights-tab">
      <p className="text-sm text-mid-gray">
        {data.total_athletes}{" "}
        {data.total_athletes === 1 ? "atleta" : "atletas"} con análisis IA
      </p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.items.map((item, index) => (
          <InsightCard
            // Se incluye `index` porque varias tarjetas enmascaradas de padre
            // comparten `athlete_id=0` + `insight_id=null` (mismo par clave),
            // lo que provoca el warning de React "two children with the same
            // key". La lista es un snapshot estable por válida (no se reordena
            // ni filtra en cliente tras el render), así que el índice es una
            // desambiguación segura.
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
