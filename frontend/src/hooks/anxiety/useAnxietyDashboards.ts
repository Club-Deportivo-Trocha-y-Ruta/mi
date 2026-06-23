import { useMutation, useQuery } from "@tanstack/react-query";

import { getAthleteSeries, getGroupByEvent, importCsv } from "@/api/anxiety";
import type {
  AthleteSeries,
  GroupTriage,
  ImportResult,
} from "@/types/anxiety.types";

/** GET /athletes/{id}/series?instrument_type= */
export function useAthleteSeries(
  athleteId: number,
  instrumentType: string,
  enabled = true,
) {
  return useQuery<AthleteSeries>({
    queryKey: ["anxiety", "series", athleteId, instrumentType],
    queryFn: () => getAthleteSeries(athleteId, instrumentType),
    enabled: enabled && athleteId > 0 && instrumentType.length > 0,
  });
}

/** GET /groups/by-event/{eventId} */
export function useGroupByEvent(eventId: number, enabled = true) {
  return useQuery<GroupTriage>({
    queryKey: ["anxiety", "group", eventId],
    queryFn: () => getGroupByEvent(eventId),
    enabled: enabled && eventId > 0,
  });
}

/** POST /import — CSV histórico. */
export function useAnxietyImport() {
  return useMutation<ImportResult, unknown, File>({
    mutationKey: ["anxiety", "import"],
    mutationFn: (file) => importCsv(file),
  });
}
