/**
 * invalidation.ts — helper centralizado de invalidación cruzada para el
 * módulo Competitions (race-events ↔ calendar ↔ results ↔ standings ↔
 * competitors ↔ race-analysis).
 *
 * Motivación (regla de tres):
 *   - useRaceEvents, useRaceResults, useRaceStandings, y futuros hooks
 *     de roster/calendar-sync necesitan invalidar combinaciones superpuestas.
 *   - Centralizar elimina magic strings duplicados y garantiza que una
 *     mutación que toca un evento invalide todas las queries dependientes.
 *
 * Uso:
 * ```ts
 * import { invalidatePaired } from "@/hooks/race/invalidation";
 *
 * // Dentro de onSuccess de una mutation:
 * onSuccess: async (_data, { id }) => {
 *   await invalidatePaired(queryClient, { raceEventId: id });
 * }
 * ```
 *
 * Keys exportadas para uso directo en tests y hooks:
 *   - raceResultsKeys   → resultados por evento
 *   - raceStandingsKeys → clasificación general de temporada
 *   - raceAnalysisKeys  → runs de análisis IA
 *   - competitorsKeys   → corredores/matches
 *   - calendarKeys      → eventos del calendario vinculados
 */
import type { QueryClient } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Query key factories
// ---------------------------------------------------------------------------

/**
 * Keys para los resultados por evento (GET /race-events/{id}/results).
 */
export const raceResultsKeys = {
  /** Raíz — invalida todos los resultados de todos los eventos. */
  all: ["raceResults"] as const,

  /** Todas las variantes de un evento específico (con y sin filtros). */
  byEvent: (raceEventId: number) =>
    ["raceResults", "event", raceEventId] as const,

  /** Resultado con filtros específicos. */
  byEventFiltered: (
    raceEventId: number,
    filters: { category_id?: number; club_only?: boolean },
  ) => ["raceResults", "event", raceEventId, filters] as const,
} as const;

/**
 * Keys para la clasificación general de temporada
 * (GET /race-events/{id}/standings).
 */
export const raceStandingsKeys = {
  /** Raíz — invalida todos los standings. */
  all: ["raceStandings"] as const,

  /** Todas las variantes de un evento específico. */
  byEvent: (raceEventId: number) =>
    ["raceStandings", "event", raceEventId] as const,

  /** Standings con filtros específicos. */
  byEventFiltered: (
    raceEventId: number,
    filters: { category_id?: number; club_only?: boolean },
  ) => ["raceStandings", "event", raceEventId, filters] as const,
} as const;

/**
 * Keys para los runs de análisis IA (race-analysis).
 * Sincronizados con los hooks existentes en useClubInsightsByRace.
 */
export const raceAnalysisKeys = {
  /** Raíz — invalida todos los análisis. */
  all: ["raceAnalysis"] as const,

  /** Análisis de una válida específica. */
  byEvent: (raceEventId: number) =>
    ["raceAnalysis", "event", raceEventId] as const,
} as const;

/**
 * Keys para corredores/matches (competitors).
 */
export const competitorsKeys = {
  /** Raíz — invalida todos los corredores. */
  all: ["competitors"] as const,

  /** Corredores de una válida específica. */
  byEvent: (raceEventId: number) =>
    ["competitors", "event", raceEventId] as const,
} as const;

/**
 * Prefijo de las queries del calendario (sincronizado con hooks/calendar/).
 * Invalidar este prefijo cubre todas las variantes de lista y detalle.
 */
export const calendarQueryRoot = ["calendar"] as const;

// ---------------------------------------------------------------------------
// invalidatePaired
// ---------------------------------------------------------------------------

export interface InvalidatePairedOptions {
  /**
   * ID del race event afectado.
   * Si se pasa, invalida las queries dependientes de ese evento específico
   * (results, standings, competitors, raceAnalysis).
   * Si no se pasa, invalida las raíces de todas las entidades.
   */
  raceEventId?: number;

  /**
   * Si es true, también invalida las queries del calendario vinculado.
   * Por defecto false — solo necesario en mutaciones que modifican la
   * asociación competition ↔ calendar event.
   */
  includeCalendar?: boolean;
}

/**
 * Invalida de forma coordinada todas las queries que dependen de un
 * race-event: resultados, clasificación, corredores, y análisis IA.
 *
 * Se llama desde el `onSuccess` de mutations de:
 *   - commit/re-import (Wave A, D)
 *   - athlete link/unlink (Wave C)
 *   - calendar-sync (Wave E)
 *
 * Las invalidaciones son `void`-ed (fire and forget) para no bloquear el
 * flujo del componente; TanStack Query gestiona el estado de re-fetch.
 */
export function invalidatePaired(
  queryClient: QueryClient,
  options: InvalidatePairedOptions = {},
): void {
  const { raceEventId, includeCalendar = false } = options;

  if (raceEventId !== undefined) {
    // Invalida resultados del evento específico (todas las variantes de filtro)
    void queryClient.invalidateQueries({
      queryKey: raceResultsKeys.byEvent(raceEventId),
    });

    // Invalida standings del evento específico
    void queryClient.invalidateQueries({
      queryKey: raceStandingsKeys.byEvent(raceEventId),
    });

    // Invalida corredores del evento específico
    void queryClient.invalidateQueries({
      queryKey: competitorsKeys.byEvent(raceEventId),
    });

    // Invalida análisis IA del evento específico
    void queryClient.invalidateQueries({
      queryKey: raceAnalysisKeys.byEvent(raceEventId),
    });
  } else {
    // Invalidación global (ej. re-import masivo o reset de temporada)
    void queryClient.invalidateQueries({ queryKey: raceResultsKeys.all });
    void queryClient.invalidateQueries({ queryKey: raceStandingsKeys.all });
    void queryClient.invalidateQueries({ queryKey: competitorsKeys.all });
    void queryClient.invalidateQueries({ queryKey: raceAnalysisKeys.all });
  }

  if (includeCalendar) {
    void queryClient.invalidateQueries({ queryKey: calendarQueryRoot });
  }
}
