/**
 * ClubInsightsPage — análisis IA grupal del club por válida (PR3).
 *
 * Ruta: /competitions/insights/club
 * Acceso: coach + admin (parents → redirect por ProtectedRoute).
 *
 * Absorbe la antigua `ClubInsightsByRacePage`: en lugar de recibir el
 * `raceEventId` por la URL, ofrece un selector de válida y muestra el grid
 * de insights del club para la válida elegida (vía `useClubInsightsByRace`).
 *
 * Privacidad: el backend aplica RBAC; para coach/admin se exponen nombres
 * reales. La query key incluye solo `raceEventId` (no-PII).
 */
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useClubInsightsByRace } from "@/hooks/athletes/useClubInsightsByRace";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { formatDateTimeCompact } from "@/lib/datetime";
import {
  confidenceLabel,
  confidenceVariant,
  validaLabel,
} from "@/lib/insights";
import type { ClubInsightByRaceItem } from "@/types/athleteRaceAnalysis.types";

function InsightCard({
  item,
  onNavigate,
}: {
  item: ClubInsightByRaceItem;
  onNavigate: (athleteId: number) => void;
}) {
  const isMasked = item.athlete_id === 0;
  const isClickable = !isMasked;
  const initials = item.athlete_display_name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();

  return (
    <div
      className={[
        "rounded-xl bg-white p-4 transition-colors shadow-card",
        isClickable
          ? "cursor-pointer hover:ring-2 hover:ring-charcoal/20"
          : "cursor-default opacity-60",
      ].join(" ")}
      onClick={isClickable ? () => onNavigate(item.athlete_id) : undefined}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onNavigate(item.athlete_id);
              }
            }
          : undefined
      }
      aria-label={
        isClickable ? `Ver análisis de ${item.athlete_display_name}` : undefined
      }
      data-testid={`club-insight-card-${item.athlete_id}`}
    >
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
              <Badge variant={confidenceVariant(item.confidence)} className="text-xs">
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

export function ClubInsightsPage() {
  const navigate = useNavigate();
  const eventsQuery = useRaceEventsList({});
  const events = useMemo(
    () => eventsQuery.data?.items ?? [],
    [eventsQuery.data],
  );

  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Default: primera válida disponible.
  const effectiveId =
    selectedId ?? (events.length > 0 ? events[0].id : null);

  const insightsQuery = useClubInsightsByRace(effectiveId, {
    latestOnly: true,
    limit: 50,
  });

  function handleNavigate(athleteId: number) {
    navigate(`/competitions/insights/athletes/${athleteId}`);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <header className="space-y-1">
        <Link
          to="/competitions/insights"
          className="inline-flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
          data-testid="back-to-insights"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Análisis IA
        </Link>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Análisis del club por válida
        </h1>
        <p className="text-sm text-mid-gray">
          Estado del análisis IA de cada deportista del club en una válida.
        </p>
      </header>

      {/* Selector de válida */}
      <div className="max-w-sm">
        <label
          htmlFor="club-insights-race-select"
          className="mb-1.5 block text-sm font-medium text-charcoal"
        >
          Válida
        </label>
        <select
          id="club-insights-race-select"
          className="w-full rounded-lg border border-light-gray bg-white px-3 py-2 text-sm text-charcoal focus:outline-none focus:ring-2 focus:ring-charcoal/20"
          value={effectiveId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value))}
          disabled={eventsQuery.isLoading || events.length === 0}
          data-testid="club-insights-race-select"
        >
          {events.length === 0 && <option value="">Sin válidas</option>}
          {events.map((ev) => (
            <option key={ev.id} value={ev.id}>
              {`Válida ${ev.sequence_number} — ${ev.name}`}
            </option>
          ))}
        </select>
      </div>

      {effectiveId === null && !eventsQuery.isLoading && (
        <div
          className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center shadow-card"
          data-testid="club-insights-no-races"
        >
          <p className="text-sm text-mid-gray">
            No hay válidas registradas todavía.
          </p>
        </div>
      )}

      {effectiveId !== null && insightsQuery.isLoading && (
        <div
          className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
          data-testid="club-insights-loading"
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl bg-white p-4 shadow-card"
            >
              <div className="mb-3 flex items-center gap-3">
                <Skeleton className="h-9 w-9 rounded-full" />
                <Skeleton className="h-4 w-32" />
              </div>
              <Skeleton className="h-12 w-full" />
            </div>
          ))}
        </div>
      )}

      {effectiveId !== null &&
        insightsQuery.isError &&
        !insightsQuery.isLoading && (
          <div
            className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6 shadow-card"
            data-testid="club-insights-error"
          >
            <p className="text-sm text-mid-gray">
              No se pudo cargar los insights. Intenta de nuevo.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void insightsQuery.refetch()}
            >
              Reintentar
            </Button>
          </div>
        )}

      {effectiveId !== null &&
        !insightsQuery.isLoading &&
        !insightsQuery.isError &&
        insightsQuery.data && (
          <>
            <p className="text-sm text-mid-gray">
              {insightsQuery.data.total_athletes}{" "}
              {insightsQuery.data.total_athletes === 1 ? "atleta" : "atletas"}
            </p>
            {insightsQuery.data.items.length === 0 ? (
              <div
                className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center shadow-card"
                data-testid="club-insights-empty"
              >
                <p className="text-sm text-mid-gray">
                  No hay insights generados para esta válida aún.
                </p>
              </div>
            ) : (
              <div
                className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
                data-testid="club-insights-grid"
              >
                {insightsQuery.data.items.map((item) => (
                  <InsightCard
                    key={`${item.athlete_id}-${item.insight_id ?? "none"}`}
                    item={item}
                    onNavigate={handleNavigate}
                  />
                ))}
              </div>
            )}
          </>
        )}
    </div>
  );
}

export default ClubInsightsPage;
