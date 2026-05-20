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
 *  - `useRunResult`        → GET /result, enabled sólo si state=done.
 *
 * Notas:
 *  - El servidor entrega `304 Not Modified` (sin body) si no hubo
 *    cambios — `getRunStatus` devuelve `null` y respetamos los datos
 *    cacheados.
 *  - El `select` de TanStack transforma la respuesta cruda en
 *    `RunStatusAccumulated` con todos los eventos acumulados hasta el
 *    momento. El estado se mantiene fuera del cache vía `useRef`.
 */
import { useCallback, useMemo, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  getRunResult,
  getRunStatus,
  startRun,
  submitHITLDecision,
} from "@/api/raceAnalysis";
import type {
  HITLDecisionRequest,
  RunEvent,
  RunResultEnvelope,
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

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const raceRunKeys = {
  all: ["race-analysis"] as const,
  status: (runId: string) =>
    ["race-analysis", "status", runId] as const,
  result: (runId: string) =>
    ["race-analysis", "result", runId] as const,
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
  const { enabled = true, pollIntervalMs = POLL_INTERVAL_MS } = options;

  // Estado mutable fuera del cache: cursor + buffer eventos.
  const sinceRef = useRef<number>(0);
  const eventsRef = useRef<RunEvent[]>([]);
  // El state interno fuerza re-render cuando hay cambios efectivos.
  const [, bump] = useState(0);

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
      return isTerminalState(data.latest.state) ? false : pollIntervalMs;
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
        if (prev) return prev;
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
    },
  });
}

// ---------------------------------------------------------------------------
// useRunResult
// ---------------------------------------------------------------------------

export function useRunResult(
  runId: string | null | undefined,
  state: RunState | undefined,
) {
  return useQuery<RunResultEnvelope, unknown>({
    queryKey: raceRunKeys.result(runId ?? "none"),
    enabled: !!runId && state === "done",
    queryFn: () => {
      if (!runId) throw new Error("runId requerido");
      return getRunResult(runId);
    },
    retry: false,
    staleTime: Infinity,
  });
}
