/**
 * RegenerateDialog — instrucción opcional (≤ 200 caracteres) para
 * `POST .../regenerate-block` (feature 038, T302, contracts/api.md).
 *
 * El límite de 200 caracteres es del estudio (UX: "más corto y menciona la
 * lluvia" cabe de sobra); el backend acepta hasta 300
 * (`RegenerateBlockRequest.instruction`, `max_length=300`) — el estudio es
 * deliberadamente más estricto, nunca al revés.
 */
import { useState } from "react";

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

const MAX_INSTRUCTION_LENGTH = 200;

export interface RegenerateDialogProps {
  open: boolean;
  blockTitle: string;
  isPending?: boolean;
  onConfirm: (instruction: string | undefined) => void;
  onCancel: () => void;
}

export function RegenerateDialog({
  open,
  blockTitle,
  isPending = false,
  onConfirm,
  onCancel,
}: RegenerateDialogProps) {
  const [instruction, setInstruction] = useState("");

  function handleClose() {
    setInstruction("");
    onCancel();
  }

  function handleConfirm() {
    const trimmed = instruction.trim();
    onConfirm(trimmed.length > 0 ? trimmed : undefined);
    setInstruction("");
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Regenerar «{blockTitle}»</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-2">
          <p className="text-sm text-charcoal">
            La IA generará una nueva versión de este bloque. Puedes agregar una
            indicación opcional (por ejemplo, "más corto" o "menciona la
            lluvia").
          </p>
          <Textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value.slice(0, MAX_INSTRUCTION_LENGTH))}
            placeholder="Indicación opcional (máximo 200 caracteres)"
            aria-label="Indicación para la regeneración"
            rows={3}
            maxLength={MAX_INSTRUCTION_LENGTH}
            disabled={isPending}
          />
          <p className="text-right text-xs text-mid-gray">
            {instruction.length}/{MAX_INSTRUCTION_LENGTH}
          </p>
        </DialogBody>
        <DialogFooter>
          <button
            type="button"
            onClick={handleClose}
            disabled={isPending}
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-charcoal shadow-ring transition-opacity disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={isPending}
            className="rounded-lg bg-charcoal px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            data-testid="regenerate-dialog-confirm"
          >
            {isPending ? "Regenerando…" : "Regenerar"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
