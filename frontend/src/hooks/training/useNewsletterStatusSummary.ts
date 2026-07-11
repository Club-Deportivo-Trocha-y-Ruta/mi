/**
 * useNewsletterStatusSummary — resumen de estado de boletines mensuales de
 * TODOS los atletas del club para un año/mes, en UNA sola petición.
 *
 * Reemplaza el fan-out N+1 que usaba el dashboard (un `useAthleteNewsletters`
 * por card renderizada) por una única llamada a un endpoint de resumen
 * liviano. `useAthleteNewsletters`/`useAthleteNewsletter` (src/api/athleteNewsletters.ts)
 * siguen existiendo sin cambios para la vista de detalle por atleta y para
 * `AthleteNewslettersTabPanel` — este hook NO los reemplaza, solo evita que
 * el dashboard los invoque una vez por atleta.
 *
 * Endpoint: GET /api/training/athlete-newsletters/summary?year=&month=
 * Privacy R2: userId al inicio del queryKey (mismo patrón que
 * src/api/athleteNewsletters.ts y src/hooks/consent/index.ts).
 */
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
import type { NewsletterStatus } from "@/types/athleteNewsletter.types";

const SUMMARY_URL = "/api/training/athlete-newsletters/summary";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

/**
 * Una entrada del resumen por atleta. Solo aparecen atletas que YA tienen un
 * boletín generado para el año/mes consultado (igual que antes: la ausencia
 * de un atleta en `items` se interpreta como estado "Sin generar" en la UI).
 */
export interface NewsletterStatusSummaryItem {
  athlete_id: number;
  newsletter_id: number;
  status: NewsletterStatus;
  generated_at: string;
  sent_at: string | null;
}

export interface NewsletterStatusSummary {
  year: number;
  month: number;
  items: NewsletterStatusSummaryItem[];
}

// ---------------------------------------------------------------------------
// Función API pura
// ---------------------------------------------------------------------------

export async function fetchNewsletterStatusSummary(
  year: number,
  month: number,
): Promise<NewsletterStatusSummary> {
  const response = await apiClient.get<NewsletterStatusSummary>(SUMMARY_URL, {
    params: { year, month },
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Hook TanStack Query
// ---------------------------------------------------------------------------

/**
 * Resumen de estado de boletines de todos los atletas del club para un
 * período dado. Pensado para poblar grids/dashboards con una sola petición
 * en lugar de una por atleta renderizado.
 */
export function useNewsletterStatusSummary(
  year: number | undefined,
  month: number | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: ["newsletter-status-summary", userId, year, month],
    queryFn: () => fetchNewsletterStatusSummary(year!, month!),
    enabled: !!accessToken && !!year && !!month,
  });
}
