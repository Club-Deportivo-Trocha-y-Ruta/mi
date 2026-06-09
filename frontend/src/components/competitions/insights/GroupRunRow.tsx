/**
 * GroupRunRow — fila de estado por deportista en el panel de análisis grupal.
 *
 * Cada fila:
 *  - Muestra nombre del atleta + chip de estado (es-CO).
 *  - Si hay un run_id activo, pollea su estado vía useRunStatus.
 *  - Cuando el run llega a hitl_waiting, muestra HITLApprovalCard.
 *  - Notifica al padre cuando el run alcanza estado terminal (done/failed).
 *
 * Privacidad: sólo muestra athlete_display_name (pseudónimo del backend),
 * nunca el athlete_id real ni datos identificadores adicionales.
 */
import { useEffect } from "react";
import { CheckCircle2, AlertCircle, Clock, Loader2, XCircle } from "lucide-react";

import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { Badge } from "@/components/ui/badge";
import { useRunStatus, isTerminalState } from "@/hooks/ai/useRaceRun";
import { cn } from "@/lib/utils";
import type { GroupRunOutcome, RunState } from "@/types/raceAnalysis.types";
import type { TrackedRunEntry } from "@/hooks/ai/useGroupAnalysis";

// ---------------------------------------------------------------------------
// State chip
// ---------------------------------------------------------------------------

interface StateChipProps {
  /** Run state from polling (only available when run_id is set). */
  runState: RunState | undefined;
  /** Outcome from the launch response (for runs with no run_id). */
  outcome: GroupRunOutcome | "recovered";
}

function StateChip({ runState, outcome }: StateChipProps) {
  // Priority: live run state > launch outcome
  if (runState) {
    switch (runState) {
      case "running":
        return (
          <Badge
            variant="secondary"
            className="gap-1 bg-blue-50 text-blue-700"
            aria-label="Análisis en curso"
          >
            <Loader2 size={10} className="animate-spin" aria-hidden="true" />
            En curso
          </Badge>
        );
      case "hitl_waiting":
        return (
          <Badge
            variant="secondary"
            className="gap-1 bg-amber-50 text-amber-700"
            aria-label="Esperando aprobación del coach"
          >
            <Clock size={10} aria-hidden="true" />
            Esperando aprobación
          </Badge>
        );
      case "done":
        return (
          <Badge
            variant="secondary"
            className="gap-1 bg-emerald-50 text-emerald-700"
            aria-label="Análisis completado"
          >
            <CheckCircle2 size={10} aria-hidden="true" />
            Completado
          </Badge>
        );
      case "failed":
      case "error":
        return (
          <Badge
            variant="secondary"
            className="gap-1 bg-red-50 text-red-700"
            aria-label="Análisis fallido"
          >
            <XCircle size={10} aria-hidden="true" />
            Fallido
          </Badge>
        );
      case "cancelled":
        return (
          <Badge
            variant="secondary"
            className="gap-1 bg-gray-100 text-gray-600"
            aria-label="Análisis rechazado"
          >
            <XCircle size={10} aria-hidden="true" />
            Rechazado
          </Badge>
        );
    }
  }

  // No live state: use outcome chip
  switch (outcome) {
    case "started":
    case "recovered":
      return (
        <Badge
          variant="secondary"
          className="gap-1 bg-blue-50 text-blue-700"
          aria-label="Análisis en curso"
        >
          <Loader2 size={10} className="animate-spin" aria-hidden="true" />
          En curso
        </Badge>
      );
    case "backpressure":
      return (
        <Badge
          variant="secondary"
          className="gap-1 bg-orange-50 text-orange-700"
          aria-label="Límite alcanzado"
        >
          <AlertCircle size={10} aria-hidden="true" />
          Límite alcanzado
        </Badge>
      );
    case "already_running":
      return (
        <Badge
          variant="secondary"
          className="gap-1 bg-sky-50 text-sky-700"
          aria-label="Ya en curso"
        >
          <Clock size={10} aria-hidden="true" />
          Ya en curso
        </Badge>
      );
    case "error":
    case "no_results":
    case "budget_exceeded":
      return (
        <Badge
          variant="secondary"
          className="gap-1 bg-red-50 text-red-700"
          aria-label="Análisis fallido"
        >
          <XCircle size={10} aria-hidden="true" />
          Fallido
        </Badge>
      );
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface GroupRunRowProps {
  entry: TrackedRunEntry;
  /** Callback al padre cuando el run llega a estado terminal. */
  onTerminated?: (runId: string, state: RunState) => void;
}

export function GroupRunRow({ entry, onTerminated }: GroupRunRowProps) {
  const { run_id, name, outcome, detail } = entry;

  // Poll live status only when we have a run_id.
  const statusQuery = useRunStatus(run_id ?? null);
  const runState = statusQuery.data?.latest?.state;

  // Extract HITL step from events (mirrors pattern in AthleteAIAnalysisTab).
  const lastHitlEvent = statusQuery.data?.events
    ?.slice()
    .reverse()
    .find(
      (e) =>
        e.type === "hitl_request" ||
        e.type === "hitl_required" ||
        e.node === "hitl_gate_review",
    );
  const hitlStepId =
    typeof lastHitlEvent?.payload?.step_id === "string"
      ? (lastHitlEvent.payload.step_id as string)
      : "hitl_default";
  const draftMarkdown =
    typeof lastHitlEvent?.payload?.draft_markdown === "string"
      ? (lastHitlEvent.payload.draft_markdown as string)
      : "_(El agente generó un borrador, pero no incluyó el markdown en el evento. Aprueba o rechaza.)_";

  const showHITL =
    run_id !== null &&
    (runState === "hitl_waiting" || !!lastHitlEvent);

  // Notify parent on terminal state.
  useEffect(() => {
    if (!run_id) return;
    if (isTerminalState(runState)) {
      onTerminated?.(run_id, runState!);
    }
  }, [run_id, runState, onTerminated]);

  return (
    <li
      className="flex flex-col gap-2"
      data-testid={`group-run-row-${entry.athlete_id}`}
    >
      <div
        className={cn(
          "flex items-center justify-between gap-3 rounded-lg bg-white px-4 py-3",
          "ring-1 ring-black/5",
        )}
      >
        {/* Nombre del atleta */}
        <span
          className="truncate text-sm font-medium text-charcoal"
          data-testid={`group-run-name-${entry.athlete_id}`}
        >
          {name}
        </span>

        {/* Chip de estado */}
        <StateChip runState={runState} outcome={outcome} />
      </div>

      {/* Mensaje de detalle para outcomes no-started */}
      {detail && !run_id && (
        <p
          className="px-4 text-xs text-mid-gray"
          data-testid={`group-run-detail-${entry.athlete_id}`}
        >
          {detail}
        </p>
      )}

      {/* HITL approval card — reusa el componente compartido exacto */}
      {showHITL && run_id && (
        <HITLApprovalCard
          runId={run_id}
          stepId={hitlStepId}
          draftMarkdown={draftMarkdown}
        />
      )}
    </li>
  );
}
