/**
 * StaleAnalysisBadge — badge "Análisis desactualizado" + acción re-ejecutar (PR5).
 *
 * Se muestra junto a un run/insight cuyo `stale_since` no es null (el análisis
 * se basó en resultados que luego fueron corregidos por una re-ingesta).
 *
 * D5 honrado: la re-ejecución es MANUAL y requiere confirmación explícita del
 * coach (ConfirmDialog). No hay cron ni auto-trigger.
 */
import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { useReExecuteRun } from "@/hooks/ai/useRaceRun";

/**
 * staleAnalysisStatus — adaptador puro para el único estado de este badge
 * ("stale" → warning), per contracts/status-vocabulary-sweep.md §7.
 */
export function staleAnalysisStatus(): { status: Status; label: string } {
  return { status: "warning", label: "Análisis desactualizado" };
}

export interface StaleAnalysisBadgeProps {
  /** external_run_id del run desactualizado. */
  runId: string;
  /** Callback opcional tras lanzar la re-ejecución (ej. navegar al nuevo run). */
  onReExecuted?: (newRunId: string) => void;
}

export function StaleAnalysisBadge({ runId, onReExecuted }: StaleAnalysisBadgeProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const reExecute = useReExecuteRun();

  function handleConfirm() {
    reExecute.mutate(runId, {
      onSuccess: (res) => {
        setConfirmOpen(false);
        onReExecuted?.(res.run_id);
      },
    });
  }

  const badge = staleAnalysisStatus();

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="stale-analysis-badge"
    >
      <StatusBadge status={badge.status} label={badge.label} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setConfirmOpen(true)}
        data-testid="stale-reexecute-button"
      >
        <RefreshCw size={14} aria-hidden="true" />
        Re-ejecutar
      </Button>

      <ConfirmDialog
        open={confirmOpen}
        title="Re-ejecutar análisis"
        description={
          "Se generará un nuevo análisis IA con los resultados corregidos. " +
          "El análisis anterior se conservará en el histórico. ¿Continuar?"
        }
        confirmLabel="Re-ejecutar"
        tone="default"
        isPending={reExecute.isPending}
        onCancel={() => {
          if (!reExecute.isPending) setConfirmOpen(false);
        }}
        onConfirm={handleConfirm}
      />
    </div>
  );
}
