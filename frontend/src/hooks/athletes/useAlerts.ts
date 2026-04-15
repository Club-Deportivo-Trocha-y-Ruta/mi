import { useQuery } from "@tanstack/react-query";

import { getAlerts } from "@/api/alerts";

export function useAlerts(params?: { club_id?: number }) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => getAlerts(params),
  });
}
