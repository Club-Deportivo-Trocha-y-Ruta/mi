/**
 * StaleAnalysisBadge — badge "Análisis desactualizado" + acción re-ejecutar (PR5).
 *
 * Se muestra junto a un run/insight cuyo `stale_since` no es null (el análisis
 * se basó en resultados que luego fueron corregidos por una re-ingesta).
 *
 * D5 honrado: la re-ejecución es MANUAL y requiere confirmación explícita del
 * coach (ConfirmModal). No hay cron ni auto-trigger.
 */
import { useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { useReExecuteRun } from "@/hooks/ai/useRaceRun";

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

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="stale-analysis-badge"
    >
      <Badge
        variant="secondary"
        className="gap-1 bg-amber-100 text-amber-800"
      >
        <AlertTriangle size={12} aria-hidden="true" />
        Análisis desactualizado
      </Badge>
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

      <ConfirmModal
        open={confirmOpen}
        title="Re-ejecutar análisis"
        body={
          "Se generará un nuevo análisis IA con los resultados corregidos. " +
          "El análisis anterior se conservará en el histórico. ¿Continuar?"
        }
        confirmLabel="Re-ejecutar"
        isPending={reExecute.isPending}
        onCancel={() => {
          if (!reExecute.isPending) setConfirmOpen(false);
        }}
        onConfirm={handleConfirm}
      />
    </div>
  );
}
