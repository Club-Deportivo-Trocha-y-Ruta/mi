/**
 * Hooks TanStack Query para el módulo race-analysis v2 (Fase 6).
 *
 * Diseño:
 *  - `useStartRun`         → mutation POST /runs, retorna run_id.
 *  - `useRunStatus(runId)` → polling cada 2s, se detiene en estados
 *                            terminales {done, failed, cancelled, error}.
 *                            Acumula `new_events` localmente y mantiene
 *                            el cursor `since` (last_seq) para slicing.
 *  - `useApproveStep`      → mutation POST /hitl/:step.
 *
 * Notas:
 *  - El servidor entrega `304 Not Modified` (sin body) si no hubo
 *    cambios — `getRunStatus` devuelve `null` y respetamos los datos
 *    cacheados.
 *  - El `select` de TanStack transforma la respuesta cruda en
 *    `RunStatusAccumulated` con todos los eventos acumulados hasta el
 *    momento. El estado se mantiene fuera del cache vía `useRef`.
 *
 * Feature 036 (T082): `useRunResult` y `useInvalidateRun` se eliminaron de
 * este módulo — ningún componente los llamaba. `useRunResult` quedó
 * redundante frente al camino real por el que la UI ya se entera del
 * análisis terminado: `handleRunComplete` invalida las queries de
 * `insights` (ver `invalidateAthleteAiQueries`) y el coach lee el
 * resultado ya persistido, nunca el envelope crudo de `/result`.
 * `useInvalidateRun` marcaba un run como stale a mano, pero esa
 * marca (`stale_since`) la calcula el backend automáticamente
 * (`app/services/race/ai/run_staleness.py`) — `StaleAnalysisBadge.tsx`
 * sólo dispara la re-ejecución (`useReExecuteRun`, que si sigue en uso).
 * Si se necesitara invalidar manualmente en el futuro, el endpoint
 * `POST /runs/:id/invalidate` y su wrapper `invalidateRun` en
 * `api/raceAnalysis.ts` siguen intactos — sólo se quitó el hook sin
 * consumidores.
 */
import { useCallback, useMemo, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  getRunStatus,
  reExecuteRun,
  startRun,
  submitHITLDecision,
} from "@/api/raceAnalysis";
import { invalidateAthleteAiQueries } from "@/hooks/ai/invalidateAthleteAiQueries";
import type {
  HITLDecisionRequest,
  RunEvent,
  RunState,
  RunStatusResponse,
  StartRunRequest,
  StartRunResponse,
} from "@/types/raceAnalysis.types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATES: ReadonlySet<RunState> = new Set([
  "done",
  "failed",
  "cancelled",
  "error",
]);

export function isTerminalState(state: RunState | undefined | null): boolean {
  return !!state && TERMINAL_STATES.has(state);
}

/**
 * T017 — techo duro de polling.
 *
 * Un run que nunca llega a un estado terminal (por ejemplo, quedó
 * huérfano porque Render redesplegó el backend a mitad de un
 * `hitl_waiting`; el checkpoint sqlite del HITL no sobrevive un deploy
 * en el free tier — ver `specs/036-ai-insights-tab-review/research.md`
 * R2) deja de emitir eventos nuevos para siempre: cada poll recibe el
 * mismo `last_seq` y el backend responde 304 indefinidamente. Sin este
 * techo el cliente pollearía por siempre y el coach vería un spinner
 * eterno en vez de un mensaje accionable.
 *
 * Espejo del lado servidor (`data-model.md`, T016): la reconciliación de
 * runs huérfanos al arrancar usa "un umbral generoso, ≥ 2× la duración
 * máxima esperada del pipeline". Este valor sigue el mismo criterio del
 * lado cliente, como red de seguridad independiente para la ventana
 * antes de que corra esa reconciliación (o mientras no esté desplegada).
 *
 * Se mide desde que ESTE hook empezó a observar el run (reloj local,
 * `useRef`), no desde el `started_at` que reporta el servidor: el
 * servidor es la fuente correcta en teoría, pero atarse a él acopla el
 * techo al reloj de quien construya cada fixture de prueba (este
 * módulo y varios más usan fechas fijas tipo "2026-05-20..." que ya
 * quedan "viejas" frente al reloj real). El reloj local sí puede
 * reiniciarse con un refresh de página a mitad de un run — se acepta
 * ese costo a cambio de no depender de relojes ajenos.
 */
export const DEFAULT_MAX_POLLING_MS = 15 * 60 * 1000; // 15 minutos

/** Copy en español que ve el coach cuando se alcanza el techo — la rama
 * `isError` de `AnalysisRunTimeline` ya renderiza `error.message` tal
 * cual, así que este mensaje llega a pantalla sin tocar ese componente.
 * Nunca debe leerse como un hang silencioso. */
