import { useMemo, useState } from "react";

import { MonthlyAveragesBanner } from "@/components/parents/MonthlyAveragesBanner";
import { ParentSessionCard } from "@/components/parents/ParentSessionCard";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentMonthlySummary, useParentSessions } from "@/api/trainingSessions";
import { useParentContextStore } from "@/store/parentContext.store";
import type { KidAttendance, SessionFilters } from "@/types/trainingSession.types";
import type { MyAthleteOut } from "@/types/parent.types";


function AthleteChip({
  athlete,
  active,
  onClick,
}: {
  athlete: MyAthleteOut;
  active: boolean;
  onClick: () => void;
}) {
  // Trim para casos donde last_name viene vacío (ej. chip sintético "Todos") —
  // evita "Todos " con trailing space que screen readers sí leen.
  const displayName = `${athlete.athlete_first_name} ${athlete.athlete_last_name}`.trim();
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
      {displayName}
    </button>
  );
}

export function ParentSessionsPage() {
  const athletesQuery = useMyAthletes();
  const athletes = athletesQuery.data ?? [];

  // Wave 4: el "atleta activo" vive en `useParentContextStore` (persistido
  // en localStorage). Para coherencia con el AthleteSwitcher del header,
  // esta página lee y escribe directo al store en vez de mantener un
  // selectedAthleteId local. Cuando el padre elige un hijo en el header,
  // los chips de esta página se sincronizan; y viceversa.
  const selectedAthleteId = useParentContextStore((s) => s.activeAthleteId);
  const setSelectedAthleteId = useParentContextStore((s) => s.setActiveAthlete);
  const [monthOffset, setMonthOffset] = useState(0); // 0 = current month, -1 = previous, etc.

  const allAthleteIds = athletes.map((a) => a.athlete_id);
  const effectiveAthleteId =
    selectedAthleteId ?? (athletes.length === 1 ? athletes[0]?.athlete_id ?? null : null);
  const focusedAthlete = useMemo<MyAthleteOut | null>(
    () => athletes.find((a) => a.athlete_id === effectiveAthleteId) ?? null,
    [athletes, effectiveAthleteId],
  );

  // Compute month range from offset (0 = current month)
  const monthMeta = useMemo(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + monthOffset;
    const target = new Date(y, m, 1);
    const ty = target.getFullYear();
    const tm0 = target.getMonth();
    const tmIso = String(tm0 + 1).padStart(2, "0");
    const lastDay = new Date(ty, tm0 + 1, 0).getDate();
    return {
      year: ty,
      month: tm0 + 1, // 1-12
      from_date: `${ty}-${tmIso}-01`,
      to_date: `${ty}-${tmIso}-${lastDay}`,
    };
  }, [monthOffset]);

  const monthLabel = new Intl.DateTimeFormat("es-CO", {
    month: "long",
    year: "numeric",
  }).format(new Date(monthMeta.from_date + "T12:00:00"));

  const filters: SessionFilters = {
    from_date: monthMeta.from_date,
    to_date: monthMeta.to_date,
    ...(selectedAthleteId ? { athlete_id: selectedAthleteId } : {}),
  };

  const sessionsQuery = useParentSessions(filters, allAthleteIds);
  const sessions = sessionsQuery.data ?? [];

  // Summary del banner: requiere un atleta concreto. Si el padre no ha elegido
  // y tiene varios atletas, NO mostramos el banner (no podemos agregar entre
  // atletas sin riesgo de exponer datos cruzados).
  const summaryQuery = useParentMonthlySummary(
    monthMeta.year,
    monthMeta.month,
    effectiveAthleteId ?? undefined,
  );
  const summaryList = summaryQuery.data ?? [];
  const focusedSummary = summaryList.find((s) => s.athlete_id === effectiveAthleteId);

  // Only show planned + executed (hide cancelled unless none visible)
  const visibleSessions = sessions.filter(
    (s) => s.status === "planned" || s.status === "executed",
  );
  const showCancelled = visibleSessions.length === 0 && sessions.length > 0;
  const displaySessions = showCancelled ? sessions : visibleSessions;

  const getKidAttendance = (sessionId: number): KidAttendance | null => {
    const athleteId = effectiveAthleteId;
    if (!athleteId) return null;
    const session = sessions.find((s) => s.id === sessionId);
    return session?.kid_attendances?.find((a) => a.athlete_id === athleteId) ?? null;
  };

  const showBanner = !!effectiveAthleteId && !!focusedAthlete;

  // Mensaje para lector de pantalla cuando cambia mes o atleta seleccionado.
  // El padre debe enterarse de que la lista debajo se está actualizando aunque
  // visualmente quede en el mismo sitio. Recalculamos solo con dependencias
  // estables — `aria-live="polite"` evita interrumpir lectura en curso.
  const liveMessage = useMemo(() => {
    const athleteLabel = focusedAthlete
      ? `${focusedAthlete.athlete_first_name} ${focusedAthlete.athlete_last_name}`.trim()
      : athletes.length > 1 ? "todos tus atletas" : "tu atleta";
    if (sessionsQuery.isLoading) {
      return `Cargando entrenamientos de ${monthLabel} para ${athleteLabel}.`;
    }
    return `Mostrando entrenamientos de ${monthLabel} para ${athleteLabel}.`;
  }, [monthLabel, focusedAthlete, athletes.length, sessionsQuery.isLoading]);

  return (
    <section className="space-y-5">
      {/* Live region — anuncia cambios de mes/atleta a lectores de pantalla.
          `sr-only` mantiene el patrón invisible visualmente. */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {liveMessage}
      </div>
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
          className="rounded-xl bg-white px-5 py-10 text-center shadow-ring-soft"
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
            <span aria-hidden="true">←</span> Mes anterior
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
            Mes siguiente <span aria-hidden="true">→</span>
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

      {/* Aviso multi-atleta: el banner solo aparece con atleta seleccionado */}
      {athletes.length > 1 && selectedAthleteId === null && (
        <div
          className="rounded-xl bg-white px-5 py-4 shadow-ring-soft"
          data-testid="multi-athlete-hint"
        >
          <p className="text-sm text-mid-gray">
            Selecciona un atleta arriba para ver los promedios del mes.
          </p>
        </div>
      )}

      {/* Banner promedios mensuales */}
      {showBanner && (
        <MonthlyAveragesBanner
          summary={focusedSummary}
          athleteAgeDecimal={focusedAthlete?.age_decimal ?? null}
          isLoading={summaryQuery.isLoading}
          isError={summaryQuery.isError}
          monthLabel={monthLabel}
          athleteName={
            focusedAthlete
              ? `${focusedAthlete.athlete_first_name} ${focusedAthlete.athlete_last_name}`
              : ""
          }
        />
      )}

      {/* Loading */}
      {(sessionsQuery.isLoading || athletesQuery.isLoading) && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando entrenamientos"
          className="space-y-3"
        >
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}

      {/* Error */}
      {sessionsQuery.isError && !sessionsQuery.isLoading && (
        <div className="rounded-xl bg-white px-5 py-6 shadow-ring-soft">
          <p className="text-sm text-mid-gray">
            No fue posible cargar las sesiones. Intenta de nuevo.
          </p>
        </div>
      )}

      {/* Vacío */}
      {!sessionsQuery.isLoading && !sessionsQuery.isError && displaySessions.length === 0 && (
        <div
          className="rounded-xl bg-white px-5 py-10 text-center shadow-ring-soft"
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
                kidAttendance={getKidAttendance(session.id)}
                athleteAgeDecimal={focusedAthlete?.age_decimal ?? null}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
