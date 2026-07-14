/**
 * GroupAnalysisPanel — panel de análisis grupal IA en el tab Insights.
 *
 * Visible solo para coach/admin (el componente padre InsightsTab controla
 * la visibilidad; este panel no reutiliza useAuthStore para mantenerse
 * presentacional y testeable).
 *
 * Comportamiento:
 *  - Botón "Analizar con IA": deshabilitado cuando !hasResults (FR-002).
 *  - Deshabilitado y con spinner mientras groupState === "in_progress" (FR-012).
 *  - Tras launch: lista de GroupRunRow por atleta con estado en tiempo real.
 *  - "Reintentar pendientes": visible cuando hay runs retryable (backpressure/error).
 *  - Errores 422/429/503 mapeados a copy es-CO (FR-010).
 *
 * Patrones:
 *  - HITL surface: GroupRunRow delega en HITLApprovalCard (componente existente).
 *  - State polling: GroupRunRow monta su propio useRunStatus(runId).
 *  - Invalida insights grid cuando cualquier run completa (via notifyRunTerminated).
 */
import { useCallback } from "react";
import { Loader2, Sparkles } from "lucide-react";
import type { AxiosError } from "axios";

import {
  AIBudgetHint,
  AI_BUDGET_EXHAUSTED_MESSAGE,
  isBudgetExhausted,
} from "@/components/ai/AIBudgetHint";
import { GroupRunRow } from "@/components/competitions/insights/GroupRunRow";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAIStatus } from "@/hooks/ai/useAIStatus";
import {
  useGroupAnalysis,
  type TrackedRunEntry,
} from "@/hooks/ai/useGroupAnalysis";
import type { RunState } from "@/types/raceAnalysis.types";

// ---------------------------------------------------------------------------
// Error message mapping (FR-010)
// ---------------------------------------------------------------------------

function mapLaunchError(error: unknown): string | null {
  if (!error) return null;

  const axiosErr = error as AxiosError<{ detail?: string }>;
  const status = axiosErr?.response?.status;

  if (status === 503) {
    return AI_BUDGET_EXHAUSTED_MESSAGE;
  }
  if (status === 429) {
    return "Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos.";
  }
  if (status === 422) {
    return "La competencia no tiene resultados importados.";
  }

  // Generic fallback
  if (axiosErr?.message) return axiosErr.message;
  return "Error al lanzar el análisis. Intenta de nuevo.";
}

// ---------------------------------------------------------------------------
// Retryable outcomes
// ---------------------------------------------------------------------------

const RETRYABLE_OUTCOMES = new Set(["backpressure", "error"]);

function getRetryableAthleteIds(runs: TrackedRunEntry[]): number[] {
  return runs
    .filter((r) => RETRYABLE_OUTCOMES.has(r.outcome))
    .map((r) => r.athlete_id);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface GroupAnalysisPanelProps {
  raceEventId: number;
  /** true cuando la competencia tiene resultados importados. */
  hasResults: boolean;
}

export function GroupAnalysisPanel({
  raceEventId,
  hasResults,
}: GroupAnalysisPanelProps) {
  const {
    runs,
    groupState,
    launch,
    retry,
    isLaunching,
    launchError,
    notifyRunTerminated,
  } = useGroupAnalysis(raceEventId);

  // Señal pre-lanzamiento (T052): degrada con gracia si falla el fetch —
  // `aiStatus.data` queda `undefined` y `AIBudgetHint` no renderiza nada.
  const aiStatus = useAIStatus();
  const budgetExhausted = isBudgetExhausted(aiStatus.data);

  const isInProgress = groupState === "in_progress" || isLaunching;
  const launchDisabled = !hasResults || isInProgress || budgetExhausted;

  const errorMessage = mapLaunchError(launchError);

  const retryableIds = getRetryableAthleteIds(runs);
  const showRetry = retryableIds.length > 0;

  const handleTerminated = useCallback(
    (runId: string, state: RunState) => {
      notifyRunTerminated(runId, state);
    },
    [notifyRunTerminated],
  );

  return (
    <section
      className="rounded-xl bg-white p-5 space-y-4 shadow-card"
      aria-label="Análisis grupal con IA"
      data-testid="group-analysis-panel"
    >
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles
            size={16}
            className="text-charcoal"
            aria-hidden="true"
          />
          <h3
            className="font-display text-sm font-semibold text-charcoal"
          >
            Análisis con IA
          </h3>
          {isInProgress && runs.length > 0 && (
            <span className="text-xs text-mid-gray">
              Análisis en curso…
            </span>
          )}
        </div>

        {/* Launch button */}
        <div className="flex flex-wrap items-center gap-2">
          {showRetry && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => retry(retryableIds)}
              disabled={isLaunching}
              data-testid="group-retry-button"
            >
              Reintentar pendientes
            </Button>
          )}

          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                {/* Wrapper span needed for Tooltip to work on disabled button */}
                <span
                  className={launchDisabled ? "cursor-not-allowed" : undefined}
                >
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => launch()}
                    disabled={launchDisabled}
                    aria-label={
                      !hasResults
                        ? "La competencia no tiene resultados importados."
                        : budgetExhausted
                          ? AI_BUDGET_EXHAUSTED_MESSAGE
                          : isInProgress
                            ? "Análisis en curso…"
                            : "Analizar con IA"
                    }
                    data-testid="group-launch-button"
                    className={launchDisabled ? "pointer-events-none" : undefined}
                  >
                    {isLaunching ? (
                      <Loader2
                        size={14}
                        className="animate-spin"
                        aria-hidden="true"
                      />
                    ) : (
                      <Sparkles size={14} aria-hidden="true" />
                    )}
                    Analizar con IA
                  </Button>
                </span>
              </TooltipTrigger>
              {!hasResults && (
                <TooltipContent side="bottom" className="max-w-56">
                  La competencia no tiene resultados importados.
                </TooltipContent>
              )}
              {hasResults && !budgetExhausted && isInProgress && (
                <TooltipContent side="bottom">
                  Análisis en curso…
                </TooltipContent>
              )}
              {hasResults && budgetExhausted && (
                <TooltipContent side="bottom" className="max-w-56">
                  {AI_BUDGET_EXHAUSTED_MESSAGE}
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      {/* Pista pre-lanzamiento de presupuesto/concurrencia (T052) */}
      <AIBudgetHint status={aiStatus.data} />

      {/* Error banner (422/429/503) */}
      {errorMessage && (
        <p
          className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
          data-testid="group-launch-error"
        >
          {errorMessage}
        </p>
      )}

      {/* Run rows */}
      {runs.length > 0 && (
        <ul className="space-y-2" aria-label="Estado por deportista">
          {runs.map((entry) => (
            <GroupRunRow
              key={entry.athlete_id}
              entry={entry}
              onTerminated={handleTerminated}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
