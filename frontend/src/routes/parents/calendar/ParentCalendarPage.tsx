import { useCallback, useEffect, useState } from "react";

import { CalendarShell } from "@/components/calendar/CalendarShell";
import { ParentEventDrawer } from "@/components/parents/ParentEventDrawer";
import { useCalendarEvents } from "@/api/calendar";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import type { CalendarView } from "@/components/calendar/CalendarShell";
import type { MyAthleteOut } from "@/types/parent.types";

// ─── matchMedia helper ────────────────────────────────────────────────────────

function isDesktop(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(min-width: 768px)").matches;
}

function useIsDesktop(): boolean {
  const [desktop, setDesktop] = useState<boolean>(isDesktop);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    function handler(e: MediaQueryListEvent) {
      setDesktop(e.matches);
    }
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return desktop;
}

// ─── Month range helper ───────────────────────────────────────────────────────

function computeMonthRange(offset: number): { from: string; to: string; label: string } {
  const now = new Date();
  const target = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const ty = target.getFullYear();
  const tm = String(target.getMonth() + 1).padStart(2, "0");
  const lastDay = new Date(ty, target.getMonth() + 1, 0).getDate();
  const from = `${ty}-${tm}-01`;
  const to = `${ty}-${tm}-${lastDay}`;
  const label = new Intl.DateTimeFormat("es-CO", {
    month: "long",
    year: "numeric",
  }).format(new Date(`${from}T12:00:00`));
  return { from, to, label };
}

// ─── Athlete chip ─────────────────────────────────────────────────────────────

function AthleteChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-2.5 min-h-11 text-sm font-medium transition-colors ${
        active
          ? "bg-charcoal text-white"
          : "bg-white text-mid-gray hover:text-charcoal shadow-ring"
      }`}
      aria-pressed={active}
    >
      {label}
    </button>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function ParentCalendarPage() {
  const desktop = useIsDesktop();

  const [selectedAthleteId, setSelectedAthleteId] = useState<number | null>(null);
  const [monthOffset, setMonthOffset] = useState(0);
  const [calendarView, setCalendarView] = useState<CalendarView>(
    desktop ? "dayGridMonth" : "listMonth",
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);

  // Rango real de la query — se actualiza tanto por los botones custom como
  // por la navegación interna de FullCalendar (onDatesSet), de modo que siempre
  // coincidan los eventos mostrados con los cargados.
  const defaultRange = computeMonthRange(0);
  const [queryFrom, setQueryFrom] = useState(defaultRange.from);
  const [queryTo, setQueryTo] = useState(defaultRange.to);

  // Sync view when viewport changes
  useEffect(() => {
    setCalendarView(desktop ? "dayGridMonth" : "listMonth");
  }, [desktop]);

  const athletesQuery = useMyAthletes();
  const athletes: MyAthleteOut[] = athletesQuery.data ?? [];

  const { from: offsetFrom, to: offsetTo, label: monthLabel } = computeMonthRange(monthOffset);

  // Cuando el usuario navega con los botones custom, sincronizamos la query range.
  useEffect(() => {
    setQueryFrom(offsetFrom);
    setQueryTo(offsetTo);
  }, [offsetFrom, offsetTo]);

  const eventsQuery = useCalendarEvents({
    from: queryFrom,
    to: queryTo,
    ...(selectedAthleteId != null ? { athlete_id: selectedAthleteId } : {}),
  });

  const events = eventsQuery.data ?? [];

  function handleEventClick(eventId: number) {
    setSelectedEventId(eventId);
    setDrawerOpen(true);
  }

  // CalendarShell requires onDateClick; no-op for parent (read-only)
  function handleDateClick(_dateStr: string) {}

  // Sincroniza el rango de la query cuando FullCalendar navega internamente
  const handleDatesSet = useCallback((start: string, end: string) => {
    setQueryFrom(start);
    setQueryTo(end);
  }, []);

  const hasAthletes = athletes.length > 0;

  return (
    <section className="space-y-5">
      {/* Header */}
      <div>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Mi calendario
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Eventos donde tu atleta está convocado.
        </p>
      </div>

      {/* Sin atletas vinculados */}
      {!athletesQuery.isLoading && !hasAthletes && (
        <div
          className="rounded-xl bg-white px-5 py-10 text-center shadow-card"
          data-testid="no-athletes-state"
        >
          <p className="text-sm font-medium text-charcoal">
            Sin atletas vinculados
          </p>
          <p className="mt-1 text-sm text-mid-gray">
            Tu cuenta no está asociada a ningún atleta. Contacta al entrenador
            para que vincule a tu hijo o hija a tu cuenta.
          </p>
        </div>
      )}

      {hasAthletes && (
        <>
          {/* Banner informativo */}
          <div
            className="rounded-xl bg-blue-50 px-4 py-3"
            role="note"
            aria-label="Información de visibilidad del calendario"
          >
            <p className="text-sm text-blue-800">
              Estás viendo eventos donde tu{athletes.length > 1 ? "s hijos están convocados" : " hijo está convocado"}.
            </p>
          </div>

          {/* Navegación mensual */}
          <div className="flex items-center gap-2" data-testid="month-nav">
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
              disabled={monthOffset >= 12}
              className="min-h-11 rounded-lg px-3 py-2.5 text-sm text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Mes siguiente"
            >
              Mes siguiente →
            </button>
          </div>

          {/* Selector de atleta (solo si padre tiene más de uno) */}
          {athletes.length > 1 && (
            <div
              className="flex flex-wrap gap-2"
              role="group"
              aria-label="Filtrar por atleta"
              data-testid="athlete-filter"
            >
              <AthleteChip
                label="Todos"
                active={selectedAthleteId === null}
                onClick={() => setSelectedAthleteId(null)}
              />
              {athletes.map((a) => (
                <AthleteChip
                  key={a.athlete_id}
                  label={`${a.athlete_first_name} ${a.athlete_last_name}`}
                  active={selectedAthleteId === a.athlete_id}
                  onClick={() => setSelectedAthleteId(a.athlete_id)}
                />
              ))}
            </div>
          )}

          {/* Loading skeleton */}
          {(eventsQuery.isLoading || athletesQuery.isLoading) && (
            <div
              className="h-80 animate-pulse rounded-xl bg-light-gray"
              aria-label="Cargando calendario"
              data-testid="calendar-loading"
            />
          )}

          {/* Error state */}
          {eventsQuery.isError && !eventsQuery.isLoading && (
            <div
              className="rounded-xl bg-white px-5 py-6 shadow-card"
              role="alert"
            >
              <p className="text-sm text-mid-gray">
                No fue posible cargar los eventos. Intenta de nuevo.
              </p>
            </div>
          )}

          {/* Empty state */}
          {!eventsQuery.isLoading && !eventsQuery.isError && events.length === 0 && (
            <div
              className="rounded-xl bg-white px-5 py-10 text-center shadow-card"
              data-testid="empty-state"
            >
              <p className="text-sm text-mid-gray">Sin eventos este mes.</p>
            </div>
          )}

          {/* Calendar */}
          {!eventsQuery.isLoading && !eventsQuery.isError && events.length > 0 && (
            <div data-testid="calendar-container">
              <CalendarShell
                events={events}
                onEventClick={handleEventClick}
                onDateClick={handleDateClick}
                view={calendarView}
                onViewChange={setCalendarView}
                onDatesSet={handleDatesSet}
              />
            </div>
          )}
        </>
      )}

      {/* Event Drawer */}
      <ParentEventDrawer
        eventId={selectedEventId}
        open={drawerOpen}
        onOpenChange={(open) => {
          setDrawerOpen(open);
          if (!open) setSelectedEventId(null);
        }}
      />
    </section>
  );
}
