/**
 * Hooks de TanStack Query para calendar events.
 *
 * Las funciones HTTP puras viven en `@/api/calendar`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelCalendarEvent,
  createCalendarEvent,
  deleteCalendarEventPermanent,
  fetchCalendarEvent,
  fetchCalendarEvents,
  fetchEventAttendances,
  rsvpEvent,
  updateCalendarEvent,
} from "@/api/calendar";
import { calendarKeys } from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";
import { useAuthStore } from "@/store/auth.store";
import type {
  CalendarFilters,
  EventType,
  EventUpdatePayload,
  RSVPPayload,
} from "@/types/calendar.types";
import type { UseFormSetError } from "react-hook-form";

export function useCalendarEvents(filters: CalendarFilters) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: calendarKeys.events(filters),
    queryFn: () => fetchCalendarEvents(filters),
    enabled: !!accessToken && !!filters.from && !!filters.to,
    staleTime: 60_000,
  });
}

export function useCalendarEvent(id: number | null) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: calendarKeys.event(id),
    queryFn: () => fetchCalendarEvent(id!),
    enabled: !!accessToken && id != null,
    staleTime: 30_000,
  });
}

export function useCreateCalendarEvent<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCalendarEvent,
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.eventsAll });
    },
  });
}

export function useUpdateCalendarEvent<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: EventUpdatePayload }) =>
      updateCalendarEvent(id, payload),
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.eventsAll });
      void queryClient.invalidateQueries({
        queryKey: calendarKeys.event(variables.id),
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
      void queryClient.invalidateQueries({ queryKey: calendarKeys.eventsAll });
      void queryClient.invalidateQueries({
        queryKey: calendarKeys.event(variables.id),
      });
    },
  });
}

export function useDeleteCalendarEventPermanent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: number }) => deleteCalendarEventPermanent(id),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.eventsAll });
      void queryClient.invalidateQueries({
        queryKey: calendarKeys.event(variables.id),
      });
    },
  });
}

export function useRSVPEvent(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RSVPPayload) => rsvpEvent(eventId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.eventsAll });
      void queryClient.invalidateQueries({
        queryKey: calendarKeys.event(eventId),
      });
      void queryClient.invalidateQueries({
        queryKey: calendarKeys.attendances(eventId),
      });
    },
  });
}

export function useEventAttendances(eventId: number | null, eventType: EventType) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: calendarKeys.attendances(eventId),
    queryFn: () => fetchEventAttendances(eventId!, eventType),
    enabled: !!accessToken && eventId != null && eventId > 0,
    staleTime: 30_000,
  });
}

export { useAvailableRaceEvents } from "@/hooks/calendar/useAvailableRaceEvents";
