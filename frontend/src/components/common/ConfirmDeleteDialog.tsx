import { AlertTriangle, Loader2, X } from "lucide-react";

const overlayStyle: React.CSSProperties = {
  background: "rgba(19, 19, 22, 0.65)",
  backdropFilter: "blur(2px)",
};

const dialogStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

const btnPrimaryStyle: React.CSSProperties = {
  boxShadow:
    "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(0, 0, 0, 0.16) 0px 1px 1.9px 0px inset, rgba(255, 255, 255, 0.15) 0px 2px 0px inset",
};

const btnSecondaryStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

interface ConfirmDeleteDialogProps {
  open: boolean;
  title: string;
  subject: string;
  description: string;
  confirmLabel?: string;
  isPending?: boolean;
  errorMessage?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDeleteDialog({
  open,
  title,
  subject,
  description,
  confirmLabel = "Eliminar",
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: ConfirmDeleteDialogProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={overlayStyle}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-delete-title"
      aria-describedby="confirm-delete-desc"
    >
      <div className="w-full max-w-md rounded-2xl bg-white" style={dialogStyle}>
        <div className="flex items-start justify-between border-b border-[rgba(34,42,53,0.08)] px-6 pb-4 pt-6">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-50">
              <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
            </div>
            <div>
              <h2
                id="confirm-delete-title"
                className="font-display text-base text-charcoal"
              >
                {title}
              </h2>
              <p className="mt-0.5 text-sm text-mid-gray">{subject}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg p-1.5 text-mid-gray transition-colors hover:bg-light-gray disabled:opacity-50"
            aria-label="Cancelar"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3"
            role="note"
          >
            <p
              id="confirm-delete-desc"
              className="text-sm text-red-700"
            >
              {description}
            </p>
          </div>

          {errorMessage && (
            <p className="text-sm text-red-600" role="alert" aria-live="assertive">
              {errorMessage}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 pb-6">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50"
            style={btnSecondaryStyle}
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            style={btnPrimaryStyle}
          >
            {isPending && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {isPending ? "Eliminando…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
