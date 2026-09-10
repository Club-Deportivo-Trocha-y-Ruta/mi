/**
 * RestoreAthleteDialog — diálogo de confirmación para restaurar un atleta
 * archivado (feature 041 — gobernanza multi-coach).
 * contracts/athlete-archive.md §11. Misma estructura que
 * `ArchiveAthleteDialog`, motivo del catálogo `athlete_restore`.
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

export interface RestoreAthleteDialogProps {
  open: boolean;
  athleteFullName: string;
  isPending?: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: (reasonCode: string) => void;
}

export function RestoreAthleteDialog({
  open,
  athleteFullName,
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: RestoreAthleteDialogProps) {
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const [reasonCode, setReasonCode] = React.useState("");
  const [validationError, setValidationError] = React.useState(false);
  const reasonCodesQuery = useAuditReasonCodes("athlete_restore", open);

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
        data-testid="restore-athlete-dialog"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          cancelRef.current?.focus();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>Restaurar atleta</AlertDialogTitle>
          <AlertDialogDescription>
            <span className="font-medium text-charcoal">{athleteFullName}</span>
            <br />
            El deportista volverá a aparecer en listas, informes, boletines y en la
            vista de su familia.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1">
          <label
            htmlFor="restore-reason-select"
            className="text-xs font-medium text-mid-gray"
          >
            Motivo de la restauración
          </label>
          <Select
            value={reasonCode}
            onValueChange={(value) => {
              setReasonCode(value);
              setValidationError(false);
            }}
          >
            <SelectTrigger id="restore-reason-select" data-testid="restore-reason-select">
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
              Selecciona un motivo para restaurar.
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
            data-testid="restore-confirm-button"
            onClick={(event) => {
              event.preventDefault();
              handleConfirm();
            }}
            disabled={isPending}
            className="min-h-12"
          >
            {isPending && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Sí, restaurar atleta
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
