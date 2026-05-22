import { http, HttpResponse } from "msw";

import type {
  CalendarEventListItem,
  CalendarEventRead,
  EventAttendanceRead,
} from "@/types/calendar.types";

// ─── Fixture factories ────────────────────────────────────────────────────────

export function makeCalendarListItem(
  overrides?: Partial<CalendarEventListItem>,
): CalendarEventListItem {
  return {
    id: 1,
    title: "Entrenamiento técnico XCO",
    start: "2026-05-15T08:00:00",
    end: "2026-05-15T09:30:00",
    allDay: false,
    event_type: "training_session",
    color_hex: null,
    extended_props: {},
    ...overrides,
  };
}

export function makeCalendarEventRead(
  overrides?: Partial<CalendarEventRead>,
): CalendarEventRead {
  return {
    id: 1,
    club_id: 1,
    event_type: "training_session",
    status: "scheduled",
    title: "Entrenamiento técnico XCO",
    description: "Foco en técnica de frenada en descenso",
    location: "Pista XCO La Buitrera",
    start_at: "2026-05-15T08:00:00",
    end_at: "2026-05-15T09:30:00",
    all_day: false,
    timezone: "America/Bogota",
    event_data: {},
    color_hex: null,
    race_event_id: null,
    created_by_user_id: 10,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
    ...overrides,
  };
}

export function makeEventAttendance(
  overrides?: Partial<EventAttendanceRead>,
): EventAttendanceRead {
  return {
    id: 1,
    event_id: 1,
    athlete_id: 42,
    rsvp_status: "pending",
    rsvp_at: null,
    rsvp_by_user_id: null,
    actual_status: "unknown",
    notes: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

// ─── MSW handlers ─────────────────────────────────────────────────────────────

export const calendarHandlers = [
  // GET /api/calendar/events — list
  http.get("*/api/calendar/events", () => {
    return HttpResponse.json([
      makeCalendarListItem(),
      makeCalendarListItem({
        id: 2,
        title: "Copa Valle II — Ginebra",
        event_type: "competition",
        start: "2026-05-28T08:00:00",
        end: "2026-05-28T17:00:00",
        color_hex: "#dc2626",
      }),
    ]);
  }),

  // GET /api/calendar/events/:id — detail
  http.get("*/api/calendar/events/:id", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeCalendarEventRead({ id }));
  }),

  // POST /api/calendar/events — create
  http.post("*/api/calendar/events", () => {
    return HttpResponse.json(makeCalendarEventRead({ id: 99 }), { status: 201 });
  }),

  // PATCH /api/calendar/events/:id — update
  http.patch("*/api/calendar/events/:id", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeCalendarEventRead({ id }));
  }),

  // DELETE /api/calendar/events/:id — cancel
  http.delete("*/api/calendar/events/:id", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(
      makeCalendarEventRead({ id, status: "cancelled" }),
    );
  }),

  // POST /api/calendar/events/:id/rsvp — RSVP
  http.post("*/api/calendar/events/:id/rsvp", ({ params }) => {
    const eventId = Number(params.id);
    return HttpResponse.json(
      makeEventAttendance({ event_id: eventId, rsvp_status: "accepted" }),
    );
  }),

  // GET /api/calendar/events/:id/attendances — attendances list
  http.get("*/api/calendar/events/:id/attendances", ({ params }) => {
    const eventId = Number(params.id);
    return HttpResponse.json([
      makeEventAttendance({ event_id: eventId }),
      makeEventAttendance({
        id: 2,
        event_id: eventId,
        athlete_id: 43,
        rsvp_status: "accepted",
      }),
    ]);
  }),
];
