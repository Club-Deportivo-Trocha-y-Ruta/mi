/**
 * Funciones HTTP puras para calendar events.
 *
 * Los hooks de TanStack Query viven en `@/hooks/calendar/index.ts`.
 * Re-exports al final preservan los imports históricos.
 */
import { apiClient } from "@/api/client";
import type {
  AvailableRaceEvent,
  CalendarEventListItem,
  CalendarEventRead,
  CalendarFilters,
  EventAttendanceRead,
  EventCreatePayload,
  EventType,
  EventUpdatePayload,
  RSVPPayload,
} from "@/types/calendar.types";

const BASE = "/api/calendar/events";

// ─── API functions ────────────────────────────────────────────────────────────

export async function fetchCalendarEvents(
  filters: CalendarFilters,
): Promise<CalendarEventListItem[]> {
  const params: Record<string, string | string[]> = {
    from: filters.from,
    to: filters.to,
  };
  if (filters.event_types && filters.event_types.length > 0) {
    params["event_types[]"] = filters.event_types;
  }
  if (filters.athlete_id != null) {
    params.athlete_id = String(filters.athlete_id);
  }
  if (filters.category) {
    params.category = filters.category;
  }
  const response = await apiClient.get<CalendarEventListItem[]>(BASE, {
    params,
    paramsSerializer: (p) => {
      const parts: string[] = [];
      for (const [k, v] of Object.entries(p)) {
        if (Array.isArray(v)) {
          v.forEach((item) => parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(item)}`));
        } else {
          parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v as string)}`);
        }
      }
      return parts.join("&");
    },
  });
  return response.data;
}

export async function fetchCalendarEvent(id: number): Promise<CalendarEventRead> {
  const response = await apiClient.get<CalendarEventRead>(`${BASE}/${id}`);
  return response.data;
}

export async function createCalendarEvent(
  payload: EventCreatePayload,
): Promise<CalendarEventRead> {
  const response = await apiClient.post<CalendarEventRead>(BASE, payload);
  return response.data;
}

export async function updateCalendarEvent(
  id: number,
  payload: EventUpdatePayload,
): Promise<CalendarEventRead> {
  const response = await apiClient.patch<CalendarEventRead>(`${BASE}/${id}`, payload);
  return response.data;
}

export async function cancelCalendarEvent(
  id: number,
  reason?: string,
): Promise<CalendarEventRead> {
  const params: Record<string, string> = {};
  if (reason) params.reason = reason;
  const response = await apiClient.delete<CalendarEventRead>(`${BASE}/${id}`, { params });
  return response.data;
}

export async function deleteCalendarEventPermanent(id: number): Promise<void> {
  await apiClient.delete(`${BASE}/${id}/permanent`);
}

export async function rsvpEvent(
  id: number,
  payload: RSVPPayload,
): Promise<EventAttendanceRead> {
  const response = await apiClient.post<EventAttendanceRead>(
    `${BASE}/${id}/rsvp`,
    payload,
  );
  return response.data;
}

export async function fetchEventAttendances(
  id: number,
  _eventType: EventType,
): Promise<EventAttendanceRead[]> {
  const response = await apiClient.get<EventAttendanceRead[]>(
    `${BASE}/${id}/attendances`,
  );
  return response.data;
}

// ─── Race events helpers (BE-2) ──────────────────────────────────────────────

/**
 * Lista los race_events de la temporada que aún no están enlazados a
 * un calendar_event (excluye los `cancelled`). Pueblan el dropdown de
 * "asociar válida" cuando se crea/edita un evento de calendario tipo
 * `competition` (FE-2).
 */
export async function getAvailableRaceEvents(
  season: number,
): Promise<AvailableRaceEvent[]> {
  const response = await apiClient.get<AvailableRaceEvent[]>(
    "/api/race-events/available-for-calendar",
    { params: { season } },
  );
  return response.data;
}

// ─── Re-export de hooks (migración incremental: ver @/hooks/calendar) ────────

export {
  useAvailableRaceEvents,
  useCalendarEvent,
  useCalendarEvents,
  useCancelCalendarEvent,
  useCreateCalendarEvent,
  useDeleteCalendarEventPermanent,
  useEventAttendances,
  useRSVPEvent,
  useUpdateCalendarEvent,
} from "@/hooks/calendar";
