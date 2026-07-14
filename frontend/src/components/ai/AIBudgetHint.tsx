/**
 * AIBudgetHint — pista pre-lanzamiento de presupuesto/concurrencia de IA.
 *
 * Consume el payload de `useAIStatus()` (`GET /api/ai/status`) y presenta
 * una sola variante, en orden de prioridad, per contracts/ai-identity.md §4:
 *
 *   1. `budget_status="exhausted"` → explicación en texto plano ANTES de
 *      cualquier click. El control que la usa es responsable de
 *      deshabilitar su propio botón (ver `isBudgetExhausted`).
 *   2. `budget_status="warning"` → hint ámbar "Presupuesto de IA: N% restante".
 *   3. `concurrency_available=false` → "Alta demanda — espera ≈Ns".
 *   4. de lo contrario (presupuesto ok + concurrencia disponible) → hint
 *      neutro "≈Ns" (misma convención de copy que el ETA de
 *      `AnalysisRunTimeline`).
 *
 * Sin datos (fetch en curso, deshabilitado, o error de red) no renderiza
 * nada — degradación al comportamiento reactivo de hoy, nunca bloquea el
 * botón que la consume por un fallo de `useAIStatus()`.
 *
 * Un solo componente para los tres puntos de lanzamiento
 * (`AnalyzeAthleteButton`, `GroupAnalysisPanel`, `SessionAssistantPage`) —
 * un patrón, no tres implementaciones (T051-T053).
 */
import { AlertCircle, AlertTriangle, Clock } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AIStatusResponse } from "@/types/ai.types";

/** Copy reutilizado de `AnalyzeAthleteButton`'s mapeo de error 503
 * existente — el mismo texto, ahora también mostrado antes del clic. */
export const AI_BUDGET_EXHAUSTED_MESSAGE =
  "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo.";

/** True cuando el presupuesto está agotado — el control que consume este
 * hint debe deshabilitar su botón de lanzamiento con este valor (FR-006). */
export function isBudgetExhausted(status: AIStatusResponse | undefined): boolean {
  return status?.budget_status === "exhausted";
}

export interface AIBudgetHintProps {
  /** `undefined` cuando `useAIStatus()` aún no resolvió o falló — no renderiza nada. */
  status: AIStatusResponse | undefined;
  className?: string;
}

export function AIBudgetHint({ status, className }: AIBudgetHintProps) {
  if (!status) return null;

  if (status.budget_status === "exhausted") {
    return (
      <p
        role="alert"
        data-testid="ai-budget-hint-exhausted"
        className={cn("flex items-start gap-1.5 text-xs text-danger", className)}
      >
        <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>{AI_BUDGET_EXHAUSTED_MESSAGE}</span>
      </p>
    );
  }

  if (status.budget_status === "warning") {
    return (
      <p
        data-testid="ai-budget-hint-warning"
        className={cn("flex items-center gap-1.5 text-xs text-warning", className)}
      >
        <AlertTriangle size={13} className="shrink-0" aria-hidden="true" />
        <span>Presupuesto de IA: {status.budget_remaining_pct}% restante</span>
      </p>
    );
  }

  if (!status.concurrency_available) {
    return (
      <p
        data-testid="ai-budget-hint-concurrency"
        className={cn("flex items-center gap-1.5 text-xs text-mid-gray", className)}
      >
        <Clock size={13} className="shrink-0" aria-hidden="true" />
        <span>Alta demanda — espera ≈{status.est_wait_seconds}s</span>
      </p>
    );
  }

  if (status.est_wait_seconds > 0) {
    return (
      <p
        data-testid="ai-budget-hint-duration"
        className={cn("flex items-center gap-1.5 text-xs text-mid-gray", className)}
      >
        <Clock size={13} className="shrink-0" aria-hidden="true" />
        <span>≈{status.est_wait_seconds}s</span>
      </p>
    );
  }

  return null;
}
