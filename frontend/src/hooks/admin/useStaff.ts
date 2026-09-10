/**
 * useStaff — listado de personal (`coach`/`admin`) para la página
 * "Personal del club" (feature 041, contracts/staff-admin.md §7).
 *
 * No duplica `hooks/governance/useClubStaff.ts` (que solo pide
 * `role=coach` para alimentar el filtro del historial de auditoría): esta
 * lista pide ambos roles, acepta el filtro de estado y devuelve la forma
 * completa de `UserOut` (incluida `created_by_display_name`).
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listUsers } from "@/api/users";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

export interface UseStaffParams {
  isActive?: boolean;
}

export function staffQueryKey(isActive?: boolean) {
  return ["staff", "list", { isActive: isActive ?? null }] as const;
}

export function useStaff({ isActive }: UseStaffParams = {}) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: staffQueryKey(isActive),
    queryFn: ({ signal }) =>
      listUsers(
        { role: [UserRole.coach, UserRole.admin], is_active: isActive },
        { signal },
      ),
    placeholderData: keepPreviousData,
    enabled: !!accessToken,
  });
}
