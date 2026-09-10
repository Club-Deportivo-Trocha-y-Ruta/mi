/**
 * ArchiveAthleteDialog — diálogo de confirmación para archivar un atleta
 * (feature 041 — gobernanza multi-coach). contracts/athlete-archive.md §10.
 *
 * `ConfirmDialog` (`components/shared/ConfirmDialog.tsx`) no tiene slot para
 * un control que condicione el botón Confirmar, así que este diálogo usa las
 * mismas primitivas `AlertDialog` directamente, conservando su mismo
 * comportamiento: `tone="danger"` enfoca Cancelar al abrir y el error se
 * muestra inline sin cerrar el diálogo.
 *
 * El motivo viene del catálogo cerrado `GET /api/audit/reason-codes` vía
 * `useAuditReasonCodes("athlete_archive")` — nunca un arreglo hardcodeado en
 * el cliente (contracts/athlete-archive.md §3).
 */
import * as React from "react";
import { Loader2 } from "lucide-react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuditReasonCodes } from "@/hooks/useAuditReasonCodes";
import { cn } from "@/lib/utils";

export interface ArchiveAthleteDialogProps {
  open: boolean;
  athleteFullName: string;
  isPending?: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: (reasonCode: string) => void;
}

export function ArchiveAthleteDialog({
  open,
  athleteFullName,
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: ArchiveAthleteDialogProps) {
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const [reasonCode, setReasonCode] = React.useState("");
  const [validationError, setValidationError] = React.useState(false);
  const reasonCodesQuery = useAuditReasonCodes("athlete_archive", open);

  React.useEffect(() => {
    if (!open) {
      setReasonCode("");
      setValidationError(false);
    }
  }, [open]);

  const reasonOptions = reasonCodesQuery.data?.items ?? [];

  function handleConfirm() {
    if (!reasonCode) {
      setValidationError(true);
      return;
    }
    setValidationError(false);
    onConfirm(reasonCode);
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !isPending) onCancel();
      }}
    >
      <AlertDialogContent
        data-testid="archive-athlete-dialog"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          cancelRef.current?.focus();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>Archivar atleta</AlertDialogTitle>
          <AlertDialogDescription>
            <span className="font-medium text-charcoal">{athleteFullName}</span>
            <br />
            El deportista dejará de aparecer en listas, informes, boletines y en la
            vista de su familia. Se conservan sus mediciones, asistencias,
            consentimientos e historial. Un administrador puede restaurarlo.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1">
          <label
            htmlFor="archive-reason-select"
            className="text-xs font-medium text-mid-gray"
          >
            Motivo del archivado
          </label>
          <Select
            value={reasonCode}
            onValueChange={(value) => {
              setReasonCode(value);
              setValidationError(false);
            }}
          >
            <SelectTrigger id="archive-reason-select" data-testid="archive-reason-select">
              <SelectValue placeholder="Selecciona un motivo" />
            </SelectTrigger>
            <SelectContent>
              {reasonOptions.map((option) => (
                <SelectItem key={option.code} value={option.code}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {validationError && (
            <p role="alert" className="text-sm text-danger">
              Selecciona un motivo para archivar.
            </p>
          )}
        </div>

        {errorMessage && (
          <p role="alert" className="text-sm text-danger">
            {errorMessage}
          </p>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel ref={cancelRef} disabled={isPending} className="min-h-12">
            Cancelar
          </AlertDialogCancel>
          <AlertDialogAction
            data-testid="archive-confirm-button"
            onClick={(event) => {
              event.preventDefault();
              handleConfirm();
            }}
            disabled={isPending}
            className={cn("min-h-12", "bg-danger hover:bg-danger/90")}
          >
            {isPending && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Sí, archivar atleta
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
