/**
 * useClubCoaches — lista de entrenadores del club para el selector de
 * `SessionCoachesField` (feature 041 — gobernanza multi-coach, T066,
 * contracts/session-coaches.md §10.1).
 *
 * Reutiliza `listUsers` (`@/api/users`, contracts/staff-admin.md) filtrando
 * `role=coach` exclusivamente — FR-024: el *picker* del wizard nunca lista
 * `admin`, aunque el backend siga aceptando administradores como
 * entrenadores válidos en filas históricas (§3.3, V2). No duplica
 * `hooks/governance/useClubStaff.ts` (mismo endpoint, pero pensado para
 * alimentar el filtro del historial de auditoría con una forma de dato
 * distinta — `{ id, displayName }` — y sin soporte de `club_id`).
 *
 * `clubId` se propaga desde `SessionFormPage` → `SessionWizard` →
 * `StepGeneral` (sesión cargada en edición; club del propio usuario en
 * creación). Es imprescindible para un `admin`: sin `club_id`, el branch
 * admin de `GET /api/users` (`backend/app/routers/users.py:329-358`) no
 * filtra por club y devuelve entrenadores de todos los clubes. Para un
 * `coach` el backend ya acota por sus propios clubes aunque `club_id` venga
 * vacío (`backend/app/routers/users.py:359-391`), así que el filtro es
 * redundante pero inofensivo en ese caso.
 */
import { useQuery } from "@tanstack/react-query";

import { listUsers } from "@/api/users";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

export interface UseClubCoachesParams {
  clubId?: number;
}

export function clubCoachesQueryKey(clubId?: number) {
  return ["club-coaches", "picker", clubId ?? null] as const;
}

export function useClubCoaches({ clubId }: UseClubCoachesParams = {}) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: clubCoachesQueryKey(clubId),
    queryFn: ({ signal }) =>
      listUsers({ role: [UserRole.coach], club_id: clubId }, { signal }),
    enabled: !!accessToken,
    staleTime: 5 * 60_000,
  });
}
