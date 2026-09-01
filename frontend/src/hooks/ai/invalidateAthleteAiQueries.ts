/**
 * invalidateAthleteAiQueries — única fuente de verdad para "qué queries se
 * refrescan cuando un run de análisis IA de un atleta cambia algo"
 * (feature 036, T042).
 *
 * Antes de este helper la misma decisión estaba implementada TRES veces,
 * dos de ellas incompletas o demasiado amplias:
 *   - `AthleteAIAnalysisTab.tsx` (`handleRunComplete`) invalidaba sólo
 *     claves cuyo primer elemento empieza con `"athlete-"` — perdía
 *     `club-insights-by-race` (grid cross-atleta del tab Insights de
 *     competencias) y `season-panorama` (dashboard de temporada).
 *   - `useAthleteRunOutcome.ts` sí incluía `club-insights-by-race` pero
 *     tampoco `season-panorama`.
 *   - `useRaceRun.ts` (`useApproveStep`) repetía el hueco de
 *     `AthleteAIAnalysisTab.tsx`.
 *
 * Además, el predicate `startsWith("athlete-")` invalidaba de rebote
 * `athlete-activities` (sincronización Strava) y `athlete-newsletter(s)`
 * (boletín mensual) — dominios sin relación con un run de análisis IA.
 * Este helper usa una LISTA EXPLÍCITA en vez de un prefijo, para que un
 * query key futuro que empiece por "athlete-" no quede enganchado por
 * accidente.
 *
 * `athlete-races` (`useAthleteRaces.ts`) queda deliberadamente FUERA de
 * la lista: alimenta el picker de carreras y, por diseño (ver el
 * docstring de ese hook), sólo cambia cuando se ingesta una planilla
 * nueva — nunca como consecuencia de que un run de IA termine.
 */
import type { QueryClient } from "@tanstack/react-query";

/**
 * Claves con alcance de atleta: `[base, athleteId, ...resto]`. Se
 * invalidan sólo para el `athleteId` del run que cambió — otros atletas no
 * deben re-fetchear.
 */
const ATHLETE_SCOPED_AI_QUERY_BASES: readonly string[] = [
  "athlete-insights",
  "athlete-insight-detail",
  "athlete-runs",
  "athlete-evolution",
  "athlete-distribution",
];

/**
 * Claves globales / cross-atleta que un run de IA de CUALQUIER atleta
 * puede afectar (grids y dashboards agregados). Se invalidan siempre,
 * sin filtrar por `athleteId`.
 */
const GLOBAL_AI_QUERY_BASES: readonly string[] = [
  "club-insights-by-race",
  "season-panorama",
];

/**
 * Invalida las queries TanStack afectadas por un cambio de estado de un
 * run de análisis IA (terminó, un HITL se decidió, se lanzó uno nuevo...).
 *
 * @param queryClient - instancia de `useQueryClient()` del caller.
 * @param athleteId - atleta dueño del run. Cuando se omite (p. ej.
 *   `useApproveStep`, que sólo conoce el `runId`, no el `athleteId` del
 *   run que lo originó) se invalidan las claves con alcance de atleta para
 *   CUALQUIER atleta — más amplio, pero el único correcto disponible sin
 *   un round-trip extra para resolver el `athleteId` del run.
 */
export function invalidateAthleteAiQueries(
  queryClient: QueryClient,
  athleteId?: number,
): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (query) => {
      const key = query.queryKey;
      if (!Array.isArray(key) || typeof key[0] !== "string") return false;
      const [base, id] = key;
      if (GLOBAL_AI_QUERY_BASES.includes(base)) return true;
      if (!ATHLETE_SCOPED_AI_QUERY_BASES.includes(base)) return false;
      return athleteId === undefined || id === athleteId;
    },
  });
}
