/**
 * Ruta de la competencia asociada a un resultado (feature 045, FR-017).
 *
 * Coach va al detalle interno, familia a su vista de solo lectura. Mismo par
 * de rutas que `CompetitionsListPage` (`/competitions/:id`) y
 * `ParentEventDetailPage` (`/parents/competitions/:raceEventId`). Fuente
 * única para la tabla, la gráfica de progresión y la tarjeta de campeonato.
 */
export type RaceEventAudience = "coach" | "family";

export function raceEventHref(
  audience: RaceEventAudience,
  eventId: number,
): string {
  return audience === "family"
    ? `/parents/competitions/${eventId}`
    : `/competitions/${eventId}`;
}
