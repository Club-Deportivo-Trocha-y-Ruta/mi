/**
 * SeasonSummaryButton — botón on-demand para generar el resumen de
 * temporada del atleta (Task #8).
 *
 * - Disabled (con tooltip) si analyzedValidasCount < 3.
 * - Muestra spinner durante el pending de la mutation.
 * - Feedback de éxito/error inline (no depende de librería toast externa).
 * - Solo se usa en vista coach (AthleteAIAnalysisTab lo monta condicionalmente).
 *
 * La llamada es SÍNCRONA (feature 036, T040): a diferencia de
 * `useLaunchAthleteAnalysis` (que arranca un run agéntico polleable), el
 * backend ya generó y persistió el resumen para cuando la promesa resuelve
 * — nunca hay un "en proceso" que esperar. El feedback de éxito refleja
 * eso, y `onGenerated` expone el `insight_id` recién creado para que quien
 * monte este botón pueda deep-linkear al insight en el histórico (ej.
 * `InsightsTimeline`'s `selectedInsightId`).
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
   * Se invoca con el `insight_id` recién creado al terminar con éxito, para
   * que el padre pueda deep-linkear al insight (ej. controlar
   * `selectedInsightId` de `InsightsTimeline`). Opcional: si no se provee,
   * el botón sigue funcionando, solo sin affordance de "Ver resumen".
   */
  onGenerated?: (insightId: number) => void;
}

export function SeasonSummaryButton({
  athleteId,
  analyzedValidasCount,
  onGenerated,
}: SeasonSummaryButtonProps) {
  const mutation = useGenerateSeasonSummary(athleteId);
  const [feedback, setFeedback] = useState<
    | { kind: "success"; insightId: number }
    | { kind: "error"; message: string }
    | null
  >(null);

  const isInsufficient = analyzedValidasCount < MIN_VALIDAS_REQUIRED;
  const isDisabled = isInsufficient || mutation.isPending;

  const handleClick = async () => {
    setFeedback(null);
    try {
      const result = await mutation.mutateAsync();
      setFeedback({ kind: "success", insightId: result.insight_id });
      onGenerated?.(result.insight_id);
      setTimeout(() => setFeedback(null), 4000);
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
      {mutation.isPending ? "Generando…" : "Resumen temporada"}
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
        <div className="flex flex-col items-end gap-0.5">
          <p
            role="status"
            className="text-[11px] text-green-700"
            data-testid="season-summary-success"
          >
            Resumen de temporada generado — ya está en el histórico.
          </p>
          {onGenerated && (
            <button
              type="button"
              onClick={() => onGenerated(feedback.insightId)}
              className="text-[11px] font-medium text-primary hover:underline"
              data-testid="season-summary-view-link"
            >
              Ver resumen →
            </button>
          )}
        </div>
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
