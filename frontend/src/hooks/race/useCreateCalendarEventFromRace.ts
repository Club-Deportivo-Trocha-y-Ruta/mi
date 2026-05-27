/**
 * useCreateCalendarEventFromRace — wrapper sobre useCreateCalendarEvent que,
 * al crear un calendar_event con race_event_id, invalida también las queries
 * de race-events para que `has_calendar_event` se refresque en:
 *   - CompetitionDetailPage (raceEventKeys.detail)
 *   - CompetitionsListPage (raceEventKeys.lists)
 *   - EventForm dropdown (available-for-calendar)
 *
 * CF6: integración calendar ↔ competencias.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCreateCalendarEvent } from "@/api/calendar";
import { raceEventKeys } from "@/hooks/race/useRaceEvents";
import type { EventCreatePayload } from "@/types/calendar.types";

const CALENDAR_AVAILABLE_ROOT = [
  "calendar",
  "race-events",
  "available-for-calendar",
] as const;

export function useCreateCalendarEventFromRace() {
  const queryClient = useQueryClient();
  const createMutation = useCreateCalendarEvent();

  async function createWithRaceEvent(
    payload: EventCreatePayload,
    raceEventId: number,
  ) {
    const result = await createMutation.mutateAsync(payload);

    // Invalida detalle y lista del race_event para refrescar has_calendar_event
    void queryClient.invalidateQueries({
      queryKey: raceEventKeys.detail(raceEventId),
    });
    void queryClient.invalidateQueries({
      queryKey: raceEventKeys.lists(),
    });
    void queryClient.invalidateQueries({
      queryKey: CALENDAR_AVAILABLE_ROOT,
    });

    return result;
  }

  return {
    ...createMutation,
    createWithRaceEvent,
  };
}
