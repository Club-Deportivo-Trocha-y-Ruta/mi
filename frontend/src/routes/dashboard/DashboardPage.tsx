import { useTrainingSessions } from "@/api/trainingSessions";
import { AttendanceMiniChart } from "@/components/dashboard/AttendanceMiniChart";
import { MeasurementAlerts } from "@/components/dashboard/MeasurementAlerts";
import { NextRaceTile } from "@/components/dashboard/NextRaceTile";
import { NextSessionTile } from "@/components/dashboard/NextSessionTile";
import { PendingInbox } from "@/components/dashboard/PendingInbox";
import { WeeklyLoadMeter } from "@/components/dashboard/WeeklyLoadMeter";
import {
  WeekStrip,
  currentIsoWeekDays,
  currentIsoWeekNumber,
  plannedSessionsFilters,
} from "@/components/dashboard/WeekStrip";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { currentSeason, diffDaysFromToday, formatRelativeDayCount } from "@/lib/datetime";
import { useAuthStore } from "@/store/auth.store";
import type { RaceEventListItem } from "@/types/raceEvents.types";

/**
 * Nombre corto de la carrera para el subtítulo del saludo: la parte
 * específica del nombre completo ("Copa Valle — Roldanillo" → "Roldanillo").
 * Si el nombre no trae separador se usa completo — nunca se inventa una
 * abreviatura.
 */
function shortRaceName(name: string): string {
  const parts = name.split("—");
  const last = parts[parts.length - 1].trim();
  return last.length > 0 ? last : name.trim();
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

// `useDashboardStats()` (wraps the same `useAlerts()` query `MeasurementAlerts`
// consumes) is only used here for the "no athletes in this club" empty-state
// copy below. Its error case is intentionally NOT rendered here anymore —
// `MeasurementAlerts` already renders its own scoped `ErrorState` + retry for
// this exact query, and rendering a second top-level `ErrorState` for the
// same failure produced two "Reintentar" buttons on screen for one error
// (duplicate-control defect caught by DashboardPage.test.tsx's retry test).
export function DashboardPage() {
  const { total, isLoading, isError } = useDashboardStats();
  const isEmpty = !isLoading && !isError && (total ?? 0) === 0;

  const firstName = useAuthStore((state) => state.user?.first_name);

  // Mismas queries (mismos filtros → misma queryKey) que `NextSessionTile` /
  // `WeekStrip` y `NextRaceTile`: el subtítulo del saludo se arma desde el
  // cache compartido, sin requests propios.
  const plannedSessionsQuery = useTrainingSessions(plannedSessionsFilters());
  const raceQuery = useRaceEventsList({ season: currentSeason() });

  // Cada parte del subtítulo se omite mientras su fuente carga o no está
  // disponible — nunca se muestra un placeholder ni un cero falso.
  const subtitleParts: string[] = [`Semana ${currentIsoWeekNumber()}`];

  const plannedSessions =
    plannedSessionsQuery.isLoading || plannedSessionsQuery.isError
      ? undefined
      : plannedSessionsQuery.data;

  if (plannedSessions) {
    const weekDays = currentIsoWeekDays();
    const plannedThisWeek = plannedSessions.filter(
      (session) =>
        session.status === "planned" && weekDays.includes(session.scheduled_date),
    ).length;
    subtitleParts.push(
      plannedThisWeek === 1
        ? "1 sesión planificada"
        : `${plannedThisWeek} sesiones planificadas`,
    );
  }

  if (!raceQuery.isLoading && !raceQuery.isError) {
    const nextRace = selectNextRace(raceQuery.data?.items ?? []);
    if (nextRace) {
      const relative = formatRelativeDayCount(nextRace.event_date).toLowerCase();
      subtitleParts.push(`${shortRaceName(nextRace.name)} ${relative}`);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-0.5">
        {/* `data-testid` estable: los e2e esperaban el <h1> "Dashboard" que la
            feature 035 reemplazó por el saludo. Un testid los desacopla de la
            copy, que ya cambió una vez. */}
        <h1
          className="font-display text-2xl font-semibold text-charcoal"
          data-testid="dashboard-heading"
        >
          {firstName ? `Hola, ${firstName}` : "Hola"}
        </h1>
        <p className="text-sm text-mid-gray">{subtitleParts.join(" · ")}</p>
      </div>

      {isEmpty && (
        <p className="text-sm text-mid-gray">No tienes atletas asignados a un club</p>
      )}

      {/* Fila A — hoy y la semana en números */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <NextSessionTile />

        <NextRaceTile />

        <WeeklyLoadMeter />
      </div>

      {/* Fila B — semana en curso + pendientes */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr]">
        <WeekStrip />

        <PendingInbox />
      </div>

      {/* Fila C — alertas de medición + asistencia */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr]">
        <MeasurementAlerts />

        <AttendanceMiniChart />
      </div>
    </section>
  );
}
