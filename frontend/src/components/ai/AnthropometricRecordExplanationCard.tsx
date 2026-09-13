import { useEffect, useRef, useState } from "react";

import { mapAIError } from "@/api/ai";
import { AIBudgetHint, isBudgetExhausted } from "@/components/ai/AIBudgetHint";
import { AIGeneratedContent } from "@/components/ai/AIGeneratedContent";
import { StructuredInsight } from "@/components/ai/StructuredInsight";
import { useAIStatus } from "@/hooks/ai/useAIStatus";
import {
  useMeasurementExplanation,
  useMeasurementExplanationCached,
} from "@/hooks/ai/useMeasurementExplanation";
import { AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE } from "@/lib/ai/notYetAvailableMessage";
import { pendingMessage } from "@/lib/ai/pendingMessage";
import { cn } from "@/lib/utils";
import type {
  AnthropometricRecordExplanationResponse,
  AnthropometryInsightOut,
} from "@/types/ai.types";

interface AnthropometricRecordExplanationCardProps {
  athleteId: number;
  recordId: number;
  /** Modo solo lectura para padres: solo lee la caché, sin acciones. */
  readOnly?: boolean;
  /**
   * Marca visual "Desactualizado" en modo coach. La fuente de verdad de
   * `is_stale` vive en `GrowthSummaryOut.latest_ai_analysis` (feature 042,
   * Wave 3, FR-027) — este card no la calcula: quien lo monta (el modal de
   * detalle, orquestado por `GrowthTab`/`AnthropometryHistory`) decide si el
   * análisis de este registro puntual quedó desactualizado y pasa el flag.
   * Ausente/`false` no cambia el render de hoy.
   */
  isStale?: boolean;
  className?: string;
}

/**
 * `structured` puede venir corrupto (fila v2 con JSON estructurado inválido
 * guardado en BD, o una respuesta parcial). En vez de reventar el modal
 * llamando `.map()` sobre algo que no es un arreglo, se valida en runtime
 * antes de pasarlo a `StructuredInsight` — si no cumple la forma mínima, la
 * tarjeta se degrada silenciosamente a solo `AIGeneratedContent`, que sigue
 * leyendo `text` (el backend SIEMPRE puebla ese campo, incluso en v2), en
 * vez de mostrar una pantalla rota (FR-026).
 */
function isRenderableInsight(value: unknown): value is AnthropometryInsightOut {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  if (
    typeof v.summary_line !== "string" ||
    !Array.isArray(v.changes) ||
    !Array.isArray(v.meaning) ||
    !Array.isArray(v.next_weeks) ||
    !Array.isArray(v.warning_signs) ||
    !Array.isArray(v.data_gaps)
  ) {
    return false;
  }
  const confidence = v.confidence as Record<string, unknown> | undefined;
  return (
    typeof confidence === "object" &&
    confidence !== null &&
    typeof confidence.level === "string" &&
    typeof confidence.reason === "string"
  );
}

/** `null` para una fila v1 (sin veredicto) o una v2 aprobada/revisada —
 *  en ambos casos no hay nada que marcar para el coach. */
function coachOnlyVerdict(
  data: AnthropometricRecordExplanationResponse,
): "flagged" | "fallback" | "skipped" | null {
  if (data.schema_version !== "v2") return null;
  const verdict = data.critic_verdict;
  if (verdict === "flagged" || verdict === "fallback" || verdict === "skipped") {
    return verdict;
  }
  return null;
}

const VERDICT_MARKER_COPY: Record<"flagged" | "fallback" | "skipped", string> = {
  flagged: "Con observaciones — revisa el contenido antes de compartirlo con la familia.",
  fallback:
    "Análisis de respaldo — el modelo de IA no respondió a tiempo. La familia no lo verá hasta que regeneres uno aprobado.",
  skipped:
    "Sin revisión — el control de calidad no se ejecutó. La familia no lo verá hasta que regeneres uno aprobado.",
};

/** Aviso solo-coach del veredicto de revisión (FR-016). Una familia nunca
 *  llega a este componente: el backend ya filtra estas filas a 204 para un
 *  padre, así que esto solo se monta desde `RecordExplanationCoach`. */
function CoachVerdictMarker({
  data,
}: {
  data: AnthropometricRecordExplanationResponse;
}) {
  const verdict = coachOnlyVerdict(data);
  if (!verdict) return null;
  return (
    <p
      data-testid="record-explanation-verdict-marker"
      className="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-900"
    >
      {VERDICT_MARKER_COPY[verdict]}
    </p>
  );
}

function StaleChip() {
  return (
    <span
      data-testid="record-explanation-stale-chip"
      className="inline-flex items-center rounded-full bg-light-gray px-2 py-0.5 text-[11px] font-medium text-mid-gray"
    >
      Desactualizado
    </span>
  );
}

/** Render del análisis estructurado (v2 válido) colapsado por defecto,
 *  antes del contenido de `AIGeneratedContent` (FR-026). Para una fila v1,
 *  o una v2 con `structured` corrupto, no renderiza nada — el llamador cae
 *  al render de siempre vía `AIGeneratedContent`. */
