import { useState } from "react";

import { ParentSessionCard } from "@/components/parents/ParentSessionCard";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentSessions } from "@/api/trainingSessions";
import type { AttendanceStatus, SessionFilters } from "@/types/trainingSession.types";
import type { MyAthleteOut } from "@/types/parent.types";

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

function currentMonthRange(): { from_date: string; to_date: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const lastDay = new Date(y, now.getMonth() + 1, 0).getDate();
  return {
    from_date: `${y}-${m}-01`,
    to_date: `${y}-${m}-${lastDay}`,
  };
}

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
      className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
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
  const [monthRange] = useState(currentMonthRange);

  const allAthleteIds = athletes.map((a) => a.athlete_id);

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
      session?.attendance_summary?.find((a) => a.athlete_id === athleteId)
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
