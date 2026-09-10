import { useQuery } from "@tanstack/react-query";

import { getAthletes } from "@/api/athletes";
import { useAuthStore } from "@/store/auth.store";
import type { AthleteOut } from "@/types/athlete.types";

/**
 * useArchivedAthletes — atletas archivados para la vista admin
 * `/admin/atletas-archivados` (contracts/athlete-archive.md §4, §11).
 *
 * `GET /api/athletes?include_archived=true` devuelve activos + archivados en
 * una sola página (admin-only); el cliente filtra por `deleted_at !== null`
 * — el mismo query key que `useAthletes(["athletes", filters])`, con
 * `include_archived: true` en el objeto de filtros.
 */
export function useArchivedAthletes() {
  const accessToken = useAuthStore((s) => s.accessToken);

  const query = useQuery({
    queryKey: ["athletes", { include_archived: true }],
    queryFn: () => getAthletes({ include_archived: true }),
    enabled: !!accessToken,
  });

  const items: AthleteOut[] = (query.data?.items ?? []).filter(
    (athlete) => athlete.deleted_at != null,
  );

  return { ...query, items };
}
