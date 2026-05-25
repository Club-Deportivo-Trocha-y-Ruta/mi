import { useQuery } from "@tanstack/react-query";

import { getParentAthletes } from "@/api/parents";
import { parentKeys } from "@/api/queryKeys";

export function useParentAthletes(params?: {
  athlete_id?: number;
  parent_id?: number;
}) {
  return useQuery({
    queryKey: parentKeys.athletes(params),
    queryFn: () => getParentAthletes(params),
    enabled: params?.athlete_id !== undefined || params?.parent_id !== undefined,
  });
}
