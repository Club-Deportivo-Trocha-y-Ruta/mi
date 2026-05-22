/**
 * useNextSession — Próxima sesión planeada para un atleta del padre.
 *
 * Wave 4 — home feed: el card "Próximo entrenamiento" necesita una sola
 * sesión, no la lista. Reutilizamos `fetchParentSessions` con un rango
 * que cubre los próximos ~60 días (mes vigente + siguiente) para evitar
 * casos en que la próxima sesión esté justo cruzando mes.
 *
 * Privacy R2/R4: userId al inicio del queryKey + athleteId también. Si
 * el padre cambia de hijo en el AthleteSwitcher, `purgeQueriesForAthlete`
 * limpia esta key del cache.
 */
import { useQuery } from "@tanstack/react-query";

import { fetchParentSessions } from "@/api/trainingSessions";
import { useAuthStore } from "@/store/auth.store";
import type { TrainingSession } from "@/types/trainingSession.types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function plusDaysIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function useNextSession(athleteId: number | null | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useQuery<TrainingSession | null>({
    queryKey: ["parent-next-session", userId, athleteId ?? null],
    queryFn: async () => {
      if (!athleteId) return null;
      const sessions = await fetchParentSessions(
        {
          from_date: todayIso(),
          to_date: plusDaysIso(60),
          status: "planned",
          athlete_id: athleteId,
        },
        // Backend ya filtra por athlete_id, pero pasamos la lista para
        // defensa en profundidad (consistente con useParentSessions).
        [athleteId],
      );
      const planned = sessions.filter((s) => s.status === "planned");
      planned.sort((a, b) => {
        const dateCmp = a.scheduled_date.localeCompare(b.scheduled_date);
        if (dateCmp !== 0) return dateCmp;
        return a.scheduled_start_time.localeCompare(b.scheduled_start_time);
      });
      return planned[0] ?? null;
    },
    enabled: !!accessToken && !!athleteId && userId !== null,
  });
}
