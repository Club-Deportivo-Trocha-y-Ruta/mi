/**
 * DiscardImportDialog — confirmación para descartar una carga en curso
 * (feature 045, US3). Lo usan el wizard (paso 2) y el tablero de cargas.
 *
 * `POST /imports/{id}/discard`: `pending|dry_run` → `discarded`. El archivo no
 * se borra del servidor; la carga solo deja de figurar «en curso». Una carga
 * ya confirmada responde `409 import_not_discardable`.
 */
import { toast } from "sonner";

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
import { useDiscardRaceImport } from "@/hooks/ai/useRaceImports";

function discardErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const data = (err as { response?: { data?: { detail?: unknown } } }).response
      ?.data;
    const detail = data?.detail;
    if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof (detail as { message?: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message;
    }
  }
  return "No se pudo descartar la carga. Intenta de nuevo.";
}

export interface DiscardImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  importId: string | number;
  /** Nombre del archivo, solo para dar contexto en el texto (no es un dato de un menor). */
  filename?: string | null;
  /** Se llama tras descartar con éxito (el diálogo ya se cerró). */
  onDiscarded?: () => void;
}

export function DiscardImportDialog({
  open,
  onOpenChange,
  importId,
  filename,
  onDiscarded,
}: DiscardImportDialogProps) {
  const discard = useDiscardRaceImport();

  function handleConfirm() {
    discard.mutate(
      { importId },
      {
        onSuccess: () => {
          toast.success("Carga descartada.");
          onOpenChange(false);
          onDiscarded?.();
        },
        onError: (err) => {
          toast.error(discardErrorMessage(err));
        },
      },
    );
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="discard-import-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>¿Descartar esta carga?</AlertDialogTitle>
          <AlertDialogDescription>
            {filename ? `La carga de «${filename}» ` : "Esta carga "}
            dejará de aparecer entre las cargas en curso. El archivo no se
            borra: si lo necesitas, puedes subirlo de nuevo.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="min-h-12" disabled={discard.isPending}>
            Cancelar
          </AlertDialogCancel>
          <AlertDialogAction
            className="min-h-12"
            disabled={discard.isPending}
            onClick={(event) => {
              // Evita el cierre automático: se cierra al confirmar el servidor.
              event.preventDefault();
              handleConfirm();
            }}
            data-testid="confirm-discard-import"
          >
            {discard.isPending ? "Descartando..." : "Descartar carga"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
