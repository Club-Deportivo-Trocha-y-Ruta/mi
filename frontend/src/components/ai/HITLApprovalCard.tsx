/**
 * Card de aprobación HITL (race-analysis §10.2 #HITLApprovalCard).
 *
 * Aparece cuando el run está en `hitl_waiting` o llega un evento
 * `hitl_required`. Renderiza:
 *  - Draft markdown del analyst.
 *  - Feedback del critic (si presente).
 *  - 3 acciones: Aprobar / Editar / Rechazar.
 *
 * Editar abre un dialog con textarea + preview side-by-side.
 *
 * El componente NO hace polling — recibe `runId` y `stepId` desde el
 * padre (que sí los polleó vía useRunStatus). El submit dispara
 * `useApproveStep`.
 */
import { useState } from "react";
import { AlertCircle, Check, Loader2, Pencil, X } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogBody,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { MarkdownReportViewer } from "@/components/ai/MarkdownReportViewer";
import { useApproveStep } from "@/hooks/ai/useRaceRun";
import { cn } from "@/lib/utils";
import type { HITLDecisionRequest } from "@/types/raceAnalysis.types";

export interface CriticIssueLike {
  section?: string;
  problem: string;
  suggested_fix?: string;
}

interface HITLApprovalCardProps {
  runId: string;
  stepId: string;
  /** Markdown del draft del analyst (read-only inicial). */
  draftMarkdown: string;
  /** Feedback del critic agent (opcional). */
  criticFeedback?: CriticIssueLike[];
  /** Citas del marco teórico usadas. */
  principlesCited?: string[];
  /** Callback opcional tras decision submitted. */
  onSubmitted?: (decision: HITLDecisionRequest["decision"]) => void;
  className?: string;
}

