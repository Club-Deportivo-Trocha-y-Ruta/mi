import { useQuery } from "@tanstack/react-query";

import { getMyAthletes } from "@/api/parents";
import { useAuthStore } from "@/store/auth.store";

export function useMyAthletes() {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ["my-athletes"],
    queryFn: getMyAthletes,
    enabled: !!accessToken,
  });
}
