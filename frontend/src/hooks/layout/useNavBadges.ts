/**
 * useNavBadges — conteos de pendientes que el sidebar del entrenador muestra
 * como insignia junto al área correspondiente (feature 035).
 *
 * Fuentes: exactamente las mismas queries (y las mismas queryKeys) que ya
 * alimentan `PendingInbox` en el Inicio, así que el sidebar NO dispara
 * peticiones adicionales — reutiliza el cache de TanStack Query:
 *   - Competencias → `useRaceEventsList({ season: currentSeason() })`,
 *     filtrando client-side `!has_results && event_date < hoy` (resultados
 *     por importar), idéntico al filtro de la fila "Resultados por importar".
 *   - Familias    → `useNewsletterStatusSummary(año, mes)` del mes en curso,
 *     contando ítems con `status !== "sent"` (boletines pendientes).
 *   - «Cargas e identidades» (feature 045, ítem `competitions.imports` de
 *     `navigation.ts`) → `useCoachSummary()` (misma queryKey que `PendingInbox`
 *     → sin petición adicional): `identity_decisions_pending +
 *     imports_in_progress + unlinked_competitors_pending` — los tres tipos de
 *     ítem que reúne el buzón (decisiones, cargas y competidores sin enlazar,
 *     FR-033). Un sumando `null`/ausente (agregado no disponible, o backend
 *     previo a ese campo) no cuenta; si ninguno está disponible no hay
 *     insignia.
 *
 * Sobre `staleTime: 5 * 60_000`: `useRaceEventsList` ya lo fija explícitamente
 * y el `QueryClient` de la app (App.tsx) usa ese mismo default de 5 min para
 * todas las queries, así que ambas insignias respetan esa ventana sin
 * reconfigurar hooks ajenos a este feature.
 *
 * Contrato de estados: una insignia sólo existe cuando su fuente resolvió con
 * un conteo mayor que cero. Cargando, con error o en cero → `undefined`, es
 * decir *sin* insignia: nunca un "0", ni un esqueleto, ni un punto vacío que
 * el entrenador tenga que interpretar.
 */
import { useMemo } from "react";

import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { useNewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";
import { CLUB_TIMEZONE, currentSeason, diffDaysFromToday } from "@/lib/datetime";
import { getVisibleAreas, type NavRole } from "@/lib/navigation";

/**
 * Conteos por `NavArea.id` (`competitions`, `families`) y, desde la feature
 * 045, por `NavItem.id` cuando la insignia va en un sub-ítem del área
 * (`competitions.imports` = «Cargas e identidades»). Una clave ausente =
 * sin insignia.
 */
export interface NavBadgeCounts {
  competitions?: number;
  families?: number;
  "competitions.imports"?: number;
}

/**
 * Suma los conteos disponibles: `null`/`undefined` (agregado caído o backend
 * previo a la 045) se omiten en vez de tratarse como cero. Devuelve
 * `undefined` cuando ninguno está disponible.
 */
function sumAvailable(...counts: Array<number | null | undefined>): number | undefined {
  const available = counts.filter((count): count is number => typeof count === "number");
  return available.length === 0 ? undefined : available.reduce((a, b) => a + b, 0);
}

/** "Hoy" en `CLUB_TIMEZONE` — mismo cálculo que `PendingInbox`. */
function useCurrentYearMonth(): { year: number; month: number } {
  return useMemo(() => {
    const [year, month] = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: CLUB_TIMEZONE,
    })
      .format(new Date())
      .split("-")
      .map(Number);
    return { year, month };
  }, []);
}

/** Cero, cargando o error → `undefined` (sin insignia). */
function toBadge(count: number): number | undefined {
  return count > 0 ? count : undefined;
}

export function useNavBadges(role: NavRole): NavBadgeCounts {
  const visibleAreaIds = useMemo(
    () => new Set(getVisibleAreas(role).map((area) => area.id)),
    [role],
  );

  const raceQuery = useRaceEventsList({ season: currentSeason() });
  const { year, month } = useCurrentYearMonth();
  const newslettersQuery = useNewsletterStatusSummary(year, month);
  // Feature 045 — misma queryKey que `PendingInbox`: reutiliza el cache.
  const coachSummaryQuery = useCoachSummary();

  const identityPending = coachSummaryQuery.data?.identity_decisions_pending;
  const importsInProgress = coachSummaryQuery.data?.imports_in_progress;
  const unlinkedPending = coachSummaryQuery.data?.unlinked_competitors_pending;
  const coachSummaryReady = coachSummaryQuery.isSuccess;

  const raceItems = raceQuery.data?.items;
  const newsletterItems = newslettersQuery.data?.items;
  const raceReady = raceQuery.isSuccess;
  const newslettersReady = newslettersQuery.isSuccess;

  return useMemo(() => {
    const badges: NavBadgeCounts = {};

    if (visibleAreaIds.has("competitions") && raceReady) {
      const pendingResults = (raceItems ?? []).filter((item) => {
        const days = diffDaysFromToday(item.event_date);
        return !item.has_results && days !== null && days < 0;
      }).length;
      const badge = toBadge(pendingResults);
      if (badge !== undefined) badges.competitions = badge;
    }

    if (visibleAreaIds.has("competitions") && coachSummaryReady) {
      const badge = toBadge(
        sumAvailable(identityPending, importsInProgress, unlinkedPending) ?? 0,
      );
      if (badge !== undefined) badges["competitions.imports"] = badge;
    }

    if (visibleAreaIds.has("families") && newslettersReady) {
      const pendingNewsletters = (newsletterItems ?? []).filter(
        (item) => item.status !== "sent",
      ).length;
      const badge = toBadge(pendingNewsletters);
      if (badge !== undefined) badges.families = badge;
    }

    return badges;
  }, [
    coachSummaryReady,
    identityPending,
    importsInProgress,
    newsletterItems,
    newslettersReady,
    raceItems,
    raceReady,
    unlinkedPending,
    visibleAreaIds,
  ]);
}
