import { useQuery } from "@tanstack/react-query";

import { listClubs } from "@/api/clubs";
import { useAuthStore } from "@/store/auth.store";

/**
 * useClubs — catálogo de clubes para el selector "Club" de
 * `StaffCreateSheet` (contracts/staff-admin.md §7, §9). No se persiste en
 * device storage (no está en `PERSIST_ALLOWLIST_PREFIXES`).
 */
export function useClubs() {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ["clubs", "list"],
    queryFn: ({ signal }) => listClubs({ signal }),
    enabled: !!accessToken,
    staleTime: 5 * 60_000,
  });
}
