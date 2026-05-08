import { useState } from "react";

import { ParentSessionCard } from "@/components/parents/ParentSessionCard";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentSessions } from "@/api/trainingSessions";
import type { AttendanceStatus, SessionFilters } from "@/types/trainingSession.types";
import type { MyAthleteOut } from "@/types/parent.types";

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";


function AthleteChip({
  athlete,
  active,
  onClick,
}: {
  athlete: MyAthleteOut;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-2.5 min-h-11 text-sm sm:text-base font-medium transition-colors ${
        active
          ? "bg-charcoal text-white"
          : "bg-white text-mid-gray hover:text-charcoal"
      }`}
      style={!active ? { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" } : undefined}
      aria-pressed={active}
    >
      {athlete.athlete_first_name} {athlete.athlete_last_name}
    </button>
  );
}

export function ParentSessionsPage() {
  const athletesQuery = useMyAthletes();
  const athletes = athletesQuery.data ?? [];

  const [selectedAthleteId, setSelectedAthleteId] = useState<number | null>(null);
  const [monthOffset, setMonthOffset] = useState(0); // 0 = current month, -1 = previous, etc.

  const allAthleteIds = athletes.map((a) => a.athlete_id);

  // Compute month range from offset (0 = current month)
  const monthRange = (() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + monthOffset;
    const target = new Date(y, m, 1);
    const ty = target.getFullYear();
    const tm = String(target.getMonth() + 1).padStart(2, "0");
    const lastDay = new Date(ty, target.getMonth() + 1, 0).getDate();
    return { from_date: `${ty}-${tm}-01`, to_date: `${ty}-${tm}-${lastDay}` };
  })();

  const monthLabel = new Intl.DateTimeFormat("es-CO", {
    month: "long",
    year: "numeric",
  }).format(new Date(monthRange.from_date + "T12:00:00"));

  const filters: SessionFilters = {
    ...monthRange,
    ...(selectedAthleteId ? { athlete_id: selectedAthleteId } : {}),
  };

  const sessionsQuery = useParentSessions(filters, allAthleteIds);
  const sessions = sessionsQuery.data ?? [];

  // Only show planned + executed (hide cancelled unless none visible)
  const visibleSessions = sessions.filter(
    (s) => s.status === "planned" || s.status === "executed",
  );
  const showCancelled = visibleSessions.length === 0 && sessions.length > 0;
  const displaySessions = showCancelled ? sessions : visibleSessions;

  // Map athlete_id → attendance status for badge display
  const getKidStatus = (sessionId: number): AttendanceStatus | null => {
    const athleteId = selectedAthleteId ?? allAthleteIds[0] ?? null;
    if (!athleteId) return null;
    const session = sessions.find((s) => s.id === sessionId);
    return (
      session?.kid_attendances?.find((a) => a.athlete_id === athleteId)
        ?.status ?? null
    );
  };

  return (
    <section className="space-y-5">
      <div>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Entrenamientos
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">Vista de lectura — solo tus atletas.</p>
      </div>

      {/* Sin atletas vinculados */}
      {!athletesQuery.isLoading && athletes.length === 0 && (
        <div
          className="rounded-xl bg-white px-5 py-10 text-center"
          style={{ boxShadow: CARD_SHADOW }}
          data-testid="no-athletes-state"
        >
          <p className="text-sm font-medium text-charcoal">
            Aún no estás vinculado a un atleta
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            Tu cuenta no está asociada a ningún atleta. Contacta al entrenador
            para que vincule a tu hijo o hija a tu cuenta.
          </p>
        </div>
      )}

      {/* Selector de mes */}
      {!athletesQuery.isLoading && athletes.length > 0 && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMonthOffset((o) => o - 1)}
            className="min-h-11 rounded-lg px-3 py-2.5 text-sm text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal"
            aria-label="Mes anterior"
          >
            ← Mes anterior
          </button>
          <span className="flex-1 text-center text-sm font-medium capitalize text-charcoal">
            {monthLabel}
          </span>
          <button
            type="button"
            onClick={() => setMonthOffset((o) => o + 1)}
            disabled={monthOffset >= 0}
            className="min-h-11 rounded-lg px-3 py-2.5 text-sm text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Mes siguiente"
          >
            Mes siguiente →
          </button>
        </div>
      )}

      {/* Selector de atleta (solo si padre tiene más de uno) */}
      {athletes.length > 1 && (
        <div className="flex flex-wrap gap-2">
          <AthleteChip
            athlete={{ athlete_first_name: "Todos", athlete_last_name: "" } as MyAthleteOut}
            active={selectedAthleteId === null}
            onClick={() => setSelectedAthleteId(null)}
          />
          {athletes.map((a) => (
            <AthleteChip
              key={a.athlete_id}
              athlete={a}
              active={selectedAthleteId === a.athlete_id}
              onClick={() => setSelectedAthleteId(a.athlete_id)}
            />
          ))}
        </div>
      )}

      {/* Loading */}
      {(sessionsQuery.isLoading || athletesQuery.isLoading) && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-light-gray" />
          ))}
        </div>
      )}

      {/* Error */}
      {sessionsQuery.isError && !sessionsQuery.isLoading && (
        <div className="rounded-xl bg-white px-5 py-6" style={{ boxShadow: CARD_SHADOW }}>
          <p className="text-sm text-mid-gray">
            No fue posible cargar las sesiones. Intenta de nuevo.
          </p>
        </div>
      )}

      {/* Vacío */}
      {!sessionsQuery.isLoading && !sessionsQuery.isError && displaySessions.length === 0 && (
        <div
          className="rounded-xl bg-white px-5 py-10 text-center"
          style={{ boxShadow: CARD_SHADOW }}
          data-testid="empty-state"
        >
          <p className="text-sm text-mid-gray">
            Aún no hay entrenamientos registrados para tu atleta.
          </p>
        </div>
      )}

      {/* Lista */}
      {!sessionsQuery.isLoading && !sessionsQuery.isError && displaySessions.length > 0 && (
        <ul role="list" className="flex flex-col gap-3" data-testid="sessions-list">
          {displaySessions.map((session) => (
            <li key={session.id}>
              <ParentSessionCard
                session={session}
                kidAttendanceStatus={getKidStatus(session.id)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
