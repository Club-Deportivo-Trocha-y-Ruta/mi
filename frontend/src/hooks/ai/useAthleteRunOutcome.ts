/**
 * useAthleteRunOutcome — sigue un run de análisis por atleta hasta su estado
 * terminal y notifica el desenlace (FR-013 / US1-Sc5).
 *
 * Motivación: el POST de launch (`useLaunchAthleteAnalysis`) solo confirma que
 * el run agéntico arrancó, no que terminó. Sin este seguimiento, un botón
 * "Analizar con IA" se quedaba en un "Análisis iniciado" verde aunque el run
 * fallara segundos después (presupuesto, proveedor, etc.), dejando al coach con
 * un falso positivo — exactamente lo que FR-013 pide evitar ("la finalización o
 * el fallo se confirma con una notificación breve no bloqueante").
 *
 * Diseño: envuelve `useRunStatus` (mismo polling que usa GroupRunRow), el
 * `queryClient` y `toast` en un único hook con efectos, para que el componente
 * consumidor (AnalyzeAthleteButton) siga siendo presentacional y mockeable en
 * tests sin necesidad de un QueryClientProvider.
 *
 * - `done`      → toast de éxito + invalida insights/frescura del atleta.
 * - `failed | error | cancelled` → toast de error + expone `failureMessage`
 *   para que el consumidor reemplace su estado optimista por uno de error.
 * - `hitl_waiting` NO es terminal: la aprobación se hace en el tab Insights, no
 *   se emite toast en ese estado.
 *
 * Degrada con gracia: si el polling falla (red / 404), `runState` queda
 * `undefined`, no hay efecto terminal y el botón conserva su comportamiento
 * previo (el coach igual puede seguir el run en el tab Insights).
 */
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useRunStatus, isTerminalState } from "@/hooks/ai/useRaceRun";

export interface UseAthleteRunOutcomeOptions {
  athleteId: number;
  displayName: string;
}

export interface UseAthleteRunOutcomeResult {
  /** Mensaje cuando el run terminó en fallo/cancelación; null en otro caso. */
  failureMessage: string | null;
}

export function useAthleteRunOutcome(
  runId: string | null,
  { athleteId, displayName }: UseAthleteRunOutcomeOptions,
): UseAthleteRunOutcomeResult {
  const queryClient = useQueryClient();
  const runStatus = useRunStatus(runId);
  const runState = runStatus.data?.latest?.state;

  const [failureMessage, setFailureMessage] = useState<string | null>(null);
  const handledRunRef = useRef<string | null>(null);

  // Nuevo run → limpia el desenlace previo.
  useEffect(() => {
    handledRunRef.current = null;
    setFailureMessage(null);
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    if (!isTerminalState(runState)) return;
    if (handledRunRef.current === runId) return;
    handledRunRef.current = runId;

    if (runState === "done") {
      toast.success(`Análisis de ${displayName} completado.`);
      // El run terminó: refresca insights + frescura para reflejarlo.
      void queryClient.invalidateQueries({
        predicate: (q) => {
          const key = q.queryKey;
          if (!Array.isArray(key)) return false;
          const [base, id] = key;
          if (base === "club-insights-by-race") return true;
          return (
            (base === "athlete-runs" || base === "athlete-insights") &&
            id === athleteId
          );
        },
      });
      return;
    }

    // failed | error | cancelled
    const msg =
      runState === "cancelled"
        ? `El análisis de ${displayName} fue cancelado.`
        : `El análisis de ${displayName} falló. Intenta de nuevo.`;
    toast.error(msg);
    setFailureMessage(msg);
  }, [runId, runState, displayName, athleteId, queryClient]);

  return { failureMessage };
}
