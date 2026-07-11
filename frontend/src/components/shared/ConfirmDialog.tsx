/**
 * ConfirmDialog — diálogo de confirmación genérico sobre AlertDialog (Radix).
 * Reemplaza ConfirmModal/ConfirmDeleteDialog, que fijaban `autoFocus` en el
 * botón Confirmar incluso en flujos destructivos. Con tone="danger" el foco
 * inicial va a Cancelar, para que un Enter accidental nunca dispare la acción.
 */
import * as React from "react";
import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: ReactNode;
  /** @default "Confirmar" */
  confirmLabel?: string;
  /** @default "Cancelar" */
  cancelLabel?: string;
  /** "danger" enfoca Cancelar al abrir (evita confirmar por error con Enter). */
  tone?: "default" | "danger";
  /** Muestra spinner en Confirmar y deshabilita ambos botones. */
  isPending?: boolean;
  /** Falla inline, sin cerrar el diálogo. */
  errorMessage?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  tone = "default",
  isPending = false,
  errorMessage,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        // Cubre Escape y click-fuera (este último ya bloqueado por AlertDialog
        // por diseño). isPending impide cerrar mientras la acción está en vuelo.
        if (!next && !isPending) onCancel();
      }}
    >
      <AlertDialogContent
        onOpenAutoFocus={(event) => {
          if (tone === "danger") {
            event.preventDefault();
            cancelRef.current?.focus();
          }
          // tone="default": no se llama preventDefault y el autofocus por
          // defecto de Radix (ya enfoca Cancelar) queda vigente.
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {/* Radix espera un elemento describedby; sin description lo dejamos
              presente pero visualmente oculto, para no dejar aria-describedby
              apuntando a nada y evitar el warning de desarrollo de Radix. */}
          <AlertDialogDescription className={cn(!description && "sr-only")}>
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>

        {errorMessage && (
          <p role="alert" className="text-sm text-danger">
            {errorMessage}
          </p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel
            ref={cancelRef}
            disabled={isPending}
            className="min-h-12"
          >
            {cancelLabel}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              // AlertDialogAction es un Close de Radix y cerraría el diálogo
              // por defecto; lo prevenimos porque quien controla `open` es el
              // padre (decide según isPending/errorMessage tras onConfirm).
              event.preventDefault();
              onConfirm();
            }}
            disabled={isPending}
            className={cn(
              "min-h-12",
              tone === "danger" && "bg-danger hover:bg-danger/90",
            )}
          >
            {isPending && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
