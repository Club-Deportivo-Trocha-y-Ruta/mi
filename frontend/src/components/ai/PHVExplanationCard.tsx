import { useEffect, useRef, useState } from "react";

import { mapAIError } from "@/api/ai";
import { AIGeneratedContent } from "@/components/ai/AIGeneratedContent";
import {
  usePHVExplanation,
  usePHVExplanationCached,
} from "@/hooks/ai/usePHVExplanation";
import { cn } from "@/lib/utils";

interface PHVExplanationCardProps {
  athleteId: number;
  /** Si false, oculta el botón "Generar" (ej: atleta sin mediciones). */
  hasRecords: boolean;
  /** Callback opcional para llevar al usuario al formulario de medición
   *  cuando el backend devuelve 422. */
  onMeasurementCTA?: () => void;
  /** Modo solo lectura para padres: muestra el contenido cacheado pero
   *  no instancia la mutación ni ofrece acciones de generación/regeneración. */
  readOnly?: boolean;
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

// ---------------------------------------------------------------------------
// PHVExplanationReadOnly — Usado cuando readOnly=true (padres).
// Solo instancia la query GET. No instancia la mutation.
// ---------------------------------------------------------------------------

/** Vista solo lectura para padres. Muestra el texto si existe en caché, o
 *  un mensaje pasivo si el entrenador aún no ha generado la explicación. */
function PHVExplanationReadOnly({
  athleteId,
  hasRecords,
  className,
}: {
  athleteId: number;
  hasRecords: boolean;
  className?: string;
}) {
  const cachedQuery = usePHVExplanationCached(athleteId, hasRecords);

  // Loading de caché
  if (cachedQuery.isLoading) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="phv-explanation-loading-cache"
        aria-busy="true"
      >
        <h4
          className="text-sm text-charcoal font-heading tracking-[0.2px]"
        >
          Explicación PHV
        </h4>
        <p className="text-xs text-mid-gray">Cargando…</p>
        <div className="space-y-2" aria-hidden="true">
          <div className="h-3 w-full animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-5/6 animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-light-gray" />
        </div>
      </section>
    );
  }

  // Con texto cacheado: mostrar contenido sin acciones
  if (cachedQuery.data) {
    return (
      <div className={className} data-testid="phv-explanation-readonly">
        <AIGeneratedContent data={cachedQuery.data} />
      </div>
    );
  }

  // Sin caché (204 o sin mediciones): mensaje pasivo para el padre
  return (
    <section
      className={cn(
        "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
        className,
      )}
      data-testid="phv-explanation-idle"
    >
      <h4
        className="text-sm text-charcoal font-heading tracking-[0.2px]"
      >
        Explicación PHV
      </h4>
      <p className="text-xs text-mid-gray">
        Aún no hay explicación disponible. El entrenador la generará pronto.
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// PHVExplanationCard — Componente público.
// Despacha a dos implementaciones según `readOnly`.
// ---------------------------------------------------------------------------

/** Card que orquesta la visualización y (en modo coach) generación de la
 *  explicación PHV con caché backend.
 *
 * Dos modos:
 *  - Coach (`readOnly` omitido o `false`): cinco estados completos (loading-
 *    cache, pending, success, error, idle) con botones Generar / Regenerar /
 *    Cancelar / Reintentar. Idéntico al comportamiento original.
 *  - Padre (`readOnly=true`): solo lectura. Instancia únicamente la query
 *    GET (caché). No instancia la mutation. Muestra el texto si existe, o
 *    un mensaje pasivo invitando a esperar al entrenador.
 *
 * Diseño (modo coach):
 *  - Mismo handler para "Generar" y "Regenerar" — el backend hace upsert.
 *  - El error de regenerar NO borra el contenido cacheado: el coach sigue
 *    viendo el texto previo + alerta inline de error.
 *  - El botón principal está deshabilitado si `hasRecords=false` para que
 *    el coach vea el CTA pero entienda que falta una medición.
 *  - Cancelar usa AbortController; al cancelar `mutation.reset()` limpia
 *    el estado de la mutación pero conserva el `cachedQuery.data` previo.
 */
export function PHVExplanationCard({
  athleteId,
  hasRecords,
  onMeasurementCTA,
  readOnly = false,
  className,
}: PHVExplanationCardProps) {
  // Modo solo lectura: despacha al componente dedicado que no instancia mutation
  if (readOnly) {
    return (
      <PHVExplanationReadOnly
        athleteId={athleteId}
        hasRecords={hasRecords}
        className={className}
      />
    );
  }

  // Modo coach: componente original inalterado
  return (
    <PHVExplanationCoach
      athleteId={athleteId}
      hasRecords={hasRecords}
      onMeasurementCTA={onMeasurementCTA}
      className={className}
    />
  );
}

// ---------------------------------------------------------------------------
// PHVExplanationCoach — Lógica completa del coach (original, sin cambios).
// Extraída a un componente propio para que el conditional dispatch de
// PHVExplanationCard sea válido en React (hooks no condicionales).
// ---------------------------------------------------------------------------

function PHVExplanationCoach({
  athleteId,
  hasRecords,
  onMeasurementCTA,
  className,
}: {
  athleteId: number;
  hasRecords: boolean;
  onMeasurementCTA?: () => void;
  className?: string;
}) {
  const cachedQuery = usePHVExplanationCached(athleteId, hasRecords);
  const mutation = usePHVExplanation(athleteId);
  const abortRef = useRef<AbortController | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Preferir el resultado más reciente de la mutación; si no hay,
  // caer a la caché del backend. Importante: un error en mutation NO
  // borra `cachedQuery.data`, así que tras un Regenerar fallido el
  // usuario sigue viendo el texto previamente cacheado + alerta error.
  const displayed = mutation.data ?? cachedQuery.data ?? null;

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

  // Cache loading: GET es rápido (<500ms), evitamos los hints de cold-start
  // del estado pending de mutation. Solo mostramos este estado si NO hay
  // contenido displayable todavía y no hay una mutación en curso.
  if (cachedQuery.isLoading && !displayed && !mutation.isPending) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="phv-explanation-loading-cache"
        aria-busy="true"
      >
        <h4
          className="text-sm text-charcoal font-heading tracking-[0.2px]"
        >
          Explicación PHV
        </h4>
        <p className="text-xs text-mid-gray">Cargando…</p>
        <div className="space-y-2" aria-hidden="true">
          <div className="h-3 w-full animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-5/6 animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-light-gray" />
        </div>
      </section>
    );
  }

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
            className="text-sm text-charcoal font-heading tracking-[0.2px]"
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

  if (displayed) {
    const mutationErrorInfo = mutation.isError
      ? mapAIError(mutation.error)
      : null;
    return (
      <div className={className}>
        <AIGeneratedContent data={displayed} />
        {mutationErrorInfo && (
          <div
            role="alert"
            data-testid="phv-explanation-regenerate-error"
            className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
          >
            {mutationErrorInfo.message}
            {mutationErrorInfo.retryable && (
              <button
                type="button"
                onClick={handleGenerate}
                className="ml-2 font-medium underline underline-offset-2 hover:text-red-900"
              >
                Reintentar
              </button>
            )}
          </div>
        )}
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
          className="text-sm text-charcoal font-heading tracking-[0.2px]"
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