export const RUN_NOT_RESPONDING_MESSAGE =
  "El análisis ya no está disponible. Vuelve a lanzarlo.";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const raceRunKeys = {
  all: ["race-analysis"] as const,
  status: (runId: string) =>
    ["race-analysis", "status", runId] as const,
};

// ---------------------------------------------------------------------------
// 6.2 — useStartRun
// ---------------------------------------------------------------------------

export function useStartRun() {
  const queryClient = useQueryClient();
  return useMutation<StartRunResponse, unknown, StartRunRequest>({
    mutationKey: ["race-analysis", "start-run"],
    mutationFn: (body) => startRun(body),
    onSuccess: () => {
      // Reset cualquier listado de runs activos cacheado.
      void queryClient.invalidateQueries({ queryKey: raceRunKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// 6.1 — useRunStatus (polling)
// ---------------------------------------------------------------------------

export interface RunStatusAccumulated {
  /** Última respuesta cruda del backend (excluye 304s). */
  latest: RunStatusResponse;
  /** Todos los eventos acumulados, ordenados por seq asc. */
  events: RunEvent[];
}

export interface UseRunStatusOptions {
  enabled?: boolean;
  /** Override para tests. */
  pollIntervalMs?: number;
  /** Override para tests (T017). Default `DEFAULT_MAX_POLLING_MS`. */
  maxPollingMs?: number;
}

/** Hook polling para el status del run.
 *
 * Mantiene en `useRef` el cursor `since` (= last_seq visto) y el buffer
 * de eventos. Cada poll envía `?since=<cursor>` y al recibir nuevos
 * eventos se concatenan. Cuando el state es terminal, el polling se
 * detiene automáticamente vía `refetchInterval` que retorna `false`.
 */
export function useRunStatus(
  runId: string | null | undefined,
  options: UseRunStatusOptions = {},
): UseQueryResult<RunStatusAccumulated, unknown> & {
  /** Limpia eventos acumulados — útil para re-arrancar timelines. */
  resetEvents: () => void;
} {
  const {
    enabled = true,
    pollIntervalMs = POLL_INTERVAL_MS,
    maxPollingMs = DEFAULT_MAX_POLLING_MS,
  } = options;

  // Estado mutable fuera del cache: cursor + buffer eventos.
  const sinceRef = useRef<number>(0);
  const eventsRef = useRef<RunEvent[]>([]);
  // El state interno fuerza re-render cuando hay cambios efectivos.
  const [, bump] = useState(0);

  // T017 — reloj local del techo de polling: marca cuándo ESTE hook
  // empezó a observar el run actual (no el `started_at` del servidor —
  // ver comentario de `DEFAULT_MAX_POLLING_MS`). Se reinicia cuando
  // `runId` cambia, para que un run nuevo arranque con presupuesto
  // fresco.
  const pollingStartedAtRef = useRef<number | null>(null);
  const observedRunIdRef = useRef<string | null | undefined>(undefined);
  if (observedRunIdRef.current !== runId) {
    observedRunIdRef.current = runId;
    pollingStartedAtRef.current = null;
  }

  const resetEvents = useCallback(() => {
    sinceRef.current = 0;
    eventsRef.current = [];
    bump((n) => n + 1);
  }, []);

  const query = useQuery<RunStatusAccumulated, unknown>({
    queryKey: raceRunKeys.status(runId ?? "none"),
    enabled: enabled && !!runId,
    // Importante: `refetchInterval` recibe el query, devolvemos false
    // cuando el state es terminal para detener el polling.
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return pollIntervalMs;
      if (isTerminalState(data.latest.state)) return false;
      // T017: techo duro alcanzado → dejar de pollear. La query ya quedó
      // en error (ver queryFn) con RUN_NOT_RESPONDING_MESSAGE.
      if (
        pollingStartedAtRef.current !== null &&
        Date.now() - pollingStartedAtRef.current >= maxPollingMs
      ) {
        return false;
      }
      return pollIntervalMs;
    },
    // Evita refetch al recuperar foco mientras el polling ya cubre.
    refetchOnWindowFocus: false,
    retry: false,
    gcTime: 5 * 60 * 1000,
    staleTime: 0,
    queryFn: async ({ signal }) => {
      if (!runId) {
        throw new Error("runId requerido");
      }
      if (pollingStartedAtRef.current === null) {
        pollingStartedAtRef.current = Date.now();
      }
      const since = sinceRef.current;
      const fresh = await getRunStatus(runId, since, { signal });
      if (fresh === null) {
        // 304: reusar evento acumulado, devolvemos un snapshot vacío
        // que refleja "no cambios". Si nunca tuvimos data, el throw
        // forzaría error — preferimos un placeholder mínimo.
        // TanStack guardará este snapshot. Para evitar overwrite con
        // un objeto inválido, sólo devolvemos si ya teníamos uno.
        const prev: RunStatusAccumulated | undefined =
          query.data as RunStatusAccumulated | undefined;
        if (prev) {
          // T017: un run huérfano deja de emitir eventos nuevos — el
          // backend sólo respondería 304 para siempre (`last_seq` nunca
          // avanza). Sin este chequeo el techo nunca se alcanzaría por
          // esta rama, que es justo la que toma un run atascado.
          if (
            !isTerminalState(prev.latest.state) &&
            Date.now() - pollingStartedAtRef.current >= maxPollingMs
          ) {
            throw new Error(RUN_NOT_RESPONDING_MESSAGE);
          }
          return prev;
        }
        // Sin previo: simulamos respuesta vacía pero consistente.
        return {
          latest: {
            run_id: runId,
            state: "running" as RunState,
            progress_pct: 0,
            current_node: null,
            started_at: new Date().toISOString(),
            estimated_seconds_remaining: 0,
            new_events: [],
            last_seq: 0,
          },
          events: [],
        };
      }
      // T017: mismo chequeo para la rama con datos frescos. Se evalúa
      // DESPUÉS de tener el estado más reciente — así un run que
      // efectivamente termina justo pasado el techo (p. ej. llega a
      // "done" en el mismo poll que lo hubiera superado) se muestra
      // como terminado, no como "no responde".
      if (
        !isTerminalState(fresh.state) &&
        Date.now() - pollingStartedAtRef.current >= maxPollingMs
      ) {
        throw new Error(RUN_NOT_RESPONDING_MESSAGE);
      }
      // Acumula nuevos eventos preservando orden por seq.
      if (fresh.new_events.length > 0) {
        // Filtro defensivo por si el server repite seqs.
        const seenSeqs = new Set(eventsRef.current.map((e) => e.seq));
        for (const evt of fresh.new_events) {
          if (!seenSeqs.has(evt.seq)) {
            eventsRef.current.push(evt);
          }
        }
        eventsRef.current.sort((a, b) => a.seq - b.seq);
      }
      sinceRef.current = Math.max(sinceRef.current, fresh.last_seq);
      return {
        latest: fresh,
        events: [...eventsRef.current],
      };
    },
  });

  return useMemo(
    () => ({ ...query, resetEvents }),
    // Re-bind cada render para que el caller siempre vea el último ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query, resetEvents],
  );
}

// ---------------------------------------------------------------------------
// 6.3 — useApproveStep
// ---------------------------------------------------------------------------

export interface ApproveStepVariables {
  stepId: string;
  decision: HITLDecisionRequest;
}

export function useApproveStep(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["race-analysis", "hitl", runId],
    mutationFn: ({ stepId, decision }: ApproveStepVariables) =>
      submitHITLDecision(runId, stepId, decision),
    onSuccess: () => {
      // Fuerza un nuevo poll para ver el evento hitl_response.
      void queryClient.invalidateQueries({
        queryKey: raceRunKeys.status(runId),
      });
      // FE-1: cuando un HITL termina con approve/edit, el insight queda
      // aprobado y publicado por el backend. Las queries del módulo
      // /athletes/{id}/race-analysis/* deben invalidarse para que el
      // perfil del atleta refleje el nuevo insight casi inmediato.
      //
      // Trade-off: aquí no conocemos el athlete_id del run (el hook
      // recibe sólo runId). T042: delegamos en el helper compartido
      // `invalidateAthleteAiQueries` sin pasar `athleteId` — invalida las
      // claves con alcance de atleta (insights, runs, evolution,
      // distribution, insight-detail) para CUALQUIER atleta, más las
      // globales (`club-insights-by-race`, `season-panorama`) siempre. El
      // alcance sigue siendo contenido (un puñado de claves por atleta
      // activo) y evita un round-trip extra para resolver el athlete_id
      // del run. Antes este predicate ad-hoc, además de repetir la lógica
      // del helper, matcheaba por prefijo `"athlete-"` e invalidaba de
      // rebote `athlete-activities` (Strava) y `athlete-newsletter(s)`.
      void invalidateAthleteAiQueries(queryClient);
    },
  });
}

// ---------------------------------------------------------------------------
// PR5 — re-execute (manual, D5)
// ---------------------------------------------------------------------------

/** Re-ejecuta un run (manual, con confirmación del coach — D5). */
export function useReExecuteRun() {
  const queryClient = useQueryClient();
  return useMutation<StartRunResponse, unknown, string>({
    mutationKey: ["race-analysis", "re-execute-run"],
    mutationFn: (runId) => reExecuteRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: raceRunKeys.all });
    },
  });
}
