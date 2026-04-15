import { useQuery } from "@tanstack/react-query";

import { getParentUsers } from "@/api/parents";

export function useParentUsers(params?: { club_id?: number }) {
  return useQuery({
    queryKey: ["parent-users", params],
    queryFn: () => getParentUsers(params),
  });
}
