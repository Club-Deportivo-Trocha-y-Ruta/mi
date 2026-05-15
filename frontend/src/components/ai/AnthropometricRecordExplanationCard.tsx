import { useEffect, useRef, useState } from "react";

import { mapAIError } from "@/api/ai";
import { AIGeneratedContent } from "@/components/ai/AIGeneratedContent";
import {
  useMeasurementExplanation,
  useMeasurementExplanationCached,
} from "@/hooks/ai/useMeasurementExplanation";
import { cn } from "@/lib/utils";

interface AnthropometricRecordExplanationCardProps {
  athleteId: number;
  recordId: number;
  /** Modo solo lectura para padres: solo lee la caché, sin acciones. */
  readOnly?: boolean;
  className?: string;
}

const COLD_START_THRESHOLD_S = 55;
const SLOW_THRESHOLD_S = 20;

function pendingMessage(elapsed: number): string {
  if (elapsed >= COLD_START_THRESHOLD_S) {
    return "El servidor está despertando, esto puede tardar un minuto…";
  }
  if (elapsed >= SLOW_THRESHOLD_S) {
    return "Consultando modelo de IA (puede tardar hasta 30 s)…";
  }
  return "Analizando esta medición…";
}

function formatDeltaSign(value: number): string {
  if (value > 0) return `+${value.toFixed(1)}`;
  return value.toFixed(1);
}

interface DeltaSummaryProps {
  numPrevious: number;
  deltaHeight: number | null;
  deltaWeight: number | null;
}

/** Encabezado con resumen visual del delta, antes del texto IA. */
function DeltaSummary({
  numPrevious,
  deltaHeight,
  deltaWeight,
}: DeltaSummaryProps) {
  if (numPrevious === 0) {
    return (
      <p
        className="text-xs text-mid-gray"
        data-testid="record-explanation-no-history"
      >
        Primera medición registrada — no hay comparativa disponible.
      </p>
    );
  }
  return (
    <div
      className="flex flex-wrap items-center gap-3 text-xs"
      data-testid="record-explanation-deltas"
    >
      {deltaHeight !== null && (
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full bg-light-gray px-2.5 py-1",
            deltaHeight > 0 && "bg-emerald-50 text-emerald-800",
          )}
          data-testid="delta-height"
        >
          <span aria-hidden="true">{deltaHeight >= 0 ? "↑" : "↓"}</span>
          <span className="font-medium">Δ talla {formatDeltaSign(deltaHeight)} cm</span>
        </span>
      )}
      {deltaWeight !== null && (
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full bg-light-gray px-2.5 py-1",
            deltaWeight > 0 && "bg-emerald-50 text-emerald-800",
          )}
          data-testid="delta-weight"
        >
          <span aria-hidden="true">{deltaWeight >= 0 ? "↑" : "↓"}</span>
          <span className="font-medium">Δ peso {formatDeltaSign(deltaWeight)} kg</span>
        </span>
      )}
      <span className="text-mid-gray">
        Basado en {numPrevious}{" "}
        {numPrevious === 1 ? "medición previa" : "mediciones previas"}
      </span>
    </div>
  );
}

/** Footer obligatorio para modo padre con disclaimer permanente. */
function ParentDisclaimer() {
  return (
    <p
      className="mt-3 text-[13px] text-muted-foreground text-mid-gray"
      data-testid="record-explanation-disclaimer"
    >
      Generado automáticamente por IA. Ante cualquier duda, consulta con el
      entrenador o el médico del club.
    </p>
  );
}

// ---------------------------------------------------------------------------
// Modo padre — solo lectura.
// ---------------------------------------------------------------------------

