/**
 * useCoachSummary — agregado de mission-control del coach (feature 031).
 *
 * Alimenta el medidor de carga semanal y las filas "Consentimientos
 * pendientes" / "Insights IA desactualizados" del inbox de pendientes en
 * `DashboardPage`.
 *
 * Endpoint: GET /api/dashboard/coach-summary
 *
 * `staleTime: 60_000` + `refetchOnMount: "always"` (research.md R8): el
 * flujo típico es aterrizar en Inicio → resolver un pendiente en otra
 * pantalla → volver a Inicio (remount completo de la ruta), así que se
 * fuerza un refetch en cada mount en vez de depender de invalidación
 * explícita desde cinco mutaciones no relacionadas.
 */
import { useQuery } from "@tanstack/react-query";

import { fetchCoachSummary } from "@/api/dashboard";
import { useAuthStore } from "@/store/auth.store";

export function useCoachSummary() {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ["dashboard", "coach-summary"],
    queryFn: fetchCoachSummary,
    enabled: !!accessToken,
    staleTime: 60_000,
    refetchOnMount: "always",
  });
}
