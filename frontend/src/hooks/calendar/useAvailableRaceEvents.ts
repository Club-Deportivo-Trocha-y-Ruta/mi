/**
 * useAvailableRaceEvents — race_events disponibles para asociar a un
 * calendar_event de tipo `competition` (FE-2).
 *
 * Pide al backend (`GET /api/race-events/available-for-calendar?season=`)
 * la lista de válidas que aún no están enlazadas a un calendar_event
 * activo en la temporada indicada. El dropdown del `EventForm` la usa
 * para evitar que un coach asocie dos veces la misma válida.
 *
 * - `staleTime` 60 s: la lista cambia poco durante la edición del form.
 * - `enabled` exige auth + season válida (number positivo) — sin esto
 *   evitamos requests fantasma al hidratar el form.
 */
import { useQuery } from "@tanstack/react-query";

import { getAvailableRaceEvents } from "@/api/calendar";
import { useAuthStore } from "@/store/auth.store";

export function useAvailableRaceEvents(season: number | null | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["calendar", "race-events", "available-for-calendar", season],
    queryFn: () => getAvailableRaceEvents(season as number),
    enabled:
      !!accessToken && typeof season === "number" && Number.isFinite(season),
    staleTime: 60_000,
  });
}
