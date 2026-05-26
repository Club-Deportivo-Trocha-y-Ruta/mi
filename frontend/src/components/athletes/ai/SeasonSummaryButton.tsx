/**
 * SeasonSummaryButton — botón on-demand para generar el resumen de
 * temporada del atleta (Task #8).
 *
 * - Disabled (con tooltip) si analyzedValidasCount < 3.
 * - Muestra spinner durante el pending de la mutation.
 * - Feedback de éxito/error inline (no depende de librería toast externa).
 * - Solo se usa en vista coach (AthleteAIAnalysisTab lo monta condicionalmente).
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

const MIN_VALIDAS_REQUIRED = 3;

interface SeasonSummaryButtonProps {
  athleteId: number;
  /** Número de válidas ya analizadas (con análisis aprobado) para este atleta. */
  analyzedValidasCount: number;
}

function extractErrorDetail(err: unknown): string {
  const fallback = "Error al generar el resumen. Intenta de nuevo.";
  if (!err || typeof err !== "object") return fallback;
  const anyErr = err as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = anyErr.response?.data?.detail;
  if (typeof detail === "string" && detail.trim().length > 0) return detail;
  // FastAPI/Pydantic validation: detail es array de {msg, loc, type}.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === "string" && first.msg.trim().length > 0) {
      return `Datos inválidos: ${first.msg}`;
    }
  }
  if (typeof anyErr.message === "string" && anyErr.message.trim().length > 0) {
    return anyErr.message;
  }
  return fallback;
}

export function SeasonSummaryButton({
  athleteId,
  analyzedValidasCount,
}: SeasonSummaryButtonProps) {
  const mutation = useGenerateSeasonSummary(athleteId);
  const [feedback, setFeedback] = useState<
    { kind: "success" } | { kind: "error"; message: string } | null
  >(null);

  const isInsufficient = analyzedValidasCount < MIN_VALIDAS_REQUIRED;
  const isDisabled = isInsufficient || mutation.isPending;

  const handleClick = async () => {
    setFeedback(null);
    try {
      await mutation.mutateAsync();
      setFeedback({ kind: "success" });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({ kind: "error", message: extractErrorDetail(err) });
      setTimeout(() => setFeedback(null), 8000);
    }
  };

  const button = (
    <Button
      variant="outline"
      size="sm"
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
        <p
          role="status"
          className="text-[11px] text-green-700"
          data-testid="season-summary-success"
        >
          Resumen en proceso — aparecerá en el histórico al completarse.
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
