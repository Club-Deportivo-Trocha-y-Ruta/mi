/**
 * useClubStaff — lista de personal (coach + admin) para poblar el filtro
 * "Entrenador" del historial de auditoría (feature 041 — gobernanza
 * multi-coach).
 *
 * `CoachFilter` no hace fetch propio (ver su docstring) — este hook es la
 * fuente que alimenta la página contenedora (`ClubHistoryPage`). Reutiliza
 * `GET /api/users?role=coach`, ya expuesto a coach y admin
 * (`backend/app/routers/users.py::list_users`, `require_role([admin, coach])`),
 * sin declarar un endpoint nuevo — la lista de "Personal del club"
 * (`hooks/admin/useStaff.ts`, contracts/staff-admin.md §7) es un módulo
 * aparte, fuera del alcance de esta tarea.
 */
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
import type { UserListOut } from "@/types/user.types";

export interface ClubStaffOption {
  id: number;
  displayName: string;
}

async function getClubCoaches(): Promise<UserListOut> {
  const response = await apiClient.get<UserListOut>("/api/users", {
    params: { role: "coach" },
  });
  return response.data;
}

export function useClubStaff() {
  const accessToken = useAuthStore((s) => s.accessToken);

  const query = useQuery({
    queryKey: ["club-staff", "coaches"],
    queryFn: getClubCoaches,
    enabled: !!accessToken,
    staleTime: 5 * 60_000,
  });

  const coaches: ClubStaffOption[] = (query.data?.items ?? []).map((user) => ({
    id: user.id,
    displayName: `${user.first_name} ${user.last_name}`.trim(),
  }));

  return { ...query, coaches };
}
