/**
 * AnalyzeAthleteButton — botón compartido "Analizar con IA" por atleta.
 *
 * Lanza (o re-lanza) el análisis agéntico de un solo deportista para una
 * válida concreta. Auto-contenido: gestiona su propio estado de confirmación,
 * la mutación de launch, el feedback inline de éxito/error y el chequeo de
 * frescura del insight existente.
 *
 * Usado por:
 *   - ResultsTable (acción por fila, US4 feature 010) → variante compacta.
 *   - InsightsTab / InsightCard (acción por tarjeta) → label completo.
 *
 * Semántica de `insightFreshness`:
 *   - undefined → no hay insight previo → launch directo.
 *   - null      → insight fresco (stale_run_id == null) → confirmar antes de re-correr.
 *   - string    → stale run_id → launch directo (análisis desactualizado).
 *
 * Privacidad: el body del run solo viaja con athlete_id/season/valida; el run_id
 * de respuesta es el external UUID, nunca la PK interna.
 */
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sparkles, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  AIBudgetHint,
  AI_BUDGET_EXHAUSTED_MESSAGE,
  isBudgetExhausted,
} from "@/components/ai/AIBudgetHint";
import { useAIStatus } from "@/hooks/ai/useAIStatus";
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";

// ---------------------------------------------------------------------------
// Mapeo de errores del backend (FR-010)
//   503 = presupuesto agotado; 429 = límite de concurrencia.
// ---------------------------------------------------------------------------

const AI_ERROR_MESSAGES: Record<number, string> = {
  503: AI_BUDGET_EXHAUSTED_MESSAGE,
  429: "Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos.",
};

export function getAiErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const e = err as { response?: { status?: number } };
    const status = e.response?.status;
    if (status != null && status in AI_ERROR_MESSAGES) {
      return AI_ERROR_MESSAGES[status];
    }
  }
  return "No se pudo iniciar el análisis. Intenta de nuevo.";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface AnalyzeAthleteButtonProps {
  athleteId: number;
  season: number;
  validaNum: number;
  /**
   * Ancla explícita por evento. Cuando el botón vive en una competición concreta
   * se pasa para desambiguar copa vs campeonato (mismo sequence_number en la
   * temporada). Si se omite, el backend resuelve por validaNum (puede dar 409 si
   * la válida es ambigua).
   */
  eventId?: number;
  /**
   * undefined = no insight yet → launch directly.
   * null     = fresh insight (stale_run_id == null) → confirm before re-run.
   * string   = stale run_id → treat as "needs rerun", launch directly (stale).
   */
  insightFreshness: string | null | undefined;
  displayName: string;
  /** Texto del botón. @default "Analizar con IA". */
  label?: string;
  /** Muestra el label en todos los breakpoints (no oculto en mobile). @default false. */
  alwaysShowLabel?: boolean;
  /**
   * Tras éxito muestra el link "Ver progreso en Insights" (navega a ?tab=insights).
   * Desactivar cuando el botón ya vive en el tab Insights. @default true.
   */
  showInsightsLink?: boolean;
}

export function AnalyzeAthleteButton({
  athleteId,
  season,
  validaNum,
  eventId,
  insightFreshness,
  displayName,
  label = "Analizar con IA",
  alwaysShowLabel = false,
  showInsightsLink = true,
}: AnalyzeAthleteButtonProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [successRunId, setSuccessRunId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [, setSearchParams] = useSearchParams();

  const launch = useLaunchAthleteAnalysis(athleteId);

  // Señal pre-lanzamiento (T051): degrada con gracia si falla el fetch —
  // `aiStatus.data` queda `undefined` y `AIBudgetHint` no renderiza nada,
  // nunca bloqueando este botón por un error de useAIStatus().
  const aiStatus = useAIStatus();
  const budgetExhausted = isBudgetExhausted(aiStatus.data);

  // Un insight fresco existe cuando el map tiene una entrada con stale_run_id null.
  const hasFreshInsight = insightFreshness === null;

  function doLaunch() {
    setErrorMsg(null);
    launch.mutate(
      { season, valida_nums: [validaNum], event_id: eventId },
      {
        onSuccess: (res) => {
          setSuccessRunId(res.run_id);
          setConfirmOpen(false);
        },
        onError: (err) => {
          setErrorMsg(getAiErrorMessage(err));
          setConfirmOpen(false);
        },
      },
    );
  }

  function handleButtonClick() {
    if (budgetExhausted) return;
    setErrorMsg(null);
    setSuccessRunId(null);
    if (hasFreshInsight) {
      setConfirmOpen(true);
    } else {
      doLaunch();
    }
  }

  function navigateToInsights() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", "insights");
      return next;
    });
  }

  if (successRunId) {
    return (
      <div
        className="flex items-center gap-1.5 text-xs text-emerald-700"
        data-testid={`ai-launch-success-${athleteId}`}
      >
        <CheckCircle2 size={13} aria-hidden="true" />
        {showInsightsLink ? (
          <button
            type="button"
            onClick={navigateToInsights}
            className="underline underline-offset-2 hover:opacity-80"
            data-testid={`ai-launch-insights-link-${athleteId}`}
          >
            Ver progreso en Insights
          </button>
        ) : (
          <span>Análisis iniciado</span>
        )}
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div
        className="flex max-w-[200px] items-start gap-1.5 text-xs text-red-600"
        data-testid={`ai-launch-error-${athleteId}`}
        role="alert"
      >
        <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>{errorMsg}</span>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col items-start gap-1">
        <button
          type="button"
          onClick={handleButtonClick}
          disabled={launch.isPending || budgetExhausted}
          className={cn(
            "flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
            "text-mid-gray hover:bg-charcoal/8 hover:text-charcoal",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
            "min-h-[48px] min-w-[48px]",
          )}
          aria-label={
            budgetExhausted
              ? `Presupuesto de IA agotado — no se puede analizar a ${displayName}`
              : `Analizar con IA a ${displayName}`
          }
          data-testid={`ai-launch-btn-${athleteId}`}
        >
          {launch.isPending ? (
            <Loader2 size={13} className="animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles size={13} aria-hidden="true" />
          )}
          <span className={alwaysShowLabel ? undefined : "hidden sm:inline"}>
            {label}
          </span>
        </button>

        {/* Pista pre-lanzamiento de presupuesto/concurrencia (T051) */}
        <AIBudgetHint status={aiStatus.data} className="max-w-[200px]" />
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="Re-ejecutar análisis con IA"
        description="Ya existe un análisis para este deportista. ¿Deseas re-ejecutarlo?"
        confirmLabel="Re-ejecutar"
        tone="default"
        isPending={launch.isPending}
        onCancel={() => {
          if (!launch.isPending) setConfirmOpen(false);
        }}
        onConfirm={doLaunch}
      />
    </>
  );
}