function RecordExplanationReadOnly({
  athleteId,
  recordId,
  className,
}: {
  athleteId: number;
  recordId: number;
  className?: string;
}) {
  const cachedQuery = useMeasurementExplanationCached(
    athleteId,
    recordId,
    true,
  );

  if (cachedQuery.isLoading) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="record-explanation-loading-cache"
        aria-busy="true"
      >
        <h4 className="text-sm font-semibold text-charcoal">
          Análisis de esta medición
        </h4>
        <p className="text-xs text-mid-gray">Cargando…</p>
      </section>
    );
  }

  // Padre sin caché → la sección no se renderiza (sin UI degradada)
  if (!cachedQuery.data) return null;

  return (
    <section
      className={cn("space-y-3", className)}
      data-testid="record-explanation-readonly"
    >
      <h4 className="text-sm font-semibold text-charcoal">
        Análisis de esta medición
      </h4>
      <DeltaSummary
        numPrevious={cachedQuery.data.num_previous_measurements}
        deltaHeight={cachedQuery.data.delta_height_cm}
        deltaWeight={cachedQuery.data.delta_weight_kg}
      />
      <AIGeneratedContent data={cachedQuery.data} />
      <ParentDisclaimer />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Modo coach — genera/regenera + estados completos.
// ---------------------------------------------------------------------------

function RecordExplanationCoach({
  athleteId,
  recordId,
  className,
}: {
  athleteId: number;
  recordId: number;
  className?: string;
}) {
  const cachedQuery = useMeasurementExplanationCached(
    athleteId,
    recordId,
    true,
  );
  const mutation = useMeasurementExplanation(athleteId, recordId);
  const abortRef = useRef<AbortController | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const displayed = mutation.data ?? cachedQuery.data ?? null;

  useEffect(() => {
    if (!mutation.isPending) {
      setElapsed(0);
      return;
    }
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
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

  // Loading caché
  if (cachedQuery.isLoading && !displayed && !mutation.isPending) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="record-explanation-loading-cache"
        aria-busy="true"
      >
        <h4 className="text-sm font-semibold text-charcoal">
          Análisis de esta medición
        </h4>
        <p className="text-xs text-mid-gray">Cargando…</p>
      </section>
    );
  }

  // Generación en curso
  if (mutation.isPending) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="record-explanation-pending"
        aria-busy="true"
      >
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-charcoal">
            Análisis de esta medición
          </h4>
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-lg border border-light-gray px-3 py-1.5 text-xs font-medium text-charcoal hover:bg-light-gray/40"
          >
            Cancelar
          </button>
        </div>
        <p className="text-xs text-mid-gray">{pendingMessage(elapsed)}</p>
        <div className="space-y-2" aria-hidden="true">
          <div className="h-3 w-full animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-5/6 animate-pulse rounded bg-light-gray" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-light-gray" />
        </div>
      </section>
    );
  }

  // Hay contenido displayable (caché previa o resultado nuevo)
  if (displayed) {
    const mutationErrorInfo = mutation.isError ? mapAIError(mutation.error) : null;
    return (
      <section className={cn("space-y-3", className)} data-testid="record-explanation-success">
        <h4 className="text-sm font-semibold text-charcoal">
          Análisis de esta medición
        </h4>
        <DeltaSummary
          numPrevious={displayed.num_previous_measurements}
          deltaHeight={displayed.delta_height_cm}
          deltaWeight={displayed.delta_weight_kg}
        />
        <AIGeneratedContent data={displayed} />
        {mutationErrorInfo && (
          <div
            role="alert"
            data-testid="record-explanation-regenerate-error"
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
      </section>
    );
  }

  // Error fresco (sin contenido previo)
  if (mutation.isError) {
    const info = mapAIError(mutation.error);
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl border border-red-200 bg-red-50 p-5",
          className,
        )}
        role="alert"
        data-testid="record-explanation-error"
      >
        <h4 className="text-sm font-semibold text-red-800">
          Análisis de esta medición
        </h4>
        <p className="text-sm text-red-700">{info.message}</p>
        {info.retryable && (
          <button
            type="button"
            onClick={handleGenerate}
            className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100"
          >
            Reintentar
          </button>
        )}
      </section>
    );
  }

  // Idle: sin caché, sin error, sin pending
  return (
    <section
      className={cn(
        "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
        className,
      )}
      data-testid="record-explanation-idle"
    >
      <div>
        <h4 className="text-sm font-semibold text-charcoal">
          Análisis de esta medición
        </h4>
        <p className="mt-1 text-xs text-mid-gray">
          Genera con IA un análisis particular de esta medición comparada con
          el historial del atleta. El texto se compartirá con la familia.
        </p>
      </div>
      <button
        type="button"
        onClick={handleGenerate}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        Analizar esta medición
      </button>
    </section>
  );
}

/** Card que orquesta la explicación IA particular de UNA medición concreta.
 *
 * A diferencia del PHV global, esta vive dentro del modal de detalle del
 * histórico antropométrico y se enfoca en deltas vs la medición anterior.
 *
 * Modos:
 *  - Coach (`readOnly` omitido o `false`): genera/regenera con todos los
 *    estados (idle, loading-cache, pending, success, error). Distingue
 *    422 (sin historial), 451 (sin consentimiento), 503 (LLM caído) y
 *    502 (guardrail). El error de regenerar NO borra el contenido previo.
 *  - Padre (`readOnly=true`): solo lectura del caché. Si no hay caché la
 *    sección no se renderiza para evitar UI degradada con botones
 *    deshabilitados. Incluye disclaimer permanente.
 */
export function AnthropometricRecordExplanationCard({
  athleteId,
  recordId,
  readOnly = false,
  className,
}: AnthropometricRecordExplanationCardProps) {
  if (readOnly) {
    return (
      <RecordExplanationReadOnly
        athleteId={athleteId}
        recordId={recordId}
        className={className}
      />
    );
  }
  return (
    <RecordExplanationCoach
      athleteId={athleteId}
      recordId={recordId}
      className={className}
    />
  );
}
