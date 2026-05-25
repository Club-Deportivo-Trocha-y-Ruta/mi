import { Loader2 } from "lucide-react";

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ConfirmModalProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDanger?: boolean;
  isPending?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmModal({
  open,
  title,
  body,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  confirmDanger = false,
  isPending = false,
  onCancel,
  onConfirm,
}: ConfirmModalProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !isPending) onCancel();
      }}
    >
      <DialogContent role="alertdialog" hideClose>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <DialogBody>
          <DialogDescription>{body}</DialogDescription>
        </DialogBody>

        <DialogFooter>
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            autoFocus
            className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50 ${
              confirmDanger ? "bg-red-600" : "bg-charcoal"
            }`}
          >
            {isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
