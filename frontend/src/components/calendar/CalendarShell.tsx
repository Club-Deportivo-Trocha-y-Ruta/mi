import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import listPlugin from "@fullcalendar/list";
import interactionPlugin from "@fullcalendar/interaction";
import esLocale from "@fullcalendar/core/locales/es";
import type { EventClickArg, DatesSetArg, EventInput } from "@fullcalendar/core";
import type { DateClickArg } from "@fullcalendar/interaction";

import type { CalendarEventListItem } from "@/types/calendar.types";
import { bgForEventType, colorForEventType } from "./colors";

import styles from "./CalendarShell.module.css";

export type CalendarView =
  | "dayGridMonth"
  | "timeGridWeek"
  | "timeGridDay"
  | "listMonth";

interface CalendarShellProps {
  events: CalendarEventListItem[];
  onEventClick: (eventId: number) => void;
  onDateClick: (dateStr: string) => void;
  view: CalendarView;
  onViewChange?: (view: CalendarView) => void;
  onDatesSet?: (start: string, end: string) => void;
}

function toFullCalendarEvents(events: CalendarEventListItem[]): EventInput[] {
  return events.map((ev) => ({
    id: String(ev.id),
    title: ev.title,
    start: ev.start,
    end: ev.end,
    allDay: ev.allDay,
    backgroundColor: ev.color_hex ?? bgForEventType(ev.event_type),
    borderColor: "transparent",
    textColor: colorForEventType(ev.event_type).text,
    extendedProps: {
      eventType: ev.event_type,
      originalId: ev.id,
      ...ev.extended_props,
    },
  }));
}

export function CalendarShell({
  events,
  onEventClick,
  onDateClick,
  view,
  onViewChange,
  onDatesSet,
}: CalendarShellProps) {
  function handleEventClick(arg: EventClickArg) {
    const id = Number(arg.event.id);
    if (id) onEventClick(id);
  }

  function handleDateClick(arg: DateClickArg) {
    onDateClick(arg.dateStr);
  }

  function handleDatesSet(arg: DatesSetArg) {
    const newView = arg.view.type as CalendarView;
    onViewChange?.(newView);
    onDatesSet?.(
      arg.start.toISOString().slice(0, 10),
      arg.end.toISOString().slice(0, 10),
    );
  }

  return (
    <div className={styles.wrapper} data-testid="calendar-shell">
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
        initialView={view}
        locale={esLocale}
        events={toFullCalendarEvents(events)}
        nowIndicator
        dayMaxEvents={3}
        weekends
        height="auto"
        eventClick={handleEventClick}
        dateClick={handleDateClick}
        datesSet={handleDatesSet}
        headerToolbar={{
          left: "prev,next today",
          center: "title",
          right: "",
        }}
      />
    </div>
  );
}
