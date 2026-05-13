import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
import type {
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

// ─── TanStack Query hooks ─────────────────────────────────────────────────────

export function useCalendarEvents(filters: CalendarFilters) {
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["calendar", "events"] });
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
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      cancelCalendarEvent(id, reason),
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
