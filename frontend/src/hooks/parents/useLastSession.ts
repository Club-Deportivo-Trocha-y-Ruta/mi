/**
 * useLastSession — Última sesión ejecutada (executed) de un atleta del padre.
 *
 * Wave 4 — home feed: card "Última sesión" muestra qué pasó en el último
 * entrenamiento (foco técnico, asistencia, link a detalle).
 *
 * Ventana: últimos 30 días. Si el atleta lleva más de un mes sin sesión
 * ejecutada, el feed muestra el empty state en el card consumidor — eso
 * es información valiosa, no un bug.
 */
import { useQuery } from "@tanstack/react-query";

import { parentSessionKeys } from "@/api/queryKeys";
import { fetchParentSessions } from "@/api/trainingSessions";
import { useAuthStore } from "@/store/auth.store";
import type { TrainingSession } from "@/types/trainingSession.types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function minusDaysIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function useLastSession(athleteId: number | null | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useQuery<TrainingSession | null>({
    queryKey: parentSessionKeys.lastSession(userId, athleteId ?? null),
    queryFn: async () => {
      if (!athleteId) return null;
      const sessions = await fetchParentSessions(
        {
          from_date: minusDaysIso(30),
          to_date: todayIso(),
          status: "executed",
          athlete_id: athleteId,
        },
        [athleteId],
      );
      const executed = sessions.filter((s) => s.status === "executed");
      executed.sort((a, b) => {
        // Desc — más reciente primero
        const dateCmp = b.scheduled_date.localeCompare(a.scheduled_date);
        if (dateCmp !== 0) return dateCmp;
        return b.scheduled_start_time.localeCompare(a.scheduled_start_time);
      });
      return executed[0] ?? null;
    },
    enabled: !!accessToken && !!athleteId && userId !== null,
  });
}
