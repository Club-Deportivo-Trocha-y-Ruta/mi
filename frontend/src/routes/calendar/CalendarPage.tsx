import { useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";

import { CalendarShell, type CalendarView } from "@/components/calendar/CalendarShell";
import { CalendarFiltersBar } from "@/components/calendar/FiltersBar";
import { EventDrawer } from "@/components/calendar/EventDrawer";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { useCalendarEvents } from "@/api/calendar";
import { useCalendarFiltersStore } from "@/store/calendarFilters.store";
import type { CalendarEventListItem } from "@/types/calendar.types";

const VIEW_LABELS: Record<CalendarView, string> = {
  dayGridMonth: "Mes",
  timeGridWeek: "Semana",
  timeGridDay: "Día",
  listMonth: "Agenda",
};

function currentMonthRange() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  return {
    from: new Date(year, month, 1).toISOString().slice(0, 10),
    to: new Date(year, month + 1, 0).toISOString().slice(0, 10),
  };
}

export function CalendarPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<CalendarView>("dayGridMonth");
  // Inicializar con null y esperar el primer onDatesSet de FullCalendar evita
  // una segunda llamada a la API cuando el grid reporta un rango distinto al
  // mes calendario puro (FullCalendar incluye días de meses adyacentes).
  const [rangeFrom, setRangeFrom] = useState<string | null>(null);
  const [rangeTo, setRangeTo] = useState<string | null>(null);
  const [drawerEventId, setDrawerEventId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { eventTypes, athleteId, category } = useCalendarFiltersStore();

  const eventsQuery = useCalendarEvents({
    from: rangeFrom ?? currentMonthRange().from,
    to: rangeTo ?? currentMonthRange().to,
    event_types: eventTypes.length > 0 ? eventTypes : undefined,
    athlete_id: athleteId,
    category: category,
  });

  const events: CalendarEventListItem[] = eventsQuery.data ?? [];
  const eventsColdStart = isColdStartError(eventsQuery.error);

  const handleEventClick = useCallback((eventId: number) => {
    setDrawerEventId(eventId);
    setDrawerOpen(true);
  }, []);

  const handleDateClick = useCallback(
    (dateStr: string) => {
      navigate(`/calendar/events/new?date=${dateStr}`);
    },
    [navigate],
  );

  const handleDatesSet = useCallback((start: string, end: string) => {
    setRangeFrom(start);
    setRangeTo(end);
  }, []);

  return (
    <>
      <section className="space-y-5">
        <PageHeader
          title="Calendario"
          subtitle="Eventos, entrenamientos y competencias del club."
          actions={
            <>
              {/* View selector */}
              <div className="flex rounded-lg overflow-hidden shadow-ring">
                {(Object.entries(VIEW_LABELS) as [CalendarView, string][]).map(
                  ([v, label]) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setView(v)}
                      className={`px-3 py-2 text-sm font-medium transition-colors ${
                        view === v
                          ? "bg-charcoal text-white"
                          : "bg-white text-charcoal hover:bg-light-gray"
                      }`}
                      aria-pressed={view === v}
                    >
                      {label}
                    </button>
                  ),
                )}
              </div>

              <Link
                to="/calendar/events/new"
                className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white shadow-button-highlight transition-opacity hover:opacity-70"
              >
                + Nuevo evento
              </Link>
            </>
          }
        />

        <CalendarFiltersBar />

        {eventsQuery.isError && (
          <ErrorState
            message={eventsColdStart ? undefined : "No se pudieron cargar los eventos. Intenta de nuevo."}
            onRetry={() => void eventsQuery.refetch()}
            isColdStart={eventsColdStart}
          />
        )}

        {eventsQuery.isLoading && (
          <div
            className="h-96 animate-pulse rounded-xl bg-light-gray"
            aria-label="Cargando calendario..."
          />
        )}

        {!eventsQuery.isLoading && (
          <div className="rounded-xl bg-white p-4 shadow-card">
            <CalendarShell
              events={events}
              onEventClick={handleEventClick}
              onDateClick={handleDateClick}
              view={view}
              onViewChange={setView}
              onDatesSet={handleDatesSet}
            />
          </div>
        )}
      </section>

      <EventDrawer
        eventId={drawerEventId}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />
    </>
  );
}
