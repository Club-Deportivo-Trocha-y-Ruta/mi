/**
 * CancelEventDialog — diálogo de confirmación para cancelar un evento del
 * calendario (feature 041 — gobernanza multi-coach).
 * contracts/session-coaches.md §7.2.
 *
 * `ConfirmDialog` (`components/shared/ConfirmDialog.tsx`) no tiene slot para
 * un control que condicione el botón Confirmar, así que este diálogo usa las
 * mismas primitivas `AlertDialog` directamente, conservando su comportamiento:
 * `tone="danger"` enfoca "No, volver" al abrir y el error se muestra inline
 * sin cerrar el diálogo.
 *
 * El motivo viene del catálogo cerrado `GET /api/audit/reason-codes` vía
 * `useAuditReasonCodes("cancel")` — nunca un arreglo hardcodeado en el
 * cliente (contracts/session-coaches.md §7.4).
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

export interface CancelEventDialogProps {
  open: boolean;
  eventTitle?: string;
  isPending?: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: (reasonCode: string) => void;
}

export function CancelEventDialog({
  open,
  eventTitle,
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: CancelEventDialogProps) {
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const [reasonCode, setReasonCode] = React.useState("");
  const [validationError, setValidationError] = React.useState(false);
  const reasonCodesQuery = useAuditReasonCodes("cancel", open);

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
        data-testid="cancel-event-dialog"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          cancelRef.current?.focus();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>Cancelar evento</AlertDialogTitle>
          <AlertDialogDescription>
            {eventTitle && (
              <>
                <span className="font-medium text-charcoal">{eventTitle}</span>
                <br />
              </>
            )}
            El evento pasará al estado &apos;cancelado&apos;. Los participantes serán
            notificados.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-1">
          <label
            htmlFor="cancel-event-reason-select"
            className="text-xs font-medium text-mid-gray"
          >
            Motivo de la cancelación
          </label>
          <Select
            value={reasonCode}
            onValueChange={(value) => {
              setReasonCode(value);
              setValidationError(false);
            }}
          >
            <SelectTrigger
              id="cancel-event-reason-select"
              data-testid="cancel-event-reason-select"
              disabled={reasonCodesQuery.isLoading}
            >
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
              Selecciona un motivo de cancelación.
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
            No, volver
          </AlertDialogCancel>
          <AlertDialogAction
            data-testid="cancel-event-confirm-button"
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
            Cancelar evento
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
