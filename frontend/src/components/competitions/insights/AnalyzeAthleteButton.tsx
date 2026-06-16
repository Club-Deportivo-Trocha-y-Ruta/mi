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
import { BrainCircuit, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";

// ---------------------------------------------------------------------------
// Mapeo de errores del backend (FR-010)
//   503 = presupuesto agotado; 429 = límite de concurrencia.
// ---------------------------------------------------------------------------

const AI_ERROR_MESSAGES: Record<number, string> = {
  503: "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo.",
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
  /** Texto del botón. @default "Analizar". */
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
  label = "Analizar",
  alwaysShowLabel = false,
  showInsightsLink = true,
}: AnalyzeAthleteButtonProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [successRunId, setSuccessRunId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [, setSearchParams] = useSearchParams();

  const launch = useLaunchAthleteAnalysis(athleteId);

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
      <button
        type="button"
        onClick={handleButtonClick}
        disabled={launch.isPending}
        className={cn(
          "flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
          "text-mid-gray hover:bg-charcoal/8 hover:text-charcoal",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        )}
        aria-label={`Analizar con IA a ${displayName}`}
        data-testid={`ai-launch-btn-${athleteId}`}
      >
        {launch.isPending ? (
          <Loader2 size={13} className="animate-spin" aria-hidden="true" />
        ) : (
          <BrainCircuit size={13} aria-hidden="true" />
        )}
        <span className={alwaysShowLabel ? undefined : "hidden sm:inline"}>
          {label}
        </span>
      </button>

      <ConfirmModal
        open={confirmOpen}
        title="Re-ejecutar análisis"
        body="Ya existe un análisis para este deportista. ¿Deseas re-ejecutarlo?"
        confirmLabel="Re-ejecutar"
        isPending={launch.isPending}
        onCancel={() => {
          if (!launch.isPending) setConfirmOpen(false);
        }}
        onConfirm={doLaunch}
      />
    </>
  );
}
