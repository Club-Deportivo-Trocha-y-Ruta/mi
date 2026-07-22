/**
 * useGroupAnalysis — hook para lanzar y monitorear análisis grupales IA
 * desde el tab Insights de una competencia (Feature 010, US1).
 *
 * Responsabilidades:
 *  1. Recovery query: GET /race-events/{id}/runs?active_only=true para
 *     restaurar runs en curso tras refresh de página (FR-012).
 *  2. Launch mutation: POST /race-events/{id}/runs — inicia análisis para
 *     todos los atletas con resultados (o el subconjunto indicado).
 *  3. Merges recovered runs + launched items en un array `runs` unificado.
 *  4. `groupState` derivado: "idle" | "in_progress" | "partial" | "completed".
 *  5. `retry(athleteIds)`: re-lanza solo los atletas fallidos/backpressure.
 *  6. Invalida `["club-insights-by-race", raceEventId]` cuando algún run
 *     llega a terminal "done" (para que el grid de insights se refresque).
 *
 * Diseño deliberado: el hook NO hace polling directamente. Cada GroupRunRow
 * monta su propio useRunStatus(runId) para el run que le corresponde (patrón
 * componente-owns-polling). Esto mantiene el hook simple y reutilizable y
 * evita prop-drilling del estado de polling.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getRaceEventRuns, launchGroupAnalysis } from "@/api/raceAnalysis";
import type {
  GroupRunLaunchRequest,
  GroupRunLaunchResponse,
  GroupRunOutcome,
  RaceEventRunItem,
  RunState,
} from "@/types/raceAnalysis.types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Entrada unificada de un run en curso (merge de recovery + launch). */
export interface TrackedRunEntry {
  athlete_id: number;
  /** Nombre de display recuperado del backend. */
  name: string;
  /** null cuando el outcome fue backpressure / already_running / error. */
  run_id: string | null;
  /**
   * outcome viene de la respuesta de launch (started, backpressure, etc.).
   * Para runs recuperados vía GET /runs, es siempre "started" (ya corriendo).
   */
  outcome: GroupRunOutcome | "recovered";
  /** Mensaje informativo en es-CO para outcomes no-started. */
  detail: string | null;
}

export type GroupState = "idle" | "in_progress" | "partial" | "completed";

