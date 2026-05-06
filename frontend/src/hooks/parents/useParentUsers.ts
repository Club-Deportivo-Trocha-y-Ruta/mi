import { useQuery } from "@tanstack/react-query";

import { getParentUsers } from "@/api/parents";
import { useAuthStore } from "@/store/auth.store";

export function useParentUsers(params?: { club_id?: number }) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ["parent-users", params],
    queryFn: () => getParentUsers(params),
    enabled: !!accessToken,
  });
}
