/**
 * AthletesTab — atletas de Trocha y Ruta en esta válida con sus resultados.
 *
 * Secciones:
 *   1. RosterPanel — convocatoria de la válida (FR-022 / FR-023, Wave C).
 *      - Coach/admin: lectura + escritura (agregar, editar estado, retirar).
 *      - Padre: solo su propio hijo (el backend filtra; se pasa isReadOnly=true).
 *   2. Análisis IA por atleta — grid de cards con estado de insight por atleta.
 *      El nombre navega a `/athletes/{id}` vía `AthleteLink` (specs/028):
 *      esa ruta es coach-only, así que para admin/padre se renderiza como
 *      texto plano en vez de un enlace que ProtectedRoute rebotaría en
 *      silencio (antes se navegaba con un `onClick` imperativo sin chequear
 *      el rol — mismo bug que corrigió MeasurementAlerts).
 *
 * Props: `raceEventId: number`
 */
import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AthleteLink } from "@/components/shared/AthleteLink";
import { RosterPanel } from "@/components/competitions/roster/RosterPanel";
import { useClubInsightsByRace } from "@/hooks/athletes/useClubInsightsByRace";
import { useAuthStore } from "@/store/auth.store";
import {
  confidenceLabel,
  confidenceVariant,
  validaLabel,
} from "@/lib/insights";
import { UserRole } from "@/types/enums";
import type { ClubInsightByRaceItem } from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Constante de estilo compartida
// ---------------------------------------------------------------------------

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

// ---------------------------------------------------------------------------
// Card de atleta
// ---------------------------------------------------------------------------

interface AthleteCardProps {
  item: ClubInsightByRaceItem;
}

function AthleteInsightCard({ item }: AthleteCardProps) {
  const isMasked = item.athlete_id === 0;
  const hasInsight = item.insight_id !== null;
  // Navegar a `/athletes/{id}` solo tiene sentido si hay un insight que ver y
  // el atleta no está enmascarado (privacidad de padre — ver useClubInsightsByRace).
  // AthleteLink decide, según el rol actual, si esto se renderiza como <a> o
  // como texto plano (esa ruta es coach-only).
  const showLink = !isMasked && hasInsight;
  const initials = item.athlete_display_name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();

  const cardContent = (
    <>
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

      {/* Estado del análisis */}
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
        </div>
      )}
    </>
  );

  return (
    <div
      className={[
        "rounded-xl bg-white p-4 transition-colors",
        showLink ? "hover:ring-2 hover:ring-charcoal/20" : "opacity-60",
      ].join(" ")}
      style={{ boxShadow: cardShadow }}
      data-testid={`athlete-tab-card-${item.athlete_id}`}
    >
      {showLink ? (
        <AthleteLink
          athleteId={item.athlete_id}
          tab="ai_analysis"
          className="block rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-charcoal/40"
        >
          {cardContent}
        </AthleteLink>
      ) : (
        cardContent
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
      {Array.from({ length: 4 }).map((_, i) => (
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

export interface AthletesTabProps {
  raceEventId: number;
}

export function AthletesTab({ raceEventId }: AthletesTabProps) {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading, isError, refetch } = useClubInsightsByRace(
    raceEventId,
    { latestOnly: true, limit: 50 },
  );

  // El padre solo puede ver su propio hijo → RosterPanel en modo solo lectura
  const isParent = user?.role === UserRole.parent;

  return (
    <div className="space-y-8" data-testid="athletes-tab">
      {/* ── Sección 1: Convocatoria (Roster) ───────────────────────────── */}
      <section aria-labelledby="roster-section-title">
        <h2
          id="roster-section-title"
          className="mb-4 text-sm font-semibold uppercase tracking-wide text-mid-gray"
        >
          Convocatoria
        </h2>
        <RosterPanel
          raceEventId={raceEventId}
          isReadOnly={isParent}
        />
      </section>

      {/* ── Sección 2: Análisis IA por atleta ───────────────────────────── */}
      <section aria-labelledby="insights-section-title">
        <h2
          id="insights-section-title"
          className="mb-4 text-sm font-semibold uppercase tracking-wide text-mid-gray"
        >
          Análisis IA
        </h2>
        {isLoading ? (
          <SkeletonGrid />
        ) : isError || !data ? (
          <div
            className="flex min-h-[16vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-6"
            style={{ boxShadow: cardShadow }}
          >
            <p className="text-sm text-mid-gray">
              No se pudo cargar la información de atletas.
            </p>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              Reintentar
            </Button>
          </div>
        ) : data.items.length === 0 ? (
          <div
            className="flex min-h-[16vh] items-center justify-center rounded-xl bg-white p-6 text-center"
            style={{ boxShadow: cardShadow }}
          >
            <p className="text-sm text-mid-gray">
              No hay atletas de Trocha y Ruta con resultados en esta válida.
            </p>
          </div>
        ) : (
          <>
            <p className="mb-3 text-sm text-mid-gray">
              {data.total_athletes}{" "}
              {data.total_athletes === 1 ? "atleta" : "atletas"} del club en
              esta válida
            </p>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {data.items.map((item) => (
                <AthleteInsightCard
                  key={`${item.athlete_id}-${item.insight_id ?? "none"}`}
                  item={item}
                />
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