export function HITLApprovalCard({
  runId,
  stepId,
  draftMarkdown,
  criticFeedback = [],
  principlesCited = [],
  onSubmitted,
  className,
}: HITLApprovalCardProps) {
  const mutation = useApproveStep(runId);
  const [editOpen, setEditOpen] = useState(false);
  const [editedMarkdown, setEditedMarkdown] = useState(draftMarkdown);
  const [rejectionNotes, setRejectionNotes] = useState("");

  // Devuelve si el submit tuvo éxito. Antes esta función no devolvía nada y
  // `handleSaveEdit` decidía si cerrar el diálogo leyendo `mutation.isError`
  // DESPUÉS del await — pero `mutation` es la referencia capturada en el
  // render anterior al click (closure), nunca la actualizada por el propio
  // `mutateAsync` que se acaba de resolver/rechazar dentro de esta misma
  // invocación. Esa lectura era SIEMPRE `false` (el valor de antes del
  // click), así que el diálogo de edición se cerraba incluso cuando el
  // guardado fallaba, escondiendo el error de contexto. Devolver el
  // resultado real de este intento puntual evita depender del estado
  // (potencialmente stale) del hook.
  const submit = async (body: HITLDecisionRequest): Promise<boolean> => {
    try {
      await mutation.mutateAsync({ stepId, decision: body });
      onSubmitted?.(body.decision);
      return true;
    } catch {
      // El error se renderiza desde `mutation.isError` — silenciamos
      // aquí para que no se propague como unhandled rejection en tests.
      return false;
    }
  };

  const handleApprove = () => {
    void submit({ decision: "approve" });
  };

  const handleReject = () => {
    void submit({
      decision: "reject",
      notes: rejectionNotes.trim() || null,
    });
  };

  const handleSaveEdit = async () => {
    const ok = await submit({
      decision: "edit",
      edits: editedMarkdown,
    });
    if (ok) setEditOpen(false);
  };

  const submitting = mutation.isPending;
  const errorMsg = mutation.isError
    ? mutation.error instanceof Error
      ? mutation.error.message
      : "Error enviando la decisión."
    : null;

  return (
    <section
      className={cn(
        "rounded-xl border-2 border-amber-200 bg-amber-50 p-5 space-y-4",
        className,
      )}
      role="region"
      aria-label="Revisión humana requerida"
      data-testid="hitl-approval-card"
    >
      <div className="flex items-start gap-2">
        <AlertCircle
          size={20}
          className="text-amber-700 mt-0.5"
          aria-hidden="true"
        />
        <div>
          <h3 className="text-base font-semibold text-amber-900">
            Revisión humana requerida
          </h3>
          <p className="mt-0.5 text-xs text-amber-800">
            El agente generó un borrador. Revísalo antes de continuar.
          </p>
        </div>
      </div>

      <div className="rounded-lg bg-white p-1">
        <MarkdownReportViewer
          markdown={draftMarkdown}
          citations={principlesCited}
          className="ring-0"
        />
      </div>

      {criticFeedback.length > 0 && (
        <details
          className="rounded-lg bg-white p-3 ring-1 ring-amber-200"
          data-testid="hitl-critic-feedback"
        >
          <summary className="cursor-pointer text-sm font-medium text-charcoal">
            Crítico LLM dice ({criticFeedback.length})
          </summary>
          <ul className="mt-2 space-y-2 text-sm text-charcoal">
            {criticFeedback.map((issue, i) => (
              <li key={i} className="border-l-2 border-amber-300 pl-3">
                {issue.section && (
                  <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                    {issue.section}
                  </p>
                )}
                <p className="text-sm">{issue.problem}</p>
                {issue.suggested_fix && (
                  <p className="mt-1 text-xs text-mid-gray">
                    <em>Sugerencia:</em> {issue.suggested_fix}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {errorMsg && (
        <p className="text-sm text-red-700" role="alert">
          {errorMsg}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleApprove}
          disabled={submitting}
          data-testid="hitl-approve-button"
          className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? (
            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          ) : (
            <Check size={16} aria-hidden="true" />
          )}
          Aprobar
        </button>
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          disabled={submitting}
          data-testid="hitl-edit-button"
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <Pencil size={16} aria-hidden="true" />
          Editar
        </button>
        <button
          type="button"
          onClick={handleReject}
          disabled={submitting}
          data-testid="hitl-reject-button"
          className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <X size={16} aria-hidden="true" />
          Rechazar
        </button>

        <input
          type="text"
          placeholder="Motivo de rechazo (opcional)"
          value={rejectionNotes}
          onChange={(e) => setRejectionNotes(e.target.value)}
          maxLength={500}
          className={cn(
            "flex-1 min-w-[180px] rounded-lg bg-white px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-blue-500/40",
            "shadow-ring",
          )}
          aria-label="Motivo de rechazo (opcional)"
          data-testid="hitl-reject-notes-input"
        />
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Editar el borrador</DialogTitle>
            <DialogDescription>
              Tus cambios reemplazarán el markdown generado por el agente.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label
                  htmlFor="hitl-edit-textarea"
                  className="mb-2 block text-xs font-medium uppercase tracking-wide text-mid-gray"
                >
                  Edición
                </label>
                <textarea
                  id="hitl-edit-textarea"
                  value={editedMarkdown}
                  onChange={(e) => setEditedMarkdown(e.target.value)}
                  rows={18}
                  data-testid="hitl-edit-textarea"
                  className={cn(
                    "w-full rounded-lg bg-white px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-blue-500/40",
                    "shadow-ring",
                  )}
                  aria-label="Markdown editado"
                />
              </div>
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Vista previa
                </p>
                <div className="max-h-[420px] overflow-auto rounded-lg bg-light-gray/20 p-3">
                  <MarkdownReportViewer
                    markdown={editedMarkdown || "_(vacío)_"}
                    className="bg-white"
                  />
                </div>
              </div>
            </div>
            {errorMsg && (
              // El banner de error de la sección principal (más abajo en
              // este archivo) queda `aria-hidden` mientras el diálogo está
              // abierto (comportamiento estándar de Radix Dialog al ocultar
              // el fondo) y detrás del overlay visualmente — si "Guardar y
              // aprobar" falla, el coach nunca lo vería sin este duplicado
              // DENTRO del diálogo.
              <p
                className="mt-3 text-sm text-red-700"
                role="alert"
                data-testid="hitl-edit-dialog-error"
              >
                {errorMsg}
              </p>
            )}
          </DialogBody>
          <DialogFooter>
            <button
              type="button"
              onClick={() => setEditOpen(false)}
              className="rounded-lg border border-light-gray px-4 py-2 text-sm font-medium text-charcoal hover:bg-light-gray/40"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleSaveEdit}
              disabled={submitting || editedMarkdown.trim().length === 0}
              data-testid="hitl-edit-save-button"
              className="inline-flex items-center gap-1.5 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {submitting && (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              )}
              Guardar y aprobar
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
