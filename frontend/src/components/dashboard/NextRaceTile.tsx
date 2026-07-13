/**
 * NextRaceTile — hero tile "Próxima carrera Copa Valle" del Inicio del
 * coach (feature 031, US1, Tile 2 de `contracts/home-tiles.md`).
 *
 * Consume `useRaceEventsList({ season: currentSeason() })` (mismo fetch que
 * `PendingInbox`'s "Resultados por importar" — sin requests duplicados,
 * research.md R2) y selecciona el primer evento con `event_date >= hoy`
 * (zona horaria del club). El estado de urgencia (neutral/upcoming/
 * in_window) sale de `getCarreraTier` + `TAPER_GUIDANCE` (`lib/insights.ts`,
 * T024) comparando `daysUntil` contra los umbrales exactos por tier
 * (`warningAt`/`dangerAt`) — ya alineados con
 * `contracts/home-tiles.md`: A/CD → warning ≤10d, danger ≤7d;
 * B → warning ≤6d, danger ≤4d; C → siempre neutral.
 *
 * Estado vacío de fin de temporada: se muestra en texto plano vía
 * `EmptyState` sin acción (no hay "crear carrera" — el calendario Copa
 * Valle es fijo), distinto del loading (`undefined`).
 *
 * Privacidad: solo nombre/fecha/lugar de la carrera — sin resultados ni
 * nombres de atletas (contracts/home-tiles.md).
 */
import { CalendarClock } from "lucide-react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { StatCard } from "@/components/shared/StatCard";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { TAPER_GUIDANCE, getCarreraTier } from "@/lib/insights";
import { currentSeason, diffDaysFromToday, formatRelativeDayCount } from "@/lib/datetime";
import type { RaceEventListItem } from "@/types/raceEvents.types";

type Urgency = "neutral" | "upcoming" | "in_window";

const URGENCY_TONE: Record<Urgency, Status> = {
  neutral: "neutral",
  upcoming: "warning",
  in_window: "danger",
};

const URGENCY_LABEL: Record<Exclude<Urgency, "neutral">, string> = {
  upcoming: "Se acerca la ventana de tapering",
  in_window: "En ventana de tapering",
};

function resolveUrgency(daysUntil: number, warningAt: number | null, dangerAt: number | null): Urgency {
  if (warningAt === null || dangerAt === null) return "neutral";
  if (daysUntil <= dangerAt) return "in_window";
  if (daysUntil <= warningAt) return "upcoming";
  return "neutral";
}

function selectNextRace(items: RaceEventListItem[]): RaceEventListItem | null {
  const upcoming = items
    .filter((item) => {
      const days = diffDaysFromToday(item.event_date);
      return days !== null && days >= 0;
    })
    .sort((a, b) => (a.event_date < b.event_date ? -1 : a.event_date > b.event_date ? 1 : 0));
  return upcoming[0] ?? null;
}

export function NextRaceTile() {
  const query = useRaceEventsList({ season: currentSeason() });

  if (query.isLoading) {
    return <StatCard label="Próxima carrera Copa Valle" value="" isLoading />;
  }

  if (query.isError) {
    // Cold start (Render Free despertando) muestra el mismo skeleton que
    // loading, nunca un tono de error (FR-008, contracts/home-tiles.md
    // "Cold start"). Solo un error real muestra ErrorState con reintentar.
    if (isColdStartError(query.error)) {
      return <StatCard label="Próxima carrera Copa Valle" value="" isLoading />;
    }
    return (
      <ErrorState
        message="No se pudo cargar la próxima carrera."
        onRetry={() => void query.refetch()}
      />
    );
  }

  const nextRace = selectNextRace(query.data?.items ?? []);

  if (!nextRace) {
    return (
      <EmptyState icon={CalendarClock} title="Temporada finalizada — sin próximas carreras" />
    );
  }

  const daysUntil = diffDaysFromToday(nextRace.event_date) ?? 0;
  const tier = getCarreraTier(nextRace.event_date);
  const taperGuidance = tier ? TAPER_GUIDANCE[tier] : null;
  const urgency = taperGuidance
    ? resolveUrgency(daysUntil, taperGuidance.warningAt, taperGuidance.dangerAt)
    : "neutral";

  const hintParts = [
    formatRelativeDayCount(nextRace.event_date),
    nextRace.location,
    taperGuidance?.label,
  ].filter((part): part is string => Boolean(part && part.length > 0));

  return (
    <StatCard
      label="Próxima carrera Copa Valle"
      value={nextRace.name}
      hint={hintParts.join(" · ")}
      href={`/competitions/${nextRace.id}`}
      tone={URGENCY_TONE[urgency]}
      badge={
        urgency !== "neutral" ? (
          <StatusBadge status={URGENCY_TONE[urgency]} label={URGENCY_LABEL[urgency]} />
        ) : undefined
      }
    />
  );
}