function StructuredInsightIfRenderable({
  data,
}: {
  data: AnthropometricRecordExplanationResponse;
}) {
  if (data.schema_version !== "v2" || !isRenderableInsight(data.structured)) {
    return null;
  }
  return (
    <StructuredInsight
      insight={data.structured}
      className="rounded-xl bg-white p-5 ring-1 ring-light-gray"
    />
  );
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
      className="mt-3 text-[13px] text-mid-gray"
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

  // Padre sin caché (204, o un análisis bloqueado — flagged/fallback/skipped
  // ya llega como 204 desde el backend, indistinguible de "aún no generado")
  // → mensaje pasivo compartido con la tarjeta PHV (FR-033). Nunca insinúa
  // que existe un análisis bloqueado.
  if (!cachedQuery.data) {
    return (
      <section
        className={cn(
          "space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray",
          className,
        )}
        data-testid="record-explanation-empty"
      >
        <h4 className="text-sm font-semibold text-charcoal">
          Análisis de esta medición
        </h4>
        <p className="text-xs text-mid-gray">
          {AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE}
        </p>
      </section>
    );
  }

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
      <StructuredInsightIfRenderable data={cachedQuery.data} />
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
  isStale,
  className,
}: {
  athleteId: number;
  recordId: number;
  isStale?: boolean;
  className?: string;
}) {
  const cachedQuery = useMeasurementExplanationCached(
    athleteId,
    recordId,
    true,
  );
  const mutation = useMeasurementExplanation(athleteId, recordId);
  const abortRef = useRef<AbortController | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  // Pista pre-lanzamiento de presupuesto/concurrencia (FR-032), igual que en
  // los demás puntos de lanzamiento de IA. Degrada con gracia: si el fetch
  // falla, `data` queda `undefined`, `AIBudgetHint` no renderiza nada y el
  // control sigue habilitado (comportamiento reactivo de hoy).
  const aiStatus = useAIStatus();
  const budgetExhausted = isBudgetExhausted(aiStatus.data);

  const displayed = mutation.data ?? cachedQuery.data ?? null;

  useEffect(() => {
    if (!mutation.isPending) {
      setElapsedMs(0);
      return;
    }
    const id = setInterval(() => setElapsedMs((ms) => ms + 1000), 1000);
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
        <p className="text-xs text-mid-gray">
          {pendingMessage(elapsedMs, "measurement")}
        </p>
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
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold text-charcoal">
            Análisis de esta medición
          </h4>
          {isStale && <StaleChip />}
        </div>
        <DeltaSummary
          numPrevious={displayed.num_previous_measurements}
          deltaHeight={displayed.delta_height_cm}
          deltaWeight={displayed.delta_weight_kg}
        />
        <CoachVerdictMarker data={displayed} />
        <StructuredInsightIfRenderable data={displayed} />
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
        <div className="mt-3 flex flex-col items-end gap-1.5">
          <AIBudgetHint status={aiStatus.data} />
          <button
            type="button"
            onClick={handleGenerate}
            disabled={budgetExhausted}
            className="inline-flex min-h-[48px] items-center justify-center rounded-lg border border-light-gray px-4 text-sm font-medium text-charcoal hover:bg-light-gray/40 disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Regenerar análisis
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
        {info.retryable && <AIBudgetHint status={aiStatus.data} />}
        {info.retryable && (
          <button
            type="button"
            onClick={handleGenerate}
            disabled={budgetExhausted}
            className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
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
      <AIBudgetHint status={aiStatus.data} />
      <button
        type="button"
        onClick={handleGenerate}
        disabled={budgetExhausted}
        className="min-h-[48px] rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
 *    Una fila v2 muestra el análisis estructurado colapsado
 *    (`StructuredInsight`, FR-026) antes del texto plano de siempre, más
 *    el aviso de veredicto ("Con observaciones"/respaldo/sin revisión,
 *    FR-016) cuando aplica, y el chip "Desactualizado" si `isStale`.
 *  - Padre (`readOnly=true`): solo lectura del caché. Si no hay caché (o el
 *    análisis quedó bloqueado por la revisión — indistinguible por diseño)
 *    muestra el mismo mensaje pasivo que la tarjeta PHV (FR-033). Incluye
 *    disclaimer permanente.
 *
 * Una fila v1 (o una v2 con `structured` corrupto) se renderiza exactamente
 * como antes de esta funcionalidad — sin `StructuredInsight`, solo el texto
 * plano vía `AIGeneratedContent` — porque el backend siempre puebla `text`
 * (FR-026: "debe renderizar los análisis guardados antes de esta
 * funcionalidad exactamente como antes").
 */
export function AnthropometricRecordExplanationCard({
  athleteId,
  recordId,
  readOnly = false,
  isStale,
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
      isStale={isStale}
      className={className}
    />
  );
}
