/**
 * SeasonSummaryButton — botón on-demand para generar el resumen de
 * temporada del atleta (Task #8).
 *
 * - Disabled (con tooltip) si analyzedValidasCount < 3.
 * - Muestra spinner durante el pending de la mutation.
 * - Feedback de éxito/error inline (no depende de librería toast externa).
 * - Solo se usa en vista coach (AthleteAIAnalysisTab lo monta condicionalmente).
 *
 * Feature 037 (v3): la llamada es ASÍNCRONA — el backend lanza un run
 * agéntico (`analysis_kind="season"`) y responde 202 con `run_id`. El
 * resumen pasa por crítico y aprobación del coach como cualquier válida;
 * `onRunStarted` expone el `run_id` para que quien monte este botón muestre
 * la línea de tiempo del run (cableado completo en la Wave 3, T302).
 */
import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useGenerateSeasonSummary } from "@/hooks/athletes/useGenerateSeasonSummary";
import { extractErrorDetail } from "@/lib/apiError";

const MIN_VALIDAS_REQUIRED = 3;
const ERROR_FALLBACK = "Error al generar el resumen. Intenta de nuevo.";

interface SeasonSummaryButtonProps {
  athleteId: number;
  /** Número de válidas ya analizadas (con análisis aprobado) para este atleta. */
  analyzedValidasCount: number;
  /**
   * Se invoca con el `run_id` del run recién lanzado para que el padre pueda
   * mostrar su progreso (AnalysisRunTimeline + HITL). Opcional.
   */
  onRunStarted?: (runId: string) => void;
}

export function SeasonSummaryButton({
  athleteId,
  analyzedValidasCount,
  onRunStarted,
}: SeasonSummaryButtonProps) {
  const mutation = useGenerateSeasonSummary(athleteId);
  const [feedback, setFeedback] = useState<
    | { kind: "success"; runId: string }
    | { kind: "error"; message: string }
    | null
  >(null);

  const isInsufficient = analyzedValidasCount < MIN_VALIDAS_REQUIRED;
  const isDisabled = isInsufficient || mutation.isPending;

  const handleClick = async () => {
    setFeedback(null);
    try {
      const result = await mutation.mutateAsync();
      setFeedback({ kind: "success", runId: result.run_id });
      onRunStarted?.(result.run_id);
      setTimeout(() => setFeedback(null), 6000);
    } catch (err) {
      setFeedback({ kind: "error", message: extractErrorDetail(err, ERROR_FALLBACK) });
      setTimeout(() => setFeedback(null), 8000);
    }
  };

  const button = (
    <Button
      variant="outline"
      size="sm"
      className="min-h-12"
      onClick={() => void handleClick()}
      disabled={isDisabled}
      data-testid="season-summary-btn"
      aria-label="Generar resumen de temporada"
    >
      {mutation.isPending ? (
        <Loader2 size={14} className="animate-spin" aria-hidden="true" />
      ) : (
        <Sparkles size={14} aria-hidden="true" />
      )}
      {mutation.isPending ? "Lanzando…" : "Resumen temporada"}
    </Button>
  );

  return (
    <div className="flex flex-col items-end gap-1">
      <TooltipProvider delayDuration={200}>
        {isInsufficient ? (
          <Tooltip>
            <TooltipTrigger asChild>
              {/* Wrapping en span para que el tooltip funcione sobre
                  elementos disabled — Radix necesita un nodo focusable */}
              <span className="inline-flex" tabIndex={0}>
                {button}
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              Mínimo {MIN_VALIDAS_REQUIRED} válidas analizadas (tienes{" "}
              {analyzedValidasCount})
            </TooltipContent>
          </Tooltip>
        ) : (
          button
        )}
      </TooltipProvider>

      {feedback?.kind === "success" && (
        <p
          role="status"
          className="text-[11px] text-green-700"
          data-testid="season-summary-success"
        >
          Resumen de temporada en proceso. Aparecerá en el histórico cuando lo
          apruebes.
        </p>
      )}
      {feedback?.kind === "error" && (
        <p
          role="alert"
          className="max-w-xs text-right text-[11px] text-red-600"
          data-testid="season-summary-error"
        >
          {feedback.message}
        </p>
      )}
    </div>
  );
}
