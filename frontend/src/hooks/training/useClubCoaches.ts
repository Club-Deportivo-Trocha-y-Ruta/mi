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
 * Decisión T066: `clubId` queda soportado en la firma pero hoy ningún
 * llamador lo pasa — el endpoint ya acota los resultados al club del
 * entrenador que llama (`backend/app/routers/users.py:140-210`), así que un
 * entrenador de un solo club obtiene el resultado correcto sin el filtro.
 * Acotar explícitamente al club de la sesión en modo edición (§10.1)
 * requeriría propagar `session.club_id` desde `SessionFormPage`/
 * `SessionWizard` hasta `StepGeneral`, cambio que se dejó fuera para no
 * tocar más superficie de la necesaria en esta tarea — ver reporte de T066.
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
