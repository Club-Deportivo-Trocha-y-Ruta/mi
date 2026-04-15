import { useQuery } from "@tanstack/react-query";

import { getParentAthletes } from "@/api/parents";

export function useParentAthletes(params?: {
  athlete_id?: number;
  parent_id?: number;
}) {
  return useQuery({
    queryKey: ["parent-athletes", params],
    queryFn: () => getParentAthletes(params),
    enabled: params?.athlete_id !== undefined || params?.parent_id !== undefined,
  });
}
