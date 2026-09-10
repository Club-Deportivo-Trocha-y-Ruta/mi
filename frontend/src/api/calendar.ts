import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
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
import { raceEventKeys } from "@/hooks/race/useRaceEvents";

/** Prefijo de la query key de available-for-calendar. */
const CALENDAR_AVAILABLE_ROOT = [
  "calendar",
  "race-events",
  "available-for-calendar",
] as const;

const BASE = "/api/calendar/events";

/**
 * Feature 041 — gobernanza multi-coach (T067, contracts/session-coaches.md
 * §8.2, §10.3). `coach_user_id` no se agregó a `CalendarFilters`
 * (`types/calendar.types.ts`) para mantener el cambio acotado al archivo que
 * T067 tiene asignado — se modela aquí como extensión local aditiva del
 * mismo tipo. Un parent que lo envíe recibe 403 del backend.
 */
export interface CalendarFiltersWithCoach extends CalendarFilters {
  coach_user_id?: number | null;
}

// ─── API functions ────────────────────────────────────────────────────────────

export async function fetchCalendarEvents(
  filters: CalendarFiltersWithCoach,
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
  if (filters.coach_user_id != null) {
    params.coach_user_id = String(filters.coach_user_id);
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
  reasonCode: string,
): Promise<CalendarEventRead> {
  const response = await apiClient.delete<CalendarEventRead>(`${BASE}/${id}`, {
    data: { reason_code: reasonCode },
  });
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

// ─── TanStack Query hooks ─────────────────────────────────────────────────────

export function useCalendarEvents(filters: CalendarFiltersWithCoach) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["calendar", "events", filters],
    queryFn: () => fetchCalendarEvents(filters),
    enabled: !!accessToken && !!filters.from && !!filters.to,
    staleTime: 60_000,
  });
}

export function useCalendarEvent(id: number | null) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["calendar", "event", id],
    queryFn: () => fetchCalendarEvent(id!),
    enabled: !!accessToken && id != null,
    staleTime: 30_000,
  });
}

export function useCreateCalendarEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCalendarEvent,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["calendar", "events"] });

      // CF6: si el evento creado tiene race_event_id, invalidamos los datos
      // de la válida para que has_calendar_event se refresque en tiempo real
      // en CompetitionDetailPage y CompetitionsListPage.
      const raceEventId = (variables as { race_event_id?: number | null }).race_event_id;
      if (raceEventId != null) {
        void queryClient.invalidateQueries({
          queryKey: raceEventKeys.detail(raceEventId),
        });
        void queryClient.invalidateQueries({
          queryKey: raceEventKeys.lists(),
        });
        void queryClient.invalidateQueries({
          queryKey: CALENDAR_AVAILABLE_ROOT,
        });
      }
    },
  });
}

export function useUpdateCalendarEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: EventUpdatePayload }) =>
      updateCalendarEvent(id, payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["calendar", "events"] });
      void queryClient.invalidateQueries({
        queryKey: ["calendar", "event", variables.id],
      });
    },
  });
}

export function useCancelCalendarEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reasonCode }: { id: number; reasonCode: string }) =>
      cancelCalendarEvent(id, reasonCode),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["calendar", "events"] });
      void queryClient.invalidateQueries({
        queryKey: ["calendar", "event", variables.id],
      });
    },
  });
}

export function useDeleteCalendarEventPermanent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: number }) => deleteCalendarEventPermanent(id),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["calendar", "events"] });
      void queryClient.invalidateQueries({
        queryKey: ["calendar", "event", variables.id],
      });
    },
  });
}

export function useRSVPEvent(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RSVPPayload) => rsvpEvent(eventId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["calendar", "events"] });
      void queryClient.invalidateQueries({
        queryKey: ["calendar", "event", eventId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["calendar", "attendances", eventId],
      });
    },
  });
}

export function useEventAttendances(eventId: number | null, eventType: EventType) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["calendar", "attendances", eventId],
    queryFn: () => fetchEventAttendances(eventId!, eventType),
    enabled: !!accessToken && eventId != null && eventId > 0,
    staleTime: 30_000,
  });
}
