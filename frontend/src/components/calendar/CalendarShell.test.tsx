import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CalendarShell, type CalendarView } from "./CalendarShell";
import { makeCalendarListItem } from "@/test/msw/calendarHandlers";

// FullCalendar uses ResizeObserver internally
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

function renderShell({
  events = [makeCalendarListItem()],
  onEventClick = vi.fn(),
  onDateClick = vi.fn(),
  view = "dayGridMonth" as CalendarView,
} = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onEventClick,
    onDateClick,
    ...render(
      <QueryClientProvider client={qc}>
        <CalendarShell
          events={events}
          onEventClick={onEventClick}
          onDateClick={onDateClick}
          view={view}
        />
      </QueryClientProvider>,
    ),
  };
}

describe("CalendarShell", () => {
  it("renders the calendar container", () => {
    renderShell();
    expect(screen.getByTestId("calendar-shell")).toBeInTheDocument();
  });

  it("renders with empty events without crashing", () => {
    renderShell({ events: [] });
    expect(screen.getByTestId("calendar-shell")).toBeInTheDocument();
  });

  it("renders with multiple events", () => {
    renderShell({
      events: [
        makeCalendarListItem({ id: 1, title: "Entrenamiento A" }),
        makeCalendarListItem({
          id: 2,
          title: "Competencia Valle",
          event_type: "competition",
        }),
      ],
    });
    expect(screen.getByTestId("calendar-shell")).toBeInTheDocument();
  });

  it("renders in list view without crashing", () => {
    renderShell({ view: "listMonth" as CalendarView });
    expect(screen.getByTestId("calendar-shell")).toBeInTheDocument();
  });

  it("renders in week view without crashing", () => {
    renderShell({ view: "timeGridWeek" as CalendarView });
    expect(screen.getByTestId("calendar-shell")).toBeInTheDocument();
  });
});
