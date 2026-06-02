/**
 * Hooks TanStack Query para el catálogo cerrado de motivos de revisión y el
 * diff read-only de la última revisión (PR4 unificación /competitions).
 */
import { useQuery } from "@tanstack/react-query";

import { getRaceEventDiff, getRevisionReasons } from "@/api/raceImports";

/** Catálogo cerrado de motivos de revisión (estático durante la sesión). */
export function useRevisionReasons() {
  return useQuery({
    queryKey: ["revision-reasons"],
    queryFn: ({ signal }) => getRevisionReasons({ signal }),
    staleTime: 60 * 60_000, // 1h: catálogo cerrado, cambia rara vez.
  });
}

/** Diff read-only de la última revisión de una válida. */
export function useRaceEventDiff(raceEventId: number | null) {
  return useQuery({
    queryKey: ["race-event-diff", raceEventId],
    queryFn: ({ signal }) => getRaceEventDiff(raceEventId!, { signal }),
    enabled: raceEventId !== null && !Number.isNaN(raceEventId),
    staleTime: 30_000,
  });
}