export interface UseGroupAnalysisReturn {
  /** Runs actualmente trackeados (recovery + lanzados). */
  runs: TrackedRunEntry[];
  /** Estado global del grupo. */
  groupState: GroupState;
  /** Lanza análisis grupal (opcionalmente un subconjunto). */
  launch: (body?: GroupRunLaunchRequest) => void;
  /** Re-lanza solo los atletas cuyos outcomes son retryable. */
  retry: (athleteIds: number[]) => void;
  /** true mientras la mutación de launch está pendiente. */
  isLaunching: boolean;
  /** Error de la última mutación (puede ser un AxiosError). */
  launchError: unknown;
  /** Datos de la respuesta de la última mutación. */
  lastLaunchData: GroupRunLaunchResponse | null;
  /** true mientras se carga la recovery query. */
  isRecovering: boolean;
  /** Callback que GroupRunRow llama cuando un run llega a estado terminal. */
  notifyRunTerminated: (runId: string, state: RunState) => void;
}

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const groupAnalysisKeys = {
  eventRuns: (raceEventId: number) =>
    ["race-analysis", "event-runs", raceEventId] as const,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isTerminalRunState(state: RunState | undefined | null): boolean {
  return !!state && (state === "done" || state === "failed" || state === "cancelled" || state === "error");
}

const FAILED_TERMINAL_STATES = new Set<RunState>(["failed", "cancelled", "error"]);

function deriveGroupState(
  runs: TrackedRunEntry[],
  terminalStates: Record<string, RunState>,
): GroupState {
  if (runs.length === 0) return "idle";

  const nonStarted = runs.filter((r) => r.run_id === null);
  const started = runs.filter((r) => r.run_id !== null);

  if (started.length === 0) {
    // All were rejected (backpressure / already_running / error)
    return "partial";
  }

  // Un run con run_id sigue "en curso" hasta que su polling (GroupRunRow)
  // reporte un estado terminal vía notifyRunTerminated — sin este chequeo,
  // un run failed queda leído como in_progress para siempre y el botón de
  // lanzar se queda bloqueado (bug reportado: "Fallido" en la fila pero
  // "Análisis en curso…" nunca se apaga).
  const stillPending = started.some((r) => !terminalStates[r.run_id!]);
  if (stillPending) return "in_progress";

  if (nonStarted.length > 0) return "partial";

  const anyFailed = started.some((r) =>
    FAILED_TERMINAL_STATES.has(terminalStates[r.run_id!]),
  );
  return anyFailed ? "partial" : "completed";
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useGroupAnalysis(raceEventId: number): UseGroupAnalysisReturn {
  const queryClient = useQueryClient();

  // Local state: merged list of tracked runs.
  const [trackedRuns, setTrackedRuns] = useState<TrackedRunEntry[]>([]);
  const [lastLaunchData, setLastLaunchData] =
    useState<GroupRunLaunchResponse | null>(null);

  // Set of run_ids that have reached a terminal state (done/failed).
  // Used to trigger insights invalidation without re-renders from a ref.
  const terminalRunIds = useRef<Set<string>>(new Set());

  // Estado terminal por run_id (done/failed/cancelled/error), alimentado por
  // GroupRunRow vía notifyRunTerminated. Necesario para que deriveGroupState
  // sepa cuándo un run dejó de estar "en curso".
  const [terminalStates, setTerminalStates] = useState<Record<string, RunState>>({});

  // ── Recovery query ──────────────────────────────────────────────────────
  const recoveryQuery = useQuery({
    queryKey: groupAnalysisKeys.eventRuns(raceEventId),
    queryFn: ({ signal }) =>
      getRaceEventRuns(raceEventId, { activeOnly: true }, { signal }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  // Seed trackedRuns from recovery when we get data and have no local runs yet.
  useEffect(() => {
    if (!recoveryQuery.data) return;
    const recovered = recoveryQuery.data.runs;
    if (recovered.length === 0) return;

    setTrackedRuns((prev) => {
      // Only seed if we have no previous launches to avoid overwriting live data.
      if (prev.length > 0) return prev;
      return recovered.map(
        (r: RaceEventRunItem): TrackedRunEntry => ({
          athlete_id: r.athlete_id,
          name: r.athlete_display_name,
          run_id: r.run_id,
          outcome: "recovered",
          detail: null,
        }),
      );
    });
  }, [recoveryQuery.data]);

  // ── Launch mutation ─────────────────────────────────────────────────────
  const launchMutation = useMutation<
    GroupRunLaunchResponse,
    unknown,
    GroupRunLaunchRequest
  >({
    mutationKey: ["race-analysis", "launch-group", raceEventId],
    mutationFn: (body) => launchGroupAnalysis(raceEventId, body),
    onSuccess: (data) => {
      setLastLaunchData(data);

      // Merge started items into trackedRuns.
      setTrackedRuns((prev) => {
        const byAthleteId = new Map<number, TrackedRunEntry>(
          prev.map((r) => [r.athlete_id, r]),
        );
        for (const item of data.items) {
          byAthleteId.set(item.athlete_id, {
            athlete_id: item.athlete_id,
            name: item.athlete_display_name,
            run_id: item.run_id,
            outcome: item.outcome,
            detail: item.detail,
          });
        }
        return Array.from(byAthleteId.values());
      });

      // Invalidate recovery query so a page refresh sees fresh data.
      void queryClient.invalidateQueries({
        queryKey: groupAnalysisKeys.eventRuns(raceEventId),
      });
    },
  });

  // ── Public: notifyRunTerminated ─────────────────────────────────────────
  // Called by GroupRunRow when a run reaches "done" state.
  const notifyRunTerminated = useCallback(
    (runId: string, state: RunState) => {
      if (!isTerminalRunState(state)) return;

      setTerminalStates((prev) =>
        prev[runId] === state ? prev : { ...prev, [runId]: state },
      );

      if (terminalRunIds.current.has(runId)) return;
      terminalRunIds.current.add(runId);

      if (state === "done") {
        void queryClient.invalidateQueries({
          queryKey: ["club-insights-by-race", raceEventId],
        });
      }
    },
    [queryClient, raceEventId],
  );

  // ── Public: launch ──────────────────────────────────────────────────────
  const launch = useCallback(
    (body: GroupRunLaunchRequest = {}) => {
      launchMutation.mutate(body);
    },
    [launchMutation],
  );

  // ── Public: retry ───────────────────────────────────────────────────────
  const retry = useCallback(
    (athleteIds: number[]) => {
      launchMutation.mutate({ athlete_ids: athleteIds });
    },
    [launchMutation],
  );

  // ── Derived groupState ──────────────────────────────────────────────────
  const groupState = deriveGroupState(trackedRuns, terminalStates);

  return {
    runs: trackedRuns,
    groupState,
    launch,
    retry,
    isLaunching: launchMutation.isPending,
    launchError: launchMutation.error,
    lastLaunchData,
    isRecovering: recoveryQuery.isLoading,
    notifyRunTerminated,
  };
}
