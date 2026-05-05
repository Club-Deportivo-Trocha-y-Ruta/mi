import { useEffect, useRef, useState } from "react";

import { mapAIError } from "@/api/ai";
import { AIGeneratedContent } from "@/components/ai/AIGeneratedContent";
import { usePHVExplanation } from "@/hooks/ai/usePHVExplanation";
import { cn } from "@/lib/utils";

interface PHVExplanationCardProps {
  athleteId: number;
  /** Si false, oculta el botón "Generar" (ej: atleta sin mediciones). */
  hasRecords: boolean;
  /** Callback opcional para llevar al usuario al formulario de medición
   *  cuando el backend devuelve 422. */
  onMeasurementCTA?: () => void;
  className?: string;
}

const COLD_START_THRESHOLD_S = 55;
const SLOW_THRESHOLD_S = 20;

function pendingMessage(elapsedSeconds: number): string {
  if (elapsedSeconds >= COLD_START_THRESHOLD_S) {
    return "El servidor está despertando, esto puede tardar un minuto…";
  }
  if (elapsedSeconds >= SLOW_THRESHOLD_S) {
    return "Consultando modelo de IA (puede tardar hasta 30 s)…";
  }
  return "Generando explicación…";
}

/** Card que orquesta la generación de explicación PHV.
 *
 * Tres fases: idle (botón), pending (skeleton + mensaje + cancelar),
 * success (AIGeneratedContent) o error (alert con copy en español).
 *
 * Diseño:
 *  - El botón principal está deshabilitado si `hasRecords=false` para que
 *    el coach vea el CTA pero entienda que falta una medición.
 *  - Cancelar usa AbortController; al cancelar `mutation.reset()` limpia
 *    el estado.
 *  - El `text` nunca se persiste fuera del estado de la mutación (vida
 *    del componente). Al desmontar se descarta.
 */
export function PHVExplanationCard({
  athleteId,
  hasRecords,
  onMeasurementCTA,
  className,
}: PHVExplanationCardProps) {
  const mutation = usePHVExplanation(athleteId);
  const abortRef = useRef<AbortController | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!mutation.isPending) {
      setElapsedSeconds(0);
      return;
    }
    const interval = setInterval(() => {
      setElapsedSeconds((s) => s + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [mutation.isPending]);

  function handleGenerate() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    mutation.mutate({ signal: controller.signal });
  }

  function handleCancel() {
    abortRef.current?.abort();
    mutation.reset();
  }

  // -------------------------------------------------------------------------
  // States
  // -------------------------------------------------------------------------

  if (mutation.isPending) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="phv-explanation-pending"
        aria-busy="true"
      >
        <div className="flex items-center justify-between">
          <h4
            className="text-sm text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
              letterSpacing: "0.2px",
            }}
          >
            Explicación PHV
          </h4>
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg border border-light-gray px-3 py-1.5 text-xs font-medium text-charcoal hover:bg-light-gray/40"
          >
            Cancelar
          </button>
        </div>
        <p className="text-xs text-mid-gray">
          {pendingMessage(elapsedSeconds)}
        </p>
        <div className="space-y-2" aria-hidden="true">
          <div className="h-3 w-full animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-5/6 animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-light-gray" />
        </div>
      </section>
    );
  }

  if (mutation.isSuccess && mutation.data) {
    return (
      <div className={className}>
        <AIGeneratedContent data={mutation.data} />
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            onClick={handleGenerate}
            className="text-xs font-medium text-blue-600 underline-offset-2 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Regenerar
          </button>
        </div>
      </div>
    );
  }

  if (mutation.isError) {
    const info = mapAIError(mutation.error);
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl border border-red-200 bg-red-50 p-5",
          className,
        )}
        role="alert"
        data-testid="phv-explanation-error"
      >
        <h4 className="text-sm font-semibold text-red-800">
          Explicación PHV
        </h4>
        <p className="text-sm text-red-700">{info.message}</p>
        <div className="flex flex-wrap gap-2">
          {info.kind === "no_records" && onMeasurementCTA && (
            <button
              type="button"
              onClick={onMeasurementCTA}
              className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
            >
              Registrar medición
            </button>
          )}
          {info.retryable && (
            <button
              type="button"
              onClick={handleGenerate}
              className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100"
            >
              Reintentar
            </button>
          )}
        </div>
      </section>
    );
  }

  // Idle
  return (
    <section
      className={cn(
        "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
        className,
      )}
      data-testid="phv-explanation-idle"
    >
      <div>
        <h4
          className="text-sm text-charcoal"
          style={{
            fontFamily: "'Cal Sans', system-ui, sans-serif",
            fontWeight: 600,
            letterSpacing: "0.2px",
          }}
        >
          Explicación PHV para padres
        </h4>
        <p className="mt-1 text-xs text-mid-gray">
          Genera con IA una explicación clara del estado PHV del atleta.
          Revísala antes de compartirla con la familia.
        </p>
      </div>
      <button
        type="button"
        onClick={handleGenerate}
        disabled={!hasRecords}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        Generar explicación
      </button>
      {!hasRecords && (
        <p className="text-xs text-mid-gray">
          Registra una medición antropométrica para habilitar la generación.
        </p>
      )}
    </section>
  );
}
