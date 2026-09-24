/**
 * GroupRunRow — fila de estado por deportista en el panel de análisis grupal.
 *
 * Cada fila:
 *  - Muestra nombre del atleta + chip de estado (es-CO).
 *  - Si hay un run_id activo, pollea su estado vía useRunStatus.
 *  - Solo mientras el run espera aprobación (hitl_request vigente), muestra HITLApprovalCard.
 *  - Notifica al padre cuando el run alcanza estado terminal (done/failed).
 *
 * Privacidad: sólo muestra athlete_display_name (pseudónimo del backend),
 * nunca el athlete_id real ni datos identificadores adicionales.
 */
import { useEffect, useMemo, useRef } from "react";

import { AnalysisRunTimeline } from "@/components/ai/AnalysisRunTimeline";
import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { useRunStatus, isTerminalState } from "@/hooks/ai/useRaceRun";
import { familyGapMentionsFromEvent, findPendingHitlEvent } from "@/lib/hitlEvents";
import { cn } from "@/lib/utils";
import type { InsightV3 } from "@/types/insightV3.types";
import type { GroupRunOutcome, RunState } from "@/types/raceAnalysis.types";
import type { TrackedRunEntry } from "@/hooks/ai/useGroupAnalysis";

// ---------------------------------------------------------------------------
// Status adapter
// ---------------------------------------------------------------------------

/**
 * groupRunStatus — adaptador puro estado de run grupal → { status, label }
 * para `StatusBadge`, per contracts/status-vocabulary-sweep.md §8. Cubre
 * todos los estados terminales; los estados "en curso" (`running`, outcome
 * `started`/`recovered`) no son un badge — devuelven `null` porque se
 * enrutan al `AnalysisRunTimeline` compacto (ai-identity.md), no aquí.
 *
 * Prioridad: estado de polling en vivo (`runState`) > outcome del launch.
 */
export function groupRunStatus(
  runState: RunState | undefined,
  outcome: GroupRunOutcome | "recovered",
): { status: Status; label: string } | null {
  // Priority: live run state > launch outcome
  if (runState) {
    switch (runState) {
      case "running":
        return null;
      case "hitl_waiting":
        return { status: "warning", label: "Esperando aprobación" };
      case "done":
        return { status: "success", label: "Completado" };
      case "failed":
      case "error":
        return { status: "danger", label: "Fallido" };
      case "cancelled":
        return { status: "neutral", label: "Rechazado" };
    }
  }

  // No live state: use outcome
  switch (outcome) {
    case "started":
    case "recovered":
      return null;
    case "backpressure":
      return { status: "warning", label: "Límite alcanzado" };
    case "already_running":
      return { status: "neutral", label: "Ya en curso" };
    case "error":
    case "no_results":
    case "budget_exceeded":
      return { status: "danger", label: "Fallido" };
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

  const pendingHitlEvent = useMemo(
    () => findPendingHitlEvent(statusQuery.data?.events),
    [statusQuery.data],
  );

  // Mismo autorreparado que AthleteAIAnalysisTab: pausado en HITL pero sin el
  // hitl_request (único evento con el borrador) en el buffer → refetch completo
  // una sola vez por run.
  const healedRunRef = useRef<string | null>(null);
  useEffect(() => {
    if (runState !== "hitl_waiting" || !run_id || pendingHitlEvent) return;
    if (healedRunRef.current === run_id) return;
    healedRunRef.current = run_id;
    statusQuery.resetEvents();
    void statusQuery.refetch();
  }, [runState, run_id, pendingHitlEvent, statusQuery]);

  const hitlStepId =
    typeof pendingHitlEvent?.payload?.step_id === "string"
      ? (pendingHitlEvent.payload.step_id as string)
      : "hitl_default";
  const draftMarkdown =
    typeof pendingHitlEvent?.payload?.draft_markdown === "string"
      ? (pendingHitlEvent.payload.draft_markdown as string)
      : "_(El agente generó un borrador, pero no incluyó el markdown en el evento. Aprueba o rechaza.)_";
  const structuredDraft =
    pendingHitlEvent?.payload?.structured_draft &&
    typeof pendingHitlEvent.payload.structured_draft === "object"
      ? (pendingHitlEvent.payload.structured_draft as InsightV3)
      : null;

  // Un run terminado nunca muestra la tarjeta: aprobarlo devolvería 409.
  const showHITL =
    run_id !== null &&
    !isTerminalState(runState) &&
    (runState === "hitl_waiting" || !!pendingHitlEvent);

  const badge = groupRunStatus(runState, outcome);

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
          "flex items-center justify-between gap-3 rounded-lg bg-surface-raised px-4 py-3",
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

        {/* Chip de estado — solo para estados terminales; "en curso" se
            muestra abajo con el timeline compacto (mismo run-view que
            AthleteAIAnalysisTab, densidad reducida). */}
        {badge && <StatusBadge status={badge.status} label={badge.label} />}
      </div>

      {/* Timeline compacto — reemplaza el chip "En curso" hand-rolled para
          runState="running" u outcome started/recovered (T050). Un solo
          componente de run-view (AnalysisRunTimeline), dos densidades. */}
      {!badge && run_id && (
        <AnalysisRunTimeline runId={run_id} variant="compact" />
      )}

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
          structuredDraft={structuredDraft}
          familyGapMentions={familyGapMentionsFromEvent(pendingHitlEvent)}
        />
      )}
    </li>
  );
}
