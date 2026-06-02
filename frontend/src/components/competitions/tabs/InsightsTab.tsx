/**
 * InsightsTab — insights agregados del club para una válida.
 *
 * Muestra el grid de análisis IA por atleta (scopeado a la válida).
 * Es la misma vista que ClubInsightsByRacePage pero incrustada dentro
 * de un tab (sin header propio, sin botón "Volver").
 *
 * Props: `raceEventId: number`
 */
import { useNavigate } from "react-router-dom";
import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useClubInsightsByRace } from "@/hooks/athletes/useClubInsightsByRace";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  validaLabel,
} from "@/lib/insights";
import type { ClubInsightByRaceItem } from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Constante de estilo compartida
// ---------------------------------------------------------------------------

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

// ---------------------------------------------------------------------------
// Card de insight (idéntica a ClubInsightsByRacePage pero con props limpias)
// ---------------------------------------------------------------------------

interface InsightCardProps {
  item: ClubInsightByRaceItem;
  onNavigate: (athleteId: number, insightId: number) => void;
}

function InsightCard({ item, onNavigate }: InsightCardProps) {
  const isMasked = item.athlete_id === 0;
  const isClickable = !isMasked && item.insight_id !== null;
  const initials = item.athlete_display_name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();

  function handleClick() {
    if (isClickable) {
      onNavigate(item.athlete_id, item.insight_id!);
    }
  }

  return (
    <div
      className={[
        "rounded-xl bg-white p-4 transition-colors",
        isClickable
          ? "cursor-pointer hover:ring-2 hover:ring-charcoal/20"
          : "opacity-60 cursor-default",
      ].join(" ")}
      style={{ boxShadow: cardShadow }}
      onClick={handleClick}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleClick();
              }
            }
          : undefined
      }
      aria-label={
        isClickable
          ? `Ver análisis de ${item.athlete_display_name}`
          : undefined
      }
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
          className="rounded-xl bg-white p-4"
          style={{ boxShadow: cardShadow }}
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
}

/**
 * InsightsTab — grid de análisis IA por atleta scopeado a la válida.
 */
export function InsightsTab({ raceEventId }: InsightsTabProps) {
  return <ClubInsightsGrid raceEventId={raceEventId} />;
}

/**
 * ClubInsightsGrid — grid de análisis IA por atleta para una válida concreta.
 */
function ClubInsightsGrid({ raceEventId }: InsightsTabProps) {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useClubInsightsByRace(
    raceEventId,
    { latestOnly: true, limit: 50 },
  );

  function handleNavigate(athleteId: number, insightId: number) {
    navigate(`/athletes/${athleteId}?tab=ai_analysis&insight=${insightId}`);
  }

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
        className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6"
        style={{ boxShadow: cardShadow }}
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
        className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center"
        style={{ boxShadow: cardShadow }}
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
        {data.items.map((item) => (
          <InsightCard
            key={`${item.athlete_id}-${item.insight_id ?? "none"}`}
            item={item}
            onNavigate={handleNavigate}
          />
        ))}
      </div>
    </div>
  );
}
