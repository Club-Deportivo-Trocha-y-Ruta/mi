/**
 * ClubInsightsByRacePage — vista cross-atleta por válida (Sprint 3).
 *
 * Muestra un grid de cards con el estado de análisis IA de cada atleta
 * del club para un race_event_id dado.
 *
 * RBAC aplicado en backend:
 *   - Coach: nombres reales + confidence + excerpts.
 *   - Parent: solo su hijo con datos; otros → athlete_id=0, opacidad,
 *     sin excerpt, sin confidence, card no clickeable.
 *   - Admin: requiere club_id en query param (pasado si disponible).
 *
 * Privacidad Ley 1581:
 *   - Card con athlete_id === 0 → visualmente atenuada + NO clickeable.
 *   - Confidence badge NUNCA aparece si confidence === null.
 */
import { useNavigate, useParams } from "react-router-dom";
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

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

// ---------------------------------------------------------------------------
// ClubInsightCard — card individual por atleta
// ---------------------------------------------------------------------------

interface ClubInsightCardProps {
  item: ClubInsightByRaceItem;
  onNavigate: (athleteId: number, insightId: number) => void;
}

function ClubInsightCard({ item, onNavigate }: ClubInsightCardProps) {
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
      data-testid={`club-insight-card-${item.athlete_id}`}
    >
      {/* Header: avatar + nombre */}
      <div className="flex items-center gap-3 mb-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-charcoal text-white text-sm font-bold"
          aria-hidden="true"
        >
          {initials || <Users size={14} />}
        </div>
        <p className="text-sm font-semibold text-charcoal leading-tight line-clamp-2">
          {item.athlete_display_name}
        </p>
      </div>

      {/* Contenido según estado del insight */}
      {item.insight_id === null ? (
        <div className="space-y-1">
          <Badge variant="secondary" className="text-xs">
            Sin análisis
          </Badge>
          <p className="text-xs text-mid-gray">El análisis está pendiente.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {/* Badges: válida + confidence */}
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

          {/* Excerpt */}
          {item.summary_excerpt !== null && (
            <p className="line-clamp-3 text-sm text-charcoal leading-relaxed">
              {item.summary_excerpt}
            </p>
          )}

          {/* Fecha */}
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
// Skeleton placeholders
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
          <div className="flex items-center gap-3 mb-3">
            <Skeleton className="h-9 w-9 rounded-full" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="h-3 w-16 mb-2" />
          <Skeleton className="h-12 w-full" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export function ClubInsightsByRacePage() {
  const { raceEventId: raceEventIdParam } = useParams<{
    raceEventId: string;
  }>();
  const navigate = useNavigate();
  const raceEventId = Number(raceEventIdParam);

  const { data, isLoading, isError, refetch } = useClubInsightsByRace(
    Number.isNaN(raceEventId) ? null : raceEventId,
    { latestOnly: true, limit: 50 },
  );

  function handleCardNavigate(athleteId: number, insightId: number) {
    navigate(`/athletes/${athleteId}?tab=ai_analysis&insight=${insightId}`);
  }

  // ---- Param inválido -------------------------------------------------------
  if (Number.isNaN(raceEventId)) {
    return (
      <div
        className="flex min-h-[40vh] flex-col items-center justify-center gap-4"
        data-testid="club-insights-by-race-page"
      >
        <p className="text-sm text-mid-gray">Válida no válida.</p>
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </div>
    );
  }

  // ---- Loading ---------------------------------------------------------------
  if (isLoading) {
    return (
      <div
        className="p-4 md:p-6 space-y-4"
        data-testid="club-insights-by-race-page"
      >
        <div className="flex items-center gap-3 mb-2">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-16 ml-auto" />
        </div>
        <SkeletonGrid />
      </div>
    );
  }

  // ---- Error state ----------------------------------------------------------
  if (isError || !data) {
    return (
      <div
        className="flex min-h-[40vh] flex-col items-center justify-center gap-4"
        data-testid="club-insights-by-race-page"
      >
        <p className="text-sm text-mid-gray">
          No se pudo cargar la información. Intenta de nuevo.
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Reintentar
        </Button>
      </div>
    );
  }

  // ---- Contenido principal --------------------------------------------------
  return (
    <div
      className="p-4 md:p-6 space-y-4"
      data-testid="club-insights-by-race-page"
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1
            className="text-lg font-bold text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif" }}
          >
            {data.race_event_label}
          </h1>
          <p className="text-sm text-mid-gray mt-0.5">
            {data.total_athletes}{" "}
            {data.total_athletes === 1 ? "atleta" : "atletas"}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </div>

      {/* Empty state */}
      {data.items.length === 0 ? (
        <div className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center" style={{ boxShadow: cardShadow }}>
          <p className="text-sm text-mid-gray">
            No hay atletas con resultados en esta válida.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.items.map((item) => (
            <ClubInsightCard
              key={`${item.athlete_id}-${item.insight_id ?? "none"}`}
              item={item}
              onNavigate={handleCardNavigate}
            />
          ))}
        </div>
      )}
    </div>
  );
}
