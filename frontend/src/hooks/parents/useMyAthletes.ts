import { useQuery } from "@tanstack/react-query";

import { getMyAthletes } from "@/api/parents";

export function useMyAthletes() {
  return useQuery({
    queryKey: ["my-athletes"],
    queryFn: getMyAthletes,
  });
}
