import { useQuery } from "@tanstack/react-query";

import { getAlerts } from "@/api/alerts";
import { useAuthStore } from "@/store/auth.store";

export function useAlerts(params?: { club_id?: number }) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => getAlerts(params),
    enabled: !!accessToken,
  });
}
