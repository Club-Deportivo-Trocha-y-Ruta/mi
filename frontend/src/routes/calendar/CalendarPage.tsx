import { useState, useCallback } from "react";
import { Link } from "react-router-dom";

import { CalendarShell, type CalendarView } from "@/components/calendar/CalendarShell";
import { CalendarFiltersBar } from "@/components/calendar/FiltersBar";
import { EventDrawer } from "@/components/calendar/EventDrawer";
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

  const handleEventClick = useCallback((eventId: number) => {
    setDrawerEventId(eventId);
    setDrawerOpen(true);
  }, []);

  const handleDateClick = useCallback((_dateStr: string) => {
    // Navigation happens via Link with query param — handled by EventFormPage
  }, []);

  const handleDatesSet = useCallback((start: string, end: string) => {
    setRangeFrom(start);
    setRangeTo(end);
  }, []);

  return (
    <>
      <section className="space-y-5">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1
              className="text-2xl text-charcoal"
              style={{
                fontFamily: "'Cal Sans', system-ui, sans-serif",
                fontWeight: 600,
              }}
            >
              Calendario
            </h1>
            <p className="mt-0.5 text-sm text-mid-gray">
              Eventos, entrenamientos y competencias del club.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* View selector */}
            <div className="flex rounded-lg overflow-hidden">
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
              className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
            >
              + Nuevo evento
            </Link>
          </div>
        </div>

        <CalendarFiltersBar />

        {eventsQuery.isError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            No se pudieron cargar los eventos. Intenta de nuevo.
          </p>
        )}

        {eventsQuery.isLoading && (
          <div
            className="h-96 animate-pulse rounded-xl bg-light-gray"
            aria-label="Cargando calendario..."
          />
        )}

        {!eventsQuery.isLoading && (
          <div
            className="rounded-xl bg-white p-4"
          >
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
