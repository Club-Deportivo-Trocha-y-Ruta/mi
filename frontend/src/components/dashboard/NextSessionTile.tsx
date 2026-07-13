/**
 * NextSessionTile — Row 1, Tile 1 ("Próxima sesión") del home rediseñado
 * del coach (contracts/home-tiles.md Tile 1).
 *
 * Consume `useTrainingSessions` filtrado a los próximos 14 días con
 * `status: "planned"` y selecciona la sesión más próxima que no haya
 * terminado ya (Edge Case: una sesión de hoy cuyo `scheduled_start_time`
 * + `duration_min` ya pasó no debe mostrarse como pendiente). La
 * comparación de "ya terminó" se hace combinando `scheduled_date` +
 * `scheduled_start_time` como un instante en America/Bogota (offset fijo
 * -05:00, sin DST) contra el instante actual — no una comparación de
 * fecha-only.
 */
import { Link } from "react-router-dom";
import { CalendarClock } from "lucide-react";

import { useTrainingSessions } from "@/api/trainingSessions";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { StatCard } from "@/components/shared/StatCard";
import { CLUB_TIMEZONE, formatRelativeDayCount, formatTime } from "@/lib/datetime";
import type { TrainingSession } from "@/types/trainingSession.types";

/** Fecha de "hoy" en la TZ del club, como "YYYY-MM-DD". */
function todayClubIso(): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: CLUB_TIMEZONE,
  }).format(new Date());
}

/** "YYYY-MM-DD" de hoy (TZ club) + `days` días de calendario. */
function isoDateOffset(days: number): string {
  const [y, m, d] = todayClubIso().split("-").map(Number);
  const shifted = new Date(Date.UTC(y, m - 1, d) + days * 86_400_000);
  return shifted.toISOString().slice(0, 10);
}

/**
 * Instante absoluto (Date) de `scheduled_date` + `scheduled_start_time`,
 * asumiendo que la hora está expresada en America/Bogota. Bogotá no
 * observa horario de verano, así que el offset -05:00 es válido todo el
 * año — no requiere una librería de zonas horarias.
 */
function scheduledStartInstant(session: TrainingSession): Date {
  const hhmmss = session.scheduled_start_time.length === 5
    ? `${session.scheduled_start_time}:00`
    : session.scheduled_start_time;
  return new Date(`${session.scheduled_date}T${hhmmss}-05:00`);
}

function selectNextSession(sessions: TrainingSession[] | undefined): TrainingSession | null {
  if (!sessions || sessions.length === 0) return null;
  const now = Date.now();

  const upcoming = sessions
    .filter((s) => s.status === "planned")
    .filter((s) => {
      const endsAt = scheduledStartInstant(s).getTime() + s.duration_min * 60_000;
      return endsAt > now;
    })
    .sort((a, b) => {
      const dateCmp = a.scheduled_date.localeCompare(b.scheduled_date);
      if (dateCmp !== 0) return dateCmp;
      return a.scheduled_start_time.localeCompare(b.scheduled_start_time);
    });

  return upcoming[0] ?? null;
}

export function NextSessionTile() {
  const query = useTrainingSessions({
    from_date: isoDateOffset(0),
    to_date: isoDateOffset(14),
    status: "planned",
  });

  if (query.isLoading) {
    return <StatCard label="Próxima sesión" value="" isLoading />;
  }

  if (query.isError) {
    // Cold start (Render Free despertando) muestra el mismo skeleton que
    // loading, nunca un tono de error (FR-008, contracts/home-tiles.md
    // "Cold start"). Solo un error real muestra ErrorState con reintentar.
    if (isColdStartError(query.error)) {
      return <StatCard label="Próxima sesión" value="" isLoading />;
    }
    return (
      <ErrorState
        message="No se pudo cargar la próxima sesión."
        onRetry={() => void query.refetch()}
      />
    );
  }

  const session = selectNextSession(query.data);

  if (!session) {
    return (
      <EmptyState
        icon={CalendarClock}
        title="Sin sesiones planificadas"
        action={
          <Link
            to="/training/sessions/new"
            className="inline-block text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          >
            + Planificar
          </Link>
        }
      />
    );
  }

  const relativeDay = formatRelativeDayCount(session.scheduled_date);
  const time = formatTime(scheduledStartInstant(session));
  const hint = [relativeDay, time, session.location].filter(Boolean).join(" · ");

  return (
    <StatCard
      label="Próxima sesión"
      value={session.technical_focus}
      hint={hint}
      href={`/training/sessions/${session.id}`}
    />
  );
}
